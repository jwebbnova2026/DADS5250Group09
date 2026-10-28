"""The steps (nodes) of the intake graph.

Spec section 5.7. The flow for one message:

    check_input -> retrieve -> classify -> decide -> respond
                       ^                     |
                       +----- clarify <------+   (at most once)

* **check_input** rejects empty input before any model call (spec 6).
* **retrieve** finds candidate types with TF-IDF (RAG).
* **classify** asks the language model for a structured proposal.
* **decide** is plain code. It checks the proposal against the candidates and
  the catalog, then chooses ROUTE, CLARIFY, or TRIAGE. The model never
  chooses the department or queue; the code reads them from the catalog.
* **clarify** pauses the graph with a LangGraph ``interrupt`` and waits for
  the resident's answer. When the graph resumes, LangGraph re-runs this node
  from its first line, so this node contains *no* API calls: re-running it is
  harmless. The model is called again only in ``classify``, after it.
* **respond** builds the final :class:`~boston311.schemas.IntakeResult`.

Each node receives the current state (a dict) and returns only the keys it
changes; LangGraph merges them into the state.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.types import interrupt

from boston311 import config
from boston311.agent import tools
from boston311.catalog import CatalogEntry
from boston311.llm import ClassifierFailure, StructuredModel, classify
from boston311.retrieval import Retriever
from boston311.schemas import ClassificationProposal, Decision, IntakeResult


class IntakeState(TypedDict, total=False):
    """Everything the graph remembers about one conversation (one thread)."""

    message: str  # the resident's first message
    clarification: str | None  # the resident's answer to our one question
    clarifications_used: int  # 0 or 1
    candidates: list[dict]  # retrieved candidate types
    top_score: float  # best retrieval score
    proposal: dict | None  # the model's ClassificationProposal, as a dict
    failure: str | None  # why the model could not answer, if it could not
    decision: str | None  # ROUTE / CLARIFY / TRIAGE / REJECTED
    question: str | None  # the clarifying question, when decision is CLARIFY
    triage_reason: str | None
    result: dict | None  # the final IntakeResult, as a dict


class Nodes:
    """Holds the dependencies (catalog, retriever, model) the nodes need."""

    def __init__(self, catalog: dict[str, CatalogEntry], retriever: Retriever, model: StructuredModel, gate: float):
        self.catalog = catalog
        self.retriever = retriever
        self.model = model
        self.gate = gate

    # -- nodes ---------------------------------------------------------------

    def check_input(self, state: IntakeState) -> IntakeState:
        """Start a new message: reset per-message state, reject empty input.

        This node runs only when a *new* message is submitted (never when the
        graph resumes after a clarification). LangGraph keeps a thread's old
        state in the checkpointer, so if a thread ID is reused, values from the
        previous message (such as "clarification already used") would leak
        into this one. Resetting them here makes every message start clean.
        """
        fresh: IntakeState = {
            "clarification": None,
            "clarifications_used": 0,
            "candidates": [],
            "top_score": 0.0,
            "proposal": None,
            "failure": None,
            "decision": None,
            "question": None,
            "triage_reason": None,
            "result": None,
        }
        if not state.get("message", "").strip():
            # Reject before any retrieval or API call (spec 6).
            return {**fresh, "decision": Decision.REJECTED.value, "triage_reason": "empty input"}
        return fresh

    def retrieve(self, state: IntakeState) -> IntakeState:
        """Find candidate types for the message (plus any clarification answer)."""
        text = state["message"] + (" " + state["clarification"] if state.get("clarification") else "")
        candidates, top = tools.retrieve_candidates(self.retriever, self.catalog, text)
        return {"candidates": candidates, "top_score": top}

    def classify(self, state: IntakeState) -> IntakeState:
        """Ask the model for a proposal. A failure is recorded, not raised."""
        try:
            p = classify(self.model, state["message"], state.get("clarification"), state["candidates"])
            return {"proposal": p.model_dump(), "failure": None}
        except ClassifierFailure as exc:
            return {"proposal": None, "failure": exc.kind}

    def decide(self, state: IntakeState) -> IntakeState:
        """Code-owned decision: ROUTE, CLARIFY (once), or TRIAGE.

        Checks, in order:
        1. The model failed (timeout, malformed output, no offline recording)
           -> TRIAGE.
        2. The model says the request is out of scope -> TRIAGE.
        3. Something is unclear: the model flags ambiguity or several
           issues, proposes no type, or the retrieval gate fails -> CLARIFY
           if we have not asked yet, otherwise TRIAGE (second ambiguity).
           The gate is skipped when the model's pick is the top-ranked
           retrieval candidate (agreement rule).
        4. The proposed type is not one of the retrieved candidates or not
           in the catalog -> TRIAGE.
        5. The proposed type is one of an overlapping pair
           (``config.OVERLAPPING_TYPE_PAIRS``) and the other type of the pair
           was retrieved too -> TRIAGE, because the data cannot tell them apart.
        6. The type has no approved department mapping -> TRIAGE.
        7. Otherwise -> ROUTE.
        """
        if state.get("failure"):
            return _triage(f"the language model could not answer ({state['failure']})")
        p = ClassificationProposal.model_validate(state["proposal"])
        if p.out_of_scope:
            return _triage("out of scope: not a request for Public Works, Transportation, Parks & Recreation, or Inspectional Services")

        unclear_reason = None
        if p.multiple_issues:
            unclear_reason = "the message describes more than one problem"
        elif p.ambiguous:
            unclear_reason = "more than one request type fits"
        elif p.type_id is None:
            unclear_reason = "no request type clearly fits"
        elif state.get("top_score", 0.0) < self.gate and not _agrees_with_top_candidate(p, state):
            # Agreement rule (decided 2026-10-28): a weak retrieval score
            # alone does not force a question when the model's clear pick
            # is also the top-ranked candidate; the two signals agree.
            unclear_reason = "the message matches no official type closely (retrieval gate)"
        if unclear_reason:
            if state.get("clarifications_used", 0) == 0:
                question = p.clarifying_question or "Could you describe the problem in a little more detail, including where it is?"
                return {"decision": Decision.CLARIFY.value, "question": question, "triage_reason": None}
            return _triage(f"still unclear after one clarification: {unclear_reason}")

        candidate_ids = {c["type_id"] for c in state["candidates"]}
        if p.type_id not in candidate_ids or p.type_id not in self.catalog:
            return _triage(f"the proposed type {p.type_id!r} is not one of the retrieved official candidates")
        entry = self.catalog[p.type_id]
        partner = tools.overlapping_partner(entry.type)
        candidate_names = {c["type"] for c in state["candidates"]}
        if partner is not None and partner in candidate_names:
            return _triage(
                f"overlapping official types: \"{entry.type}\" and \"{partner}\" describe the same problem "
                "but are handled differently, so a person needs to route it"
            )
        department, _, _ = entry.route()
        if department is None:
            return _triage(
                f"\"{entry.type}\" is not handled consistently by one department "
                f"(most often {tools.usual_department_name(entry)}), so a person needs to route it"
            )
        return {"decision": Decision.ROUTE.value, "triage_reason": None}

    def clarify(self, state: IntakeState) -> IntakeState:
        """Pause and ask the resident one question (LangGraph interrupt).

        ``interrupt`` stops the graph here and hands ``{"question": ...}`` to
        the caller. When the caller resumes with the answer, this node runs
        again from the top and ``interrupt`` returns that answer. Nothing
        before ``interrupt`` has side effects, so re-running is safe.
        """
        answer = interrupt({"question": state["question"]})
        return {"clarification": str(answer or "").strip(), "clarifications_used": 1, "question": None, "decision": None}

    def respond(self, state: IntakeState) -> IntakeState:
        """Build the final, templated IntakeResult."""
        decision = Decision(state["decision"])
        message = state.get("message", "")
        if state.get("clarification"):
            message += f"\n[clarification] {state['clarification']}"
        proposal = ClassificationProposal.model_validate(state["proposal"]) if state.get("proposal") else None
        common = dict(
            decision=decision,
            message=message,
            clarifications_used=state.get("clarifications_used", 0),
            # The graph only reaches respond after a question if the resident
            # answered it, so here questions asked == answers received.
            questions_asked=state.get("clarifications_used", 0),
            proposal=proposal,
            candidate_ids=[c["type_id"] for c in state.get("candidates", [])],
            top_retrieval_score=state.get("top_score"),
        )
        if decision is Decision.REJECTED:
            result = IntakeResult(**common, triage_reason="empty input", response_text="Please describe the problem you would like to report.")
        elif decision is Decision.ROUTE:
            entry = self.catalog[proposal.type_id]
            department, queue, status = entry.route()
            result = IntakeResult(
                **common,
                type_id=entry.type_id,
                type_name=entry.type,
                department=department,
                queue=queue,
                queue_status=status,
                response_text=tools.route_text(entry, department, queue, status),
            )
        else:  # TRIAGE
            reason = state.get("triage_reason") or "unknown"
            if reason.startswith("out of scope"):
                text = (
                    "This does not look like a request for Public Works, Transportation, Parks & Recreation, or "
                    "Inspectional Services, so this assistant cannot route it. For emergencies, call 911."
                )
            else:
                text = f"I could not route this automatically ({reason}). A staff member would review it."
            best = proposal.type_id if proposal and proposal.type_id in self.catalog else None
            result = IntakeResult(
                **common,
                type_id=best,
                type_name=self.catalog[best].type if best else None,
                triage_reason=reason,
                response_text=f"{text}\n\n{tools.DEMO_NOTICE}",
            )
        return {"result": result.model_dump(mode="json")}

    # -- routing between nodes ------------------------------------------------

    @staticmethod
    def after_check(state: IntakeState) -> str:
        return "respond" if state.get("decision") == Decision.REJECTED.value else "retrieve"

    @staticmethod
    def after_decide(state: IntakeState) -> str:
        return "clarify" if state.get("decision") == Decision.CLARIFY.value else "respond"


def _agrees_with_top_candidate(p: ClassificationProposal, state: IntakeState) -> bool:
    """True if the model's proposed type is the top-ranked retrieved candidate.

    Candidates are stored best first (see ``tools.retrieve_candidates``).
    """
    candidates = state.get("candidates") or []
    return bool(candidates) and p.type_id is not None and p.type_id == candidates[0]["type_id"]


def _triage(reason: str) -> IntakeState:
    return {"decision": Decision.TRIAGE.value, "triage_reason": reason, "question": None}


# Expose the gate default for callers that do not pass one.
DEFAULT_GATE = config.RETRIEVAL_GATE_MIN_SCORE
