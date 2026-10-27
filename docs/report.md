<!-- Draft. Every number comes from outputs/ (python scripts/run_all.py, offline mode). -->
# Staffing Boston's 311 City Service Teams: analysis and justification (draft)

## 1. Summary

We built a month-by-month 2025 crew plan for Public Works (PWDx), Transportation (BTDT), Parks & Recreation (PARK), and Inspectional Services (ISD). We also built a GenAI intake assistant that routes residents' messages to an official request type and department.

**Against keeping January's crews all year, on a separate evaluation workload the planner never saw:**

| | Frozen plan | January crews all year |
|---|---|---|
| Total 2025 cost (crews + severance + penalties) | **$16.39M** | $19.47M |
| Share of requests due in 2025 closed on time | **89.5%** | 22.4% |
| Requests still open on December 31 | 1,441 | 27,579 |

* **What the plan does:** hires 20 Public Works, 8 Transportation, 9 Inspectional Services, and 1 Parks crew, with every hire ordered by August.
* **Parks:** covers its April-to-October peak with 42 seasonal crew-months. They are sized to keep each month's due requests at least 93% on time, Parks' own 2024 rate, and Parks reaches 95.4% on time for $1.86M.
* **Releases:** none, because the release test never passes.
* **Transportation**, the department the project page singles out, goes from 12% to 89% on time, and its cost falls from $6.79M to $2.91M because penalties shrink.

**Intake assistant.** On a 40-message test set never used for tuning:
* 40/40 correct decisions (route, triage, or reject);
* 33/34 correct request types;
* 29/30 auto-routes correct (96.7% precision).

Results are a demonstration evaluation on messages pending team review.

## 2. Data

* **Sources:** the 2023 and 2024 files of Analyze Boston's *311 Service Requests*, fetched through the CKAN API. The MD5 checksums the city publishes are verified on download, and both files were last revised by the city on 2026-09-18.
* **Cleaning:** we keep the four departments and deduplicate by case ID; the audit found no duplicates.
* **Reconciliation:** our 2024 counts match the project page exactly: 157,610 / 81,447 / 18,736 / 18,624.
* **Target classes:** 11% of 2024 in-scope requests have no target date. None have a target before their open date.
* **Target windows** run from 0 to 720 days. 58% of 2024 Parks targets are a year or longer.

## 3. Forecast

* **Method:** seasonal naive, where each 2025 month equals the same month of 2024.
* **Why:** with two years of history no fancier model can be validated fairly.
* **Backtest** (the same method predicting 2024 from 2023):

| Department | Mean absolute % error by month | Annual bias |
|---|---|---|
| PWDx | 13.6% | +8.7% |
| BTDT | 7.6% | −7.5% |
| PARK | 17.7% | −6.4% |
| ISD | 13.3% | −2.7% |

The ±20% sensitivity scenarios bracket these errors.

## 4. How plans are evaluated

* **Daily simulator.** Every plan runs through the same daily, first-in-first-out simulator.
  * Crews close up to capacity on 21 service days a month: the first 21 weekdays, plus the earliest Saturdays when a month has fewer.
  * A $20 penalty applies at the end of a request's target day if it is still open, and a further $100 thirty days later.
* **Synthetic workloads.** Monthly forecasts become individual requests with exact rounding.
  * Each request's deadline is drawn from its type's 2023-2024 history.
  * The **planning** workload and the **evaluation** workloads come from independent random streams, and the planner sees only the planning workload.
  * The ±20% and snowstorm workloads are built from the base evaluation workload by only adding or removing requests. This way, differences between scenarios come from demand alone.
* **Accounting checks.** These run on every plan and scenario and all pass:
  * request flow: start open + arrivals = closed + end open;
  * workforce: every start and departure is matched to an order or notice one month earlier;
  * penalties: at most one of each kind per request;
  * costs: the components sum to the total.

## 5. The staffing policy

At the start of each month the planner projects its own queue forward and decides, in this order:

1. **Seasonal crews (Parks, April to October):** the fewest crews that keep the month's due requests at least 93% on time, or the best rate unlimited capacity could reach if 93% is impossible. See section 5a for why.
2. **Hire** only if a shortage is projected in *both* of the next two months, and then only the smaller shortage.
   * *Why two months:* a hire costs a paid training month plus three months of severance if released (k + 4 months of pay for k productive months), so one-month spikes are not worth a permanent crew.
   * Hiring stops after October. Parks never starts a permanent crew in season, because seasonal crews are cheaper over any in-season span (1.3k < k + 4 for k ≤ 7).
3. **Release** only if no hire was ordered this month and a five-month projection shows all three of the following:
   * no more penalty events;
   * no higher cost, with severance included;
   * no bigger backlog.

   Releases stop after August.

**Why no releases happened.** Demand rises from spring to an August and September peak. By the last month a release is allowed, August, the projection still sees the September peak, so no release passes. One consequence is idle capacity late in the year:
* Public Works runs at 58–69% utilisation in October to December, and Inspectional Services at 59–60% in November and December.
* This is the price of the "no notices after August" terminal rule combined with a 25% severance.

## 5a. Balancing cost and service: the Parks seasonal target

This is a public service: timely delivery matters as much as cost, or more. Minimizing cost alone does not reflect that. The challenge's $20 overdue penalty is small next to a $13,000 seasonal crew-month, so a cost-only rule simply accepts most misses. We tested two such rules and rejected both:
* **"Add a crew only while it saves more than it costs."** No single crew ever saves that much, so the rule bought no seasonal crews. Later, 27 permanent crews were hired in October to clear the backlog. Parks came to $2.57M with 29% on time.
* **"Minimize seasonal cost plus penalties."** Parks came to $1.82M with 32% on time.

We therefore set a **service target first and let cost decide only how to meet it**. The target is Parks' own 2024 on-time rate, 93%: no worse than last year.

The frontier below re-makes the whole plan for each target and scores Parks on the base evaluation workload:

| Seasonal rule | Parks cost | Parks on-time | Seasonal crew-months |
|---|---|---|---|
| January crews all year | $1.75M | 21.3% | 0 |
| Floor 50% | $1.78M | 73.1% | 33 |
| Floor 90% | $1.84M | 93.7% | 40 |
| **Floor 93% (chosen)** | **$1.86M** | **95.4%** | **42** |
| Floor 95% | $1.95M | 96.7% | 49 |
| Floor 97% | $2.13M | 97.2% | 71 |
| Remove every avoidable miss (original spec rule) | $2.44M | 97.8% | 95 |

* **Up to 93%,** service is cheap: going from 21% to 95% on time costs about $117K more than doing nothing.
* **Beyond 93%,** each extra point costs $69K to $480K.
* **The 93% floor gives up 2.4 on-time points** against the original rule and saves $575K.

## 6. Sensitivity

The frozen plan, without re-planning, replayed on each scenario:

| Scenario | Plan cost | Plan on-time | Baseline cost | Baseline on-time |
|---|---|---|---|---|
| Base | $16.39M | 89.5% | $19.47M | 22.4% |
| Demand +20% | $20.85M | 12.2% | $33.20M | 7.9% |
| Demand −20% | $16.12M | 94.5% | $13.09M | 75.4% |
| Snowstorm (PWDx ×3, Feb 10–12) | $16.76M | 81.7% | $20.36M | 15.7% |

* **+20%:** the frozen plan cannot keep up. Backlogs push most short-deadline requests past target, although cost stays well below the baseline's.
* **−20%:** the frozen plan is overstaffed, and keeping January's crews would have been cheaper.
* **Snowstorm:** the extra Public Works volume lowers its on-time rate from 89% to 75% for the year, while costing only $0.37M more.

Both directions argue for reactive re-planning, which is a stretch item.

## 7. The intake assistant

* **Retrieval.** TF-IDF over official type names, descriptions, and reviewed aliases (RAG) finds the 8 closest of 163 official types.
* **Classification.** `gpt-6.1-sol` proposes one candidate through strict structured output.
* **Code decides.** The code validates the proposal and chooses the department and queue itself:
  * it routes only through reviewed mappings;
  * it asks at most one clarifying question, using a LangGraph interrupt;
  * otherwise it triages.

**Two-tier routing**, a spec change decided after the data audit. In the city's own routing, about 18% of in-scope volume goes to *district or region* queues chosen by the address. In addition, some requests are referred out by the 311 centre (INFO) to MassDOT, DCR, the MBTA, and others.
* We therefore route to a **department** when that department handled at least 90% of a type's handled requests (and at least 50% of all its requests).
* We name an **exact queue** only when one queue handled at least 90%. Otherwise the reply says the queue is "assigned by location" or "assigned by the department".
* **Coverage:** 132 of 163 types, which is 92% of volume.
* **Potholes stay unrouted:** Public Works handles 84% of them and the Water and Sewer Commission 14%. A pothole report is classified correctly but sent to a person.

**Results:**

| Metric | Test (40) | Dev (18) |
|---|---|---|
| Decision accuracy | 40/40 (100%) | 18/18 |
| Type accuracy | 33/34 (97%) | 15/15 |
| Department accuracy | 30/31 (97%) | 12/13 |
| Exact-queue accuracy | 19/20 (95%) | 8/8 |
| Queue-label accuracy | 10/11 (91%) | 4/5 |
| Auto-route precision | 29/30 (97%) | 12/12 |
| Auto-route coverage | 30/31 (97%) | 12/13 |
| Clarification rate | 8/40 (20%) | 3/18 |
| Triage rate | 8/40 (20%) | 5/18 |

**The two test errors:**
* "the restaurant on the corner has mice running around the kitchen" became Rodent Activity instead of a food-establishment sanitation type.
* An overflowing bus-stop trash can became the near-duplicate "Empty Litter Basket". That type has no single department, so the message was triaged rather than routed.

**Aliases matter.** Dev-set candidate recall at 8 is 100% with aliases and 47% without. The first alias draft missed everyday words ("lamp post", "recliner"), so the alias prompt was revised on the dev set only.

## 8. Other consideration: neighborhood equity

Using 2023-2024 data, we compare each neighborhood's on-time rate with the rate it would have had if every request were served at its type's citywide rate (mix adjustment).
* **Public Works, Parks, and Inspectional Services:** gaps stay within ±4.4 points.
* **Transportation varies most:** West Roxbury is 13.3 points below its expected rate, and South Boston / Waterfront 10.8 points above.

This is descriptive, not causal: reporting channels and employee-generated requests may differ by neighborhood, and there is no population data.

## 9. Limitations and open questions

* **Challenge model.** Capacities, costs, starting crews, and penalties are assignment assumptions, and the calendar is synthetic.
* **Scoring workloads are synthetic.** The plan is scored on synthetic workloads, not real 2025 requests. A 2025 holdout is stretch.
* **The 93% Parks target is a policy choice, not an optimum.** Another target moves along the frontier in section 5a. The frontier itself depends on the challenge's assumed costs and penalties.
* **Hiring looks at volume, not deadlines.** The hiring rule counts every arriving request, including Parks requests with year-long deadlines. Where the seasonal rule leaves a backlog, the rule can still order permanent crews in October, as the rejected cost-only rule showed.
* **Pending review.** The mappings, the aliases, and the eval messages are provisional, pending team review.
* **Synthetic workload contents.** No-target requests use capacity but carry no penalty, as a labelled assumption. Synthetic requests have no neighborhood, so equity is analysed historically only.
