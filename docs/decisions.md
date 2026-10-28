# Decision Log

Team decisions and approvals (for example reviewed catalog mappings). The frozen design is in [architecture.md](architecture.md).

## Data audit findings (2026-10-22)

These were checked directly in the data and need no spec change.

- 2024 department counts match the project page exactly: PWDx 157,610, BTDT 81,447, PARK 18,736, ISD 18,624. On-time shares from the city's `on_time` flag also match: 90%, 50%, 93%, 72%.
- Both files have the same 30 columns. There are no duplicate case IDs, and every date parses as ISO 8601.
- No in-scope request has a target date before its open date, so the `invalid_ordering` class has 0 records in both years. The class stays in the code.
- Valid target windows range from 0 to 720 days. 58% of 2024 Parks windows are 365 days or longer.
- The city's `on_time` flag marks about 5,000 valid-target requests per year OVERDUE that closed on the target date but after the target time. The simulator uses the spec's calendar-date convention (closed on day T counts as on time). The historical service statistics shown to residents use the city's flag, because it reproduces the page's on-time rates.
- The city last revised both files on 2026-09-18. Each run records the file checksums, and the processed tables are committed so the notebook reproduces even if the source changes again.

## Parks seasonal rule (2026-10-23)

**The problem.** The spec's original rule added seasonal crews until no avoidable overdue request remained. Parks requests are served in arrival order, and many carry year-long targets, so short-deadline requests wait behind them. Removing every avoidable miss therefore meant clearing the whole queue every service day:
- 32 seasonal crews in August, 95 crew-months in all;
- Parks at $2.44M, against $1.75M for January crews all year.

**Two cost-driven alternatives were tested and rejected:**
- **"Add a crew only while it saves more in penalties than its $13,000 cost."** No single crew ever does: a crew-month closes at most 126 requests, each worth at most $120 in penalties. The rule bought zero seasonal crews. The backlog grew all season, and in October the hiring rule ordered 27 permanent crews. Parks came to $2.57M with 29% on time, worse on both counts.
- **"Minimize seasonal cost plus projected penalties."** Parks came to $1.82M, but with only 32% on time. The $20 penalty is too small to value timely service.

**The decision.** Service matters as much as cost or more. So the target is set first, and cost decides only how to meet it. We used the department's own 2024 on-time rate of 93% (GIVEN on the project page) as a "no worse than last year" floor.

**Frontier** (`outputs/parks_seasonal_frontier.csv`; Parks only, base evaluation workload):

| Rule | Parks cost | Annual on-time | Seasonal crew-months |
|---|---|---|---|
| January crews all year | $1.75M | 21.3% | 0 |
| Floor 50% | $1.78M | 73.1% | 33 |
| Floor 90% | $1.84M | 93.7% | 40 |
| **Floor 93% (chosen)** | **$1.86M** | **95.4%** | **42** |
| Floor 95% | $1.95M | 96.7% | 49 |
| Floor 97% | $2.13M | 97.2% | 71 |
| Every avoidable miss (original) | $2.44M | 97.8% | 95 |

**What the frontier shows.**
- Up to the 93% floor, service is cheap: about $14K per extra on-time point.
- Above it, cost rises steeply: $69K per point to reach 95%, and over $360K per point beyond that.
- The 85% floor is slightly cheaper than 80%. That is because the full re-plan reacts to the seasonal choice through later hiring, so neighbouring targets can swap order.

## Provisional reviews (pending team review)

- **Mappings:** every nominated department and queue mapping in `data/catalog/catalog.json` has status `provisional`. Reviewers change it to `approved` or `rejected`; `data/catalog/mapping_review.csv` lists one row per type. Routing treats `provisional` as approved while `config.ACCEPT_PROVISIONAL_APPROVALS` is True.
- **Aliases:** descriptions and aliases for all 163 types were drafted with prompt `aliases-v1`, and every one was read. Seven were edited:
  - Pest Infestation, Rodent Activity, Animal Generic Request, Public Works General Request and General Lighting Request had aliases that described other, more specific official types. Those aliases were removed.
  - CE Collection and Major System Failure have no meaning documented in the data. Their wording was reduced to neutral text rather than invented.
- **Test and dev sets:** written before any tuning, and never used as aliases.

### Team review, round 1 (2026-10-27)

None of these changes a result: routing treats `approved` and `provisional` the same while `ACCEPT_PROVISIONAL_APPROVALS` is True.

- **Department mappings approved (14):** Parking Enforcement, Abandoned Vehicles, Parking Meter Repairs and Pavement Marking Maintenance (Transportation); Improper Storage of Trash (Barrels), Mattress_Pickup, Schedule a Bulk Item Pickup, Missed Trash/Recycling/Yard Waste/Bulk Item and Unshoveled Sidewalk (Public Works); Unsatisfactory Living Conditions, Heat - Excessive Insufficient, Mice Infestation - Residential, Chronic Dampness/Mold and Bed Bugs (Inspectional Services). `department_status` is now `approved` for these. Their exact-queue mappings were not part of this approval and stay `provisional`.
- **"Assigned by location" labels approved (8):** CE Collection, Ground Maintenance, Pick up Dead Animal, Request for Snow Plowing, Request for Snow Plowing (Emergency Responder), Requests for Street Cleaning, Snow/Ice Control and Space Savers. Their recorded District/Region queue shares (82.8% to 100%) support the label. This approves the routing label only, independently of the aliases and of what residents are eligible for. The label is derived from `location_queue_share` and has no status field, so the approval is recorded here. The eight department mappings themselves stay `provisional`.
- **Unmapped types (31): approve retaining `not_nominated`.** All 31 fail the current nomination rules. This approval keeps them unmapped; it is not permission to create a mapping for any of them.

### Test example t13 after the review (2026-10-28, accepted as is)

After the review's wording edits and the `classify-v3` prompt, all 66 classifications were re-recorded live. Test decision accuracy fell from 40/40 to 39/40, and type accuracy from 33/34 to 32/34. Both drops are t13, "streetlite broke on my block, its pitch black at nite".

- **What changed:** the model still picks Street Light Outages with no ambiguity. But the message's best retrieval score fell from 0.1504 to 0.1495, just under the 0.15 retrieval gate, so the assistant now asks one clarifying question. t13 has no scripted answer, so the evaluation ends at that question and counts it as a miss.
- **Why the score moved:** t13's own type was not edited. TF-IDF weights each word by how many types use it, so removing about 40 aliases from other types (the bike-only Abandoned Bicycle wording and the ten reworded types) shifted every score slightly. t13 had passed the gate by only 0.0004.
- **Accepted, not tuned:** the gate was tuned on the dev set only (see "Tuning, dev set only" below), and spec 5.8 forbids tuning on the test set. Lowering the gate or editing t13 to recover the point would do exactly that, so the result stands.
- **Other changes in the same run:** t22 and d15 now go to TRIAGE under the overlapping-types rule, as intended. This also changes the denominators of the coverage, department, and queue metrics.

## Implementation notes for reviewers

These are choices made where the spec was silent. None changes a GIVEN rule or a staffing decision rule.

- **Model:** `gpt-6.1-sol` rejects any temperature but the default, so it runs at low reasoning effort with `seed=5250`. Exact reproducibility comes from offline replay of `data/demo/recordings.jsonl`. Recording keys include the model, the prompt and catalog versions, and the exact input, so a stale recording is never replayed.
- **Tuning, dev set only:**
  - The alias prompt moved to v2 after dev recall missed everyday synonyms ("lamp post", "recliner").
  - The classify prompt moved to v2, adding rules for near-duplicate types and for not re-asking a location.
  - The retrieval gate was set to 0.15. The lowest correct dev route scored 0.18 and out-of-scope messages about 0.10.
  - The test set was run once, after tuning.
- **Penalty events in projections:** the seasonal rule and the release check count both $20 and $100 events.
- **Arrivals:**
  - Within one day, requests queue in type-ID order.
  - Scenario extras queue behind that day's base requests.
  - The snowstorm adds two extra requests per base request in each Public Works type-day cell on February 10 to 12, so each cell ends at exactly 3x.
- **Month-end inventory:** `open_overdue_end` (past target, under 30 days) and `open_long_overdue_end` (30+ days) are disjoint. Together with not-yet-due and no-target they partition `open_end`.
- **Neighborhoods:** for the equity analysis only, "Allston", "Brighton", "South Boston" and "Mattapan" are merged into their combined labels, and blank or citywide "Boston" becomes "Unspecified" (`config.NEIGHBORHOOD_ALIASES`).
- **Added module:** `src/boston311/equity.py`, for deliverable 6, which the spec's layout did not list. `scripts/` holds `build_data.py`, `build_catalog.py`, `build_eval_sets.py`, and `run_all.py`.
- **Not used:** the GenAI_Agents reference notebooks were not consulted or copied in this build.
- **Repairs after the code review (2026-10-23):** findings R1–R6 were fixed on branch `repair/astra-review` with no change to the spec or to any published number. See `docs/review_guide.md` section 7.
  - **Run manifests:** each run writes `outputs/manifests/run_<timestamp>.json`, which is gitignored. Only `reference_run_all.json`, the manifest of the run that produced the committed outputs, is tracked.
  - **Recordings:** the recording key now covers model, reasoning effort, seed, and response schema. Existing recordings were migrated with provenance backfilled from git evidence (`scripts/migrate_recordings_v2.py`).

## Spec changes

| Date | Change | Why | Decided by |
|---|---|---|---|
| 2026-10-27 | Overlapping types go to TRIAGE: if the model picks one type of a listed pair and the other was also retrieved, a person routes it (sections 5.6, 5.7, 6; `config.OVERLAPPING_TYPE_PAIRS`). Test example t22 now expects TRIAGE, as d15 does | Team review: Contractor Complaints / Contractors Complaint, Work Hours-Loud Noise Complaints / Working Beyond Hours, and Sidewalk Repair / Sidewalk Repair (Make Safe) describe the same problem but route differently (or one routes and one does not). Nothing in the data tells them apart, and prompt rule 8 ("pick the first" near-duplicate) made the outcome depend on retrieval order. A code rule is deterministic and testable and leaves the prompt alone | John |
| 2026-10-27 | Classifier prompt rule 4 narrowed (`classify-v3`): "emergencies" means situations needing police, fire, or an ambulance; a hazard reported to a city department, such as a tree that may fall, stays in scope (section 5.7) | The old rule excluded all "emergencies", contradicting the approved Tree Emergencies type ("pose an immediate danger") and test example t12. The new wording also matches the reviewed Carbon Monoxide and Fire in Food Establishment descriptions, which send active alarms and fires out of scope | John |
| 2026-10-23 | Parks seasonal rule became a 93% service floor: the fewest seasonal crews keeping each in-season month's due requests at least 93% on time, or the best reachable rate (spec 5.4 step 2) | See "Parks seasonal rule" below | John |
| 2026-10-22 | Q5 corrected: John and Adam own the tech build, not Andrew and John | The original entry was a mistake | John |
| 2026-10-22 | Two-tier routing replaces the single-queue mapping rule (sections 5.6, 5.7, 5.8, 9, 10.2) | Audit: only 86 of 163 types (60% of in-scope volume) have one queue with at least 90% of requests. About 18% of volume goes to district or region queues chosen by location, which text cannot determine, so potholes, street cleaning and dead-animal pickup could never auto-route. Department mapping covers 79% of volume | John |
| 2026-10-22 | 311 INFO referral and reallocation queues are left out of the mapping denominator. A mapped department must still hold at least 50% of all requests (section 5.6) | INFO queues are referrals to MassDOT, DCR, MBTA, Eversource and Massport, chosen by who owns the location, or resubmissions. They diluted common types below 90%: street cleaning was 89.5%, dead-animal pickup 85.8%, Parks ground maintenance 80.7%. Coverage rises from 122 to 132 types (79% to 92% of volume). The guard stops tiny, mostly referred types from mapping, such as Undefined Noise Disturbance (0.6% in scope). Potholes stay unmapped (Public Works 84%, Water and Sewer Commission 14%) | John |
| 2026-10-22 | Neighborhood exposure view added to the section 8 stretch list | Came up while defining the core neighborhood equity analysis. It goes beyond the core deliverable, so it is tracked as stretch rather than built now | John |
