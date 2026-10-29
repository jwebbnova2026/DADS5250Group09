<!-- Reviewer entry point, written 2026-10-23, updated 2026-10-28. -->
# Review guide

This guide is the starting point for reviewing the finished prototype. It tells you what to read, how to check that the results reproduce, where each requirement is implemented and tested, what differs from the original spec, and where bugs are most likely to hide.

**Ground rules for the review**

- `docs/architecture.md` is the authority. It is the frozen spec v5.1, plus the changes the team approved during the build. Its section 11 lists those changes with their evidence and dates, the data audit, the implementation choices made where the spec was silent, the test-set disclosure, and the catalog review outcome.
- `demo.ipynb` is the analysis deliverable: every result, with its interpretation and limitations.
- Anything this guide summarizes is stated in full in one of those two files. If this guide disagrees with them, they win.
- Code locations are given as file and function names; search for the function. This guide was last updated after the catalog review, the overlapping-types and agreement rules, and the documentation consolidation (2026-10-28).

## 1. Read in this order

1. [architecture.md](architecture.md), sections 2, 4.3, 4.4, 4.6, 4.7 and 8. These sections contain the GIVEN rules, the simulator, the policy, routing, the agent, and the acceptance checks.
2. [architecture.md](architecture.md), section 11: the approved changes, data audit, implementation decisions, test-set disclosure, and catalog review.
3. [demo.ipynb](../demo.ipynb): the executed analysis, from the problem statement to the limitations.
4. The code, in dependency order:
   1. `config.py`
   2. `data.py`
   3. `forecast.py`
   4. `simulate.py`
   5. `workload.py`
   6. `staffing.py`
   7. `catalog.py`
   8. `retrieval.py`
   9. `llm.py`
   10. `agent/`
   11. `evaluate.py`
   12. `equity.py`
   13. `manifest.py`

   Every module opens with a docstring explaining its role. The comments are written for readers new to the code.

## 2. Verify it reproduces

Everything below runs offline, with no API key and no network, from the repository root inside the `.venv` described in the README.

```bash
python -m pytest -q
```

Expected: `148 passed` (about one minute).

```bash
python scripts/run_all.py
```

This rebuilds every table and figure in `outputs/` and writes a new run manifest. It raises an error if any reconciliation check fails. Then compare against the committed outputs:

```bash
git status --short outputs
```

Expected: no changes, because every CSV and figure is byte-identical to the committed ones. The run also writes a new manifest `outputs/manifests/run_<timestamp>.json`, which git ignores. The committed `outputs/manifests/reference_run_all.json` is the manifest of the run that produced the committed outputs.

```bash
python -m nbconvert --to notebook --execute --inplace demo.ipynb
```

Expected: no errors, and the notebook saves its own manifest under `outputs/manifests/` (gitignored). The committed notebook is already executed offline, so a re-execution should change only timestamps and the manifest cell's output; run `git checkout -- demo.ipynb` to discard it.

Headline numbers you should see (`outputs/scenario_summary.csv` and `outputs/intake_metrics.csv`):

| Check | Expected value |
|---|---|
| Frozen plan, base scenario: total cost / on-time / open Dec 31 | $16,394,440 / 89.5% / 1,441 |
| Baseline (January crews), base scenario | $19,474,180 / 22.4% / 27,579 |
| Parks under the frozen plan | $1,862,860 / 95.4% on time / 42 seasonal crew-months |
| Intake test set (40 items) | decision 40/40, type 33/34, department 29/29, auto-route precision 28/29 |
| Intake dev set (18 items) | decision 18/18, type 15/15, precision 12/12 |

Optional checks that need network or a key:

- `python scripts/build_data.py` downloads the two source files (about 370 MB) through the CKAN API and rebuilds `data/processed/`. The tables should come out identical while the city's files are unchanged; the manifest records their MD5 checksums.
- Setting `MODE = "live"` in the notebook needs `OPENAI_API_KEY` in `.env`. Live mode makes fresh OpenAI requests and records successful responses, so live results may differ between runs. It does not reuse recordings; only offline mode replays them.

## 3. Requirement → code → test map

Code paths are under `src/boston311/`. Tests are under `tests/`.

### Acceptance examples (spec section 8)

| Spec | Implemented in | Tested by |
|---|---|---|
| **E1** hiring delay, paid training | `staffing.py` `DepartmentPlan.regular_crews`, `score_department`: paid = working + ordered | `test_staffing.py::test_e1_hiring_delay_and_paid_training` |
| **E2** two-month hiring persistence | `staffing.py` `hires_from_shortages`, `shortage_crews` | `test_e2_hiring_persistence` |
| **E3** no hires after October | `hires_from_shortages`; `config.LAST_HIRE_ORDER_MONTH`; enforced on every plan by `validate_department_plan` | `test_e3_no_hires_after_october`, `test_frozen_plan_respects_terminal_rules`, `test_hire_orders_after_october_are_rejected` |
| **E4** notice and severance | `score_department` (severance charged in the notice month) | `test_e4_release_notice_and_severance` |
| **E5 / E5b / E5c** release blocked by events / cost / backlog | `release_passes`, `release_window_cost`, `_release_decision` | `test_e5_release_blocked_by_more_events`, `test_e5b_release_blocked_by_cost` (+$16,000 exactly), `test_e5c_release_blocked_by_end_of_horizon_backlog` |
| **E6** no release after August | `_release_decision`; `config.LAST_RELEASE_NOTICE_MONTH` | `test_e6_no_release_after_august` (the same surplus in August does release) |
| **E7** Parks seasonal eligibility, capacity, cost | `check_seasonal`, `DepartmentPlan.__post_init__` | `test_e7_seasonal_in_march_is_rejected`, `test_e7_seasonal_outside_parks_is_rejected`, `test_e7_seasonal_capacity_and_cost` |
| **E8** deadline boundaries | `simulate.py` `period_stats` | `test_simulate.py::test_e8_deadline_boundaries` (4 cases) |
| **E9** FIFO with capacity | `simulate` | `test_e9_fifo_with_capacity` |
| **E10** target classes | `data.py` `clean_requests`; `workload.py` `_draw_attributes`; simulator treats no-target as capacity only | `test_e10_*` (simulate and workload), `test_data.py::test_target_classes_and_windows` |
| **E11** window fallback chain | `workload.py` `WindowSampler.source_for` | `test_workload.py::test_e11_fallback_to_department`, `test_fallback_to_pooled_when_department_is_small` |
| **E12** 21-day calendar | `simulate.py` `build_calendar` | `test_e12_february_adds_first_saturday`, `test_e12_month_with_23_weekdays_uses_first_21`, `test_every_month_has_21_service_days` |
| **E13** year end | `staffing.py` `year_end_report` | `test_e13_year_end` |
| **E14** stream separation, reproducibility | `workload.py` `build_base_workload`: one `SeedSequence` per stream | `test_e14_rebuilding_reproduces_each_stream`, `test_planning_and_base_have_identical_arrival_counts` |
| **E15** planner isolation | `staffing.py` `make_plan`: its only input is the planning workload, and it rejects any other | `test_e15_planner_takes_only_the_planning_workload`, `test_e15_planner_rejects_an_evaluation_workload`, `test_e15_plan_unchanged_when_evaluation_stream_changes` |
| **E16** long-deadline Parks work | `Projector.seasonal_needed`, `hires_from_shortages` Parks block | `test_e16_long_deadline_parks_work_carries_forward` |
| **E17** scenario coupling | `workload.py` `build_plus_scenario`, `build_minus_scenario`, `build_spike_scenario`, `largest_remainder` | `test_e17_*` (subset, superset, exact totals, spike tripling, cell monotonicity), `test_largest_remainder_spec_example` ([1,3,7] with totals 5 and 6) |

### General checks (spec section 8)

| Spec | Where | Tested by |
|---|---|---|
| **1** fresh install; notebook runs from a restarted kernel | README Setup; `requirements.lock` | Manual. On 2026-10-28 a new venv built from `requirements.lock` on Python 3.12.10 passed all 145 tests, `run_all.py` reproduced every committed output byte for byte, and the notebook executed with no errors in a fresh `boston311` kernel. On that Windows machine `nbconvert --execute` stopped with "Kernel didn't respond in 60 seconds" because its client connects before the kernel is listening; starting the kernel first, waiting 15 seconds, and executing through `nbclient` (the engine `nbconvert` uses) worked |
| **2** offline mode with no network or secrets | `llm.py` `OfflineModel`, `RecordingStore` | `test_intake.py::test_offline_replay_covers_every_eval_item`; the notebook executes with `OPENAI_API_KEY` unset |
| **3** 48 rows per scenario; flow and cost identities | `staffing.py` `score_plan`, `reconciliation_failures` | `test_full_reconciliation` (8 plan × scenario combinations) |
| **4** same seed and scenario → identical workloads across plans | By construction: both plans are scored on the same `Workload` object (`scripts/run_all.py`, notebook section 5) | Indirectly only, through `test_full_reconciliation`. No test asserts object identity |
| **5** forecast never reads past Dec 2024 | `forecast.forecast_2025`; `data.build_all` raises on later dates | `test_forecast_never_reads_past_2024` |
| **6** routing only through approved mappings | `catalog.py` `CatalogEntry.route`, `_approved`; `agent/nodes.py` `decide` | `test_rejected_mapping_never_routes`, `test_provisional_requires_flag`, `test_unmapped_type_triage` |
| **7** every section 5 condition (table below) | | |
| **8** full-dataset reconciliation | `reconciliation_failures`: flow, workforce, seasonal, cost identities, and per-request penalty counts | `test_full_reconciliation`; plus `test_simulate.py::test_fast_simulator_matches_naive_reference_on_real_workload`, a literal deque transcription of the daily order of events, compared on about 18,600 real-sized requests |

### Failure behavior (spec section 5)

| Condition | Where | Tested by |
|---|---|---|
| Missing API key | `llm.py` `LiveModel.__init__` | `test_missing_api_key_message` |
| Timeout, rate limit, or server error (HTTP 5xx) → bounded retries → TRIAGE | `llm.py` `TRANSIENT_ERRORS`, `LiveModel.ask`; `nodes.classify` | `test_transient_errors_retry_then_fail`, `test_real_wrapper_server_error_is_retried_as_transient`, `test_model_failure_triage` |
| Malformed structured output → one retry → TRIAGE. Includes a truncated, content-filtered, or refused reply, and a complete reply that is not valid JSON for the schema (pydantic `ValidationError` raised inside the SDK) | `llm.py` `MALFORMED_ERRORS`, `LiveModel.ask` | `test_malformed_output_retries_once_then_fails`, `test_real_wrapper_truncated_then_valid_recovers`, `test_real_wrapper_repeated_truncation_fails_as_malformed`, `test_real_wrapper_refusal_fails_as_malformed`, `test_real_wrapper_truncation_ends_in_triage_not_a_crash`, `test_real_wrapper_invalid_reply_then_valid_recovers`, `test_real_wrapper_repeated_invalid_reply_fails_as_malformed`, `test_corrupt_recording_is_not_retried_as_a_fresh_reply` |
| Any other API error (bad request, bad key, unknown model, context too long) → no retry → TRIAGE | `LiveModel.ask` (`openai.APIError`) | `test_real_wrapper_other_api_error_fails_without_retry`, `test_every_langchain_openai_error_class_is_handled` |
| Type not in candidates or catalog | `nodes.decide` | `test_type_not_in_candidates_triage` |
| Out of scope | `nodes.decide`, `nodes.respond` | `test_out_of_scope_triage_with_explanation` |
| Empty input, before any API call | `nodes.check_input` | `test_empty_input_rejected_before_any_api_call` (asserts 0 model calls) |
| Second unresolved ambiguity | `nodes.decide` | `test_second_ambiguity_triage` |
| Missing data column | `data.py` `check_columns` | `test_missing_column_error_names_the_column` |
| Seasonal crews outside Parks or outside April to October | `staffing.check_seasonal` | `test_e7_seasonal_in_march_is_rejected`, `test_e7_seasonal_outside_parks_is_rejected` |
| Invalid staffing input | `DepartmentPlan.__post_init__`, `daily_capacity_from_crews` | `test_invalid_staffing_input_names_parameter`, `test_negative_crews_rejected` |

### Other spec items

| Spec | Where | Tested by |
|---|---|---|
| 4.1 data reconciliation against the page | `data.reconciliation_report`; `data/processed/reconciliation.json` | `test_2024_counts_reconcile_with_project_page` |
| 4.2 seasonal naive forecast and backtest | `forecast.py` | `test_forecast_is_seasonal_naive_from_2024`, `test_backtest_reports_every_department` |
| 4.3 arrivals match the forecast exactly | `workload.allocate_to_cells` | `test_arrivals_match_forecast_exactly`, `test_largest_remainder_*`, `test_round_half_up` |
| 4.3 class shares reproduced per type | `_draw_attributes` | `test_generated_class_shares_track_history` (statistical, ±0.005) |
| 4.4 seasonal service floor (changed) | `Projector.month_on_time_rate`, `seasonal_needed` | `test_seasonal_floor_uses_fewest_crews_meeting_target`, `test_seasonal_floor_falls_back_to_best_possible_rate`, `test_seasonal_rule_only_for_parks_in_season`, `test_seasonal_frontier_is_ordered_and_restores_config` |
| 4.6 two-tier mapping rule (changed) | `catalog.build_mappings` | `test_mappings_follow_the_two_tier_rule`, `test_audit_examples` |
| 4.6 retrieval, recall with and without aliases | `retrieval.py`, `evaluate.retrieval_recall` | `test_retrieval_tolerates_misspelling`, `test_aliases_improve_recall_on_dev` |
| 4.7 one clarification via interrupt, no API calls on resume | `nodes.clarify`, `agent/graph.py` | `test_clarify_once_then_route_without_rerunning_the_model`, `test_multiple_issues_ask_first`, `test_reused_thread_id_starts_clean` |
| 4.7 retrieval gate, and the agreement rule that skips it | `nodes.decide`; `config.RETRIEVAL_GATE_MIN_SCORE` | `test_retrieval_gate_asks_for_detail`, `test_agreement_with_top_candidate_skips_gate` |
| 4.6 / 4.7 overlapping types go to TRIAGE | `nodes.decide`; `config.OVERLAPPING_TYPE_PAIRS` | `test_overlap_pairs_name_real_types`, `test_overlap_pair_triage_when_partner_retrieved`, `test_overlap_pair_routes_when_partner_not_retrieved` |
| 4.4 terminal rules apply to every plan; plans cannot be edited after validation | `staffing.validate_department_plan`, frozen `DepartmentPlan`, re-check in `score_department` | `test_hire_orders_after_october_are_rejected`, `test_release_notices_after_august_are_rejected`, `test_last_allowed_months_are_valid`, `test_plan_cannot_be_edited_after_validation`, `test_scoring_revalidates_the_plan` |
| 4.7 templated response, never claims submission | `agent/tools.py` `route_text`, `DEMO_NOTICE` | `test_route`, `test_assigned_by_location_label` |
| 4.6 / 4.7 historical statistics: "unavailable" for small samples, each statistic gated on its own sample | `catalog.historical_stats_text` | `test_median_hidden_when_too_few_closed`, `test_median_boundary_at_min_sample`, `test_on_time_hidden_when_too_few_with_target`, `test_all_statistics_unavailable` |
| 4.8 metrics (clarification counted when asked) | `evaluate.metrics`, `evaluate.run_set`, `IntakeResult.questions_asked` | `test_metrics_on_a_tiny_frame`, `test_clarification_rate_counts_questions_asked` |
| 4.9 recordings: key and provenance include model, reasoning effort, seed, schema | `llm.recording_key`, `llm.schema_id`, `RecordingStore.put`; `scripts/migrate_recordings_v2.py` | `test_recording_key_depends_on_generation_settings_and_schema`, `test_record_stores_the_settings_used`, `test_committed_recordings_have_verifiable_provenance` |
| 4.9 live mode always calls the model and records each success; offline replays the latest recording and never calls it | `llm.py` `LiveModel.ask`, `OfflineModel.ask`, `RecordingStore` | `test_live_calls_the_model_even_when_a_recording_exists`, `test_repeated_live_request_calls_the_model_again`, `test_successful_live_responses_are_recorded`, `test_offline_replays_the_latest_response_without_calling_the_model`, `test_corrupt_recording_is_not_retried_as_a_fresh_reply` |
| 4.9 run manifest, one JSON file per run (CLI and notebook) | `manifest.build_manifest`, `manifest.write_manifest`; notebook section 9 | `test_manifest_records_inputs_seeds_and_model`, `test_sources_are_pinned`, `test_notebook_manifest_cell_writes_a_manifest`, `test_write_manifest_never_overwrites` |
| Deliverable 6, neighborhood equity | `equity.py` | `test_equity_expected_on_time_sums_to_actual_per_department`, `test_equity_covers_every_department_and_flags_small_groups` |

## 4. Deviations from the original spec v5.1

Each deviation is approved by John and recorded in architecture section 11.1, with the spec text updated:

1. **Two-tier intake routing** (spec 4.6–4.8, 8, 10.2).
   - **Change:** route to a department when one handles at least 90% of a type's requests. Name an exact queue only when one queue has at least 90%. Otherwise label the queue `assigned_by_location` or `assigned_by_department`.
   - **Why:** about 18% of volume goes to district or region queues, which depend on location.
2. **INFO referral queues** are left out of the share denominator, with a guard that the mapped department must hold at least 50% of *all* the type's requests (spec 4.6).
3. **Parks seasonal rule.** The original rule removed every avoidable miss. The new rule is a **93% monthly on-time service floor**, with fallback to the best reachable rate (spec 4.4 step 2, the plain-language rules, E16, and 10.2). Two cost-only rules were tested and rejected; the evidence is in `outputs/parks_seasonal_frontier.csv`.
4. **Overlapping types** (spec 4.6, 4.7, 5). If the model picks one type of a listed pair and the other was also retrieved, the request goes to TRIAGE (`config.OVERLAPPING_TYPE_PAIRS`).
5. **Scope rule narrowed** (`classify-v3`, spec 4.7). Emergencies are situations needing police, fire, or an ambulance; a hazard such as a tree that may fall stays in scope.
6. **Agreement rule** (spec 4.7). The retrieval gate does not apply when the model's clear, in-scope pick is also retrieval's top candidate. It was prompted by test example t13 (spec 11.4).
7. **Q5 ownership** corrected (John and Adam on the build). The **exposure view** was added to the stretch list.

Additions and choices where the spec was silent (architecture section 11.3):

- **Added module:** `equity.py`.
- **Added scripts:** `build_data.py`, `build_catalog.py`, `build_eval_sets.py`, `run_all.py`.
- **StaffingRow:** gains `open_start`. The month-end inventory fields partition `open_end`, with overdue and long-overdue kept disjoint.
- **Penalty counting:** projections count both penalty kinds.
- **Arrival order:** within a day, requests queue in type-ID order. Scenario extras queue behind that day's base requests.
- **Snowstorm:** applied cell by cell (each Public Works type-day cell on February 10 to 12 ends at exactly 3×).
- **Neighborhoods:** labels are merged for the equity analysis only.
- **Model settings:** the model rejects `temperature`, so it runs at low reasoning effort with a fixed seed. Repeatability comes from offline replay.

## 5. Where to look hardest

These are ordered by how much depends on them and how easy a subtle error would be to miss.

1. **`simulate.py` `simulate` and `period_stats`.**
   - The whole queue state is one integer, `head`: requests are served strictly in sorted order, so the closed ones are always the first `head`.
   - Close days come from a `searchsorted` over the end-of-day head counts.
   - Check the boundary conventions:
     - closing on day T is on time;
     - the $20 event falls at the end of day T;
     - the $100 event falls at the end of day T+30;
     - requests below `head_start` can produce no events.
   - The naive cross-check test is the main safety net; review it as well.
2. **`staffing.py` projections.**
   - `Projector.project`, `_hire_decision` and `_release_decision`. In the release decision, month t is simulated once and both branches start from it.
   - The order of decisions in `plan_department`: apply changes → seasonal → hire → release (only if no hire) → advance.
   - Confirm that nothing in planning reads an evaluation workload.
3. **The Parks seasonal floor.**
   - "Due in month t" counts requests already closed before the month (positions below `head`) as on time.
   - The rate is monotone in crews, which the binary search relies on.
   - The fallback target is `min(93%, best reachable)`.
4. **`workload.py` scenario construction.**
   - Integer-exact largest remainder, with ties going to the lower index.
   - Half-up rounding through `Fraction`.
   - The minus scenario never removes more than a cell holds.
   - Each extra stream uses its own `SeedSequence([EVALUATION_SEED, key])`.
5. **`score_department` cost accounting.**
   - Trainees are paid in their order month.
   - Noticed crews are paid and work in the notice month.
   - Severance is charged in the notice month.
   - Seasonal crews cost 1.3 × monthly.
6. **`catalog.build_mappings`.** The denominator is handled requests, but the 50% guard uses all requests. The exact queue must belong to the mapped department. Ties go to department code.
7. **The agent (`agent/nodes.py`).**
   - Check the order of tests in `decide`.
   - `check_input` resets state, because LangGraph keeps thread state between runs.
   - `clarify` must contain no side effects before `interrupt`.
8. **`evaluate.py`.**
   - Alternates: the acceptable decisions, departments, and queues are derived from every acceptable type.
   - A triaged item counts as wrong for department and queue accuracy.

9. **`llm.py` error grouping and recording keys.**
   - Every exception the installed OpenAI SDK and LangChain can raise must land in `TRANSIENT_ERRORS`, `MALFORMED_ERRORS`, or `openai.APIError`. The guard test lists the LangChain error classes for langchain-openai 1.7.2; re-check it after upgrading. **It only covers LangChain's own classes:** the SDK can also raise exceptions from other libraries, such as pydantic's `ValidationError` (R1a). Those are covered by the mocked-HTTP tests, not by the guard.
   - Programming errors must still surface.
   - `recording_key` covers the settings and the schema, and `LiveModel` captures its settings once, at construction.
   - Schema identity includes class docstrings, which is why `AliasDraft` and `AliasBatch` deliberately have none.

## 6. Known limitations and open items

- **Catalog review (2026-10-27):** every nominated mapping is approved or rejected (`data/catalog/mapping_review.csv`). Wording for 10 types is still provisional and is still indexed for retrieval, and the scooter/moped overlap between Abandoned Bicycle and Abandoned Vehicles is unresolved. Approval checks consistency with the routing data, not the city's service eligibility. See architecture section 11.5.
- **Evaluation sets:** the test and dev messages were not written independently of the catalog aliases, a possible source of optimistic accuracy. The test set was run once after dev-set tuning, six labels were corrected in the review, and the agreement rule was prompted by test example t13 (architecture section 11.4).
- **Synthetic evaluation:** the plan is scored on synthetic workloads from one planning seed and one evaluation seed, not on real 2025 requests. The challenge's costs and penalties are assumptions.
- **Volume-based hiring:** the hiring rule counts long-deadline requests in its shortage. It is safe with the 93% floor, but a weaker seasonal rule can trigger large October hires (architecture section 4.4).
- **No releases occur.** As a result, Public Works and Inspectional Services run at about 60% utilization in Q4. This follows from the "no notices after August" rule and is discussed in the notebook, section 4.
- **Frontier wobble:** neighbouring targets can swap order on cost, because the planner fully re-plans for each target.

## 7. Repairs after the 2026-10-23 review

The code review of `d1d1c7d` is in [code_review_2026-10-23.md](code_review_2026-10-23.md). Each finding was repaired on branch `repair/astra-review`. The follow-up review of `01630ca`, [code_review_2026-10-23_round2.md](code_review_2026-10-23_round2.md), closed R2–R6 and found R1 partially fixed (R1a), which was then repaired the same way.

Each repair followed the same steps:
1. Write the regression test first and confirm it fails.
2. Apply the fix.
3. Pass the regression gate. The gate runs the full test suite, then `run_all.py`, and requires every tracked output to stay byte-identical to the pre-repair baseline. It then re-executes the notebook offline in a fresh kernel and requires zero errors.

| Finding | Commit | What changed | New tests |
|---|---|---|---|
| R1: SDK exceptions escaped the retry/TRIAGE path | `498d710` | Model errors are grouped as transient (timeouts, 5xx), malformed (truncated, filtered, refused), or `api_error`. Every group ends in `ClassifierFailure` and then TRIAGE. **Wider than reported:** HTTP 5xx and non-status API errors also escaped | 7 tests through the real ChatOpenAI and SDK with `httpx.MockTransport` |
| R1a (round 2): SDK-raised pydantic `ValidationError` skipped the malformed retry | `fcfae5b` | `ValidationError` joins `MALFORMED_ERRORS`, caught only around the model call. A corrupt *recorded* answer is still not retried | 5 (4 failed before; the corrupt-recording guard passed before and after) |
| R2: median shown from too few closed requests | `165daa7` | Each statistic is gated on its own sample (30), its count is stated, and the median is labeled as over closed requests. Only reply wording changes | 5 |
| R3: terminal rules not enforced on every plan | `2114461` | `validate_department_plan` adds the terminal rules. `DepartmentPlan` is frozen with tuple fields, and scoring re-validates | 9 |
| R4: seed and reasoning effort missing from the recording key | `1efe1d9` | The key and each record cover model, effort, seed, and schema id. All 83 recordings were migrated after verification against their v1 keys, with provenance justified from git (`scripts/migrate_recordings_v2.py`) | 4 |
| R5: unanswered clarifications not counted | `33824dc` | New `IntakeResult.questions_asked`; the metric counts questions asked | 4 |
| R6: notebook did not save its manifest | `294c072`, `b0dafb6` | The notebook writes its manifest. Run manifests are gitignored, `reference_run_all.json` describes the committed outputs, and manifests are never overwritten | 2 |

**What did not change:** every published number (costs, plans, scenario results, intake metrics), and the spec. The only visible changes are the reply wording for statistics and the notebook's manifest line.
