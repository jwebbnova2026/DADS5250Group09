"""Central configuration: every number and rule the rest of the code relies on.

How to read this file
---------------------
The architecture spec (docs/architecture.md) labels each rule with one of:

* GIVEN   - stated on the course project page. We must not change these.
* DEFAULT - a rule our team proposed. The team may change it, and the code
            reads it from here, so changing it is a one-line edit.

Every constant below says which kind it is and which spec section it comes
from. No other module should hard-code these numbers; they import them from
here instead. That way a reviewer can check every assumption in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

# ---------------------------------------------------------------------------
# File-system paths
# ---------------------------------------------------------------------------
# This file lives at <repo>/src/boston311/config.py, so the repository root is
# three levels up. Using paths relative to this file (instead of the current
# working directory) means the code works no matter where it is launched from,
# e.g. from the notebook, from pytest, or from a script in scripts/.
REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"  # downloaded source CSVs (large, gitignored)
PROCESSED_DIR = DATA_DIR / "processed"  # small derived tables (committed)
CATALOG_DIR = DATA_DIR / "catalog"  # official request-type catalog (committed)
EVAL_DIR = DATA_DIR / "eval"  # intake dev and test message sets (committed)
DEMO_DIR = DATA_DIR / "demo"  # recorded LLM outputs for offline mode (committed)
OUTPUTS_DIR = REPO_ROOT / "outputs"  # tables, figures, run manifests
PROMPTS_DIR = REPO_ROOT / "prompts"  # prompt templates (plain text)

# ---------------------------------------------------------------------------
# Source data (spec section 5.1)
# ---------------------------------------------------------------------------
# The data is fetched at run time through the CKAN API of Analyze Boston
# (data.boston.gov). CKAN is the open-source catalogue software the city uses;
# its "resource_show" endpoint returns the download URL and metadata of one
# file ("resource"). We pin the resource IDs so the code always asks for the
# same files, even if their display names change.
CKAN_API_BASE = "https://data.boston.gov/api/3/action"
DATASET_ID = "311-service-requests"
RESOURCE_IDS: dict[int, str] = {
    2023: "e6013a93-1321-4f2a-bf91-8d8a02f1e62f",
    2024: "dff4d804-5031-443a-8409-8344efd0e5c8",
}
# Training data years (GIVEN: "using 2023 and 2024 data").
DATA_YEARS: tuple[int, ...] = (2023, 2024)
# The year we plan for (DECIDED, spec section 3).
PLAN_YEAR = 2025
# Forecasting must never look past this date (spec section 9, check 5).
TRAINING_CUTOFF = "2024-12-31"

# Columns we keep from the 30-column source file (spec section 5.1). If any
# is missing, data.py raises an error that names the missing column
# (spec section 6, "Missing data column").
REQUIRED_COLUMNS: tuple[str, ...] = (
    "case_enquiry_id",
    "open_dt",
    "sla_target_dt",
    "closed_dt",
    "type",
    "queue",
    "department",
    "case_title",
    "neighborhood",
    "source",
)

# Neighborhood labels are not fully consistent in the source data: a few
# requests use a sub-area ("Allston") where most use the combined area
# ("Allston / Brighton"). For the neighborhood equity analysis only (spec
# deliverable 6) we merge those into the combined label, and treat a blank or
# the citywide label "Boston" as "Unspecified". DEFAULT, documented in
# docs/decisions.md. Labels not listed here are kept exactly as they are.
NEIGHBORHOOD_ALIASES: dict[str, str] = {
    "Allston": "Allston / Brighton",
    "Brighton": "Allston / Brighton",
    "South Boston": "South Boston / South Boston Waterfront",
    "Mattapan": "Greater Mattapan",
    "Boston": "Unspecified",
}
UNSPECIFIED_NEIGHBORHOOD = "Unspecified"

# ---------------------------------------------------------------------------
# Departments (GIVEN, spec section 2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Department:
    """The fixed planning facts for one department.

    Attributes:
        code: Department code exactly as it appears in the data's
            ``department`` column (for example ``"PWDx"``).
        name: Human-readable name.
        capacity_per_crew_day: Requests one crew can close on one service day.
        annual_cost: Cost of one regular crew for a full year, in dollars.
        start_crews: Regular crews working on January 1, 2025.
        requests_2024: 2024 request count stated on the project page. Used only
            to reconcile our data load against the page.
        on_time_2024: 2024 on-time share stated on the project page.
    """

    code: str
    name: str
    capacity_per_crew_day: int
    annual_cost: int
    start_crews: int
    requests_2024: int
    on_time_2024: float

    @property
    def monthly_cost(self) -> float:
        """Cost of one regular crew for one month (annual cost / 12, derived)."""
        return self.annual_cost / 12

    @property
    def capacity_per_crew_month(self) -> int:
        """Requests one crew can close in a month ("C" in spec section 5.4)."""
        return self.capacity_per_crew_day * SERVICE_DAYS_PER_MONTH


DEPARTMENTS: dict[str, Department] = {
    "PWDx": Department("PWDx", "Public Works", 12, 130_000, 50, 157_610, 0.90),
    "BTDT": Department("BTDT", "Transportation", 15, 110_000, 18, 81_447, 0.50),
    "PARK": Department("PARK", "Parks & Recreation", 6, 120_000, 10, 18_736, 0.93),
    "ISD": Department("ISD", "Inspectional Services", 4, 140_000, 16, 18_624, 0.72),
}
# A fixed order used everywhere we loop over departments, so outputs and
# random-number draws always happen in the same order (reproducibility).
DEPT_CODES: tuple[str, ...] = ("PWDx", "BTDT", "PARK", "ISD")

# ---------------------------------------------------------------------------
# Challenge rules (GIVEN, spec section 2)
# ---------------------------------------------------------------------------
SERVICE_DAYS_PER_MONTH = 21  # a crew works 21 days a month
HIRE_LEAD_MONTHS = 1  # one month of hiring and training before a crew starts
RELEASE_NOTICE_MONTHS = 1  # one month of notice before a crew leaves
SEVERANCE_FRACTION = 0.25  # releasing a crew costs 25% of its annual cost

SEASONAL_DEPT = "PARK"  # only Parks may use seasonal crews
SEASONAL_MONTHS: frozenset[int] = frozenset(range(4, 11))  # April (4) .. October (10)
SEASONAL_COST_MULTIPLIER = 1.3  # seasonal crew costs 1.3 x the regular monthly cost

OVERDUE_PENALTY = 20  # dollars, once, when a request passes its target date open
LONG_OVERDUE_PENALTY = 100  # extra dollars, once, if still open 30 days after target
LONG_OVERDUE_DAYS = 30

# ---------------------------------------------------------------------------
# Staffing-policy rules (DEFAULT unless noted, spec section 5.4)
# ---------------------------------------------------------------------------
# DECIDED (default, configurable): trainees are paid during their training
# month. Set to False to test the other interpretation of the project page.
PAID_TRAINING = True
# Terminal rules: no hire orders after the start of October, no release notices
# after the start of August (months are 1 = January .. 12 = December).
LAST_HIRE_ORDER_MONTH = 10
LAST_RELEASE_NOTICE_MONTH = 8
# The release check looks at months t .. t + 4 (a four-month look-ahead after
# the notice month).
RELEASE_LOOKAHEAD_MONTHS = 4
# A department always keeps at least this many regular crews.
MIN_REGULAR_CREWS = 1
# Parks orders no permanent hire whose first productive month is April-October.
PARKS_BLOCK_IN_SEASON_PERMANENT_HIRES = True
# Parks seasonal crews (DECIDED 2026-10-23, spec 5.4 step 2): each in-season
# month, use the fewest seasonal crews that keep the projected on-time rate of
# that month's due requests at or above this target. 0.93 is Parks' own 2024
# on-time rate from the project page ("no worse than last year"). The
# cost-vs-service frontier behind this choice is in
# outputs/parks_seasonal_frontier.csv (scripts/seasonal_frontier.py).
SEASONAL_ON_TIME_TARGET = 0.93

# ---------------------------------------------------------------------------
# Workload generation (DEFAULT, spec section 5.3)
# ---------------------------------------------------------------------------
# Two independent random streams. The planning stream builds the only workload
# the planner may see; the evaluation stream builds the workloads used to score
# the frozen plan. Any integers work; changing one changes only its workload.
PLANNING_SEED = 20250101
EVALUATION_SEED = 20251231
# A request type needs at least this many historical valid target windows to
# use its own distribution; otherwise we fall back to the department's pool,
# then to the pooled windows of all four departments (spec section 5.3).
MIN_WINDOW_SAMPLES = 50

# Sensitivity scenarios. Factors are exact fractions (not floats) so that
# "base total x 1.2, rounded" is computed exactly with no floating-point error.
SCENARIO_FACTORS: dict[str, Fraction] = {
    "plus20": Fraction(6, 5),
    "minus20": Fraction(4, 5),
}
# Snowstorm spike (DEFAULT, spec section 5.4): Public Works arrivals are tripled
# on February 10-12, 2025. "Tripled" means each affected type-day cell gets two
# extra requests for every base request, so its count becomes 3x the base.
SPIKE_DEPT = "PWDx"
SPIKE_DATES: tuple[str, ...] = ("2025-02-10", "2025-02-11", "2025-02-12")
SPIKE_MULTIPLIER = 3

# Names of all scenarios scored in the sensitivity analysis, in report order.
SCENARIOS: tuple[str, ...] = ("base", "plus20", "minus20", "spike")

# ---------------------------------------------------------------------------
# Catalog and routing (DEFAULT, spec section 5.6)
# ---------------------------------------------------------------------------
# Two-tier mapping rule (DECIDED 2026-10-22, spec 5.6). Shares are computed
# over ALL of a type's 2023-2024 requests, in every department.
#   Tier 1: if one in-scope department handled at least this share, the
#           type -> department mapping is nominated for human review.
#   Tier 2: if one queue of that department handled at least this share, the
#           type -> queue mapping is nominated too.
MAPPING_SHARE_THRESHOLD = 0.90
# Departments left out of the share denominator (DECIDED 2026-10-22). INFO is
# the 311 center itself; its queues are referrals to agencies outside the city
# (MassDOT, DCR, MBTA, Eversource, Massport) chosen by who owns the location,
# or "Reallocation From Dept" resubmissions. Neither is a department doing the
# work, so counting them would dilute the share of the department that does.
ROUTING_EXCLUDED_DEPARTMENTS: tuple[str, ...] = ("INFO",)
# Guard: the mapped department must ALSO have handled at least this share of
# ALL the type's requests (INFO included), so a type that is mostly referred
# elsewhere is never mapped into our four departments.
MIN_ALL_REQUESTS_SHARE = 0.50
# A type without a queue mapping is labeled "assigned_by_location" when at
# least this share of its requests went to district or region queues (queue
# names containing one of these words), else "assigned_by_department".
LOCATION_QUEUE_SHARE = 0.50
LOCATION_QUEUE_WORDS: tuple[str, ...] = ("District", "Region")
# Mapping review statuses recorded in data/catalog/catalog.json. For this
# build every nomination was provisionally approved; the team replaces
# "provisional" with "approved" or "rejected" after review. Routing treats
# "provisional" as approved only while this flag is True.
ACCEPT_PROVISIONAL_APPROVALS = True
# Pairs of official types that describe the same problem but route
# differently (DECIDED 2026-10-27, team review). Nothing in the data tells
# them apart, so if the model picks one type of a pair while the other was
# also retrieved, the request goes to TRIAGE and a person routes it, rather
# than the code silently picking one department. Names, not IDs, because IDs
# follow alphabetical order and could shift.
OVERLAPPING_TYPE_PAIRS: tuple[tuple[str, str], ...] = (
    ("Contractor Complaints", "Contractors Complaint"),  # unmapped vs Inspectional Services
    ("Work Hours-Loud Noise Complaints", "Working Beyond Hours"),  # Public Works vs Inspectional Services
    ("Sidewalk Repair", "Sidewalk Repair (Make Safe)"),  # Public Works vs unmapped
)
# Historical service statistics are shown only if a type has at least this many
# relevant requests; otherwise the response says "unavailable".
MIN_STATS_SAMPLE = 30

# ---------------------------------------------------------------------------
# Retrieval and LLM (DEFAULT, spec sections 5.6, 5.7, 6)
# ---------------------------------------------------------------------------
RETRIEVAL_TOP_K = 8  # how many candidate types the classifier is shown
# Retrieval gate (spec 5.7): auto-route only if the best retrieval score is at
# least this. Below it, the message shares too few words with any official
# type to trust, so the assistant asks for more detail instead. Tuned on the
# dev set only (see docs/decisions.md); never on the test set.
RETRIEVAL_GATE_MIN_SCORE = 0.15

LLM_PROVIDER = "openai"  # DECIDED (Q4)
LLM_MODEL = "gpt-6.1-sol"  # chosen by the team on 2026-10-22
LLM_REASONING_EFFORT = "low"
# gpt-6.1-sol is a reasoning model: it rejects any temperature other than the
# default (checked 2026-10-22), so we cannot set temperature=0. A fixed seed is
# accepted and makes answers *more* repeatable, but OpenAI does not guarantee
# identical output. Exact reproducibility comes from offline mode, which
# replays the recorded answers.
LLM_SEED = 5250
LLM_TIMEOUT_SECONDS = 60
# Bounded retries for timeouts and rate limits before the request goes to TRIAGE.
LLM_MAX_TRANSIENT_RETRIES = 2
# Malformed structured output gets exactly one retry, then TRIAGE (spec section 6).
LLM_MAX_MALFORMED_RETRIES = 1

# Version labels recorded in the run manifest so a reader can tell exactly
# which prompt and catalog produced a result. Bump them when you edit those.
PROMPT_VERSION = "classify-v3"
ALIAS_PROMPT_VERSION = "aliases-v2"
CATALOG_VERSION = "catalog-v2"

# Demo modes (spec section 5.9). "live" calls the model API and records the
# answers; "offline" replays the recorded answers with no network or key.
MODES: tuple[str, ...] = ("live", "offline")
