"""Catalog and retrieval helpers used by the intake agent's nodes.

These are deterministic Python functions, not LLM tool calls: the language
model never decides what to look up. Keeping them separate from the graph
makes each one easy to test on its own.
"""

from __future__ import annotations

from boston311 import config
from boston311.catalog import CatalogEntry, historical_stats_text
from boston311.retrieval import Retriever
from boston311.schemas import QueueStatus


def usual_department_name(entry: CatalogEntry) -> str:
    """Name of the department that handled most of a type's requests."""
    top = next(iter(entry.department_shares))  # shares are stored largest first
    return config.DEPARTMENTS[top].name if top in config.DEPARTMENTS else top


def department_label(entry: CatalogEntry) -> str:
    """The department text shown to the model for a candidate type."""
    if entry.department:
        return config.DEPARTMENTS[entry.department].name
    return f"no single department (most often {usual_department_name(entry)})"


def overlapping_partner(type_name: str) -> str | None:
    """The other type of this type's overlapping pair, or None if it has none.

    See ``config.OVERLAPPING_TYPE_PAIRS``: pairs that describe the same problem
    but route differently, which the data cannot tell apart.
    """
    for a, b in config.OVERLAPPING_TYPE_PAIRS:
        if type_name == a:
            return b
        if type_name == b:
            return a
    return None


def retrieve_candidates(retriever: Retriever, catalog: dict[str, CatalogEntry], text: str) -> tuple[list[dict], float]:
    """Top-k candidate types for ``text`` as plain dicts, plus the best score.

    Plain dicts (not objects) are stored in the graph state because LangGraph
    saves state in its checkpointer between the clarification question and
    the resident's answer.
    """
    hits = retriever.search(text)
    candidates = []
    for h in hits:
        e = catalog[h.type_id]
        candidates.append(
            {
                "type_id": e.type_id,
                "type": e.type,
                "department_name": department_label(e),
                "description": e.description,
                "aliases": e.aliases,
                "score": round(h.score, 4),
            }
        )
    return candidates, (hits[0].score if hits else 0.0)


def queue_sentence(queue: str | None, status: QueueStatus) -> str:
    """How to tell the resident which queue the request would reach."""
    if status is QueueStatus.EXACT:
        return f"It would go to the {queue} queue."
    if status is QueueStatus.ASSIGNED_BY_LOCATION:
        return "The exact queue is assigned by location (the district or region of the address)."
    return "The department assigns the exact queue."


def route_text(entry: CatalogEntry, department: str, queue: str | None, status: QueueStatus) -> str:
    """The templated reply for a routed request (spec 4.7: templated, never promises)."""
    dept_name = config.DEPARTMENTS[department].name
    return (
        f"This looks like a \"{entry.type}\" request, handled by {dept_name}. "
        f"{queue_sentence(queue, status)} {historical_stats_text(entry)}\n\n{DEMO_NOTICE}"
    )


DEMO_NOTICE = "This is a demonstration assistant: nothing has been submitted to the City of Boston, and no completion date is promised."
