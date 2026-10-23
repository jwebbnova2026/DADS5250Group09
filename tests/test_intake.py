"""Tests for the catalog, retrieval, LLM wrapper, intake agent, and evaluation.

No test here calls the real model: a FakeModel returns scripted proposals,
and the offline replay test uses the committed recordings. So these tests
need no network and no API key (spec check 2).

Covers spec section 6 (failure behavior) and check 6 (routing only through
approved official mappings).
"""

from __future__ import annotations

import copy

import httpx
import openai
import pytest

from boston311 import config, evaluate, llm
from boston311.agent import IntakeAssistant
from boston311.catalog import APPROVED, REJECTED, load_catalog
from boston311.llm import ClassifierFailure, LiveModel, MissingAPIKeyError, OfflineModel, RecordingStore
from boston311.retrieval import Retriever
from boston311.schemas import ClassificationProposal, Decision, QueueStatus


def proposal(type_id=None, *, ambiguous=False, out_of_scope=False, multiple=False, question=None) -> ClassificationProposal:
    return ClassificationProposal(
        type_id=type_id,
        ambiguous=ambiguous,
        missing_detail="detail" if ambiguous else None,
        clarifying_question=question or ("Which one?" if ambiguous else None),
        out_of_scope=out_of_scope,
        multiple_issues=multiple,
        evidence_ids=[type_id] if type_id else [],
        reason="test",
    )


class FakeModel:
    """Returns proposals from a script, in order, and counts calls."""

    mode = "fake"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def ask(self, kind, system, user, schema):
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def retriever(catalog):
    return Retriever(list(catalog.values()))


def assistant(catalog, retriever, model, gate=0.0):
    return IntakeAssistant(model=model, catalog=catalog, retriever=retriever, gate=gate)


def type_id_of(catalog, name):
    return next(e.type_id for e in catalog.values() if e.type == name)


# ---------------------------------------------------------------------------
# Catalog: the two-tier mapping rule
# ---------------------------------------------------------------------------


def test_mappings_follow_the_two_tier_rule(catalog):
    for e in catalog.values():
        if e.department:
            assert e.department in config.DEPT_CODES
            assert e.department_share >= config.MAPPING_SHARE_THRESHOLD
            assert e.department_share_all >= config.MIN_ALL_REQUESTS_SHARE
        else:
            assert e.queue is None and e.queue_status is None
        if e.queue:
            assert e.queue_share >= config.MAPPING_SHARE_THRESHOLD
            assert e.queue.startswith(e.department)  # the queue belongs to the mapped department
            assert e.queue_status == QueueStatus.EXACT.value


def test_audit_examples(catalog):
    by_name = {e.type: e for e in catalog.values()}
    assert by_name["Parking Enforcement"].queue == "BTDT_Parking Enforcement"
    # Street cleaning reaches 90% only once INFO referrals are left out.
    sc = by_name["Requests for Street Cleaning"]
    assert sc.department == "PWDx" and sc.department_share_all < 0.9 <= sc.department_share
    assert sc.queue_status == QueueStatus.ASSIGNED_BY_LOCATION.value
    # Potholes are split with the Water and Sewer Commission: never mapped.
    assert by_name["Request for Pothole Repair"].department is None
    # The 50% guard: a type almost entirely referred elsewhere stays unmapped.
    assert by_name["Undefined Noise Disturbance"].department is None


def test_rejected_mapping_never_routes(catalog):
    entry = copy.deepcopy(catalog[type_id_of(catalog, "Parking Enforcement")])
    entry.queue_status_review = REJECTED
    assert entry.route() == ("BTDT", None, QueueStatus.ASSIGNED_BY_DEPARTMENT)  # department only
    entry.department_status = REJECTED
    assert entry.route() == (None, None, None)


def test_provisional_requires_flag(catalog, monkeypatch):
    entry = catalog[type_id_of(catalog, "Parking Enforcement")]
    monkeypatch.setattr(config, "ACCEPT_PROVISIONAL_APPROVALS", False)
    assert entry.route()[0] is None
    approved = copy.deepcopy(entry)
    approved.department_status = APPROVED
    approved.queue_status_review = APPROVED
    assert approved.route() == ("BTDT", "BTDT_Parking Enforcement", QueueStatus.EXACT)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def test_retrieval_tolerates_misspelling(catalog, retriever):
    top = [h.type_id for h in retriever.search("strret lite is out on my block", 3)]
    assert type_id_of(catalog, "Street Light Outages") in top


def test_aliases_improve_recall_on_dev():
    recall = evaluate.retrieval_recall(evaluate.load_set("dev")).set_index("aliases")["recall_pct"]
    assert recall[True] > recall[False]


# ---------------------------------------------------------------------------
# The intake agent (with a fake model)
# ---------------------------------------------------------------------------


def test_route(catalog, retriever):
    pe = type_id_of(catalog, "Parking Enforcement")
    a = assistant(catalog, retriever, FakeModel(proposal(pe)))
    r = a.run("A car is blocking my driveway")
    assert r.decision is Decision.ROUTE and r.department == "BTDT"
    assert r.queue == "BTDT_Parking Enforcement" and r.queue_status is QueueStatus.EXACT
    assert "nothing has been submitted" in r.response_text  # never claims submission


def test_assigned_by_location_label(catalog, retriever):
    sc = type_id_of(catalog, "Requests for Street Cleaning")
    r = assistant(catalog, retriever, FakeModel(proposal(sc))).run("The street needs sweeping, litter everywhere")
    assert r.decision is Decision.ROUTE and r.queue is None
    assert r.queue_status is QueueStatus.ASSIGNED_BY_LOCATION and "assigned by location" in r.response_text


@pytest.mark.parametrize("message", ["", "    "])
def test_empty_input_rejected_before_any_api_call(catalog, retriever, message):
    model = FakeModel()
    r = assistant(catalog, retriever, model).run(message)
    assert r.decision is Decision.REJECTED and model.calls == 0


def test_out_of_scope_triage_with_explanation(catalog, retriever):
    r = assistant(catalog, retriever, FakeModel(proposal(out_of_scope=True))).run("Someone stole my bike")
    assert r.decision is Decision.TRIAGE and "911" in r.response_text


def test_type_not_in_candidates_triage(catalog, retriever):
    r = assistant(catalog, retriever, FakeModel(proposal("T999"))).run("A car is blocking my driveway")
    assert r.decision is Decision.TRIAGE and "not one of the retrieved" in r.triage_reason


def test_unmapped_type_triage(catalog, retriever):
    pothole = type_id_of(catalog, "Request for Pothole Repair")
    r = assistant(catalog, retriever, FakeModel(proposal(pothole))).run("There is a pothole in the road")
    assert r.decision is Decision.TRIAGE and r.type_id == pothole and "most often Public Works" in r.triage_reason


def test_clarify_once_then_route_without_rerunning_the_model(catalog, retriever):
    light = type_id_of(catalog, "Street Light Outages")
    model = FakeModel(proposal(None, ambiguous=True, question="Is it a street light?"), proposal(light))
    a = assistant(catalog, retriever, model)
    turn = a.submit("There's a light out.")
    assert turn.question == "Is it a street light?" and model.calls == 1
    turn = a.answer(turn.thread_id, "Yes, a street light on the sidewalk")
    # Exactly one more model call: resuming re-runs the clarify node, which
    # makes no API calls, and then classify runs once.
    assert model.calls == 2
    assert turn.result.decision is Decision.ROUTE and turn.result.clarifications_used == 1


def test_second_ambiguity_triage(catalog, retriever):
    model = FakeModel(proposal(None, ambiguous=True), proposal(None, ambiguous=True))
    r = assistant(catalog, retriever, model).run("Problem.", clarification_answer="Not sure.")
    assert r.decision is Decision.TRIAGE and "still unclear" in r.triage_reason


def test_multiple_issues_ask_first(catalog, retriever):
    rodent = type_id_of(catalog, "Rodent Activity")
    model = FakeModel(proposal(None, ambiguous=True, multiple=True), proposal(rodent))
    r = assistant(catalog, retriever, model).run("Rats and missed trash", clarification_answer="The rats")
    assert r.decision is Decision.ROUTE and r.type_id == rodent


def test_retrieval_gate_asks_for_detail(catalog, retriever):
    pe = type_id_of(catalog, "Parking Enforcement")
    model = FakeModel(proposal(pe))
    r = assistant(catalog, retriever, model, gate=0.99).run("A car is blocking my driveway")
    assert r.decision is Decision.CLARIFY


def test_model_failure_triage(catalog, retriever):
    model = FakeModel(ClassifierFailure("transient", "timeout"))
    r = assistant(catalog, retriever, model).run("A car is blocking my driveway")
    assert r.decision is Decision.TRIAGE and "transient" in r.triage_reason


# ---------------------------------------------------------------------------
# LLM wrapper failure behavior (spec 6)
# ---------------------------------------------------------------------------


class FakeStructured:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


class FakeChat:
    def __init__(self, structured):
        self.structured = structured

    def with_structured_output(self, schema, **kwargs):
        return self.structured


def _timeout():
    return openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))


def test_transient_errors_retry_then_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    structured = FakeStructured([_timeout()] * (config.LLM_MAX_TRANSIENT_RETRIES + 1))
    model = LiveModel(RecordingStore(tmp_path / "r.jsonl"), llm=FakeChat(structured))
    with pytest.raises(ClassifierFailure) as exc:
        model.ask("classify", "sys", "user", ClassificationProposal)
    assert exc.value.kind == "transient" and structured.calls == config.LLM_MAX_TRANSIENT_RETRIES + 1


def test_malformed_output_retries_once_then_fails(tmp_path):
    bad = {"parsed": None, "parsing_error": ValueError("bad json"), "raw": None}
    structured = FakeStructured([bad, bad])
    model = LiveModel(RecordingStore(tmp_path / "r.jsonl"), llm=FakeChat(structured))
    with pytest.raises(ClassifierFailure) as exc:
        model.ask("classify", "sys", "user", ClassificationProposal)
    assert exc.value.kind == "malformed" and structured.calls == 2


def test_live_answers_are_recorded_and_replayed_offline(tmp_path):
    good = {"parsed": proposal("T082"), "parsing_error": None, "raw": None}
    store = RecordingStore(tmp_path / "r.jsonl")
    LiveModel(store, llm=FakeChat(FakeStructured([good]))).ask("classify", "sys", "user", ClassificationProposal)
    replay = OfflineModel(RecordingStore(tmp_path / "r.jsonl")).ask("classify", "sys", "user", ClassificationProposal)
    assert replay.type_id == "T082"
    with pytest.raises(ClassifierFailure) as exc:
        OfflineModel(store).ask("classify", "sys", "a different input", ClassificationProposal)
    assert exc.value.kind == "no_recording"


def test_missing_api_key_message(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **k: None)  # do not read the real .env
    with pytest.raises(MissingAPIKeyError, match="offline mode"):
        LiveModel(RecordingStore())


# ---------------------------------------------------------------------------
# Offline mode on the real sets (spec check 2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["dev", "test"])
def test_offline_replay_covers_every_eval_item(name, catalog, retriever):
    a = IntakeAssistant(mode="offline", catalog=catalog, retriever=retriever)
    df = evaluate.run_set(a, evaluate.load_set(name))
    missing = df[df["triage_reason"].fillna("").str.contains("no_recording")]
    assert missing.empty, f"no recording for {missing['id'].tolist()}"


def test_metrics_on_a_tiny_frame():
    import pandas as pd

    df = pd.DataFrame(
        {
            "decision": ["ROUTE", "TRIAGE"],
            "expected_decision": ["ROUTE", "TRIAGE"],
            "decision_ok": [True, True],
            "type_ok": [True, None],
            "department_ok": [True, None],
            "queue_ok": [False, None],
            "queue_kind": ["exact", None],
            "clarified": [False, True],
        }
    )
    m = {x.name: (x.correct, x.total) for x in evaluate.metrics(df)}
    assert m["decision accuracy"] == (2, 2)
    assert m["queue accuracy (exact queues)"] == (0, 1)
    assert m["auto-route precision"] == (1, 1)
    assert m["clarification rate"] == (1, 2)
