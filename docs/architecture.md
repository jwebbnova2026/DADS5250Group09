<!-- Architecture proposal v5.1, frozen. GIVEN = stated on the project page. DECIDED = confirmed by the team or agreed in review. DEFAULT = proposed rule the team may change. AUDIT = to be checked directly in the data. -->

# Boston 311 Crew Planner: Architecture Proposal v5.1 (frozen)

**Course:** DADS5250 Generative AI in Practice, Module 7 Hackathon (midterm group project)
**Date:** October 22, 2026
**Hackathon due:** Wednesday, October 28, 2026, 11:59 PM ET
**Status:** Architecture frozen and accepted by both reviewers. v5.1 records three implementation details from the final review. Further issues are resolved with implementation evidence, not design changes. The changes the team approved after the freeze are written into the sections they affect and listed with dates in section 11, which also records the implementation decisions needed to interpret the results.

**What changed from v4:**
- the staffing plan is generated entirely from the planning workload, frozen, then scored; the planner never sees evaluation workloads or queues
- the seed-separation claim is narrowed: evaluation uses a separate synthetic workload, not unseen real requests
- the release rule adds an economic safeguard (no projected cost increase) and an end-of-horizon backlog check
- the false claim that Parks seasonal crews eliminate all in-season shortage is removed; a separate explicit rule bars Parks permanent hires that would start April to October
- evaluation scenarios are coupled: shared requests keep identical attributes, and demand changes add or remove requests reproducibly
- cost-derivation wording is corrected, and the seasonal comparison is stated as conditional on a new hire
- new acceptance examples cover release economics, long-deadline workload, and planning/evaluation separation

---

## 1. Purpose and scope

Build a month-by-month 2025 staffing plan for four City of Boston departments from real 2023 and 2024 311 data, plus a GenAI intake assistant. The plan balances cost efficiency, timely service (especially Transportation), and flexibility under the hiring, release, and seasonal-crew rules.

**Deliverables (GIVEN):**
1. 2025 monthly demand forecast per department
2. Intake assistant with a 30 to 50 message test set and reported accuracy
3. Dynamic staffing table with hire and release timing
4. Analysis and justification report
5. Sensitivity analysis: demand 20% higher, demand 20% lower, and a weather spike
6. Other considerations, such as neighborhood equity or employee vs resident requests

**Submission (GIVEN):**
- executed notebook
- GitHub repo with README (setup, architecture diagram, team contributions)
- 3-minute video link

**Stack (GIVEN):** LangChain, LangGraph, prompt engineering, structured output, RAG, and agents. No other agent SDKs.

The system is a demonstration. It never claims a request was submitted to the city and never promises a completion date.

## 2. Fixed challenge assumptions (GIVEN, used as stated)

These are assignment-provided assumptions. They support meaningful comparisons within the challenge model. They are not estimates of Boston's actual operations.

| Rule | Value |
|---|---|
| Service days per crew-month | 21 |
| Hiring | 1 month of hiring and training before a new crew starts |
| Release | 1 month notice; costs 25% of the crew's annual cost |
| Seasonal crews | Parks only, April to October, 1.3x monthly crew cost, no training delay, no release cost |
| Starting backlog | Zero on January 1, 2025 |
| Overdue | $20 when a request is not closed by its target date (`sla_target_dt`) |
| Long overdue | Additional $100 if still open 30 days after its target date |

| Dept | Code | 2024 requests | On time 2024 | Capacity per crew-day | Annual cost per crew | Monthly cost per crew | Crews Jan 2025 |
|---|---|---|---|---|---|---|---|
| Public Works | PWDx | 157,610 | 90% | 12 | $130,000 | $10,833.33 | 50 |
| Transportation | BTDT | 81,447 | 50% | 15 | $110,000 | $9,166.67 | 18 |
| Parks & Recreation | PARK | 18,736 | 93% | 6 | $120,000 | $10,000.00 | 10 |
| Inspectional Services | ISD | 18,624 | 72% | 4 | $140,000 | $11,666.67 | 16 |

Monthly cost per crew is annual cost divided by 12 (derived).

**Capacity check (derived):** under the challenge assumptions, holding the starting workforce constant provides less annual capacity than stated 2024 demand in every department.

| Dept | Avg 2024 monthly demand | Jan 2025 monthly capacity | Coverage |
|---|---|---|---|
| PWDx | 13,134 | 12,600 | 96% |
| BTDT | 6,787 | 5,670 | 84% |
| PARK | 1,561 | 1,260 | 81% |
| ISD | 1,552 | 1,344 | 87% |

This motivates comparing fixed staffing with a dynamic plan. It does not mean every department must add permanent crews; Parks may cover its shortfall seasonally. It also cannot explain actual 2024 on-time performance, because actual 2024 staffing is not supplied.

## 3. Decisions recorded

| Decision | Status | Source |
|---|---|---|
| Boston 311 project | DECIDED | Nicholas |
| Planning year 2025 from 2023 and 2024 data; January 2025 crews and zero backlog as given | DECIDED / GIVEN | John, project page |
| Optional 2025 actuals holdout | DECIDED (stretch) | Review |
| Installable package plus thin demo notebook | DECIDED | John |
| Reference notebooks: GenAI_Agents Customer Support Agent and Contextual Quoting System (custom non-commercial license, attribution required) | DECIDED | John |
| Seasonal naive forecast baseline | DECIDED | Review |
| Routing uses official type, department, and queue values; auto-routing requires a reviewer-approved mapping | DECIDED | Review |
| LLM proposes a type; code validates and assigns department and queue | DECIDED | Review |
| One clarification, then route or triage | DECIDED | Review |
| Exact heuristic is the core decision method (two-month hiring persistence, simulator-projected release check); bounded search is stretch | DECIDED | Review |
| Paid training month, as a configurable labeled interpretation | DECIDED (default) | Review |
| The plan is generated from the planning workload only, frozen, then scored; sensitivity replays the frozen plan; reactive re-planning is stretch | DECIDED | Review |
| Daily simulator scores every plan, including the fixed-workforce baseline | DECIDED | Review |
| One JSON run manifest per run | DECIDED | Review |
| Labeled live and offline demo modes | DECIDED | Review |

## 4. Course techniques

| Technique | Use |
|---|---|
| Structured output | Pydantic classification proposal; aliases and descriptions for official request types (LLM-drafted and reviewed, or written by a person) |
| Prompt engineering | Classification prompt with confusion rules and retrieved candidates; alias-generation prompt |
| RAG | Retrieval over official request types plus their reviewed aliases |
| LangGraph agent | Validation gate, interrupt-based clarification, triage fallback |
| LangChain | Model wrappers, prompt templates, structured-output binding |

## 5. Components

### 5.1 Data pipeline

- Load the 2023 and 2024 files; filter to the four department codes early.
- Keep: case ID, open date, `sla_target_dt`, close date, type, queue, department, `case_title`, neighborhood, and source.
- Deduplicate by case ID. Reconcile counts against the page's 2024 totals and report included, excluded, and unmapped records.
- Aggregate to monthly demand per department and to monthly type shares per department.
- Build target-window distributions (section 5.3).
- AUDIT: the page's "Things to watch for in this data" section and its column list (not yet captured).

### 5.2 Forecast

- Monthly series per department; training cutoff December 2024.
- Baseline: seasonal naive (each 2025 month equals the same 2024 month).
- Optional candidate model only if a fair validation is possible (predict 2024 from 2023). Otherwise the baseline is final.
- Stretch: score the frozen forecast and plan against 2025 actuals if available. Nothing is tuned on 2025.

### 5.3 Daily simulator

The simulator exists because penalties depend on deadlines. Every plan, including the fixed-workforce baseline, runs through the same simulator. Decision projections (section 5.4) also use it, so there is only one source of truth for how the queue behaves.

**Synthetic 21-day operating calendar (DEFAULT):**
- Requests arrive on every calendar day.
- Service days are the first 21 weekdays (Monday to Friday) of each month, in date order.
- If a month has fewer than 21 weekdays, Saturdays are added in date order, earliest first, until there are 21.
- If a month has more than 21 weekdays, the weekdays after the 21st are non-service days.
- Holidays are ignored.
- This is a modeling calendar, labeled as synthetic in the report.

**Workloads:**
- A workload is the full list of generated requests for 2025: arrival day, type, target class, and target day.
- Two independent random streams are configured:
  - the **planning stream**, used only to build the planning workload
  - the **evaluation stream**, used only to build evaluation workloads
- **Planning workload:** base forecast, planning stream. The planner sees only this workload.
- **Base evaluation workload:** base forecast, evaluation stream.
- Arrival counts per type and day are deterministic, so the planning and base evaluation workloads have identical arrival counts. Only sampled target classes and windows differ.
- This is evaluation on a separate synthetic workload, not validation against real unseen requests. The only real out-of-sample test is the stretch 2025 actuals holdout.

**Arrival generation (DEFAULT):**
1. Monthly total = base forecast, rounded to an integer.
2. The monthly total is split across types by 2024 same-month type shares, using largest-remainder rounding, with ties to the lower type ID.
3. Each type's monthly count is split across the month's calendar days uniformly, using largest-remainder rounding, with ties to the earlier day.
4. Totals are preserved exactly at every step.

**Coupled sensitivity workloads:** every scenario is constructed directly from the base evaluation workload, so coupling holds by construction. Independently recomputing largest-remainder allocations is not used, because it can shrink a cell when the total grows. For weights [1, 3, 7], a total of 5 allocates [1, 1, 3] but a total of 6 allocates [0, 2, 4].
- **Scenario totals:** each department-month total is the base total times the scenario factor, rounded to an integer. These rounded totals are preserved exactly.
- **Plus 20%:** retain every base request unchanged. Allocate only the additional requests (scenario total minus base total) across types and days with largest-remainder rounding on base shares. Extra requests draw attributes from a dedicated sub-stream of the evaluation stream.
- **Minus 20%:** remove requests only from the existing base workload. Allocate the removal count (base total minus scenario total) across type-day cells in proportion to their base counts with largest-remainder rounding, never removing more than a cell holds. Within each cell, remove the last requests in generation order. Retained requests keep their attributes.
- **Spike:** retain every base request and allocate additional requests on the spike days only, as in the plus scenario.
- Every compared plan (frozen plan and fixed-workforce baseline) uses exactly the same workload within each scenario.

**Target classes:** every historical request falls in exactly one class, from 2023 to 2024 data:

| Class | Rule | In distributions? | In workload? |
|---|---|---|---|
| valid | `sla_target_dt` on or after open date | Yes | Yes, with a sampled window |
| missing | no `sla_target_dt` | No | Yes, as no-target |
| invalid_ordering | target date before open date | No | Yes, as no-target, counted separately |

- Window = calendar-date difference between target date and open date, in days. A same-day target is window 0.
- There is no upper cutoff. Very long windows are valid; they simply never become overdue within 2025.
- Generation reproduces each type's historical class shares. Each generated request first receives a class by seeded sampling from its type's shares, then a window only if its class is valid. The no-target population is never silently given deadlines.

**Window distribution fallback chain:**
1. The type's own valid windows, if it has at least 50.
2. Otherwise, its department's valid windows, if the department has at least 50.
3. Otherwise, the pooled valid windows of all four departments.
4. If that pool is empty, the request becomes no-target and an audit warning is logged. This is not expected to happen with real data.

**Daily order of events for day d:**
1. Day d arrivals join the back of the queue in generation order.
2. If d is a service day, crews close up to (active regular crews + seasonal crews) x capacity per crew-day requests, from the front of the queue.
3. End of day: each still-open valid-target request with target day equal to d incurs a one-time $20 overdue event.
4. End of day: each still-open valid-target request with target day + 30 equal to d incurs a one-time $100 long-overdue event.

**FIFO tie-breaking:** arrival day, then generation sequence number.

**Deadline convention (target day T):**

| Closed on | Cost |
|---|---|
| T or earlier | $0 (on time) |
| T + 1 through T + 30 | $20 |
| Still open at end of T + 30 | $120 total |

**No-target requests** (missing and invalid_ordering) consume capacity like any other request. They are excluded from on-time metrics and penalties, and are counted by class. This is a labeled assumption.

### 5.4 Staffing policy (core heuristic)

**Notation:**
- C = capacity per crew-month = capacity per crew-day x 21
- N_t = regular crews active in month t
- S_t = Parks seasonal crews in month t

**How the plan is produced:**
1. The planner runs month by month on the planning workload only. Its queue state is the planning run's own simulated queue.
2. Each month's decisions follow the rules below.
3. After December, every monthly regular and seasonal staffing decision is frozen as the plan.
4. The frozen plan is scored on the base evaluation workload, then replayed unchanged on the sensitivity workloads.

The planning function receives no evaluation workload and no evaluation queue.

**Projection:** a projection copies the planner's queue at the start of month t, then runs the simulator forward on the planning workload under a stated workforce path. Every estimate below comes from a projection.

**Initial state (GIVEN plus DEFAULT):** January crews as given, zero backlog, and no hires or releases pending on January 1.

**Order of decisions at the start of month t:**
1. **Apply scheduled changes.** Hires ordered in month t-1 start. Releases noticed in month t-1 leave.
2. **Parks seasonal crews (April to October only). Service-floor rule, DECIDED 2026-10-23 (section 11.1).**
   - S_t is the smallest number of seasonal crews for which a one-month projection of month t keeps the on-time rate of requests due in month t at or above 93%. That is Parks' own 2024 on-time rate (GIVEN).
     - A due request has its target day in month t. It is on time if it closes on or before that day.
   - If even unlimited capacity cannot reach 93% in a month, the target for that month becomes the best rate unlimited capacity reaches. Some requests are unavoidably overdue, such as same-day targets arriving on non-service days.
   - This rule is deadline-based. It does not guarantee that all arriving work is cleared; long-deadline and no-target work can still accumulate.
   - No cap (DEFAULT; the page states none).
   - Replaced rule: the original rule added crews until no avoidable overdue request remained (equivalent to a 100% target).
     - On the base evaluation workload it bought 95 seasonal crew-months for 97.8% Parks on-time at $2.44M.
     - The 93% floor buys 42 crew-months for 95.4% at $1.86M.
     - Two cost-driven rules were also tested and rejected, because service matters as much as cost:
       - "Add a crew only while it saves more in penalties than its $13,000 cost" bought no seasonal crews, since a crew-month closes at most 126 requests worth at most $120 each. The backlog grew all season, the hiring rule ordered 27 permanent crews in October, and Parks came to $2.57M at 29% on time.
       - "Minimize seasonal cost plus projected penalties" came to $1.82M at 32% on time. The $20 penalty is too small to value timely service.
     - The full cost-versus-service frontier is in `outputs/parks_seasonal_frontier.csv`.
3. **Hiring decision**, only if t is October or earlier:
   - Project months t through t+2 with the scheduled workforce, no new hires or releases, and the seasonal rule applied to future Parks in-season months.
   - For each productive month m = t+1 and m = t+2, compute shortage_m = ceil(max(0, open at start of m + arrivals in m - capacity in m) / C), using the actual projected residual workload after seasonal crews.
   - If both shortages are at least 1, order h = min(shortage_(t+1), shortage_(t+2)) hires. They train in month t and are productive from month t+1.
4. **Parks permanent-hire restriction (explicit heuristic policy):** Parks orders no permanent hires whose first productive month falls in April to October. In-season residual work carries forward; off-season shortfalls can still trigger hires through rule 3. Rationale: for a new permanent crew that is later released after the compared service period, seasonal staffing is cheaper over any in-season span (see cost derivations). This does not prove seasonal staffing is always cheaper than retaining a permanent hire for continuing work. The report states this qualification; the model is not expanded to resolve it.
5. **Release decision**, only if no hire was ordered this month and t is August or earlier:
   - For n = 1, 2, and so on, keeping at least 1 crew, compare a projection with N_t - n crews from month t+1 against the no-release projection, over months t through t+4.
   - A candidate n passes only if all three hold:
     - projected overdue events (both types) over months t+1 to t+4 are no higher than with no release
     - projected total cost over months t to t+4 is no higher than with no release, counting severance in the notice month, regular and seasonal salaries, and both penalty types
     - projected open requests at the end of month t+4 are no higher than with no release
   - Give notice to the largest passing n. Noticed crews work and are paid through month t and leave in month t+1.
6. **Advance the planning run** through month t.

**Plain-language rules for the report and video:**
- We hire only when there is a capacity shortfall in both projected productive months, and we hire the smaller shortfall.
- We release crews only if the remaining workforce keeps up with new and accumulated work for the next four months and the release actually saves money after severance and any extra seasonal staffing.
- Parks covers its April to October peak with seasonal crews, buying just enough each month to stay at or above its 2024 on-time rate of 93%. It does not start new permanent crews in season.

**Cost derivations:**
- **Hire then release:** let k be all productive paid months of a new crew, including its notice month. Training month + k productive months + 3 months of severance = k + 4 months of crew cost. For a one-month need (k = 1), that is 5 months of cost for 1 productive month.
- **Release economics:** severance alone equals 3 months of crew cost, and a release can shift work to more expensive seasonal crews. The release rule therefore checks projected total cost directly rather than relying on a break-even shortcut. Within-year horizon rules still apply (no notices after August).
- **Parks seasonal vs new permanent hire (conditional):** for a newly hired permanent crew used for k productive months and then released, cost is k + 4 months of crew cost; a seasonal crew costs 1.3k. Seasonal is cheaper whenever k < 13.3, longer than the 7-month season. This comparison applies only to new hires. It does not show that replacing an existing permanent crew with seasonal crews is economical; that case is handled by the release rule's cost check.

**Example the release cost check blocks:** releasing one Parks crew in January causes no service deterioration but requires one extra seasonal crew in April and May.

| Change over January to May | Amount |
|---|---|
| Regular salary saved, February to May | -$40,000 |
| Additional seasonal staffing, April and May | +$26,000 |
| Severance charged in January | +$30,000 |
| Net change | +$16,000 |

The release fails the cost check and is not noticed.

**Terminal rules (applied to every plan):**
- Costs and savings are counted only within 2025.
- No hire orders after the start of October.
- No release notices after the start of August.
- Effects beyond December 31 are disclosed, not charged.
- The fixed-workforce baseline makes no changes, so the rules do not affect it.

**Cost timing (GIVEN rates, DEFAULT timing):**

| Cost | Charged when |
|---|---|
| Regular crew | Each month employed, including the training month (paid-training default, configurable) |
| Release severance | 25% of annual cost, in the notice month |
| Seasonal crew | 1.3 x monthly cost, in each month used |
| Overdue | $20, once, at the end of the target day |
| Long overdue | $100, once, at the end of target day + 30 |

**Baseline plan:** January crews all year, with no hires, releases, or seasonal crews.

**Sensitivity (core):** the frozen plan and the fixed-workforce baseline are both scored on the coupled base, plus 20%, minus 20%, and spike workloads. Reactive re-planning is stretch.

**Spike scenario (DEFAULT):** snowstorm. Public Works arrival counts are tripled for February 10 to 12, 2025, by adding requests to the base workload. A heat-wave variant is optional.

**Optional stretch, bounded search:** evaluate a bounded candidate set per department and report the result as the best evaluated candidate. Full enumeration is 3^12 = 531,441 sequences per department.

### 5.5 Staffing output fields

Each StaffingRow (one per department per month per scenario) separates events from inventory:

- **Workforce:** hires_ordered, hires_started, releases_noticed, releases_effective, regular_crews, seasonal_crews, capacity
- **Flow:** arrivals, closed, closed_on_time, late_completions (closed after target), no_target_closed
- **Penalty events this month:** overdue_events, long_overdue_events
- **Month-end inventory:** open_end, open_overdue_end, open_long_overdue_end, open_not_yet_due_end, open_no_target_end
- **Costs:** regular_cost, seasonal_cost, severance_cost, overdue_penalty, long_overdue_penalty, total_cost

**Year-end report (December 31):**
- costs accrued through December 31
- overdue unresolved requests, which have already been charged
- requests whose deadlines have not arrived, excluded from cost and reported as future exposure
- overdue requests whose 30-day threshold falls in 2026, not charged and disclosed
- outstanding commitments: hires ordered and release notices given in 2025 that take effect in 2026 (expected zero under the terminal rules, reported regardless)

### 5.6 Request-type catalog and retrieval

- **Routing targets come from official values only.** Each target is an official type with its observed department and queue from 2023 to 2024.
- **Two-tier mapping rule (DECIDED 2026-10-22, replacing the single-queue rule; section 11.1):** The data audit found that about 18% of in-scope volume goes to queues chosen by the request's district or region, for example `PWDx_District 1C: Downtown`. Text alone cannot determine those queues.
  - **Handled requests (DECIDED 2026-10-22):** shares are computed over a type's 2023 to 2024 requests in every department, except the 311 center's own INFO queues. Those queues refer requests to agencies outside the city (MassDOT, DCR, MBTA, Eversource, Massport), depending on who owns the location, or hold "Reallocation From Dept" resubmissions. No department does the work there, so they are left out of the denominator.
  - **Department mapping (tier 1):** a type-to-department mapping is nominated for review only if both hold:
    - one of the four in-scope departments handled at least 90% of the type's handled requests;
    - that department also handled at least 50% of all the type's requests, INFO included. This guard ensures a type mostly referred elsewhere is never mapped into the four departments.
  - **Queue mapping (tier 2):** a type with a department mapping gets an exact queue only if one queue of that department handled at least 90% of the type's handled requests.
  - **Queue status:** every type with a department mapping gets exactly one status.
    - `exact`: it has a queue mapping.
    - `assigned_by_location`: no queue mapping, and at least 50% of its handled requests went to district or region queues (queue names containing "District" or "Region").
    - `assigned_by_department`: any other type with no queue mapping.
  - A team member approves or rejects each nominated mapping, and the decision is recorded in the catalog file. The team review of 2026-10-27 gave every nominated department and queue mapping an approved or rejected status (section 11.5).
  - Only types with an approved department mapping auto-route. Types without one go to clarification or triage. Historical exceptions may reflect legitimate contextual routing or changes over time, so they are not silently overridden.
  - **Overlapping types (DECIDED 2026-10-27, section 11.1):** three pairs of official types describe the same problem but route differently, and nothing in the data tells them apart: Contractor Complaints and Contractors Complaint; Work Hours-Loud Noise Complaints and Working Beyond Hours; Sidewalk Repair and Sidewalk Repair (Make Safe). If the model picks one type of a pair and the other type was also retrieved, the request goes to TRIAGE, so the code never picks a department arbitrarily. The pairs are listed in `config.OVERLAPPING_TYPE_PAIRS`, and test and dev examples for these types expect TRIAGE.
- **Aliases (core, small):** each official type gets a short description and a few resident-style aliases, drafted by the LLM with structured output or written by a person. A team member reviews every one. After the 2026-10-27 review, 153 sets are approved and 10 remain provisional (section 11.5).
  - Aliases attach to official types. They never create, merge, or rename categories.
  - Aliases never assert service eligibility or responsibilities the data does not support.
  - Candidate recall@k on the dev set is measured with and without aliases. The test set is never used for this.
- **Stretch:** broader `case_title` cleanup, mining title variants as extra aliases.
- **Retriever (DEFAULT):** TF-IDF with cosine scoring over type names, descriptions, and aliases. Retrieval works offline. Classifying an arbitrary message still requires the model; offline demos replay recorded classifications, clearly labeled. Embeddings are added only if dev-set recall justifies it.
- Service statistics (historical on-time share, median days to close) are stored separately and joined by type.

### 5.7 Intake agent

- Retrieve candidates, classify once, validate in code, then route, clarify, or triage.
- **LLM owns:** selected type ID or none, ambiguity flag, missing detail, clarifying question, evidence IDs, short reason.
- **Code owns:** checking the type against candidates and catalog, assigning the department and, where the type has an `exact` status, the queue, and choosing the decision.
- **Clarification:** at most one, via a LangGraph interrupt with a checkpointer and stable thread ID. API calls stay outside the part of the node that re-runs on resume.
- **Auto-route requires:** a valid candidate, an approved department mapping, no unresolved ambiguity, passing the dev-tuned retrieval gate, and not being one of an overlapping pair whose other type was also retrieved (section 5.6).
- **Agreement rule (DECIDED 2026-10-28, section 11.1):** the retrieval gate does not apply when the model's clear, in-scope pick is also the top-ranked retrieval candidate. The two signals agree, so a weak retrieval score alone does not force a clarifying question. The gate threshold itself is unchanged. This rule was prompted by a test-set result (section 11.4).
- **Scope (DECIDED 2026-10-27, section 11.1):** out of scope includes emergencies that need police, fire, or an ambulance, such as a fire burning now, a gas or carbon monoxide alarm sounding now, or someone hurt or in danger. A hazard reported to a city department, such as a tree or branch that may fall, stays in scope as its official type (for example Tree Emergencies).
- **Response:** templated. It shows the type and department, plus one of: the exact queue; "queue assigned by location (district or region)"; or "queue assigned by the department". It also shows historical statistics labeled as historical, or "unavailable" for small samples.

### 5.8 Evaluation

- **Test set:** 30 to 50 messages with expected type, department, and queue (GIVEN size). The expected queue is the exact queue, or the label `assigned_by_location` or `assigned_by_department`. The team reviewed every message and label on 2026-10-27 (section 11.5).
- **Dev set:** 15 to 20 separate messages for prompt and gate tuning (DEFAULT).
- Test messages are never used as retrieval aliases. The prompts, aliases, and retrieval gate were tuned on the dev set only. One logic change, the agreement rule, was prompted by a test-set result, so the test set is not strictly untouched (section 11.4).
- **Coverage:** clear requests, paraphrases, confusions, missing context, out-of-scope requests, multiple issues, and empty input.
- **Metrics:**
  - type and department accuracy on every message
  - queue accuracy, scored as exact-queue match for `exact` types and as correct queue status for the other two statuses, reported separately
  - auto-route precision and coverage
  - clarification rate and triage rate
- Report counts with percentages, and label results as a demonstration evaluation.

### 5.9 Run manifest and demo modes

- One JSON manifest per run: sources, retrieval dates, hashes, exclusions, training cutoff, scenario seeds, parameters, model, prompt, and catalog versions, mode, and output paths.
- **Live mode** needs an API key.
- **Offline mode** replays recorded outputs, visibly labeled.

## 6. Failure behavior

| Condition | Outcome |
|---|---|
| Missing API key | Clear message; offline mode available |
| Timeout or rate limit | Bounded retries, then TRIAGE |
| Malformed structured output | One retry, then TRIAGE |
| Type not in candidates or catalog | TRIAGE |
| Type is one of an overlapping pair and the other type was also retrieved | TRIAGE |
| Out-of-scope request | TRIAGE with explanation |
| Empty input | Rejected before any API call |
| Second unresolved ambiguity | TRIAGE |
| Missing data column | Adapter fails naming the column |
| Seasonal crews requested outside Parks or outside April to October | Typed error |
| Invalid staffing input (for example a negative crew count) | Typed error naming the parameter |

## 7. File layout

```text
boston311-crew-planner/
├── pyproject.toml
├── requirements.lock
├── README.md
├── AGENTS.md                 # points to this spec; no duplicated requirements
├── .env.example
├── .gitignore
├── demo.ipynb
├── src/boston311/
│   ├── config.py             # GIVEN parameters, DEFAULT rules, paths, model IDs
│   ├── schemas.py
│   ├── data.py
│   ├── catalog.py            # official targets, mapping audit, alias generation
│   ├── forecast.py
│   ├── workload.py           # seeded scenario workload generation
│   ├── simulate.py           # daily FIFO simulator and penalty events
│   ├── staffing.py           # heuristic policy, baseline, cost accounting
│   ├── retrieval.py
│   ├── llm.py
│   ├── evaluate.py
│   ├── manifest.py
│   └── agent/
│       ├── graph.py
│       ├── nodes.py
│       └── tools.py
├── scripts/
├── prompts/
├── data/                     # raw (ignored), processed, catalog, eval, demo
├── tests/
├── outputs/
└── docs/
    ├── report.md
    └── decisions.md
```

## 8. Core vs stretch

**Core:**
- data pipeline
- seasonal naive forecast
- separate planning and evaluation streams with coupled scenario workloads
- daily simulator
- heuristic policy
- fixed-workforce baseline
- replayed sensitivity (plus or minus 20% and snowstorm)
- official catalog with reviewed mappings and aliases
- TF-IDF retrieval
- intake agent
- test and dev sets
- manifest, package, and offline mode
- report, README, and notebook

**Stretch:**
- 2025 holdout
- second forecast model
- bounded search
- reactive sensitivity re-runs
- heat-wave scenario
- `case_title` mining
- embedding retriever
- a second "other consideration"
- neighborhood exposure view: estimate where the simulated 2025 overdue requests fall by neighborhood. For each request type, multiply its simulated overdue count by that type's 2023 to 2024 neighborhood shares, then sum over types. This is deterministic, with no sampling. Compare the frozen plan with the baseline in each scenario, and label it request-mix exposure, not unequal treatment.

## 9. Acceptance checks with hand-calculated examples

General checks:
1. Fresh install, and the notebook runs from a restarted kernel.
2. Offline mode runs with no network or secrets.
3. Each scenario yields 48 StaffingRows; arrivals equal closed plus change in open; costs sum to total_cost.
4. The same seed and scenario produce identical workloads across plans.
5. Forecasting never reads past December 2024.
6. Intake routes only through approved official department mappings, and names a queue only through approved queue mappings.
7. Every condition in section 6 produces its typed outcome.
8. **Full-dataset reconciliation**, run on every scenario and plan, not just fixtures. The hand-calculated examples establish only the behaviors they exercise; these checks cover the full run.
   - **Request flow:** for each department-month, start open + arrivals = closed + end open. Annual arrivals equal the workload total.
   - **Workforce:** crews(t) = crews(t-1) + hires_started(t) - releases_effective(t). Every hire start is matched to an order one month earlier, and every release to a notice one month earlier. Seasonal crews are nonzero only for Parks, April to October.
   - **Penalties:** each valid-target request incurs at most one $20 and one $100 event. Overdue events match requests whose target day passed while open. No-target requests incur none.
   - **Costs:** monthly cost components sum to total_cost, and the annual total equals the sum of monthly totals.

Hand-calculated examples (each becomes a unit test):

**E1. Hiring delay and paid training.** ISD orders 2 hires at the start of March.
- March: 16 working crews, capacity 16 x 4 x 21 = 1,344. Crew cost 18 x 11,666.67 = 210,000, because trainees are paid.
- April: 18 working crews, capacity 1,512, cost 210,000.

**E2. Hiring persistence.** At the start of January, a projection shows a shortage of 3 crews in February and 0 in March. No hire is ordered. If the shortages are 3 in February and 2 in March, 2 hires are ordered.

**E3. Hiring horizon.** At the start of November, a projection shows shortages in December. No hire is ordered, because the crew would have only one productive month in 2025.

**E4. Release notice and severance.** Public Works gives notice to 1 crew at the start of June.
- June: the crew still works. Severance 0.25 x 130,000 = 32,500 is charged in June, plus its June salary of 10,833.33.
- July: the crew is gone.

**E5. Release blocked by backlog.** A department has surplus capacity against forecast arrivals, but the projection carries enough unfinished work that releasing 1 crew raises projected overdue events or end-of-horizon open requests. No release is noticed.

**E5b. Release blocked by cost.** Releasing one Parks crew in January causes no added overdue events but requires one extra seasonal crew in April and May. Net projected change is -40,000 + 26,000 + 30,000 = +16,000. No release is noticed.

**E5c. Release deferring work.** A release adds no overdue events within months t+1 to t+4 because the extra unfinished work has long deadlines, but projected open requests at the end of month t+4 rise. No release is noticed.

**E6. Late-year release block.** Surplus at the start of September triggers no release.

**E7. Parks seasonal eligibility.**
- Seasonal crews in March are rejected with a typed error.
- In April, 3 seasonal crews add 3 x 6 x 21 = 378 capacity and cost 3 x 1.3 x 10,000 = 39,000.
- Nothing is charged when they end.

**E8. Deadline boundaries.** For a valid-target request with target day 5:

| Closed on | Cost |
|---|---|
| day 5 | $0 |
| day 6 | $20 |
| day 35 | $20 |
| still open at end of day 35 | $120 |

**E9. FIFO with capacity.** One crew with capacity 2 per day. Day 1 arrivals in order: A (target day 1), B (target day 2), C (target day 1). Days 1 and 2 are service days.
- Day 1: A and B close.
- End of day 1: C becomes overdue, $20.
- Day 2: C closes as a late completion.
- Totals: 2 on time, 1 overdue event, $20.

**E10. Target classes.**
- A missing-target request consumes one unit of capacity, incurs no penalty, and counts as missing.
- An invalid_ordering request behaves the same way and counts as invalid_ordering.
- A valid request with a 400-day window is included in distributions and never becomes overdue within 2025.

**E11. Fallback chain.** A type with 12 valid windows in a department with 3,000 valid windows draws from the department distribution.

**E12. Calendar.** February 2025 has 20 weekdays, so its service days are those 20 weekdays plus Saturday, February 1. A month with 23 weekdays uses its first 21 weekdays.

**E13. Year end.** Two requests are open at the end of December 31.
- X has target date December 20. Its $20 is accrued. Its January 19, 2026 threshold is not charged and is disclosed.
- Y has target date January 10, 2026. It is reported as not yet due, with no cost.

**E14. Stream separation and reproducibility.** Planning and evaluation workloads are built from separately configured streams. Rebuilding either workload from its stream reproduces it exactly. The test does not assert that the two workloads differ.

**E15. Planner isolation.** The planning function's inputs contain no evaluation workload or evaluation queue. Changing the evaluation stream leaves the frozen plan identical; scored results may change. The planner also runs successfully, producing the same frozen plan, when no evaluation data exist at all.

**E16. Long-deadline workload.** A Parks month has more arrivals than regular capacity, all with targets in 2026. The seasonal rule adds 0 crews, because no request is due within the month, so there is no on-time rate to protect. The hiring rule sees the residual volume, and the Parks restriction blocks any permanent hire starting in season. The work carries forward and appears in month-end open counts.

**E17. Scenario coupling.**
- Subset: every request in the minus 20% workload appears in the base workload with identical attributes.
- Superset: every base request appears in the plus 20% and spike workloads with identical attributes.
- Totals: each scenario's department-month counts equal the base counts times the scenario factor, rounded, exactly.
- Cell monotonicity: no type-day cell in the plus or spike workload has fewer requests than in base; no cell in the minus workload has more.
- Both compared plans are scored on the same workload object in each scenario.
- A unit test with weights [1, 3, 7] and totals 5 and 6 confirms the generator never produces the shrinking allocation.

---

## 9a. Implementation order

1. Complete the source-data audit (section 10.3) and confirm provider and model, component ownership, and topic sign-up.
2. Build workload generation and the simulator against the hand-calculated fixtures.
3. Implement staffing decisions and frozen-plan evaluation, with the full-dataset reconciliation checks.
4. Build the reviewed catalog and the intake workflow.
5. Run the notebook from a clean environment, then prepare the report and video.

## 10. Questions

### 10.1 Team decisions

| ID | Question | Answer |
|---|---|---|
| Q1 | Are trainees paid during their training month? An optional one-line Q&A forum check; does not block. | Yes, paid (configurable) |
| Q2 | Which spike scenario: snowstorm, heat wave, or both? | Snowstorm only |
| Q3 | Which "other consideration": neighborhood equity or employee vs resident requests? | Neighborhood equity |
| Q4 | Which provider and model (OpenAI or Gemini), and does everyone have access? | OpenAI |
| Q5 | Who owns each component (data, simulator and staffing, catalog and intake, evaluation, report, README and video)? | Andrew & Nicholas are doing report and video. John and Adam are doing tech build pieces |
| Q6 | Is Nicholas's topic sign-up confirmed? | Yes |

### 10.2 Defaults in use

- **Calendar:** synthetic 21-day operating calendar, first 21 weekdays with earliest Saturdays added, holidays ignored.
- **Arrivals:** uniform daily arrivals with largest-remainder rounding.
- **Target windows:** classes valid, missing, and invalid_ordering; no upper cutoff; fallback chain type (50 or more), then department (50 or more), then pooled.
- **No-target requests:** consume capacity, no penalties.
- **Hiring:** two-month persistence, hire the smaller shortage, no orders after the start of October.
- **Release:** four-month projected look-ahead requiring no added overdue events, no added projected cost, and no added end-of-horizon backlog; no notices after the start of August; at least 1 crew.
- **Seasonal:** the Parks service-floor rule uses the fewest crews that keep the month's due requests at least 93% on time, or the best reachable rate if 93% is impossible, with no cap. Parks permanent hires never start April to October.
- **Routing:** a 90% department share nominates a department mapping and a 90% queue share nominates a queue mapping, both for human approval. Types without a queue mapping are labeled assigned by location or assigned by department.
- **Retrieval:** TF-IDF first.
- **Sensitivity:** coupled workloads; the frozen plan and baseline are replayed; snowstorm spike.

### 10.3 Data audits (investigate directly)

- Capture the page's "Things to watch for in this data" section and its column list.
- Confirm the 2023 and 2024 files share the same 30 columns and department codes.
- List nominated mappings (90% or more) and exceptions (under 90%) for review and approval. Done 2026-10-22: 86 of 163 types qualify for a single queue, covering 60% of in-scope volume. A department mapping covers 79%. This led to the two-tier rule in section 5.6. Leaving out the INFO referral queues gives 132 department mappings (92% of volume) and 90 exact queues. Request for Pothole Repair stays unmapped: Public Works handles 84% of its handled requests and the Water and Sewer Commission 14%.
- Measure target classes per type and department: valid, missing, and invalid_ordering counts, and the window distribution, including long windows.
- Check whether the 2025 file is available for the stretch holdout.

### 10.4 Logistics

- Post a one-line Q&A forum check that pandas and scikit-learn are fine under the course-stack rule.
- Set a code freeze date before recording the video.

---

## 11. Approved changes and implementation decisions

This section is the record of what the team approved after the freeze and of the choices the build made where the spec was silent. The rules themselves are written into the sections above.

### 11.1 Approved changes

| Date | Change | Why | Decided by |
|---|---|---|---|
| 2026-10-28 | Agreement rule: the retrieval gate does not apply when the model's clear, in-scope pick is also the top-ranked retrieval candidate (section 5.7). The 0.15 threshold is unchanged | The gate exists to stop auto-routing when a message matches no official type well. When the model and retrieval independently agree on the same top type, a low score mostly reflects wording such as misspellings ("streetlite"). The trade-off is reliance on the model flagging out-of-scope messages, which it did for every out-of-scope dev and test message. Prompted by test example t13 (section 11.4) | John |
| 2026-10-27 | Overlapping types go to TRIAGE: if the model picks one type of a listed pair and the other was also retrieved, a person routes it (sections 5.6, 5.7, 6; `config.OVERLAPPING_TYPE_PAIRS`). Test example t22 and dev example d15 expect TRIAGE | Contractor Complaints / Contractors Complaint, Work Hours-Loud Noise Complaints / Working Beyond Hours, and Sidewalk Repair / Sidewalk Repair (Make Safe) describe the same problem but route differently (or one routes and one does not). Nothing in the data tells them apart, and the earlier prompt rule ("pick the first" near-duplicate) made the outcome depend on retrieval order. A code rule is deterministic and testable | John |
| 2026-10-27 | Classifier prompt rule 4 narrowed (`classify-v3`): "emergencies" means situations needing police, fire, or an ambulance; a hazard reported to a city department, such as a tree that may fall, stays in scope (section 5.7) | The old rule excluded all "emergencies", contradicting the approved Tree Emergencies type ("pose an immediate danger") and test example t12. The new wording matches the reviewed Carbon Monoxide and Fire in Food Establishment descriptions, which send active alarms and fires out of scope | John |
| 2026-10-23 | Parks seasonal rule became a 93% service floor (section 5.4, step 2) | Clearing every avoidable miss was very expensive, and both cost-driven alternatives gave poor service (section 5.4) | John |
| 2026-10-22 | Q5 corrected: John and Adam own the tech build | The original entry was a mistake | John |
| 2026-10-22 | Two-tier routing replaces the single-queue mapping rule (sections 5.6, 5.7, 5.8, 9, 10.2) | Only 86 of 163 types (60% of in-scope volume) have one queue with at least 90% of requests. About 18% of volume goes to district or region queues chosen by location, which text cannot determine, so potholes, street cleaning, and dead-animal pickup could never auto-route. Department mapping covers 79% of volume | John |
| 2026-10-22 | 311 INFO referral and reallocation queues are left out of the mapping denominator; a mapped department must still hold at least 50% of all requests (section 5.6) | INFO queues are referrals to MassDOT, DCR, MBTA, Eversource, and Massport, chosen by who owns the location, or resubmissions. They diluted common types below 90%: street cleaning was 89.5%, dead-animal pickup 85.8%, Parks ground maintenance 80.7%. Coverage rises from 122 to 132 types (79% to 92% of volume). The guard stops tiny, mostly referred types from mapping, such as Undefined Noise Disturbance (0.6% in scope). Potholes stay unmapped (Public Works 84%, Water and Sewer Commission 14%) | John |
| 2026-10-22 | Neighborhood exposure view added to the stretch list (section 8) | It goes beyond the core equity deliverable | John |

### 11.2 Data audit findings (2026-10-22)

- 2024 department counts match the project page exactly: PWDx 157,610, BTDT 81,447, PARK 18,736, ISD 18,624. On-time shares from the city's `on_time` flag also match: 90%, 50%, 93%, 72%.
- Both files have the same 30 columns. There are no duplicate case IDs, and every date parses as ISO 8601.
- No in-scope request has a target date before its open date, so the `invalid_ordering` class has 0 records in both years. The class stays in the code.
- Valid target windows range from 0 to 720 days. 58% of 2024 Parks windows are 365 days or longer.
- The city's `on_time` flag marks about 5,000 valid-target requests per year OVERDUE that closed on the target date but after the target time. The simulator uses this spec's calendar-date convention (closed on day T is on time). The historical statistics shown to residents use the city's flag, because it reproduces the page's on-time rates. The two kinds of on-time rate are therefore not directly comparable.
- The city last revised both files on 2026-09-18. Each run records the file checksums, and the processed tables are committed, so the notebook reproduces even if the source changes again.

### 11.3 Implementation decisions

These are choices made where the spec was silent. None changes a GIVEN rule or a staffing decision rule.

- **Model:** `gpt-6.1-sol` rejects any temperature but the default, so it runs at low reasoning effort with `seed=5250`. Exact reproducibility comes from offline replay of `data/demo/recordings.jsonl`. A recording's key covers the model, reasoning effort, seed, response schema, prompt and catalog versions, and the exact input, so a stale recording is never replayed. Recordings made before the key included reasoning effort, seed, and schema were migrated with provenance backfilled from git evidence (`scripts/migrate_recordings_v2.py`).
- **Tuning, dev set only:**
  - The alias prompt moved to `aliases-v2` after dev recall missed everyday synonyms ("lamp post", "recliner").
  - The classify prompt moved to `classify-v2`, adding rules for near-duplicate types and for not re-asking a location. `classify-v3` is the scope change in section 11.1.
  - The retrieval gate was set to 0.15. The lowest correct dev route scored 0.18 and out-of-scope messages about 0.10.
- **Penalty events in projections:** the seasonal rule and the release check count both $20 and $100 events.
- **Arrivals:**
  - Within one day, requests queue in type-ID order.
  - Scenario extras queue behind that day's base requests.
  - The snowstorm adds two extra requests per base request in each Public Works type-day cell on February 10 to 12, so each cell ends at exactly 3x.
- **Month-end inventory:** `open_overdue_end` (past target, under 30 days) and `open_long_overdue_end` (30+ days) are disjoint. Together with not-yet-due and no-target they partition `open_end`.
- **Neighborhoods:** for the equity analysis only, "Allston", "Brighton", "South Boston", and "Mattapan" are merged into their combined labels, and blank or citywide "Boston" becomes "Unspecified" (`config.NEIGHBORHOOD_ALIASES`).
- **Added module:** `src/boston311/equity.py`, for deliverable 6, which the spec's layout did not list. `scripts/` holds `build_data.py`, `build_catalog.py`, `build_eval_sets.py`, and `run_all.py`.
- **Not used:** the GenAI_Agents reference notebooks were not consulted or copied in this build.
- **Run manifests:** each run writes `outputs/manifests/run_<timestamp>.json`, which is gitignored. Only `reference_run_all.json`, the manifest of the run that produced the committed outputs, is tracked.

### 11.4 Test-set disclosure (2026-10-28)

The test set was run once after dev-set tuning. A later catalog review then reworded 11 types, and all classifications were re-recorded live with `classify-v3`. After that run, test example t13 ("streetlite broke on my block, its pitch black at nite") fell from a best retrieval score of 0.1504 to 0.1495, just under the 0.15 gate. The model still picked Street Light Outages with no ambiguity, but the assistant asked a clarifying question, and t13 has no scripted answer, so it counted as a miss.

t13's own type was not edited. TF-IDF weights each word by how many types use it, so removing about 40 aliases from other types shifted every score slightly; t13 had passed the gate by only 0.0004. Lowering the gate or editing t13 would have tuned on the test set, so neither was done. Instead, t13 showed that the gate can overrule a model pick that retrieval also ranks first, which led to the agreement rule (section 11.1). Because that logic revision was prompted by a test result, the test set is no longer strictly untouched. The gate threshold, the prompt, the catalog, and every test message were unchanged by it.

### 11.5 Catalog review (2026-10-27) and remaining exceptions

The team reviewed every nominated mapping, every description and alias set, and every evaluation example. The decisions are recorded in `data/catalog/catalog.json`; `data/catalog/mapping_review.csv` is regenerated from it.

| Item | Outcome |
|---|---|
| Department mappings (132 nominated) | 124 approved, 8 rejected. The 31 types that never met the rule stay `not_nominated` (approved to remain unmapped) |
| Exact queues (90 nominated) | 83 approved, 7 rejected. Every rejected queue belongs to a type whose department mapping was also rejected |
| "Assigned by location" labels (8) | All 8 confirmed: CE Collection, Ground Maintenance, Pick up Dead Animal, Request for Snow Plowing, Request for Snow Plowing (Emergency Responder), Requests for Street Cleaning, Snow/Ice Control, and Space Savers. Their District/Region queue shares are 82.8% to 100%. The label is derived from `location_queue_share` and has no status field, so the confirmation is recorded here |
| Descriptions and aliases (163) | 153 approved, 10 provisional. 11 types were reworded, for example Abandoned Bicycle now covers bicycles only, and Carbon Monoxide and Fire in Food Establishment now send active alarms and fires out of scope |
| Evaluation examples (40 test, 18 dev) | Six were relabeled: t20, t22, t25, t29, d10, and d15 |

**Rejected routing (8 types).** Big Buildings Recycling (INTERNAL), Follow-Up, Major System Failure, Notification, Phone Bank Service Inquiry, Sign Shop WO, Utility Call-In, and Walk-In Service Inquiry describe internal staff work or are undefined in the data. They never auto-route; a message classified as one of them goes to triage. Two other types first held as possible staff workflows, Capital Improvement Long Term and StreetLight Pole WO, were approved.

**Remaining exceptions (prototype limitations).**
- **Provisional wording (10 types):** Abandoned Vehicles, Contractor Complaints, Contractors Complaint, Follow-Up, Notification, Phone Bank Service Inquiry, Sign Shop WO, Walk-In Service Inquiry, Work Hours-Loud Noise Complaints, and Working Beyond Hours. `alias_status` does not change retrieval, so this wording is still indexed and shown to the model. Five have rejected routing and always go to triage. Four are in the overlapping pairs (section 5.6), which go to triage when both types of a pair are retrieved. Abandoned Vehicles routes to its approved exact queue.
- **Scooters and mopeds:** historical titles put scooters and mopeds under both Abandoned Bicycle and Abandoned Vehicles. The prototype describes them only under Abandoned Vehicles, which names an exact queue. The data does not establish that distinction.
- **What approval means:** an approval says a mapping is consistent with the 2023 to 2024 routing data and the agreed rules. It does not verify the city's service eligibility, and the rules set no minimum sample size, so some approved types rest on few requests.
- **Provisional acceptance:** `config.ACCEPT_PROVISIONAL_APPROVALS` is still True, but no department or queue mapping is provisional any more, so it has no effect on routing.
- **Evaluation independence:** the test and dev messages were written within the same build as the catalog wording, not independently of it. Six labels were corrected during the review, and the agreement rule was prompted by t13 (section 11.4). The results are a demonstration evaluation; a claim about new residents' messages would need a fresh held-out set.
- **One evaluation seed:** staffing results come from one planning seed and one evaluation seed. Other draws of target dates would change the numbers somewhat.
- **Live service:** the live model path was exercised by the recorded live classification runs and by mocked-HTTP tests of the real SDK wrapper. It has not been run as a service with real residents.

---

## 12. References

- Boston 311 project page: https://www.ai2lab.ai/courses/DADS5250/hackathon/
- Analyze Boston 311 Service Requests: https://data.boston.gov/dataset/311-service-requests
- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- GenAI_Agents Customer Support Agent: https://github.com/NirDiamant/GenAI_Agents/blob/main/all_agents_tutorials/customer_support_agent_langgraph.ipynb
- GenAI_Agents Contextual Quoting System: https://github.com/NirDiamant/GenAI_Agents/blob/main/all_agents_tutorials/contextual_quoting_agentic_system.ipynb
- GenAI_Agents license: https://raw.githubusercontent.com/NirDiamant/GenAI_Agents/main/LICENSE
