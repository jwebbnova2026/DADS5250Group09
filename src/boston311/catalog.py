"""The official request-type catalog: routing mappings, aliases, and statistics.

Spec section 5.6, with the two-tier routing rule decided on 2026-10-22.

What is in the catalog
----------------------
One entry per official request type that appears in the four in-scope
departments in 2023-2024 (163 types). Each entry holds:

* **Routing evidence**: how the type's requests were split across
  departments and queues (in *all* departments, so a type mostly handled
  outside our four departments is never mapped into them).
* **Department mapping (tier 1)**: nominated when one in-scope department
  handled at least 90% of the type's requests.
* **Queue mapping (tier 2)**: nominated when, in addition, one queue of that
  department handled at least 90%.
* **Queue status**: ``exact`` (has a queue mapping), ``assigned_by_location``
  (mostly district or region queues, which depend on the address), or
  ``assigned_by_department`` (several queues; the department assigns).
* **Review status** of each mapping: ``provisional`` (nominated and
  provisionally approved, awaiting team review), ``approved``,
  ``rejected``, or ``not_nominated``.
* **Description and aliases**: a neutral one-sentence description and a few
  resident-style phrasings, used only to help retrieval find the type. They
  never create, rename, or merge types.
* **Historical service statistics**, joined by type and shown to residents
  labeled as historical.

The catalog lives in ``data/catalog/catalog.json`` and is committed. Human
review decisions and aliases are kept when the catalog is rebuilt, so
rebuilding never silently overwrites a reviewer's work.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import pandas as pd

from boston311 import config
from boston311.data import load_processed
from boston311.schemas import QueueStatus

CATALOG_PATH = config.CATALOG_DIR / "catalog.json"
REVIEW_CSV_PATH = config.CATALOG_DIR / "mapping_review.csv"

# Review statuses.
PROVISIONAL = "provisional"
APPROVED = "approved"
REJECTED = "rejected"
NOT_NOMINATED = "not_nominated"


@dataclass
class CatalogEntry:
    """One official request type. See the module docstring for the fields."""

    type_id: str
    type: str
    n_requests: int  # all departments, 2023-2024
    department_shares: dict[str, float]  # share of the type's requests per department
    top_queues: list[dict]  # up to 5 of {"queue", "department", "share"}, largest first
    location_queue_share: float  # share that went to district/region queues
    department: str | None  # tier-1 mapping (None if not nominated)
    department_share: float  # top handling department's share of HANDLED requests (INFO excluded)
    department_status: str
    queue: str | None  # tier-2 mapping (None if not nominated)
    queue_share: float  # top queue of the mapped department, share of HANDLED requests
    queue_status_review: str  # review status of the tier-2 mapping
    queue_status: str | None  # QueueStatus value, or None if no department mapping
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    alias_status: str = "missing"  # "missing", "provisional", "approved"
    top_titles: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    department_share_all: float = 0.0  # same department's share of ALL requests (guard: >= 50%)
    referral_share: float = 0.0  # share sent to 311 referral/reallocation queues (INFO)

    # -- routing helpers ---------------------------------------------------

    def department_approved(self) -> bool:
        """True if this type may auto-route to its department."""
        return self.department is not None and _approved(self.department_status)

    def queue_approved(self) -> bool:
        """True if this type may name an exact queue."""
        return self.queue is not None and _approved(self.queue_status_review)

    def route(self) -> tuple[str | None, str | None, QueueStatus | None]:
        """(department, exact queue or None, queue status), using approved mappings only."""
        if not self.department_approved():
            return None, None, None
        if self.queue_approved():
            return self.department, self.queue, QueueStatus.EXACT
        # No approved queue mapping (none nominated, or a reviewer rejected
        # it): name the department and label how the queue gets chosen.
        location = self.location_queue_share >= config.LOCATION_QUEUE_SHARE
        return self.department, None, QueueStatus.ASSIGNED_BY_LOCATION if location else QueueStatus.ASSIGNED_BY_DEPARTMENT

    def search_text(self, with_aliases: bool = True) -> str:
        """The text retrieval indexes for this type."""
        parts = [self.type, self.description]
        if with_aliases:
            parts += self.aliases
        return " . ".join(p for p in parts if p)


def _approved(status: str) -> bool:
    return status == APPROVED or (status == PROVISIONAL and config.ACCEPT_PROVISIONAL_APPROVALS)


def _is_location_queue(queue: str) -> bool:
    return any(word in queue for word in config.LOCATION_QUEUE_WORDS)


def build_mappings() -> list[CatalogEntry]:
    """Apply the two-tier mapping rule to the processed routing evidence.

    Every nomination starts as ``provisional`` (see module docstring); every
    other mapping is ``not_nominated``.
    """
    types = load_processed("types")
    qc = load_processed("type_queue_counts")
    stats = load_processed("type_service_stats").set_index("type_id")
    titles = load_processed("type_titles")

    entries = []
    for type_id, name in types.itertuples(index=False):
        rows = qc[qc["type_id"] == type_id]
        total = int(rows["requests"].sum())
        # Evidence kept for reviewers: shares over ALL departments.
        dept_shares = (rows.groupby("department")["requests"].sum() / total).sort_values(ascending=False)
        queue_counts_all = rows.groupby(["queue", "department"])["requests"].sum().sort_values(ascending=False)
        top_queues = [
            {"queue": q, "department": d, "share": round(n / total, 4)} for (q, d), n in queue_counts_all.head(5).items()
        ]

        # The mapping rule works on the requests some department actually
        # handled: 311 referral / reallocation queues (department INFO) are
        # left out of the denominator (DECIDED 2026-10-22, spec 5.6).
        handled_rows = rows[~rows["department"].isin(config.ROUTING_EXCLUDED_DEPARTMENTS)]
        handled = int(handled_rows["requests"].sum())
        referral_share = 1 - handled / total
        if handled:
            handled_shares = handled_rows.groupby("department")["requests"].sum() / handled
            queue_counts = handled_rows.groupby(["queue", "department"])["requests"].sum().sort_values(ascending=False)
            location_share = float(handled_rows.loc[handled_rows["queue"].map(_is_location_queue), "requests"].sum() / handled)
            # Tier 1: the largest handling department (ties: alphabetical).
            dept, dept_share = sorted(handled_shares.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        else:  # every request was referred elsewhere: nothing to map
            dept, dept_share, location_share, queue_counts = None, 0.0, 0.0, queue_counts_all.iloc[:0]
        dept_share_all = float(dept_shares.get(dept, 0.0)) if dept else 0.0
        # It must be in scope, hold >= 90% of handled requests, AND >= 50% of
        # all requests (so a type mostly referred elsewhere is never mapped).
        dept_ok = (
            dept in config.DEPT_CODES
            and dept_share >= config.MAPPING_SHARE_THRESHOLD
            and dept_share_all >= config.MIN_ALL_REQUESTS_SHARE
        )

        # Tier 2: queue mapping within the mapped department, same denominator.
        queue, queue_share = None, 0.0
        if dept_ok:
            in_dept = queue_counts[queue_counts.index.get_level_values("department") == dept]
            best_queue, best_n = in_dept.index[0][0], int(in_dept.iloc[0])
            queue_share = best_n / handled
            if queue_share >= config.MAPPING_SHARE_THRESHOLD:
                queue = best_queue
        if not dept_ok:
            queue_status = None
        elif queue is not None:
            queue_status = QueueStatus.EXACT.value
        elif location_share >= config.LOCATION_QUEUE_SHARE:
            queue_status = QueueStatus.ASSIGNED_BY_LOCATION.value
        else:
            queue_status = QueueStatus.ASSIGNED_BY_DEPARTMENT.value

        s = stats.loc[type_id]
        entries.append(
            CatalogEntry(
                type_id=type_id,
                type=name,
                n_requests=total,
                department_shares={k: round(float(v), 4) for k, v in dept_shares.items()},
                top_queues=top_queues,
                location_queue_share=round(location_share, 4),
                department=dept if dept_ok else None,
                department_share=round(float(dept_share), 4),
                department_share_all=round(dept_share_all, 4),
                referral_share=round(float(referral_share), 4),
                department_status=PROVISIONAL if dept_ok else NOT_NOMINATED,
                queue=queue,
                queue_share=round(float(queue_share), 4),
                queue_status_review=PROVISIONAL if queue else NOT_NOMINATED,
                queue_status=queue_status,
                top_titles=titles.loc[titles["type_id"] == type_id, "case_title"].tolist(),
                stats={
                    "requests_in_scope": int(s["requests"]),
                    "with_target": int(s["with_target"]),
                    "on_time": int(s["on_time"]),
                    "closed": int(s["closed"]),
                    "median_days_to_close": None if pd.isna(s["median_days_to_close"]) else float(s["median_days_to_close"]),
                },
            )
        )
    return entries


def merge_reviews(new: list[CatalogEntry], old: list[CatalogEntry]) -> list[CatalogEntry]:
    """Carry human work from an existing catalog into a rebuilt one.

    Kept from the old entry (matched by type name, since IDs follow
    alphabetical order and could shift if a new type appears):
    descriptions, aliases, and their status; and any ``approved`` or
    ``rejected`` mapping decision, as long as the mapping itself is unchanged.
    """
    by_name = {e.type: e for e in old}
    for e in new:
        o = by_name.get(e.type)
        if o is None:
            continue
        e.description, e.aliases, e.alias_status = o.description, o.aliases, o.alias_status
        if o.department == e.department and o.department_status in (APPROVED, REJECTED):
            e.department_status = o.department_status
        if o.queue == e.queue and o.queue_status_review in (APPROVED, REJECTED):
            e.queue_status_review = o.queue_status_review
    return new


def save_catalog(entries: list[CatalogEntry]) -> None:
    """Write catalog.json and a one-row-per-type review sheet (CSV)."""
    config.CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "catalog_version": config.CATALOG_VERSION,
        "rule": (
            "Two-tier mapping (spec 5.6): department mapping if one in-scope department has >= 90% of the "
            "type's 2023-2024 requests (all departments); exact queue if one queue of that department has >= 90%. "
            "'provisional' = nominated and provisionally approved, pending team review."
        ),
        "entries": [asdict(e) for e in entries],
    }
    CATALOG_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    review = pd.DataFrame(
        [
            {
                "type_id": e.type_id,
                "type": e.type,
                "n_requests": e.n_requests,
                "top_department": next(iter(e.department_shares)),
                "department": e.department or "",
                "department_share": e.department_share,
                "department_share_all": e.department_share_all,
                "referral_share": e.referral_share,
                "department_status": e.department_status,
                "queue": e.queue or "",
                "queue_share": e.queue_share,
                "queue_review": e.queue_status_review,
                "queue_status": e.queue_status or "",
                "location_queue_share": e.location_queue_share,
                "alias_status": e.alias_status,
                "aliases": " | ".join(e.aliases),
            }
            for e in entries
        ]
    )
    review.to_csv(REVIEW_CSV_PATH, index=False, lineterminator="\n", encoding="utf-8")


def load_catalog() -> dict[str, CatalogEntry]:
    """Read the committed catalog, keyed by type ID."""
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"{CATALOG_PATH} not found. Run `python scripts/build_catalog.py`.")
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {e["type_id"]: CatalogEntry(**e) for e in payload["entries"]}


def historical_stats_text(entry: CatalogEntry) -> str:
    """A short, clearly historical summary for the resident.

    The two statistics are computed over *different* groups of past
    requests, so each is shown only if its own group is large enough
    (``config.MIN_STATS_SAMPLE``, 30):

    * the on-time share is over requests that had a target date;
    * the median time to close is over requests that were closed.

    A type can have many requests with a target date but very few closed
    (for example Parking Meter Repairs: 75 and 7), so one statistic may be
    shown while the other says "unavailable". Each statistic states how many
    requests it is based on.
    """
    s = entry.stats
    with_target, closed = s.get("with_target", 0), s.get("closed", 0)
    median = s.get("median_days_to_close")
    on_time_ok = with_target >= config.MIN_STATS_SAMPLE
    median_ok = closed >= config.MIN_STATS_SAMPLE and median is not None
    if not on_time_ok and not median_ok:
        return "Historical service statistics: unavailable (too few past requests)."
    parts = []
    if on_time_ok:
        parts.append(
            f"{s['on_time'] / with_target:.0%} of these requests with a target date were closed on time "
            f"(based on {with_target:,} requests)"
        )
    else:
        parts.append(f"on-time share: unavailable (only {with_target} requests had a target date)")
    if median_ok:
        parts.append(f"closed requests took a median of {median:.1f} days to close (based on {closed:,} closed requests)")
    else:
        parts.append(f"median time to close: unavailable (only {closed} requests were closed)")
    return f"Historically (2023-2024), {parts[0]}; {parts[1]}. This is past performance, not a promise."


# ---------------------------------------------------------------------------
# Alias drafting (LLM, structured output; reviewed afterwards)
# ---------------------------------------------------------------------------


def alias_batches(entries: list[CatalogEntry], size: int = 10) -> list[list[CatalogEntry]]:
    """Group entries that still need aliases into batches for the LLM."""
    todo = [e for e in entries if e.alias_status == "missing"]
    return [todo[i : i + size] for i in range(0, len(todo), size)]


def alias_prompt_input(batch: list[CatalogEntry]) -> str:
    """Describe a batch of types to the alias-drafting prompt."""
    lines = []
    for e in batch:
        dept = config.DEPARTMENTS[e.department].name if e.department else "/".join(e.department_shares)
        titles = "; ".join(e.top_titles[:6]) or "(none)"
        lines.append(f"- {e.type_id} | type: {e.type} | handled by: {dept} | common case titles: {titles}")
    return "\n".join(lines)
