"""The LangGraph intake graph and a small wrapper class to use it.

Spec section 4.7. LangGraph describes a workflow as a graph: nodes are steps
(see nodes.py) and edges say which step runs next. A *checkpointer* saves
the state after every step under a *thread ID*, which is what lets the graph
pause to ask the resident a question and later resume the same conversation.

Typical use::

    assistant = IntakeAssistant(mode="offline")
    turn = assistant.submit("There's a huge hole in the road on Tremont St")
    if turn.question:                       # the assistant wants one detail
        turn = assistant.answer(turn.thread_id, "It's in the street, not the sidewalk")
    print(turn.result.response_text)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from boston311 import config
from boston311.agent.nodes import IntakeState, Nodes
from boston311.catalog import CatalogEntry, load_catalog
from boston311.llm import StructuredModel, get_model
from boston311.retrieval import Retriever
from boston311.schemas import IntakeResult


@dataclass
class IntakeTurn:
    """What one call returns: a final result, or a question to answer first."""

    thread_id: str
    result: IntakeResult | None = None
    question: str | None = None


def build_graph(nodes: Nodes):
    """Wire the nodes into a compiled LangGraph with an in-memory checkpointer."""
    g = StateGraph(IntakeState)
    g.add_node("check_input", nodes.check_input)
    g.add_node("retrieve", nodes.retrieve)
    g.add_node("classify", nodes.classify)
    g.add_node("decide", nodes.decide)
    g.add_node("clarify", nodes.clarify)
    g.add_node("respond", nodes.respond)
    g.add_edge(START, "check_input")
    g.add_conditional_edges("check_input", nodes.after_check, {"retrieve": "retrieve", "respond": "respond"})
    g.add_edge("retrieve", "classify")
    g.add_edge("classify", "decide")
    g.add_conditional_edges("decide", nodes.after_decide, {"clarify": "clarify", "respond": "respond"})
    g.add_edge("clarify", "retrieve")  # after the answer, search and classify again
    g.add_edge("respond", END)
    return g.compile(checkpointer=InMemorySaver())


class IntakeAssistant:
    """The intake assistant: retrieve, classify once, validate, then route / clarify / triage.

    Args:
        mode: "live" (calls the model, records answers) or "offline" (replays
            recorded answers; no network or key needed).
        model: optionally pass a model object directly (used by tests).
        catalog, retriever: optionally pass prebuilt ones (used by evaluation).
        gate: retrieval gate threshold (default from config).
    """

    def __init__(
        self,
        mode: str = "offline",
        *,
        model: StructuredModel | None = None,
        catalog: dict[str, CatalogEntry] | None = None,
        retriever: Retriever | None = None,
        gate: float | None = None,
    ):
        self.catalog = catalog or load_catalog()
        self.retriever = retriever or Retriever(list(self.catalog.values()))
        self.model = model or get_model(mode)
        self.mode = getattr(self.model, "mode", mode)
        gate = config.RETRIEVAL_GATE_MIN_SCORE if gate is None else gate
        self.graph = build_graph(Nodes(self.catalog, self.retriever, self.model, gate))

    def _turn(self, thread_id: str, out: dict) -> IntakeTurn:
        """Convert a graph run's output into an IntakeTurn."""
        interrupts = out.get("__interrupt__")
        if interrupts:  # the graph paused in the clarify node
            return IntakeTurn(thread_id, question=interrupts[0].value["question"])
        return IntakeTurn(thread_id, result=IntakeResult.model_validate(out["result"]))

    def submit(self, message: str, thread_id: str | None = None) -> IntakeTurn:
        """Start a conversation with a resident's message."""
        thread_id = thread_id or str(uuid.uuid4())
        cfg = {"configurable": {"thread_id": thread_id}}
        return self._turn(thread_id, self.graph.invoke({"message": message or ""}, cfg))

    def answer(self, thread_id: str, text: str) -> IntakeTurn:
        """Resume a paused conversation with the resident's answer."""
        cfg = {"configurable": {"thread_id": thread_id}}
        return self._turn(thread_id, self.graph.invoke(Command(resume=text), cfg))

    def run(self, message: str, clarification_answer: str | None = None, thread_id: str | None = None) -> IntakeResult:
        """One-shot helper for evaluation.

        If the assistant asks a question and ``clarification_answer`` is
        given, it is used as the reply. If no answer is given, the result
        reports the CLARIFY decision itself.
        """
        turn = self.submit(message, thread_id)
        if turn.question is not None:
            if clarification_answer is None:
                from boston311.schemas import Decision

                return IntakeResult(
                    decision=Decision.CLARIFY,
                    message=message,
                    clarifying_question=turn.question,
                    questions_asked=1,  # a question was asked, though never answered
                    response_text=turn.question,
                )
            turn = self.answer(turn.thread_id, clarification_answer)
        if turn.question is not None:  # cannot happen: clarify runs at most once
            raise RuntimeError("assistant asked a second question")
        return turn.result
