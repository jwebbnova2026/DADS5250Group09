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

## Spec changes

| Date | Change | Why | Decided by |
|---|---|---|---|
| 2026-10-22 | Q5 corrected: John and Adam own the tech build, not Andrew and John | The original entry was a mistake | John |
| 2026-10-22 | Two-tier routing replaces the single-queue mapping rule (sections 5.6, 5.7, 5.8, 9, 10.2) | Audit: only 86 of 163 types (60% of in-scope volume) have one queue with at least 90% of requests. About 18% of volume goes to district or region queues chosen by location, which text cannot determine, so potholes, street cleaning and dead-animal pickup could never auto-route. Department mapping covers 79% of volume | John |
| 2026-10-22 | Neighborhood exposure view added to the section 8 stretch list | Came up while defining the core neighborhood equity analysis. It goes beyond the core deliverable, so it is tracked as stretch rather than built now | John |
