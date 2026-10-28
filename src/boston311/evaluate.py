"""Evaluate the intake assistant on the dev and test sets (spec 4.8).

The test set (40 messages) measures the final system and is never used for
tuning. The dev set (18 separate messages) is used for prompt and gate
tuning and for the retrieval recall comparison with and without aliases.

Metrics (counts and percentages, labeled as a demonstration evaluation):

* **decision accuracy** - the final decision (ROUTE / TRIAGE / REJECTED)
  matches what a correct assistant would do under the approved mappings.
* **type accuracy** - over items with an expected type: the proposed type
  (routed, or the best guess on triage) is an acceptable type.
* **department accuracy** - over items expected to ROUTE: the routed
  department is correct (a triaged item counts as wrong).
* **queue accuracy** - over items expected to ROUTE, reported separately for
  ``exact`` queues (exact name match) and for the two labels (correct label).
* **auto-route precision** - of the items the assistant routed, the share
  routed to an acceptable type and department.
* **auto-route coverage** - of the items that should route, the share it did
  route (correctly or not).
* **clarification rate** - share of items where the assistant asked a
  clarifying question (answered or not).
* **triage rate** - share of items that ended in TRIAGE.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from boston311 import config
from boston311.agent import IntakeAssistant
from boston311.catalog import load_catalog
from boston311.retrieval import Retriever
from boston311.schemas import Decision, IntakeResult, QueueStatus


def load_set(name: str) -> list[dict]:
    """Read ``data/eval/<name>.jsonl`` (``name`` is "dev" or "test")."""
    path = config.EVAL_DIR / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_set(assistant: IntakeAssistant, items: list[dict]) -> pd.DataFrame:
    """Run every item through the assistant; one row per item with outcomes."""
    rows = []
    for item in items:
        res: IntakeResult = assistant.run(item["message"], item.get("clarification_answer"), thread_id=item["id"])
        queue_or_label = res.queue if res.queue_status is QueueStatus.EXACT else (res.queue_status.value if res.queue_status else None)
        rows.append(
            {
                "id": item["id"],
                "category": item["category"],
                "message": item["message"],
                "expected_decision": item["expected_decision"],
                "decision": res.decision.value,
                "expected_type_id": item["expected_type_id"],
                "type_id": res.type_id,
                "type_name": res.type_name,
                "expected_department": item["expected_department"],
                "department": res.department,
                "expected_queue": item["expected_queue"],
                "queue": queue_or_label,
                # Counted when the assistant ASKS, whether or not an answer came
                # back, so over-asking on clear messages always shows up.
                "clarified": res.questions_asked > 0,
                "triage_reason": res.triage_reason,
                "top_score": res.top_retrieval_score,
                "decision_ok": res.decision.value in item["acceptable_decisions"],
                "type_ok": (res.type_id in item["acceptable_type_ids"]) if item["expected_type_id"] else None,
                "department_ok": (res.department in item["acceptable_departments"]) if item["expected_decision"] == "ROUTE" else None,
                "queue_ok": (queue_or_label in item["acceptable_queues"]) if item["expected_decision"] == "ROUTE" else None,
                "queue_kind": ("exact" if item["expected_queue"] not in ("assigned_by_location", "assigned_by_department") else "label")
                if item["expected_decision"] == "ROUTE"
                else None,
            }
        )
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class Metric:
    name: str
    correct: int
    total: int

    @property
    def pct(self) -> float:
        return 100 * self.correct / self.total if self.total else float("nan")

    def __str__(self) -> str:
        return f"{self.name}: {self.correct}/{self.total} ({self.pct:.0f}%)"


def metrics(df: pd.DataFrame) -> list[Metric]:
    """Compute every metric in the module docstring from :func:`run_set` output."""

    def frac(name: str, mask: pd.Series) -> Metric:
        sub = mask.dropna().astype(bool)
        return Metric(name, int(sub.sum()), int(len(sub)))

    routed = df[df["decision"] == Decision.ROUTE.value]
    should_route = df[df["expected_decision"] == Decision.ROUTE.value]
    return [
        frac("decision accuracy", df["decision_ok"]),
        frac("type accuracy", df["type_ok"]),
        frac("department accuracy", df["department_ok"]),
        frac("queue accuracy (exact queues)", df.loc[df["queue_kind"] == "exact", "queue_ok"]),
        frac("queue accuracy (location/department labels)", df.loc[df["queue_kind"] == "label", "queue_ok"]),
        Metric("auto-route precision", int((routed["type_ok"].fillna(False) & routed["department_ok"].fillna(False)).sum()), len(routed)),
        Metric("auto-route coverage", int((should_route["decision"] == Decision.ROUTE.value).sum()), len(should_route)),
        Metric("clarification rate", int(df["clarified"].sum()), len(df)),
        Metric("triage rate", int((df["decision"] == Decision.TRIAGE.value).sum()), len(df)),
    ]


def metrics_table(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{"metric": m.name, "correct": m.correct, "total": m.total, "percent": round(m.pct, 1)} for m in metrics(df)])


def retrieval_recall(items: list[dict], k: int = config.RETRIEVAL_TOP_K) -> pd.DataFrame:
    """Candidate recall@k with and without aliases (spec 4.6; dev set only).

    Recall@k = share of items whose acceptable type appears among the top-k
    retrieved candidates. For items with a clarification answer, the search
    text is the message plus the answer, as in the agent.
    """
    entries = list(load_catalog().values())
    rows = []
    for with_aliases in (True, False):
        r = Retriever(entries, with_aliases=with_aliases)
        hits = []
        for item in items:
            if not item["expected_type_id"]:
                continue
            text = item["message"] + (" " + item["clarification_answer"] if item.get("clarification_answer") else "")
            found = {h.type_id for h in r.search(text, k)}
            hits.append(bool(found & set(item["acceptable_type_ids"])))
        rows.append({"aliases": with_aliases, "k": k, "found": sum(hits), "items": len(hits), "recall_pct": round(100 * sum(hits) / len(hits), 1)})
    return pd.DataFrame(rows)
