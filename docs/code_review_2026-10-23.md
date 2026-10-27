<!-- Independent repository review; no implementation fixes made. -->
# Code review — October 23, 2026

Reviewed commit: `d1d1c7d` (`Zero_Shot_Attempt_1`). The working tree was clean at the start. The authority for this review is `docs/architecture.md`, including the approved changes in `docs/decisions.md`; `docs/review_guide.md` supplied the verification map.

**Verdict:** the documented offline build reproduces, and I found no error in the published baseline staffing totals. There are **five P2 findings and one P3 finding** below. Fix these before treating the implementation as finished. The evidence supports a focused repair pass, not a replacement of the simulator or planner. P2 means a correctness issue to fix; P3 means a lower-priority completion gap. None of these findings is a demonstrated P0/P1 failure of the committed baseline run.

## Confirmed findings

### R1 — P2: Handle structured-output exceptions raised before the parser result exists

**Location:** `src/boston311/llm.py:189–203`, `LiveModel.ask`.

The malformed-output retry handles only a returned dictionary with `parsed=None` or `parsing_error`. The installed OpenAI SDK can instead raise `LengthFinishReasonError` while parsing a completion whose `finish_reason` is `length`. LangChain's `include_raw=True` does not catch that exception: the model invocation happens before its parser fallback. The exception passes through `classify` and the graph, which catch `ValidationError` and `ClassifierFailure`, respectively. A truncated response therefore aborts the resident interaction instead of receiving the specified one malformed-output retry and then TRIAGE.

**Reproduced:** with the installed `ChatOpenAI` and SDK, an `httpx.MockTransport` returned a valid HTTP 200 chat-completion envelope containing truncated JSON and `finish_reason="length"`. `LiveModel.ask` raised `LengthFinishReasonError` after **one** mock HTTP call. A graph-level probe with the same SDK exception also escaped `IntakeAssistant.run`. No real network request or API key was used.

**Fix:** translate the SDK's incomplete/invalid structured-response exceptions into the appropriate bounded retry/failure path. Keep exception handling specific; do not hide unrelated programming errors. Retain the existing distinction between transient and malformed retries.

**Acceptance:** exercise the real installed wrapper with mocked HTTP responses, including truncated-then-valid and repeated-truncated responses. The first must recover after two attempts; the second must produce TRIAGE after the allowed malformed retry. The current test only supplies a preconstructed parser-error dictionary and cannot catch this failure.

### R2 — P2: Apply the minimum sample to the statistic being displayed

**Location:** `src/boston311/catalog.py:279–289`, `historical_stats_text`.

The small-sample gate checks `with_target`, but the median is calculated over `closed`. These are different populations. An entry with many target-bearing requests and very few completions passes the gate and displays an inadequately supported completion-time statistic. This violates the stated small-sample behavior and the meaning of `MIN_STATS_SAMPLE` in configuration.

**Reproduced on the committed catalog:**

| Type | With target | Closed | Median displayed |
|---|---:|---:|---:|
| Parking Meter Repairs | 75 | 7 | 0.7 days |
| Pavement Marking Maintenance | 64 | 14 | 420.5 days |
| Bicycle Issues | 100 | 25 | 2.9 days |

`MIN_STATS_SAMPLE` is 30. The first two are approved-for-demo routes and appear in the current test messages. For Parking Meter Repairs, the response combines 9% on time with a 0.7-day median without explaining that only seven requests contribute to that median.

**Fix:** gate the on-time statistic on its target-bearing sample and the median on its closed-request sample, or suppress the whole statistical summary when either required sample is too small. Label a reported median as applying to closed requests.

**Acceptance:** with 75 target-bearing requests and seven closures, the median is unavailable. Cover both sides of the 30-closure boundary and the case where one statistic has enough observations but the other does not.

### R3 — P2: Reject plans that violate the terminal rules before scoring them

**Location:** `src/boston311/staffing.py:115–127`, `DepartmentPlan.__post_init__`; also the scoring/reconciliation boundary.

The planner respects the hiring and release cutoffs, but the plan contract checks only month coverage, negative quantities, seasonal eligibility, and minimum workforce. A caller can construct and score a November hire or September release. The architecture explicitly says the terminal rules apply to **every plan**, not just plans emitted by the heuristic.

**Reproduced:** a Public Works plan with one September release notice and one November hire order was accepted. The crew reduction took effect in October and the hire in December. Scoring it on the actual base evaluation workload succeeded, and `reconciliation_failures` returned `[]`. The reported verification can therefore certify a prohibited plan. This does not invalidate the current heuristic plan; it affects imported, edited, or future comparison plans.

**Fix:** enforce the configured terminal restrictions at a common plan-validation boundary before scoring, with `StaffingInputError` naming the decision field. Since plans are mutable, ensure validation cannot be bypassed by editing decisions after construction. Keep any intentional experimental relaxation explicit.

**Acceptance:** direct plans with November/December hires or September–December release notices are rejected, including a plan mutated after creation. October hires and August notices remain valid. Retain the existing valid-plan year-end accounting checks.

### R4 — P2: Include model-generation settings in recording identity and provenance

**Location:** `src/boston311/llm.py:68–72`, `recording_key`, and `RecordingStore.put`.

The recording key includes model name, versions, and prompt text, but omits `LLM_SEED` and `LLM_REASONING_EFFORT`, both of which are passed to the model. Changing either setting leaves the key unchanged. Because live mode checks the recording first, the changed configuration silently returns the old answer without invoking the model. Meanwhile, the run manifest records the new seed and reasoning effort as if they described that answer. The recordings themselves do not store those settings to resolve the discrepancy.

**Reproduced:** computing a classification key, changing the seed and reasoning effort, and recomputing it returned the same key. The cache-hit branch in `LiveModel.ask` returns immediately for that key.

**Fix:** fingerprint and record the generation settings used for each answer. Consider including the structured-output schema identity as well. Provide a deliberate compatibility/migration strategy for the committed recordings; merely changing the key algorithm would otherwise break every existing offline example.

**Acceptance:** identical settings replay without a call; changing seed or reasoning effort causes a cache miss; per-record provenance matches the settings used to generate the output. All committed offline demos must still work after an explicit migration or refresh, with no invented provenance.

### R5 — P2: Count a clarification when the assistant asks, even without an answer

**Location:** `src/boston311/evaluate.py:64`; related result construction in `src/boston311/agent/graph.py:115–124`.

`run_set` marks an item clarified only when `clarifications_used > 0`. That count is incremented when a resident answers. If the graph interrupts and the evaluation item has no scripted answer, `IntakeAssistant.run` returns CLARIFY with the default count of zero. The clarification-rate metric consequently excludes that question. A prompt or gate regression that asks unnecessary questions on clear messages can therefore disappear from this metric.

**Reproduced:** one evaluation item whose model asks for detail, with no supplied answer, produced `decision=CLARIFY`, `clarified=False`, and **clarification rate 0/1 (0%)**.

**Fix:** distinguish questions asked from answers received, or count both a final CLARIFY decision and completed clarification rounds in this metric. Preserve the one-question limit.

**Acceptance:** unanswered CLARIFY, clarified-then-ROUTE, and clarified-then-TRIAGE each count as one clarification; a direct route counts as zero. The current test-set rate of 8/40 need not change because its observed clarification cases have scripted answers.

### R6 — P3: Persist the notebook's run manifest

**Location:** `demo.ipynb:3325`, code cell under “9. Run manifest”.

The cell calls `build_manifest(MODE, outputs=[])` and prints a subset of its fields, but never calls `write_manifest`. Running the README's primary notebook workflow therefore creates no JSON manifest. The complete input hashes and environment metadata remain only in kernel memory and are not preserved in the displayed notebook output. This falls short of architecture section 5.9's one-JSON-manifest-per-run requirement. The CLI workflow does persist its manifest correctly.

**Reproduced:** the fresh-kernel notebook completed all 18 code cells with zero error outputs. Inspection of its manifest cell confirms only construction and abbreviated printing; no manifest write occurs anywhere in the notebook.

**Fix:** persist the complete manifest and display its path. Identify the notebook/run artifact in the output metadata where appropriate, without creating a self-hashing dependency.

**Acceptance:** notebook execution in offline mode creates one readable JSON manifest with the input hashes, settings, environment, and mode for that execution. No API key or network should be needed.

## Verification and scope

- Read the architecture, decisions, review guide, implementation modules, build/evaluation scripts, notebook, report, and tests.
- `.venv\Scripts\python.exe -m pytest -q`: **105 passed in 29.03 seconds**.
- `.venv\Scripts\python.exe scripts/run_all.py`: completed, including reconciliation for all eight plan/scenario combinations. Every tracked table, figure, and log remained byte-identical. Only `outputs/manifests/run_20261023T132148Z.json` was added by that run.
- Independently rebuilt all **10 processed tables** in memory from the locally cached 2023/2024 raw CSVs and compared them to the committed tables: all matched. This did not download data or overwrite inputs.
- Executed `demo.ipynb` with nbconvert in a fresh kernel, writing `C:/Users/baldw/AppData/Local/Temp/review_demo.ipynb`: **18/18 code cells executed; zero error outputs**. The original notebook was not changed. Kernel startup stalled in the sandbox; execution outside it succeeded. That environment restriction is not counted as a project defect.
- Reproduced the findings with isolated probes. Model-error verification used mocked responses, not a paid live classification.
- No implementation, test, configuration, catalog, evaluation, or specification changes were made. This review document and the CLI verification manifest are the repository additions.

The published base comparison reproduced: heuristic **$16,394,440**, **89.5035% on time**, **1,441 open**; baseline **$19,474,180**, **22.4108% on time**, **27,579 open**. Inspection found the FIFO/deadline boundaries, paid training, seasonal search, projection ordering, and scenario coupling consistent with the approved specification. Reproduction and inspection are evidence, not proof that all possible defects have been exhausted.

## Follow-up boundaries

The provisional approvals, unreviewed evaluation set, synthetic demand, single evaluation seed, and lack of reactive sensitivity planning are disclosed limitations or approved scope choices. I have not relabeled them as implementation bugs. Human review of mappings/aliases/messages and the report/video/logistics still remains as documented. A live API smoke test and a genuinely clean dependency installation were not performed in this review.

For a single repair pass, address R1–R6, add the targeted regression checks above, preserve the frozen specification, rerun the suite and offline CLI/notebook, and explain any changed outputs. Reuse the current tests as regression checks, but do not rely exclusively on fixtures that bypass the actual SDK behavior. A second independent review should then inspect the repair diff and rerun the new counterexamples. No findings have been sent to another chat or author by this review.
