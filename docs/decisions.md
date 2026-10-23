<!-- [AI-authored: Claude] scaffold -->
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

## Provisional reviews by Claude (pending team review)

- **Mappings:** every nominated department and queue mapping in `data/catalog/catalog.json` has status `provisional`. Reviewers change it to `approved` or `rejected`; `data/catalog/mapping_review.csv` lists one row per type. Routing treats `provisional` as approved while `config.ACCEPT_PROVISIONAL_APPROVALS` is True.
- **Aliases:** the LLM (gpt-6.1-sol, prompt `aliases-v1`) drafted descriptions and aliases for all 163 types, and Claude read every one. Seven were edited:
  - Pest Infestation, Rodent Activity, Animal Generic Request, Public Works General Request and General Lighting Request had aliases that described other, more specific official types. Those aliases were removed.
  - CE Collection and Major System Failure have no meaning documented in the data. Their wording was reduced to neutral text rather than invented.
- **Test and dev sets:** written by Claude, labeled AI-authored, before any tuning, and never used as aliases.

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

## Spec changes

| Date | Change | Why | Decided by |
|---|---|---|---|
| 2026-10-22 | Q5 corrected: John and Adam own the tech build, not Andrew and John | The original entry was a mistake | John |
| 2026-10-22 | Two-tier routing replaces the single-queue mapping rule (sections 5.6, 5.7, 5.8, 9, 10.2) | Audit: only 86 of 163 types (60% of in-scope volume) have one queue with at least 90% of requests. About 18% of volume goes to district or region queues chosen by location, which text cannot determine, so potholes, street cleaning and dead-animal pickup could never auto-route. Department mapping covers 79% of volume | John |
| 2026-10-22 | 311 INFO referral and reallocation queues are left out of the mapping denominator. A mapped department must still hold at least 50% of all requests (section 5.6) | INFO queues are referrals to MassDOT, DCR, MBTA, Eversource and Massport, chosen by who owns the location, or resubmissions. They diluted common types below 90%: street cleaning was 89.5%, dead-animal pickup 85.8%, Parks ground maintenance 80.7%. Coverage rises from 122 to 132 types (79% to 92% of volume). The guard stops tiny, mostly referred types from mapping, such as Undefined Noise Disturbance (0.6% in scope). Potholes stay unmapped (Public Works 84%, Water and Sewer Commission 14%) | John |
| 2026-10-22 | Neighborhood exposure view added to the section 8 stretch list | Came up while defining the core neighborhood equity analysis. It goes beyond the core deliverable, so it is tracked as stretch rather than built now | John |
