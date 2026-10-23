"""Language-model access through LangChain, with live and offline modes.

Spec sections 4, 5.7, 5.9, and 6.

Live mode calls OpenAI (model ``config.LLM_MODEL``) through LangChain's
``ChatOpenAI``. It forces the model to answer in the exact shape of a
Pydantic class ("structured output") and records every answer to
``data/demo/recordings.jsonl``.

Offline mode makes no network calls and needs no API key. It replays the
recorded answers. A message that was never recorded cannot be classified
offline; the assistant then sends it to TRIAGE and says why.

Recording keys
--------------
Each answer is stored under a key computed from everything that determines
it: the model name, the prompt version, the catalog version, and the exact
text sent to the model. If any of these change, old recordings no longer
match, so offline mode can never silently replay a stale answer.

Failure handling (spec 6)
-------------------------
* Missing API key in live mode: :class:`MissingAPIKeyError` with a clear
  message that points to offline mode.
* Timeouts, rate limits, connection errors: retried up to
  ``config.LLM_MAX_TRANSIENT_RETRIES`` times, then :class:`ClassifierFailure`.
* Malformed structured output: retried ``config.LLM_MAX_MALFORMED_RETRIES``
  time, then :class:`ClassifierFailure`.
The intake agent turns every :class:`ClassifierFailure` into a TRIAGE.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Protocol, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from boston311 import config
from boston311.schemas import ClassificationProposal

RECORDINGS_PATH = config.DEMO_DIR / "recordings.jsonl"
T = TypeVar("T", bound=BaseModel)


class MissingAPIKeyError(RuntimeError):
    """Live mode was requested but no OpenAI API key is configured."""


class ClassifierFailure(RuntimeError):
    """The model could not produce a usable answer. ``kind`` says why."""

    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind  # "transient", "malformed", "no_recording"
        super().__init__(f"{kind}: {detail}" if detail else kind)


def read_prompt(name: str) -> str:
    """Load a prompt template from ``prompts/<name>.txt``."""
    return (config.PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


def recording_key(kind: str, system: str, user: str) -> str:
    """A stable fingerprint of one model request (see module docstring)."""
    version = config.PROMPT_VERSION if kind == "classify" else config.ALIAS_PROMPT_VERSION
    blob = json.dumps([config.LLM_MODEL, version, config.CATALOG_VERSION, kind, system, user], ensure_ascii=False)
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

    def put(self, key: str, kind: str, user: str, output: dict, usage: dict | None) -> None:
        rec = {"key": key, "kind": kind, "model": config.LLM_MODEL, "input": user, "output": output, "usage": usage}
        self._load()[key] = rec
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


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
        rec = self.store.get(recording_key(kind, system, user))
        if rec is None:
            raise ClassifierFailure("no_recording", "offline mode has no recorded answer for this exact input")
        return schema.model_validate(rec["output"])


class LiveModel:
    """Calls the OpenAI model through LangChain and records every answer."""

    mode = "live"

    def __init__(self, store: RecordingStore, *, llm=None):
        self.store = store
        if llm is None:
            load_dotenv(config.REPO_ROOT / ".env")
            if not os.environ.get("OPENAI_API_KEY"):
                raise MissingAPIKeyError(
                    "Live mode needs OPENAI_API_KEY. Put it in a .env file at the repository root "
                    "(see .env.example), or run in offline mode, which replays recorded answers."
                )
            from langchain_openai import ChatOpenAI  # imported here so offline mode never needs it

            llm = ChatOpenAI(
                model=config.LLM_MODEL,
                reasoning_effort=config.LLM_REASONING_EFFORT,
                seed=config.LLM_SEED,
                timeout=config.LLM_TIMEOUT_SECONDS,
                max_retries=0,  # we do our own bounded retries below
            )
        self.llm = llm

    def ask(self, kind: str, system: str, user: str, schema: type[T]) -> T:
        # Reuse a recording if this exact request was already answered, so
        # rerunning live mode does not pay twice for the same question.
        key = recording_key(kind, system, user)
        rec = self.store.get(key)
        if rec is not None:
            return schema.model_validate(rec["output"])

        import openai  # the SDK's exception classes

        # json_schema + strict: OpenAI guarantees the reply matches the schema.
        structured = self.llm.with_structured_output(schema, method="json_schema", strict=True, include_raw=True)
        messages = [("system", system), ("human", user)]
        transient_left, malformed_left = config.LLM_MAX_TRANSIENT_RETRIES, config.LLM_MAX_MALFORMED_RETRIES
        while True:
            try:
                out = structured.invoke(messages)
            except (openai.APITimeoutError, openai.RateLimitError, openai.APIConnectionError) as exc:
                if transient_left == 0:
                    raise ClassifierFailure("transient", type(exc).__name__) from exc
                transient_left -= 1
                time.sleep(2 * (config.LLM_MAX_TRANSIENT_RETRIES - transient_left))  # 2 s, then 4 s
                continue
            parsed = out.get("parsed")
            if parsed is None or out.get("parsing_error") is not None:
                if malformed_left == 0:
                    raise ClassifierFailure("malformed", str(out.get("parsing_error")))
                malformed_left -= 1
                continue
            usage = getattr(out.get("raw"), "usage_metadata", None)
            self.store.put(key, kind, user, parsed.model_dump(mode="json"), dict(usage) if usage else None)
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
