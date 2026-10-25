<!-- [AI-authored: Codex] Independent follow-up review; no implementation fixes made. -->
# Code review — October 23, 2026, round 2

Reviewed commit: `01630ca7b870cdeb5239a30a486fb1f76dca0897`. The working tree was clean at the start. This review checks the repair changes since the original review of `d1d1c7d`, against the unchanged architecture and the acceptance criteria in [the first review](code_review_2026-10-23.md).

**Verdict: R2–R6 are closed. R1 is partially fixed, with one remaining P2 retry defect.** The original truncation crash is fixed. No other material regression was identified in the repair changes. Published outputs still reproduce exactly.

## Remaining finding

### R1a — P2: Retry validation errors raised by the SDK during structured-response parsing

**Location:** `src/boston311/llm.py:77–81` (`MALFORMED_ERRORS`), used at lines 277–294 in `LiveModel.ask`.

The installed SDK raises a Pydantic `ValidationError` when a completion finishes with `finish_reason="stop"` but its content is invalid JSON or does not satisfy the requested schema. This happens inside `structured.invoke`, before LangChain can return its `parsed` / `parsing_error` dictionary. `ValidationError` is absent from the malformed-error group, so the exception bypasses the retry loop.

The outer `classify` function catches it and returns a malformed failure, so the resident interaction now ends safely in TRIAGE. However, it does so after the **first** attempt, contrary to spec section 6's one malformed-output retry. A recoverable error causes an unnecessary handoff even when the next response would be valid. Direct callers of `LiveModel.ask` receive the raw `ValidationError` rather than the documented `ClassifierFailure`.

**Reproduced with the real installed ChatOpenAI/OpenAI wrapper and `httpx.MockTransport`:**

| First response content | Next queued response | Direct `ask` outcome | Graph outcome | HTTP attempts |
|---|---|---|---|---:|
| `not JSON` | Valid `ClassificationProposal` | `ValidationError` | TRIAGE | 1 |
| `{}` | Valid `ClassificationProposal` | `ValidationError` | TRIAGE | 1 |

Both first responses used a normal HTTP 200 chat-completion envelope with `finish_reason="stop"`. The valid second response was never requested. These were local simulated responses; no live service call was made.

The existing regression tests cover `finish_reason="length"`, refusal, HTTP errors, and a fake preconstructed parser-error dictionary. They do not cover Pydantic validation failing inside the SDK. The test enumerating LangChain-specific exception classes also cannot establish coverage of exceptions raised by Pydantic.

**Requested fix:** handle SDK response-validation failures inside the same bounded malformed-output retry loop. Keep the catch scoped to model invocation, preserving visibility of unrelated programming errors. Do not retry a corrupt cached answer as if it were a fresh API response.

**Acceptance checks:**

1. Through the real wrapper with mocked HTTP, invalid JSON followed by a valid response succeeds after two attempts.
2. A schema-invalid object followed by a valid response also succeeds after two attempts.
3. Repeated invalid responses produce `ClassifierFailure(kind="malformed")` after exactly two attempts, and the intake graph returns TRIAGE.
4. Existing truncation, refusal, transient-error, and offline-replay tests continue to pass.

Minimal reproduction using the existing test helper, from the repository root:

```python
import runpy
import tempfile
from pathlib import Path
from boston311.schemas import ClassificationProposal

h = runpy.run_path("tests/test_intake.py")
with tempfile.TemporaryDirectory() as directory:
    model, calls = h["mocked_live_model"](
        Path(directory),
        [lambda: h["completion"]("{}"), h["VALID"]],
    )
    try:
        model.ask("classify", "sys", "user", ClassificationProposal)
    except Exception as error:
        print(type(error).__name__, calls["n"])
# Current result: ValidationError 1
```

## Disposition of the original findings

| Finding | Status | Evidence |
|---|---|---|
| R1: SDK exceptions escape malformed handling | Partially fixed | Truncated responses now retry and reach TRIAGE; SDK-raised validation errors still skip the retry, as above. |
| R2: wrong sample minimum for median | Closed | Each statistic checks its own denominator, states its sample size, and labels the median as applying to closed requests. Boundary tests cover 29 versus 30 closures. |
| R3: terminal restrictions bypassed by manual plans | Closed | Shared validation rejects late orders/notices; department plans use frozen dataclasses and tuple fields; scoring revalidates, including a deliberately bypassed constructor. |
| R4: incomplete recording identity/provenance | Closed | Model, seed, effort, and schema identity participate in the key and are stored. All 83 migrated records preserve the original inputs, outputs, and usage; both old and new keys independently verify. Git history is consistent with the documented settings/schema migration. |
| R5: unanswered clarification omitted from metric | Closed | `questions_asked` is separate from answers received. Tests cover direct routes, unanswered questions, clarified routes, and clarified triage. |
| R6: notebook manifest not persisted | Closed | Fresh notebook execution saved one complete JSON manifest with its mode, input hashes, environment, and run identity. |

## Verification

- Full suite: **136 passed in 30.00 seconds**.
- Offline `scripts/run_all.py`: completed all eight plan/scenario reconciliations. SHA-256 comparison before and after found **every tracked output byte-identical**. CLI manifest: `outputs/manifests/run_20261023T143543Z.json`.
- Fresh-kernel offline notebook: **18/18 code cells executed, zero error outputs**. It created exactly one new complete notebook manifest: `outputs/manifests/run_20261023T143619Z.json`.
- Executed notebook copy: `C:/Users/baldw/AppData/Local/Temp/boston311-review2-x5qnx_ft/review_demo.ipynb`. The tracked notebook was not edited.
- Independently compared all 83 recordings with their pre-repair versions and recomputed both key formats. Original answers were preserved; the migration did not substitute new answers to make tests pass.
- Read the repair diffs, new tests, migration script, updated documentation, and affected call paths. The frozen architecture is unchanged.

The default sandbox blocked the SDK's inherited Windows SSL logging path during test collection. Tests, mocked-SDK probes, and end-to-end runs succeeded outside the sandbox. This is recorded as an execution-environment limitation, not an additional project finding. No paid API calls or fresh dependency installation were performed.

No implementation, tests, configuration, recordings, or specification were changed during this review. This document is the only new tracked-candidate file; verification manifests are gitignored. No review findings were sent to another chat. One small follow-up repair for R1a is warranted; a new full implementation attempt is not.
