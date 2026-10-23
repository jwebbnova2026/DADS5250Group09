"""Data contracts shared across the package (Pydantic models).

Pydantic models are Python classes whose fields have declared types. Pydantic
checks the types when an object is created and can describe the model as a
JSON schema. We use them for two kinds of contract:

* **Staffing output** (spec section 5.5): :class:`StaffingRow`, one row per
  department x month x scenario x plan.
* **Intake assistant** (spec section 5.7): what the language model must
  return (:class:`ClassificationProposal`) and what the code decides
  (:class:`IntakeResult`). The LLM is forced to answer in exactly the
  ``ClassificationProposal`` shape ("structured output"), so the code never
  has to parse free text.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Staffing output (spec 5.5)
# ---------------------------------------------------------------------------


class StaffingRow(BaseModel):
    """One department in one month of 2025, under one plan and one scenario.

    The fields separate *events* (things that happened during the month) from
    *inventory* (what was still open at the end of the month), so the table
    can be checked with simple identities:

    * open_start + arrivals = closed + open_end
    * open_end = open_not_yet_due_end + open_overdue_end
                 + open_long_overdue_end + open_no_target_end
    * total_cost = regular_cost + seasonal_cost + severance_cost
                   + overdue_penalty + long_overdue_penalty
    """

    plan: str = Field(description="'heuristic' (our plan) or 'baseline' (January crews all year)")
    scenario: str = Field(description="'base', 'plus20', 'minus20', or 'spike'")
    department: str
    month: int = Field(ge=1, le=12)

    # Workforce
    hires_ordered: int = Field(ge=0, description="Hires ordered this month; they train now and work next month")
    hires_started: int = Field(ge=0, description="Hires ordered last month who start working this month")
    releases_noticed: int = Field(ge=0, description="Crews given notice this month; they still work this month")
    releases_effective: int = Field(ge=0, description="Crews noticed last month who left at the start of this month")
    regular_crews: int = Field(ge=0, description="Regular crews working this month (trainees not included)")
    seasonal_crews: int = Field(ge=0, description="Parks seasonal crews this month")
    capacity: int = Field(ge=0, description="Requests the working crews can close this month")

    # Flow during the month
    open_start: int = Field(ge=0, description="Requests open at the start of the month")
    arrivals: int = Field(ge=0)
    closed: int = Field(ge=0)
    closed_on_time: int = Field(ge=0, description="Closed on or before the target day")
    late_completions: int = Field(ge=0, description="Closed after the target day")
    no_target_closed: int = Field(ge=0, description="Closed requests that had no target date")

    # Penalty events during the month
    overdue_events: int = Field(ge=0, description="Requests that passed their target day while open ($20 each)")
    long_overdue_events: int = Field(ge=0, description="Requests still open 30 days after target (extra $100 each)")

    # Month-end inventory
    open_end: int = Field(ge=0)
    open_overdue_end: int = Field(ge=0, description="Open, past target, less than 30 days past")
    open_long_overdue_end: int = Field(ge=0, description="Open, 30 or more days past target")
    open_not_yet_due_end: int = Field(ge=0, description="Open, target day still ahead")
    open_no_target_end: int = Field(ge=0, description="Open, no target date")

    # Costs (dollars)
    regular_cost: float = Field(ge=0, description="Regular crews paid this month, including trainees if paid")
    seasonal_cost: float = Field(ge=0)
    severance_cost: float = Field(ge=0, description="25% of annual cost per crew noticed this month")
    overdue_penalty: float = Field(ge=0)
    long_overdue_penalty: float = Field(ge=0)
    total_cost: float = Field(ge=0)


# ---------------------------------------------------------------------------
# Intake assistant (spec 5.7)
# ---------------------------------------------------------------------------


class ClassificationProposal(BaseModel):
    """What the language model returns for one resident message.

    The model only *proposes*. The code then checks the proposal against the
    retrieved candidates and the catalog, and the code alone decides the
    department, the queue, and whether to route, clarify, or triage.
    """

    type_id: str | None = Field(
        description=(
            "The ID (for example 'T042') of the single candidate request type that best matches the "
            "message, copied exactly from the candidate list. Use null if no candidate fits, if the "
            "request is not something these city services handle, or if the message is empty or unclear."
        )
    )
    ambiguous: bool = Field(
        description=(
            "True if two or more candidates fit about equally well, or if an important detail is "
            "missing so you cannot choose confidently. False if one candidate clearly fits."
        )
    )
    missing_detail: str | None = Field(
        description="If ambiguous, the one detail that would settle it (for example 'whether the light is on a street or in a park'). Otherwise null."
    )
    clarifying_question: str | None = Field(
        description="If ambiguous, one short, polite question to ask the resident that would settle it. Otherwise null."
    )
    out_of_scope: bool = Field(
        description="True if the message is not a request for Public Works, Transportation, Parks & Recreation, or Inspectional Services."
    )
    multiple_issues: bool = Field(
        description="True if the message reports two or more separate problems that would need different request types."
    )
    evidence_ids: list[str] = Field(
        description="IDs of the candidates you seriously considered, best first (at most 3)."
    )
    reason: str = Field(description="One short sentence explaining the choice. Do not promise any action or timing.")


# The model's draft description and aliases for one official type, used only
# when building the catalog (scripts/build_catalog.py). These two classes live
# here so recorded alias answers can be identified by their schema.
#
# NOTE: no docstrings on these two classes. Pydantic copies a class docstring
# into the JSON schema sent to the model, so adding one would change the schema
# the committed alias recordings were made with (see llm.schema_id).
class AliasDraft(BaseModel):
    type_id: str = Field(description="The type_id exactly as given")
    description: str = Field(description="One neutral sentence describing what this type covers")
    aliases: list[str] = Field(description="5 to 8 short, varied resident-style phrasings")


class AliasBatch(BaseModel):  # one model call drafts about ten types
    items: list[AliasDraft]


class Decision(str, Enum):
    """What the intake assistant does with a message."""

    ROUTE = "ROUTE"  # confident: show the type, department, and queue
    CLARIFY = "CLARIFY"  # ask the resident one question (at most once)
    TRIAGE = "TRIAGE"  # hand to a human: unclear, out of scope, or an error
    REJECTED = "REJECTED"  # empty input, refused before any model call


class QueueStatus(str, Enum):
    """How precisely a routed type identifies its queue (two-tier rule, spec 5.6)."""

    EXACT = "exact"  # one queue handles at least 90% of the type
    ASSIGNED_BY_LOCATION = "assigned_by_location"  # district / region queues chosen by address
    ASSIGNED_BY_DEPARTMENT = "assigned_by_department"  # several queues; the department assigns


class IntakeResult(BaseModel):
    """The final outcome for one message, produced by code (not by the model)."""

    decision: Decision
    message: str = Field(description="The resident's text, including any clarification answer")
    type_id: str | None = None
    type_name: str | None = None
    department: str | None = None
    queue: str | None = Field(default=None, description="Exact queue name, only when queue_status is 'exact'")
    queue_status: QueueStatus | None = None
    clarifying_question: str | None = None
    # Two different counts: questions the assistant ASKED, and answers it
    # RECEIVED. They differ when the assistant asks and the conversation ends
    # before the resident replies (final decision CLARIFY).
    questions_asked: int = 0
    clarifications_used: int = Field(default=0, description="Clarification answers received (0 or 1)")
    triage_reason: str | None = None
    response_text: str = Field(description="The templated reply shown to the resident")
    proposal: ClassificationProposal | None = None
    candidate_ids: list[str] = Field(default_factory=list)
    top_retrieval_score: float | None = None
