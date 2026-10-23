<!-- [AI-authored: Claude] Reviewer entry point for branch Zero_Shot_Attempt_1, written 2026-10-23. -->
# Review guide

This guide is the starting point for reviewing the zero-shot build on branch `Zero_Shot_Attempt_1`. It tells you what to read, how to check that the results reproduce, where each requirement is implemented and tested, what differs from the original spec, and where bugs are most likely to hide.

**Ground rules for the review**

- `docs/architecture.md` is the authority. It is the frozen spec v5.1, plus the changes the team approved during the build.
- `docs/decisions.md` records every one of those changes with its evidence and date. It also records the data audit and the implementation choices made where the spec was silent.
- Anything this guide summarizes is stated in full in one of those two files. If this guide disagrees with them, they win.
- Line numbers below are for commit `91ad4ac` plus this guide and may drift slightly.

## 1. Read in this order

1. [architecture.md](architecture.md), sections 2, 5.3, 5.4, 5.6, 5.7 and 9. These sections contain the GIVEN rules, the simulator, the policy, routing, the agent, and the acceptance checks.
2. [decisions.md](decisions.md): the data audit, Parks seasonal rule, provisional reviews, implementation notes, and spec changes.
3. The code, in dependency order:
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

Expected: `105 passed` (about 30 seconds).

```bash
python scripts/run_all.py
```

This rebuilds every table and figure in `outputs/` and writes a new run manifest. It raises an error if any reconciliation check fails. Then compare against the committed outputs:

```bash
git status --short outputs
```

Expected: only a new file under `outputs/manifests/`. Every CSV and figure should be byte-identical to the committed ones.

```bash
python -m nbconvert --to notebook --execute --inplace demo.ipynb
```

Expected: no errors. Afterwards, run `git checkout -- demo.ipynb` to discard the re-execution, which only changes timestamps and the manifest cell.

Headline numbers you should see (`outputs/scenario_summary.csv` and `outputs/intake_metrics.csv`):

| Check | Expected value |
|---|---|
| Frozen plan, base scenario: total cost / on-time / open Dec 31 | $16,394,440 / 89.5% / 1,441 |
| Baseline (January crews), base scenario | $19,474,180 / 22.4% / 27,579 |
| Parks under the frozen plan | $1,862,860 / 95.4% on time / 42 seasonal crew-months |
| Intake test set (40 items) | decision 40/40, type 33/34, auto-route precision 29/30 |
| Intake dev set (18 items) | decision 18/18, type 15/15, precision 12/12 |

Optional checks that need network or a key:

- `python scripts/build_data.py` downloads the two source files (about 370 MB) through the CKAN API and rebuilds `data/processed/`. The tables should come out identical while the city's files are unchanged; the manifest records their MD5 checksums.
- Setting `MODE = "live"` in the notebook needs `OPENAI_API_KEY` in `.env`. Live mode reuses recordings for any input it has already seen.

## 3. Requirement → code → test map

Code paths are under `src/boston311/`. Tests are under `tests/`.

### Acceptance examples (spec section 9)

| Spec | Implemented in | Tested by |
|---|---|---|
| **E1** hiring delay, paid training | `staffing.py` `DepartmentPlan.regular_crews` (132), `score_department` (507): paid = working + ordered | `test_staffing.py::test_e1_hiring_delay_and_paid_training` |
| **E2** two-month hiring persistence | `staffing.py` `hires_from_shortages` (325), `shortage_crews` (320) | `test_e2_hiring_persistence` |
| **E3** no hires after October | `hires_from_shortages`; `config.LAST_HIRE_ORDER_MONTH` | `test_e3_no_hires_after_october`, `test_frozen_plan_respects_terminal_rules` |
| **E4** notice and severance | `score_department` (severance charged in the notice month) | `test_e4_release_notice_and_severance` |
| **E5 / E5b / E5c** release blocked by events / cost / backlog | `release_passes` (379), `release_window_cost` (369), `_release_decision` (398) | `test_e5_release_blocked_by_more_events`, `test_e5b_release_blocked_by_cost` (+$16,000 exactly), `test_e5c_release_blocked_by_end_of_horizon_backlog` |
| **E6** no release after August | `_release_decision`; `config.LAST_RELEASE_NOTICE_MONTH` | `test_e6_no_release_after_august` (the same surplus in August does release) |
| **E7** Parks seasonal eligibility, capacity, cost | `check_seasonal` (76), `DepartmentPlan.__post_init__` | `test_e7_seasonal_in_march_is_rejected`, `test_e7_seasonal_outside_parks_is_rejected`, `test_e7_seasonal_capacity_and_cost` |
| **E8** deadline boundaries | `simulate.py` `period_stats` (295) | `test_simulate.py::test_e8_deadline_boundaries` (4 cases) |
| **E9** FIFO with capacity | `simulate` (210) | `test_e9_fifo_with_capacity` |
| **E10** target classes | `data.py` `clean_requests`; `workload.py` `_draw_attributes` (260); simulator treats no-target as capacity only | `test_e10_*` (simulate and workload), `test_data.py::test_target_classes_and_windows` |
| **E11** window fallback chain | `workload.py` `WindowSampler.source_for` (168) | `test_workload.py::test_e11_fallback_to_department`, `test_fallback_to_pooled_when_department_is_small` |
| **E12** 21-day calendar | `simulate.py` `build_calendar` (93) | `test_e12_february_adds_first_saturday`, `test_e12_month_with_23_weekdays_uses_first_21`, `test_every_month_has_21_service_days` |
| **E13** year end | `staffing.py` `year_end_report` (568) | `test_e13_year_end` |
| **E14** stream separation, reproducibility | `workload.py` `build_base_workload` (309): one `SeedSequence` per stream | `test_e14_rebuilding_reproduces_each_stream`, `test_planning_and_base_have_identical_arrival_counts` |
| **E15** planner isolation | `staffing.py` `make_plan` (468): its only input is the planning workload, and it rejects any other | `test_e15_planner_takes_only_the_planning_workload`, `test_e15_planner_rejects_an_evaluation_workload`, `test_e15_plan_unchanged_when_evaluation_stream_changes` |
| **E16** long-deadline Parks work | `Projector.seasonal_needed` (251), `hires_from_shortages` Parks block | `test_e16_long_deadline_parks_work_carries_forward` |
| **E17** scenario coupling | `workload.py` `build_plus_scenario` (363), `build_minus_scenario` (385), `build_spike_scenario` (417), `largest_remainder` (72) | `test_e17_*` (subset, superset, exact totals, spike tripling, cell monotonicity), `test_largest_remainder_spec_example` ([1,3,7] with totals 5 and 6) |

### General checks (spec section 9)

| Spec | Where | Tested by |
|---|---|---|
| **1** fresh install; notebook runs from a restarted kernel | README Setup; `requirements.lock` | Manual. A clean venv built from `requirements.lock` passed the tests and executed the notebook on 2026-10-22. After later changes the notebook was re-executed with `nbconvert` (a fresh kernel) on 2026-10-23, using Miniconda's Jupyter and the `boston311` kernel |
| **2** offline mode with no network or secrets | `llm.py` `OfflineModel`, `RecordingStore` | `test_intake.py::test_offline_replay_covers_every_eval_item`; the notebook executes with `OPENAI_API_KEY` unset |
| **3** 48 rows per scenario; flow and cost identities | `staffing.py` `score_plan` (769), `reconciliation_failures` (700) | `test_full_reconciliation` (8 plan × scenario combinations) |
| **4** same seed and scenario → identical workloads across plans | By construction: both plans are scored on the same `Workload` object (`scripts/run_all.py`, notebook section 5) | Indirectly only, through `test_full_reconciliation`. No test asserts object identity |
| **5** forecast never reads past Dec 2024 | `forecast.forecast_2025`; `data.build_all` raises on later dates | `test_forecast_never_reads_past_2024` |
| **6** routing only through approved mappings | `catalog.py` `CatalogEntry.route` (91), `_approved` (110); `agent/nodes.py` `decide` (106) | `test_rejected_mapping_never_routes`, `test_provisional_requires_flag`, `test_unmapped_type_triage` |
| **7** every section 6 condition (table below) | | |
| **8** full-dataset reconciliation | `reconciliation_failures`: flow, workforce, seasonal, cost identities, and per-request penalty counts | `test_full_reconciliation`; plus `test_simulate.py::test_fast_simulator_matches_naive_reference_on_real_workload`, a literal deque transcription of the daily order of events, compared on about 18,600 real-sized requests |

### Failure behavior (spec section 6)

| Condition | Where | Tested by |
|---|---|---|
| Missing API key | `llm.py` `LiveModel.__init__` (155) | `test_missing_api_key_message` |
| Timeout or rate limit → bounded retries → TRIAGE | `LiveModel.ask` (175); `nodes.classify` | `test_transient_errors_retry_then_fail`, `test_model_failure_triage` |
| Malformed structured output → one retry → TRIAGE | `LiveModel.ask` | `test_malformed_output_retries_once_then_fails` |
| Type not in candidates or catalog | `nodes.decide` | `test_type_not_in_candidates_triage` |
| Out of scope | `nodes.decide`, `nodes.respond` | `test_out_of_scope_triage_with_explanation` |
| Empty input, before any API call | `nodes.check_input` (66) | `test_empty_input_rejected_before_any_api_call` (asserts 0 model calls) |
| Second unresolved ambiguity | `nodes.decide` | `test_second_ambiguity_triage` |
| Missing data column | `data.py` `check_columns` | `test_missing_column_error_names_the_column` |
| Seasonal crews outside Parks or outside April to October | `staffing.check_seasonal` | `test_e7_seasonal_in_march_is_rejected`, `test_e7_seasonal_outside_parks_is_rejected` |
| Invalid staffing input | `DepartmentPlan.__post_init__`, `daily_capacity_from_crews` | `test_invalid_staffing_input_names_parameter`, `test_negative_crews_rejected` |

### Other spec items

| Spec | Where | Tested by |
|---|---|---|
| 5.1 data reconciliation against the page | `data.reconciliation_report`; `data/processed/reconciliation.json` | `test_2024_counts_reconcile_with_project_page` |
| 5.2 seasonal naive forecast and backtest | `forecast.py` | `test_forecast_is_seasonal_naive_from_2024`, `test_backtest_reports_every_department` |
| 5.3 arrivals match the forecast exactly | `workload.allocate_to_cells` (202) | `test_arrivals_match_forecast_exactly`, `test_largest_remainder_*`, `test_round_half_up` |
| 5.3 class shares reproduced per type | `_draw_attributes` | `test_generated_class_shares_track_history` (statistical, ±0.005) |
| 5.4 seasonal service floor (changed) | `Projector.month_on_time_rate` (233), `seasonal_needed` (251) | `test_seasonal_floor_uses_fewest_crews_meeting_target`, `test_seasonal_floor_falls_back_to_best_possible_rate`, `test_seasonal_rule_only_for_parks_in_season`, `test_seasonal_frontier_is_ordered_and_restores_config` |
| 5.6 two-tier mapping rule (changed) | `catalog.build_mappings` (118) | `test_mappings_follow_the_two_tier_rule`, `test_audit_examples` |
| 5.6 retrieval, recall with and without aliases | `retrieval.py`, `evaluate.retrieval_recall` | `test_retrieval_tolerates_misspelling`, `test_aliases_improve_recall_on_dev` |
| 5.7 one clarification via interrupt, no API calls on resume | `nodes.clarify` (154), `agent/graph.py` | `test_clarify_once_then_route_without_rerunning_the_model`, `test_multiple_issues_ask_first`, `test_reused_thread_id_starts_clean` |
| 5.7 retrieval gate | `nodes.decide`; `config.RETRIEVAL_GATE_MIN_SCORE` | `test_retrieval_gate_asks_for_detail` |
| 5.7 templated response, never claims submission | `agent/tools.py` `route_text`, `DEMO_NOTICE` | `test_route`, `test_assigned_by_location_label` |
| 5.8 metrics | `evaluate.metrics` | `test_metrics_on_a_tiny_frame` |
| 5.9 run manifest | `manifest.build_manifest` | `test_manifest_records_inputs_seeds_and_model`, `test_sources_are_pinned` |
| Deliverable 6, neighborhood equity | `equity.py` | `test_equity_expected_on_time_sums_to_actual_per_department`, `test_equity_covers_every_department_and_flags_small_groups` |

## 4. Deviations from the original spec v5.1

Each deviation is approved by John and recorded in `decisions.md`, with the spec text updated:

1. **Two-tier intake routing** (spec 5.6–5.8, 9, 10.2).
   - **Change:** route to a department when one handles at least 90% of a type's requests. Name an exact queue only when one queue has at least 90%. Otherwise label the queue `assigned_by_location` or `assigned_by_department`.
   - **Why:** about 18% of volume goes to district or region queues, which depend on location.
2. **INFO referral queues** are left out of the share denominator, with a guard that the mapped department must hold at least 50% of *all* the type's requests (spec 5.6).
3. **Parks seasonal rule.** The original rule removed every avoidable miss. The new rule is a **93% monthly on-time service floor**, with fallback to the best reachable rate (spec 5.4 step 2, the plain-language rules, E16, and 10.2). Two cost-only rules were tested and rejected; the evidence is in `outputs/parks_seasonal_frontier.csv`.
4. **Q5 ownership** corrected (John and Adam on the build). The **exposure view** was added to the stretch list.

Additions and choices where the spec was silent (`decisions.md` → *Implementation notes for reviewers*):

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

## 6. Known limitations and open items

- **Pending team review:**
  - the provisional mappings (`data/catalog/mapping_review.csv`) and aliases (`catalog.json`);
  - the AI-written test and dev messages. The same AI wrote the aliases and the messages, a possible source of optimistic accuracy. The test set was run once, after tuning on the dev set only.
- **Synthetic evaluation:** the plan is scored on synthetic workloads, not real 2025 requests. The challenge's costs and penalties are assumptions.
- **Volume-based hiring:** the hiring rule counts long-deadline requests in its shortage. It is safe with the 93% floor, but a weaker seasonal rule can trigger large October hires (see `decisions.md`).
- **No releases occur.** As a result, Public Works and Inspectional Services run at about 60% utilization in Q4. This follows from the "no notices after August" rule and is discussed in `report.md`.
- **Frontier wobble:** neighbouring targets can swap order on cost, because the planner fully re-plans for each target.
- **Spec 10.4 logistics** are still open: the Q&A forum check on pandas and scikit-learn, an owner for `authorship.md`, and a code-freeze date.
