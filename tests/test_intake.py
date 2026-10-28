"""Tests for the catalog, retrieval, LLM wrapper, intake agent, and evaluation.

No test here calls the real model: a FakeModel returns scripted proposals,
and the offline replay test uses the committed recordings. So these tests
need no network and no API key (spec check 2).

Covers spec section 6 (failure behavior) and check 6 (routing only through
approved official mappings).
"""

from __future__ import annotations

import copy
import json

import httpx
import openai
import pytest
from pydantic import ValidationError

from boston311 import config, evaluate, llm
from boston311.agent import IntakeAssistant
from boston311.catalog import APPROVED, PROVISIONAL, REJECTED, load_catalog
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
    # Use a provisional copy: the real entry has since been approved in review.
    entry = copy.deepcopy(catalog[type_id_of(catalog, "Parking Enforcement")])
    entry.department_status = PROVISIONAL
    entry.queue_status_review = PROVISIONAL
    monkeypatch.setattr(config, "ACCEPT_PROVISIONAL_APPROVALS", False)
    assert entry.route()[0] is None
    approved = copy.deepcopy(entry)
    approved.department_status = APPROVED
    approved.queue_status_review = APPROVED
    assert approved.route() == ("BTDT", "BTDT_Parking Enforcement", QueueStatus.EXACT)


# ---------------------------------------------------------------------------
# Historical statistics shown to residents (R2): each statistic needs its own sample
# ---------------------------------------------------------------------------


def stats_entry(catalog, with_target, on_time, closed, median=2.5):
    e = copy.deepcopy(next(iter(catalog.values())))
    e.stats = {"requests_in_scope": max(with_target, closed), "with_target": with_target, "on_time": on_time,
               "closed": closed, "median_days_to_close": median}
    return e


def test_median_hidden_when_too_few_closed(catalog):
    from boston311.catalog import historical_stats_text

    text = historical_stats_text(stats_entry(catalog, with_target=75, on_time=7, closed=7))  # Parking Meter Repairs case
    assert "9% of these requests with a target date" in text
    assert "2.5" not in text and "median time to close: unavailable" in text.lower()


@pytest.mark.parametrize("closed, median_shown", [(29, False), (30, True)])
def test_median_boundary_at_min_sample(catalog, closed, median_shown):
    from boston311.catalog import historical_stats_text

    text = historical_stats_text(stats_entry(catalog, with_target=100, on_time=50, closed=closed))
    assert ("median of 2.5 days" in text) is median_shown
    assert "50% of these requests" in text  # the on-time statistic has its own, sufficient sample


def test_on_time_hidden_when_too_few_with_target(catalog):
    from boston311.catalog import historical_stats_text

    text = historical_stats_text(stats_entry(catalog, with_target=29, on_time=29, closed=200))
    assert "on-time share: unavailable" in text.lower() and "100%" not in text
    assert "closed requests took a median of 2.5 days" in text


def test_all_statistics_unavailable(catalog):
    from boston311.catalog import historical_stats_text

    assert "unavailable" in historical_stats_text(stats_entry(catalog, with_target=5, on_time=5, closed=5, median=None))


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


# Overlapping official types (decided 2026-10-27): when the model picks one
# type of a pair and the other one was also retrieved, the data cannot say
# which is right, so a person routes it instead of the code picking one.


def test_overlap_pairs_name_real_types(catalog):
    names = {e.type for e in catalog.values()}
    for pair in config.OVERLAPPING_TYPE_PAIRS:
        assert len(pair) == 2 and set(pair) <= names


def test_overlap_pair_triage_when_partner_retrieved(catalog, retriever):
    sidewalk = type_id_of(catalog, "Sidewalk Repair")
    r = assistant(catalog, retriever, FakeModel(proposal(sidewalk))).run(
        "The sidewalk on my street is all cracked and the slabs are uneven."
    )
    assert type_id_of(catalog, "Sidewalk Repair (Make Safe)") in r.candidate_ids  # the partner was retrieved
    assert r.decision is Decision.TRIAGE and r.type_id == sidewalk
    assert "overlapping official types" in r.triage_reason


def test_overlap_pair_routes_when_partner_not_retrieved(catalog, retriever, monkeypatch):
    # A made-up pair whose second type cannot be retrieved for this message.
    monkeypatch.setattr(config, "OVERLAPPING_TYPE_PAIRS", (("Parking Enforcement", "Cemetery Maintenance Request"),))
    pe = type_id_of(catalog, "Parking Enforcement")
    r = assistant(catalog, retriever, FakeModel(proposal(pe))).run("A car is blocking my driveway")
    assert type_id_of(catalog, "Cemetery Maintenance Request") not in r.candidate_ids
    assert r.decision is Decision.ROUTE


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


def test_reused_thread_id_starts_clean(catalog, retriever):
    """A second message on the same thread ID must not inherit the first one's
    used clarification (it would otherwise triage instead of asking)."""
    light = type_id_of(catalog, "Street Light Outages")
    model = FakeModel(
        proposal(None, ambiguous=True), proposal(light),  # first message: ask, then route
        proposal(None, ambiguous=True),  # second message, same thread: must ask again
    )
    a = assistant(catalog, retriever, model)
    first = a.run("There's a light out.", clarification_answer="A street light", thread_id="same")
    assert first.decision is Decision.ROUTE
    second = a.submit("There's a light out.", thread_id="same")
    assert second.question is not None


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
    # The model picks a candidate that is NOT the top retrieval hit, so the
    # two signals disagree and the gate applies.
    message = "A car is blocking my driveway"
    second = retriever.search(message)[1].type_id
    model = FakeModel(proposal(second))
    r = assistant(catalog, retriever, model, gate=0.99).run(message)
    assert r.decision is Decision.CLARIFY


def test_agreement_with_top_candidate_skips_gate(catalog, retriever):
    # Agreement rule (decided 2026-10-28): the model's clear pick is also the
    # top retrieval hit, so a weak retrieval score alone does not force a question.
    message = "A car is blocking my driveway"
    top = retriever.search(message)[0].type_id
    assert top == type_id_of(catalog, "Parking Enforcement")
    r = assistant(catalog, retriever, FakeModel(proposal(top)), gate=0.99).run(message)
    assert r.decision is Decision.ROUTE and r.department == "BTDT"


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


# --- Through the REAL LangChain/OpenAI wrapper, with fake HTTP responses (R1) ---
# These tests send requests through the installed ChatOpenAI and OpenAI SDK, so
# they see the exceptions the SDK really raises. httpx.MockTransport answers
# every request locally: no network, no API key.

VALID_PROPOSAL = {
    "type_id": "T082", "ambiguous": False, "missing_detail": None, "clarifying_question": None,
    "out_of_scope": False, "multiple_issues": False, "evidence_ids": ["T082"], "reason": "test",
}


def completion(content: str, finish_reason: str = "stop") -> httpx.Response:
    """A well-formed HTTP 200 chat-completion envelope."""
    return httpx.Response(200, json={
        "id": "test", "object": "chat.completion", "created": 0, "model": config.LLM_MODEL,
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })


TRUNCATED = lambda: completion('{"type_id": "T08', finish_reason="length")  # noqa: E731
VALID = lambda: completion(json.dumps(VALID_PROPOSAL))  # noqa: E731
SERVER_ERROR = lambda: httpx.Response(500, json={"error": {"message": "server error"}})  # noqa: E731
BAD_REQUEST = lambda: httpx.Response(400, json={"error": {"message": "bad request"}})  # noqa: E731


def mocked_live_model(tmp_path, responses):
    """A LiveModel whose ChatOpenAI answers from ``responses`` in order; counts HTTP calls."""
    from langchain_openai import ChatOpenAI

    queue = list(responses)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return queue.pop(0)()

    chat = ChatOpenAI(
        model=config.LLM_MODEL, api_key="test-key-not-real", max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return LiveModel(RecordingStore(tmp_path / "r.jsonl"), llm=chat), calls


@pytest.fixture
def no_backoff(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


def test_real_wrapper_truncated_then_valid_recovers(tmp_path):
    model, calls = mocked_live_model(tmp_path, [TRUNCATED, VALID])
    out = model.ask("classify", "sys", "user", ClassificationProposal)
    assert out.type_id == "T082" and calls["n"] == 2  # one malformed retry


def test_real_wrapper_repeated_truncation_fails_as_malformed(tmp_path):
    model, calls = mocked_live_model(tmp_path, [TRUNCATED, TRUNCATED])
    with pytest.raises(ClassifierFailure) as exc:
        model.ask("classify", "sys", "user", ClassificationProposal)
    assert exc.value.kind == "malformed" and calls["n"] == 1 + config.LLM_MAX_MALFORMED_RETRIES


def test_real_wrapper_server_error_is_retried_as_transient(tmp_path, no_backoff):
    model, calls = mocked_live_model(tmp_path, [SERVER_ERROR, VALID])
    assert model.ask("classify", "sys", "user", ClassificationProposal).type_id == "T082"
    assert calls["n"] == 2
    model, calls = mocked_live_model(tmp_path, [SERVER_ERROR] * (config.LLM_MAX_TRANSIENT_RETRIES + 1))
    with pytest.raises(ClassifierFailure) as exc:
        model.ask("classify", "sys", "other user", ClassificationProposal)
    assert exc.value.kind == "transient" and calls["n"] == config.LLM_MAX_TRANSIENT_RETRIES + 1


def test_real_wrapper_other_api_error_fails_without_retry(tmp_path):
    model, calls = mocked_live_model(tmp_path, [BAD_REQUEST])
    with pytest.raises(ClassifierFailure) as exc:
        model.ask("classify", "sys", "user", ClassificationProposal)
    assert exc.value.kind == "api_error" and calls["n"] == 1


def test_real_wrapper_refusal_fails_as_malformed(tmp_path):
    refusal = lambda: httpx.Response(200, json={  # noqa: E731
        "id": "test", "object": "chat.completion", "created": 0, "model": config.LLM_MODEL,
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": None, "refusal": "I can't help with that."}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })
    model, calls = mocked_live_model(tmp_path, [refusal, refusal])
    with pytest.raises(ClassifierFailure) as exc:
        model.ask("classify", "sys", "user", ClassificationProposal)
    assert exc.value.kind == "malformed" and calls["n"] == 2


def test_every_langchain_openai_error_class_is_handled():
    """Guard against escaping exceptions: each error class the installed
    langchain-openai can raise must fall into one of LiveModel's groups."""
    from langchain_openai.chat_models import base

    handled = llm.TRANSIENT_ERRORS + llm.MALFORMED_ERRORS + (openai.APIError,)
    for name in ("OpenAIAPIError", "OpenAIAuthenticationError", "OpenAIConnectionError", "OpenAIContextOverflowError",
                 "OpenAIAPIContextOverflowError", "OpenAIInvalidRequestError", "OpenAIModelNotFoundError",
                 "OpenAIPermissionDeniedError", "OpenAIRateLimitError", "OpenAIRefusalError", "OpenAITimeoutError"):
        assert issubclass(getattr(base, name), handled), name


# R1a: a complete reply (finish_reason "stop") whose content is not valid JSON,
# or not a valid ClassificationProposal, makes the SDK raise pydantic's
# ValidationError inside the model call. It must get the one malformed retry.
NOT_JSON = lambda: completion("not JSON")  # noqa: E731
SCHEMA_INVALID = lambda: completion("{}")  # noqa: E731


@pytest.mark.parametrize("bad", [NOT_JSON, SCHEMA_INVALID], ids=["invalid-json", "schema-invalid"])
def test_real_wrapper_invalid_reply_then_valid_recovers(tmp_path, bad):
    model, calls = mocked_live_model(tmp_path, [bad, VALID])
    out = model.ask("classify", "sys", "user", ClassificationProposal)
    assert out.type_id == "T082" and calls["n"] == 2


@pytest.mark.parametrize("bad", [NOT_JSON, SCHEMA_INVALID], ids=["invalid-json", "schema-invalid"])
def test_real_wrapper_repeated_invalid_reply_fails_as_malformed(tmp_path, bad, catalog, retriever):
    model, calls = mocked_live_model(tmp_path, [bad, bad])
    with pytest.raises(ClassifierFailure) as exc:
        model.ask("classify", "sys", "user", ClassificationProposal)
    assert exc.value.kind == "malformed" and calls["n"] == 1 + config.LLM_MAX_MALFORMED_RETRIES
    # The same through the whole intake graph: TRIAGE, after exactly two attempts.
    model, calls = mocked_live_model(tmp_path, [bad, bad])
    r = assistant(catalog, retriever, model).run("A car is blocking my driveway")
    assert r.decision is Decision.TRIAGE and "malformed" in r.triage_reason and calls["n"] == 2


def test_corrupt_recording_is_not_retried_as_a_fresh_reply(tmp_path, catalog, retriever):
    """A stored answer that no longer fits the schema is a data problem, not a
    model reply: no API call is made to 'retry' it, and the intake triages."""
    model, calls = mocked_live_model(tmp_path, [VALID])
    key = llm.recording_key("classify", "sys", "user", ClassificationProposal, model.settings)
    model.store.put(key, "classify", "user", {"type_id": 123}, None, settings=model.settings, schema=ClassificationProposal)
    with pytest.raises(ValidationError):
        model.ask("classify", "sys", "user", ClassificationProposal)
    assert calls["n"] == 0


def test_real_wrapper_truncation_ends_in_triage_not_a_crash(tmp_path, catalog, retriever):
    model, _ = mocked_live_model(tmp_path, [TRUNCATED, TRUNCATED])
    r = assistant(catalog, retriever, model).run("A car is blocking my driveway")
    assert r.decision is Decision.TRIAGE and "malformed" in r.triage_reason


# --- Recording identity and provenance (R4) ---


def test_recording_key_depends_on_generation_settings_and_schema(monkeypatch):
    from boston311.schemas import AliasBatch

    base = llm.recording_key("classify", "sys", "user", ClassificationProposal)
    assert llm.recording_key("classify", "sys", "user", ClassificationProposal) == base  # stable
    assert llm.recording_key("classify", "sys", "user", AliasBatch) != base  # schema matters
    monkeypatch.setattr(config, "LLM_SEED", config.LLM_SEED + 1)
    assert llm.recording_key("classify", "sys", "user", ClassificationProposal) != base
    monkeypatch.undo()
    monkeypatch.setattr(config, "LLM_REASONING_EFFORT", "high")
    assert llm.recording_key("classify", "sys", "user", ClassificationProposal) != base


def test_changed_seed_is_a_cache_miss(tmp_path, monkeypatch):
    good = {"parsed": proposal("T082"), "parsing_error": None, "raw": None}
    store = RecordingStore(tmp_path / "r.jsonl")
    first = FakeStructured([good])
    LiveModel(store, llm=FakeChat(first)).ask("classify", "sys", "user", ClassificationProposal)
    same = FakeStructured([good])
    LiveModel(store, llm=FakeChat(same)).ask("classify", "sys", "user", ClassificationProposal)
    assert (first.calls, same.calls) == (1, 0)  # identical settings replay without a call
    monkeypatch.setattr(config, "LLM_SEED", config.LLM_SEED + 1)
    changed = FakeStructured([good])
    LiveModel(store, llm=FakeChat(changed)).ask("classify", "sys", "user", ClassificationProposal)
    assert changed.calls == 1  # a changed seed must call the model again


def test_record_stores_the_settings_used(tmp_path):
    good = {"parsed": proposal("T082"), "parsing_error": None, "raw": None}
    store = RecordingStore(tmp_path / "r.jsonl")
    LiveModel(store, llm=FakeChat(FakeStructured([good]))).ask("classify", "sys", "user", ClassificationProposal)
    rec = json.loads((tmp_path / "r.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert rec["seed"] == config.LLM_SEED and rec["reasoning_effort"] == config.LLM_REASONING_EFFORT
    assert rec["model"] == config.LLM_MODEL and rec["schema"] == llm.schema_id(ClassificationProposal)


def test_committed_recordings_have_verifiable_provenance():
    """Every committed recording states the settings it was made with, and its
    key re-computes from those settings, the current prompt, and its schema."""
    from boston311.schemas import AliasBatch

    schemas = {"classify": ClassificationProposal, "aliases": AliasBatch}
    systems = {"classify": llm.read_prompt("classify_system"), "aliases": llm.read_prompt("aliases_system")}
    lines = llm.RECORDINGS_PATH.read_text(encoding="utf-8").splitlines()
    assert lines
    for line in lines:
        rec = json.loads(line)
        settings = {k: rec[k] for k in ("model", "reasoning_effort", "seed")}
        assert settings == llm.generation_settings(), rec["key"]
        assert rec["schema"] == llm.schema_id(schemas[rec["kind"]])
        assert rec["key"] == llm.recording_key(rec["kind"], systems[rec["kind"]], rec["input"], schemas[rec["kind"]])


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


def eval_item(item_id, message, answer=None, expected_decision="ROUTE"):
    """A minimal evaluation item in the data/eval/*.jsonl format."""
    return {
        "id": item_id, "category": "test", "message": message, "clarification_answer": answer,
        "expected_type_id": "T082", "acceptable_type_ids": ["T082"], "expected_department": "BTDT",
        "expected_queue": "BTDT_Parking Enforcement", "expected_decision": expected_decision,
        "acceptable_decisions": [expected_decision], "acceptable_departments": ["BTDT"],
        "acceptable_queues": ["BTDT_Parking Enforcement"],
    }


@pytest.mark.parametrize(
    "answers, clarification_answer, expected_count",
    [
        ([proposal("T082")], None, 0),  # routed directly: no question
        ([proposal(None, ambiguous=True)], None, 1),  # asked, never answered (final CLARIFY)
        ([proposal(None, ambiguous=True), proposal("T082")], "A car in my driveway", 1),  # asked, then ROUTE
        ([proposal(None, ambiguous=True), proposal(None, ambiguous=True)], "Not sure", 1),  # asked, then TRIAGE
    ],
)
def test_clarification_rate_counts_questions_asked(catalog, retriever, answers, clarification_answer, expected_count):
    a = assistant(catalog, retriever, FakeModel(*answers))
    df = evaluate.run_set(a, [eval_item("x1", "A car is blocking my driveway", clarification_answer)])
    m = {x.name: (x.correct, x.total) for x in evaluate.metrics(df)}
    assert m["clarification rate"] == (expected_count, 1)


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
