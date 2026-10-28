# Team review: routine approvals and remaining exceptions

**To approve items, use [the itemized approval checklist](team_review_approvals_itemized.md).** It lists each recommended department, exact queue, description/alias set, and evaluation example with its own unchecked decision box. This document holds the exceptions to review afterward.

Prepared by Codex on October 27, 2026, from the current catalog, processed routing counts, evaluation generator, classifier prompt, and full team review checklist. These are reviewer recommendations, not a record of completed human approval. No catalog statuses or application behavior have been changed.

Use this document as the working review list. Keep [the full checklist](team_review_checklist.md) as the inventory and evidence behind the decisions. Type IDs below identify entries in `data/catalog/catalog.json`.

At the final check, `docs/decisions.md` recorded round-1 approval of 14 department mappings, all eight location labels, and retaining all 31 unmapped types. Those changes were made separately while this shortlist was being prepared. The 122-department recommendation below includes those 14: **108 additional department approvals** remain in the routine batch. The round-1 record explicitly leaves exact queues provisional; the 82 queue approvals below are additional recommendations, not already recorded approvals.

## Recommended routine batch

| Area | Recommendation | Exact boundary |
|---|---|---|
| Department mappings | Approve 122 of 132 nominations | Every nominated department except the 10 types in groups 1–3 below |
| Exact queues | Approve 82 of 90 nominations | Every nominated exact queue except those belonging to the same 10 held types |
| Types without a mapping | Retain all 31 as `not_nominated` | This is approval to KEEP them unmapped, not to nominate or approve a route |
| Location-based labels | Confirm all 8 existing labels | Confirm the derived label independently of whether a type is appropriate for resident intake |
| Descriptions and aliases | Recommend keeping 133 of 163 entries | Every entry except the 30 type IDs in groups 1–8 below; this is a repository consistency review, not external verification of city service eligibility |
| Test/dev examples | Recommend accepting 51 of 58 examples | All except `t12`, `t20`, `t22`, `t25`, `t29`, `d10`, and `d15`; correct the checklist's empty-input display as described below |

The mapping audit independently recomputed nominations from `data/processed/type_queue_counts.csv`: all catalog request counts and department nominations matched, all nominated queues met the 90% rule, and no qualifying exact queue was omitted. Counts and shares pool 2023–2024. The agreed policy is at least 90% handled share and at least 50% overall share, not 95%. It sets no minimum sample size. A small sample remains a limitation, but is not by itself a reason to invent a new rejection rule. This checks consistency with the supplied data, not whether historical routing was operationally correct in every case.

The 10 held mapping types also meet the numerical rule. They remain open because their meaning or suitability for resident intake needs a decision. Keeping wording is separate from approving a route; aliases for an unmapped type can help identify it and send it to triage.

## Only these content decisions remain

### 1. Big Buildings Recycling (INTERNAL): 1 type

**T009.** Hold department/queue activation and wording together. There are only three requests, all pointing to `PWDx_WM_Mattress_Pickup`, while the type is explicitly internal recycling work. That is an unexplained destination mismatch, not just a low count.

**Recommended disposition:** do not approve the exact queue without supporting evidence. Decide whether to allow department-only routing or keep the type in triage. Do not interpret rejection of the queue alone as rejection of the department.

Decision / reviewer / date:

### 2. Staff workflows represented as resident requests: 8 types

| ID | Type |
|---|---|
| T013 | Capital Improvement Long Term |
| T029 | Follow-Up |
| T075 | Notification |
| T090 | Phone Bank Service Inquiry |
| T128 | Sign Shop WO |
| T135 | StreetLight Pole WO |
| T155 | Utility Call-In |
| T158 | Walk-In Service Inquiry |

**Decision needed:** are these valid destinations for new resident messages, or records of an internal process? The titles and counts alone do not settle that. Notification includes fire and BWSC event titles, while the classifier excludes emergencies and BWSC main breaks. Some entries describe inquiries even though the prompt excludes general questions.

**Recommended disposition:** approve only the types whose resident use the team can explain from evidence. Otherwise keep routing unapproved and remove or narrow unsupported resident-style aliases. This does not imply that all queues containing `(INTERNAL)` are unsuitable; normal housing complaints legitimately map to such queues in this dataset.

Decision / reviewer / date:

### 3. Major System Failure: 1 type

**T053.** The description admits that the data does not define this category, but aliases such as “a major system has stopped working” are broad enough to match unrelated problems.

**Recommended disposition:** remove the generic aliases; retain only wording specific to the official category. Resolve intended use before approving automatic routing. Do not invent a meaning from the department name.

Decision / reviewer / date:

### 4. Similar wording can select different departments: 4 types

- **T020 / T021:** Contractor Complaints / Contractors Complaint. The first is unmapped; the second routes to ISD.
- **T160 / T162:** Work Hours-Loud Noise Complaints / Working Beyond Hours. Similar construction-hours wording routes to PWDx versus ISD.

**Recommended disposition:** define the distinguishing context if the data supports one, or use clarification/triage when it is unknown. Do not invent a distinction. The current prompt's “pick the first” near-duplicate instruction is not adequate evidence that these categories are interchangeable. The numerical mapping nominations themselves can be accepted independently.

Decision / reviewer / date:

### 5. Overlap changes routing or hides a category boundary: 7 types

- **T025 / T050:** Empty Litter Basket / Litter Basket Maintenance. Both currently describe a full basket; one triages and one routes.
- **T125 / T126:** Sidewalk Repair / Sidewalk Repair (Make Safe). Overlapping damage descriptions can route or triage.
- **T037 / T085:** Ground Maintenance / Parks General Request. Both describe weeds and park upkeep; one routes and one triages.
- **T129:** Snow/Ice Control. Only two examples support a broad description overlapping the ordinary street-plowing and unshoveled-sidewalk categories. Clarify its purpose before accepting its broad aliases; its numerical mapping is consistent with the rule.

**Recommended disposition:** resolve the ambiguous wording and acceptable outcomes together. Do not accept routing and triage as interchangeable merely to preserve a score. Review affected test examples in group 9.

Decision / reviewer / date:

### 6. Scooter/moped ambiguity: 2 types

**T001 / T003:** Abandoned Bicycle / Abandoned Vehicles. Historical titles explicitly support scooters/mopeds under BOTH categories, so removing that wording from one category without evidence would invent a distinction. One category gives a department-assigned queue; the other names the AVRS queue.

**Recommended disposition:** approve ordinary bicycle/car wording, but resolve how scooter/moped ambiguity affects queue specificity. If no supported distinguishing detail exists, use a conservative department-level result or triage rather than claiming an exact queue is established. This is an implementation decision if the existing graph cannot express it.

Decision / reviewer / date:

### 7. Technical terms expanded beyond established meaning: 2 types

- **T092 Pickup/Clear Conduit:** aliases assume removal of discarded electrical tubing. The name could also describe clearing installed conduit; the current evidence does not establish the intended interpretation.
- **T096 Pole Compliance:** aliases broaden this to utility poles and unspecified placement rules; its recorded queue is Public Works street-light pole compliance.

**Recommended disposition:** narrow to supported official wording unless further source evidence establishes those expansions. Department/queue associations can be approved separately.

Decision / reviewer / date:

### 8. Reconcile catalog wording with the prompt's scope exclusions: 5 types

**T014 Carbon Monoxide; T028 Fire in Food Establishment; T103 Rat Bite; T110 Request for Snow Plowing (Emergency Responder); T142 Tree Emergencies.**

The prompt excludes emergencies and medical issues, while some aliases describe an active incident or immediate danger. These are real catalog categories; this is not a recommendation to delete them or change their historical mappings.

**Recommended disposition:** document the distinction between a permitted municipal service report and an excluded emergency/medical request. Verify examples on both sides. Review `t12`'s expected route for an apparently imminent falling branch against that distinction. Use the existing triage path for excluded inputs; no new emergency-service integration is proposed here.

Decision / reviewer / date:

### 9. Seven evaluation examples need a specific decision

| ID | What needs resolution |
|---|---|
| t12 | Expected Tree Emergencies route versus the prompt's emergency exclusion; resolve with group 8 |
| t20 | Mice running in a restaurant kitchen is a premises condition; justify accepting the food-contamination category as an alternate without any explicit contaminated-food statement |
| t22 | Accepting Sidewalk Repair (Make Safe) permits a different route/triage outcome from the main label; resolve with group 5 |
| t25 | Full basket can match either maintenance or emptying and can route or triage; resolve with group 5 |
| t29 | Explicit mice complaint accepts an insect-oriented Pest Infestation category as an alternate; remove that alternate unless evidence supports it |
| d10 | A sign knocked over is still present; justify accepting Missing Sign as an alternate |
| d15 | Sidewalk damage after clarification has the same route/triage ambiguity as t22 |

Accepting the other 51 examples means their text, labels, and scripted answers are reasonable for this demonstration. It does not turn them into independently authored examples or establish generalization to new residents. Do not tune aliases/prompts from held-out test text and then continue describing that test as untouched. Document corrected labels and review-driven tuning honestly; use a fresh held-out set if making a new generalization claim.

Decision / reviewer / date:

## Mechanical corrections, not additional team debates

- In the full checklist, show `t39` as empty string, `t40` as whitespace-only, and `d18` as empty; all expect `REJECTED`, not `TRIAGE`.
- Distinguish department rejection (no auto-route) from queue rejection (approved department can still route without an exact queue).
- For aliases, “reject” must mean deleting/replacing wording or implementing explicit exclusion. `alias_status` alone does not prevent indexing or inclusion in model candidates.
- Apply only actual recorded decisions. Preserve `not_nominated` for unqualified types; do not set every status field to approved/rejected indiscriminately.
- Rebuild the catalog, then run `python scripts/build_eval_sets.py` after approved changes to mappings or evaluation definitions. `run_all.py` does not regenerate those JSONL files.
- Check recording coverage after changes to input text or candidate descriptions/aliases. Obtain authentic new recordings where needed before claiming offline replay is complete; do not re-key old answers as new inference.
- Disable provisional acceptance only when the remaining nominations have explicit dispositions. Run the regression checks and report changed metrics, including coverage and denominators.
- Preserve the completed review with reviewer names, dates, reasons for exceptions, and the reviewed catalog version/hash. Remove pending wording only for completed items; retain the full checklist as an archive.

Report finalization, a code-freeze date, and any outstanding course logistics are still human deliverables, not catalog decisions that this audit can approve.
