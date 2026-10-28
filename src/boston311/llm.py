"""Language-model access through LangChain, with live and offline modes.

Spec sections 3, 4.7, 4.9, and 5.

Live mode makes a fresh OpenAI request (model ``config.LLM_MODEL``) through
LangChain's ``ChatOpenAI`` every time, even for an input that was recorded
before. It forces the model to answer in the exact shape of a Pydantic class
("structured output") and appends every successful answer to
``data/demo/recordings.jsonl``. Live results may differ between runs.

Offline mode makes no network calls and needs no API key. It replays the
latest recorded answer for each input. A message that was never recorded
cannot be classified offline; the assistant then sends it to TRIAGE and says
why. Recordings live in that file, so restarting the kernel does not erase
them.

Recording keys and provenance
-----------------------------
Each answer is stored under a key computed from everything that determines
it:
* the **generation settings**: model name, reasoning effort, and seed;
* the prompt version and catalog version;
* the **response schema** the model was forced to follow (its name plus a
  hash of its JSON schema);
* the exact text sent to the model.

If any of these change, old recordings no longer match, so offline mode
reports "no recording" and a stale answer can never be replayed silently. Each recording also stores those settings
next to the answer, so its provenance can be checked without trusting the
current configuration.

Failure handling (spec 5)
-------------------------
* Missing API key in live mode: :class:`MissingAPIKeyError` with a clear
  message that points to offline mode.
* Timeouts, rate limits, connection errors, server errors (HTTP 5xx):
  retried up to ``config.LLM_MAX_TRANSIENT_RETRIES`` times, then
  :class:`ClassifierFailure` ("transient").
* Malformed structured output: retried ``config.LLM_MAX_MALFORMED_RETRIES``
  time, then :class:`ClassifierFailure` ("malformed"). This covers a reply the
  parser rejects *and* the exceptions raised inside the model call before any
  parser result exists: a truncated reply, the content filter, a refusal, or
  a complete reply that is not valid JSON for the schema (pydantic
  ``ValidationError``). A corrupt *recorded* answer is not retried.
* Any other API error (bad request, bad key, unknown model, context too
  long): no retry, :class:`ClassifierFailure` ("api_error").
The intake agent turns every :class:`ClassifierFailure` into a TRIAGE.
Programming errors are deliberately *not* caught, so they stay visible.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Protocol, TypeVar

import openai  # the SDK's exception classes (LangChain's errors subclass them)
from dotenv import load_dotenv
from langchain_openai.chat_models.base import OpenAIRefusalError
from pydantic import BaseModel, ValidationError

from boston311 import config
from boston311.schemas import ClassificationProposal

RECORDINGS_PATH = config.DEMO_DIR / "recordings.jsonl"
T = TypeVar("T", bound=BaseModel)

# Exceptions from the model API, grouped by how LiveModel.ask handles them.
# LangChain wraps SDK errors in its own classes (for example OpenAIAPIError for
# an HTTP 500), but those subclass these OpenAI SDK classes, so catching the SDK
# class catches both. Checked against langchain-openai 1.7.2 / openai 3.37.0.
TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.InternalServerError,  # HTTP 5xx
)
MALFORMED_ERRORS: tuple[type[Exception], ...] = (
    openai.LengthFinishReasonError,  # reply cut off at the length limit: truncated JSON
    openai.ContentFilterFinishReasonError,  # reply stopped by the content filter
    OpenAIRefusalError,  # the model refused to answer in the schema
    # A complete reply whose content is not JSON, or not a valid instance of
    # the schema: the SDK validates it with pydantic inside the call and raises
    # this before LangChain can return a parser result (review finding R1a).
    # It is caught ONLY around the model call (see LiveModel.ask). A corrupt
    # *recorded* answer is only ever read offline (OfflineModel.ask), where it
    # raises without a retry.
    ValidationError,
)
# Anything else from the API (400 bad request, 401 bad key, 404 unknown model,
# context too long, ...) is caught as openai.APIError: retrying cannot help.


class MissingAPIKeyError(RuntimeError):
    """Live mode was requested but no OpenAI API key is configured."""


class ClassifierFailure(RuntimeError):
    """The model could not produce a usable answer. ``kind`` says why."""

    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind  # "transient", "malformed", "api_error", "no_recording"
        super().__init__(f"{kind}: {detail}" if detail else kind)


def read_prompt(name: str) -> str:
    """Load a prompt template from ``prompts/<name>.txt``."""
    return (config.PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


def generation_settings() -> dict:
    """The settings passed to the model with every request (from config)."""
    return {"model": config.LLM_MODEL, "reasoning_effort": config.LLM_REASONING_EFFORT, "seed": config.LLM_SEED}


def schema_id(schema: type[BaseModel]) -> str:
    """Identify a structured-output schema: class name + short hash of its JSON schema.

    The JSON schema is what is actually sent to the model, including field
    descriptions (and class docstrings), so editing any of them changes this id.
    """
    text = json.dumps(schema.model_json_schema(), sort_keys=True, ensure_ascii=False)
    return f"{schema.__name__}:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


def prompt_version(kind: str) -> str:
    return config.PROMPT_VERSION if kind == "classify" else config.ALIAS_PROMPT_VERSION


def recording_key(kind: str, system: str, user: str, schema: type[BaseModel], settings: dict | None = None) -> str:
    """A stable fingerprint of one model request (see module docstring).

    ``settings`` defaults to the current :func:`generation_settings`.
    """
    settings = generation_settings() if settings is None else settings
    blob = json.dumps(
        {
            **settings,
            "prompt_version": prompt_version(kind),
            "catalog_version": config.CATALOG_VERSION,
            "kind": kind,
            "schema": schema_id(schema),
            "system": system,
            "user": user,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class RecordingStore:
    """Append-only store of recorded model answers (one JSON object per line)."""

    def __init__(self, path=RECORDINGS_PATH):
        self.path = path
        self._cache: dict[str, dict] | None = None

    def _load(self) -> dict[str, dict]:
        if self._cache is None:
            self._cache = {}
            if self.path.exists():
                for line in self.path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        rec = json.loads(line)
                        self._cache[rec["key"]] = rec
        return self._cache

    def get(self, key: str) -> dict | None:
        return self._load().get(key)

    def put(
        self, key: str, kind: str, user: str, output: dict, usage: dict | None, *, settings: dict, schema: type[BaseModel]
    ) -> None:
        """Append one answer, with the settings and schema it was generated with."""
        rec = {
            "key": key,
            "kind": kind,
            **settings,  # model, reasoning_effort, seed actually sent to the model
            "schema": schema_id(schema),
            "prompt_version": prompt_version(kind),
            "catalog_version": config.CATALOG_VERSION,
            "input": user,
            "output": output,
            "usage": usage,
        }
        self._load()[key] = rec
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def prune(self, systems: dict[str, tuple[str, type[BaseModel]]]) -> tuple[int, int]:
        """Drop recordings that can no longer be replayed.

        A recording stays only if its key still equals the key computed with
        the *current* settings, versions, system prompt, and schema
        (``systems`` maps kind -> (system prompt text, schema class)).
        Returns (kept, dropped).
        """
        records = self._load()
        keep = {}
        for k, r in records.items():
            if r["kind"] not in systems:
                continue
            system, schema = systems[r["kind"]]
            if recording_key(r["kind"], system, r["input"], schema) == k:
                keep[k] = r
        self._cache = keep
        with self.path.open("w", encoding="utf-8", newline="\n") as fh:
            for r in keep.values():
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        return len(keep), len(records) - len(keep)


class StructuredModel(Protocol):
    """Anything that can answer a (system, user) prompt as a Pydantic object."""

    mode: str

    def ask(self, kind: str, system: str, user: str, schema: type[T]) -> T: ...


@dataclass
class OfflineModel:
    """Replays recorded answers; never touches the network."""

    store: RecordingStore
    mode: str = "offline"

    def ask(self, kind: str, system: str, user: str, schema: type[T]) -> T:
        # The key uses the configured settings: offline mode replays only
        # answers that were generated with exactly these settings.
        rec = self.store.get(recording_key(kind, system, user, schema))
        if rec is None:
            raise ClassifierFailure("no_recording", "offline mode has no recorded answer for this exact input")
        return schema.model_validate(rec["output"])


class LiveModel:
    """Calls the OpenAI model through LangChain for every request and records each answer."""

    mode = "live"

    def __init__(self, store: RecordingStore, *, llm=None):
        self.store = store
        # Capture the settings once, so the model client, the recording key,
        # and the stored provenance always describe the same request even if
        # the configuration is changed while this object exists.
        self.settings = generation_settings()
        if llm is None:
            load_dotenv(config.REPO_ROOT / ".env")
            if not os.environ.get("OPENAI_API_KEY"):
                raise MissingAPIKeyError(
                    "Live mode needs OPENAI_API_KEY. Put it in a .env file at the repository root "
                    "(see .env.example), or run in offline mode, which replays recorded answers."
                )
            from langchain_openai import ChatOpenAI  # imported here so offline mode never needs it

            llm = ChatOpenAI(
                model=self.settings["model"],
                reasoning_effort=self.settings["reasoning_effort"],
                seed=self.settings["seed"],
                timeout=config.LLM_TIMEOUT_SECONDS,
                max_retries=0,  # we do our own bounded retries below
            )
        self.llm = llm

    def ask(self, kind: str, system: str, user: str, schema: type[T]) -> T:
        # Live mode always makes a fresh request, even if this exact input was
        # recorded before; the answer is then recorded under the same key, and
        # offline mode replays the latest recording for a key.
        key = recording_key(kind, system, user, schema, self.settings)

        # json_schema + strict: OpenAI guarantees the reply matches the schema.
        structured = self.llm.with_structured_output(schema, method="json_schema", strict=True, include_raw=True)
        messages = [("system", system), ("human", user)]
        transient_left, malformed_left = config.LLM_MAX_TRANSIENT_RETRIES, config.LLM_MAX_MALFORMED_RETRIES
        while True:
            # Every failure the model API can produce ends in a ClassifierFailure
            # (which the agent turns into TRIAGE), sorted into three kinds. Only
            # the specific SDK exception classes are caught, so a genuine
            # programming error still surfaces instead of being hidden.
            try:
                out = structured.invoke(messages)
            except TRANSIENT_ERRORS as exc:
                # Timeouts, rate limits, lost connections, and server errors
                # (HTTP 5xx): wait and retry a bounded number of times.
                if transient_left == 0:
                    raise ClassifierFailure("transient", type(exc).__name__) from exc
                transient_left -= 1
                time.sleep(2 * (config.LLM_MAX_TRANSIENT_RETRIES - transient_left))  # 2 s, then 4 s
                continue
            except MALFORMED_ERRORS as exc:
                # The SDK raises these *instead of* returning a parser result,
                # e.g. when the reply was cut off at the length limit (truncated
                # JSON). They are malformed output: one retry, then failure.
                if malformed_left == 0:
                    raise ClassifierFailure("malformed", type(exc).__name__) from exc
                malformed_left -= 1
                continue
            except openai.APIError as exc:
                # Any other API error (400 bad request, 401 bad key, 404
                # unknown model, context too long, ...): retrying cannot help,
                # so fail at once.
                status = getattr(exc, "status_code", None)
                raise ClassifierFailure("api_error", type(exc).__name__ + (f" (HTTP {status})" if status else "")) from exc
            parsed = out.get("parsed")
            if parsed is None or out.get("parsing_error") is not None:
                if malformed_left == 0:
                    raise ClassifierFailure("malformed", str(out.get("parsing_error")))
                malformed_left -= 1
                continue
            usage = getattr(out.get("raw"), "usage_metadata", None)
            self.store.put(
                key, kind, user, parsed.model_dump(mode="json"), dict(usage) if usage else None,
                settings=self.settings, schema=schema,
            )
            return parsed


def get_model(mode: str, store: RecordingStore | None = None) -> StructuredModel:
    """Return the model for a demo mode ("live" or "offline")."""
    store = store or RecordingStore()
    if mode == "offline":
        return OfflineModel(store)
    if mode == "live":
        return LiveModel(store)
    raise ValueError(f"mode must be one of {config.MODES}, got {mode!r}")


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def format_candidates(candidates: list[dict]) -> str:
    """One line per candidate for the classification prompt."""
    lines = []
    for c in candidates:
        aliases = "; ".join(c.get("aliases", [])) or "-"
        lines.append(f"{c['type_id']} | {c['type']} | {c['department_name']} | {c['description'] or '-'} | {aliases}")
    return "\n".join(lines)


def classify(model: StructuredModel, message: str, clarification: str | None, candidates: list[dict]) -> ClassificationProposal:
    """Ask the model for a :class:`ClassificationProposal`.

    Raises :class:`ClassifierFailure` (or ValidationError, wrapped) when no
    usable answer can be obtained; the agent turns that into TRIAGE.
    """
    system = read_prompt("classify_system")
    user = read_prompt("classify_user").format(
        message=message, clarification=clarification or "(none)", candidates=format_candidates(candidates)
    )
    try:
        return model.ask("classify", system, user, ClassificationProposal)
    except ValidationError as exc:  # a recorded answer that no longer fits the schema
        raise ClassifierFailure("malformed", str(exc)) from exc
