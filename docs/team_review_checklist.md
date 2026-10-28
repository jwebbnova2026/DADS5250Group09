# Team review checklist

Everything in the repository that is still provisional, in the order it should be reviewed.
Fill in the **Decision** column: `approve`, `reject`, or `change: ...`. Claude applies the decisions to
`data/catalog/catalog.json` (the source; `mapping_review.csv` is regenerated from it) and to
`scripts/build_eval_sets.py`, reruns everything, and reports any change in results.

Generated from `data/catalog/mapping_review.csv` and `scripts/build_eval_sets.py`. Counts and shares cover 2023 and 2024 combined.

## Summary

| # | What | Count | Where it lives |
|---|---|---|---|
| 1a | Department mappings that need a close look | 46 | `catalog.json` `department_status` |
| 1b | Clear-cut department mappings (skim) | 86 | same |
| 1c | Exact-queue mappings that need a close look (queue share under 95%) | 20 | `catalog.json` `queue_status_review` |
| 1d | Clear-cut exact-queue mappings (skim) | 70 | same |
| 1e | Location-based routing labels | 8 | derived; confirm only |
| 1f | Types not mapped (always triage): sanity check | 31 | `not_nominated` |
| 2 | Aliases and descriptions (keep, edit, or delete; no reject) | 163 | `catalog.json` `aliases` |
| 3 | Test and dev messages | 40 + 18 | `scripts/build_eval_sets.py` |
| 4 | Spec 10.1 and 10.2 open questions | 2 sections | `docs/architecture.md` |
| 5 | Report title "(draft)" | 1 | `docs/report.md` |
| 6 | Spec 10.4 logistics (forum check, code-freeze date) | 2 | `docs/review_guide.md` |

Rules the code used: a department is nominated when it handled at least 90% of the handled
requests (INFO referral queues left out) **and** at least 50% of all requests. An exact queue is
nominated when one queue had at least 90%. Approving a nomination does not change any result;
rejecting one sends that type to triage and can change the intake scores.

## 1a. Department mappings that need a close look (46)

Flag key: **close** = handled share under 95% or all-requests share under 60% (near a cut-off);
**small** = fewer than 30 requests in 2023-2024, so the share rests on very little data;
**internal?** = the name suggests a staff work-order type a resident would not file.

| Type | Requests | Dept | Handled share | All-requests share | Flags | Decision |
|---|---:|---|---:|---:|---|---|
| Pick up Dead Animal | 15,300 | PWDx | 93.7% | 85.8% | close |  |
| Rodent Activity | 8,950 | ISD | 93.8% | 93.2% | close |  |
| Pest Infestation - Residential | 3,470 | ISD | 92.1% | 91.3% | close |  |
| Contractors Complaint | 2,027 | ISD | 93.7% | 92.2% | close |  |
| Public Works General Request | 1,357 | PWDx | 91.0% | 85.3% | close |  |
| Street Light Knock Downs | 951 | PWDx | 93.5% | 85.1% | close |  |
| Short Term Rental | 501 | ISD | 93.6% | 87.4% | close |  |
| Work Hours-Loud Noise Complaints | 416 | PWDx | 93.1% | 91.3% | close |  |
| General Traffic Engineering Request | 307 | BTDT | 95.0% | 91.9% | close |  |
| Abandoned Building | 163 | ISD | 92.6% | 92.0% | close |  |
| Sewage/Septic Back-Up | 92 | ISD | 93.5% | 93.5% | close |  |
| Bridge Maintenance | 21 | PWDx | 94.7% | 85.7% | close, small |  |
| Occupying W/Out A Valid CO/CI | 17 | ISD | 94.1% | 94.1% | close, small |  |
| Requests for Directional or Roadway Changes | 12 | BTDT | 90.9% | 83.3% | close, small |  |
| StreetLight Pole WO | 303 | PWDx | 100.0% | 99.0% | internal? |  |
| No Utilities Residential - Gas | 29 | ISD | 100.0% | 96.5% | small |  |
| Scanning Overcharge | 28 | ISD | 100.0% | 100.0% | small |  |
| Lead | 27 | ISD | 100.0% | 100.0% | small |  |
| Rental Unit Delivery Conditions | 27 | ISD | 100.0% | 100.0% | small |  |
| Misc. Snow Complaint | 25 | PWDx | 96.0% | 96.0% | small |  |
| Phone Bank Service Inquiry | 23 | BTDT | 100.0% | 100.0% | small, internal? |  |
| Item Price Missing | 22 | ISD | 100.0% | 100.0% | small |  |
| Mechanical | 21 | ISD | 100.0% | 100.0% | small |  |
| No Utilities - Food Establishment - Flood | 19 | ISD | 100.0% | 100.0% | small |  |
| Unit Pricing Wrong/Missing | 16 | ISD | 100.0% | 93.8% | small |  |
| Carbon Monoxide | 15 | ISD | 100.0% | 100.0% | small |  |
| Valet Parking Problems | 14 | BTDT | 100.0% | 100.0% | small |  |
| Private Parking Lot Complaints | 11 | BTDT | 100.0% | 100.0% | small |  |
| No Price on Gas/Wrong Price | 10 | ISD | 100.0% | 100.0% | small |  |
| Pickup/Clear Conduit | 10 | PWDx | 100.0% | 100.0% | small |  |
| Product Short Measure | 8 | ISD | 100.0% | 100.0% | small |  |
| No Utilities - Food Establishment - Sewer | 7 | ISD | 100.0% | 100.0% | small |  |
| No Utilities - Food Establishment - Electricity | 5 | ISD | 100.0% | 100.0% | small |  |
| Student Overcrowding | 5 | ISD | 100.0% | 100.0% | small |  |
| Walk-In Service Inquiry | 5 | BTDT | 100.0% | 100.0% | small, internal? |  |
| Scale Not Visible | 4 | ISD | 100.0% | 100.0% | small |  |
| Short Measure - Gas | 4 | ISD | 100.0% | 100.0% | small |  |
| Big Buildings Recycling (INTERNAL) | 3 | PWDx | 100.0% | 100.0% | small, internal? |  |
| News Boxes | 3 | PWDx | 100.0% | 100.0% | small |  |
| Utility Call-In | 3 | PWDx | 100.0% | 100.0% | small, internal? |  |
| Capital Improvement Long Term | 2 | PARK | 100.0% | 100.0% | small, internal? |  |
| Snow/Ice Control | 2 | PWDx | 100.0% | 100.0% | small |  |
| Water in Gas - High Priority | 2 | ISD | 100.0% | 100.0% | small |  |
| Follow-Up | 1 | ISD | 100.0% | 100.0% | small, internal? |  |
| Oil Truck - No Receipt | 1 | ISD | 100.0% | 100.0% | small |  |
| Sign Shop WO | 1 | BTDT | 100.0% | 100.0% | small, internal? |  |

## 1b. Clear-cut department mappings (86)

At least 95% handled share, at least 60% of all requests, and 30 or more requests. A skim is enough.

| Type | Requests | Dept | Handled share | All-requests share | Decision |
|---|---:|---|---:|---:|---|
| Parking Enforcement | 119,925 | BTDT | 99.8% | 99.7% | approved 2026-10-27 |
| Requests for Street Cleaning | 44,324 | PWDx | 97.0% | 89.5% |  |
| Improper Storage of Trash (Barrels) | 39,920 | PWDx | 99.5% | 99.1% | approved 2026-10-27 |
| Mattress_Pickup | 36,547 | PWDx | 100.0% | 100.0% | approved 2026-10-27 |
| CE Collection | 33,551 | PWDx | 99.7% | 99.0% |  |
| Schedule a Bulk Item Pickup | 25,116 | PWDx | 100.0% | 100.0% | approved 2026-10-27 |
| Missed Trash/Recycling/Yard Waste/Bulk Item | 23,181 | PWDx | 100.0% | 99.9% | approved 2026-10-27 |
| Poor Conditions of Property | 17,001 | PWDx | 99.2% | 98.6% |  |
| Tree Maintenance Requests | 15,614 | PARK | 95.8% | 93.0% |  |
| Schedule a Bulk Item Pickup SS | 12,755 | PWDx | 100.0% | 100.0% |  |
| Sign Repair | 11,263 | BTDT | 97.7% | 90.4% |  |
| Abandoned Vehicles | 9,432 | BTDT | 99.3% | 98.7% | approved 2026-10-27 |
| Street Light Outages | 9,075 | PWDx | 97.5% | 90.5% |  |
| Request for Recycling Cart | 8,276 | PWDx | 100.0% | 100.0% |  |
| Traffic Signal Inspection | 8,212 | BTDT | 98.6% | 85.0% |  |
| Ground Maintenance | 8,020 | PARK | 96.0% | 80.7% |  |
| Recycling Cart Return | 7,632 | PWDx | 100.0% | 100.0% |  |
| Illegal Dumping | 6,151 | PWDx | 99.5% | 99.0% |  |
| Equipment Repair | 5,880 | PARK | 96.0% | 83.4% |  |
| Unsatisfactory Living Conditions | 5,229 | ISD | 99.0% | 98.8% | approved 2026-10-27 |
| New Tree Requests | 4,895 | PARK | 99.5% | 98.8% |  |
| Sticker Request | 4,666 | PWDx | 100.0% | 100.0% |  |
| Unshoveled Sidewalk | 4,202 | PWDx | 98.2% | 97.5% | approved 2026-10-27 |
| Abandoned Bicycle | 2,245 | BTDT | 98.8% | 97.3% |  |
| General Lighting Request | 2,081 | PWDx | 99.0% | 97.0% |  |
| New Sign  Crosswalk or Pavement Marking | 1,902 | BTDT | 96.2% | 92.0% |  |
| Work w/out Permit | 1,762 | ISD | 98.9% | 94.2% |  |
| Tree Emergencies | 1,726 | PARK | 99.8% | 97.4% |  |
| Heat - Excessive  Insufficient | 1,669 | ISD | 100.0% | 100.0% | approved 2026-10-27 |
| Requests for Traffic Signal Studies or Reviews | 1,332 | BTDT | 98.5% | 92.3% |  |
| Working Beyond Hours | 1,237 | ISD | 99.0% | 97.7% |  |
| Electrical | 1,234 | ISD | 100.0% | 100.0% |  |
| Building Inspection Request | 1,230 | ISD | 99.0% | 97.5% |  |
| Unsanitary Conditions - Establishment | 1,184 | ISD | 99.7% | 98.9% |  |
| Transportation General Request | 1,184 | BTDT | 96.2% | 95.7% |  |
| Maintenance Complaint - Residential | 1,050 | ISD | 98.2% | 98.0% |  |
| Request for Snow Plowing | 1,046 | PWDx | 98.9% | 95.9% |  |
| Missing Sign | 838 | BTDT | 98.9% | 96.4% |  |
| Roadway Repair | 817 | PWDx | 96.5% | 94.7% |  |
| Unsafe Dangerous Conditions | 786 | ISD | 97.3% | 95.2% |  |
| Mice Infestation - Residential | 776 | ISD | 99.9% | 99.9% | approved 2026-10-27 |
| Major System Failure | 584 | PWDx | 99.5% | 93.8% |  |
| Chronic Dampness/Mold | 575 | ISD | 100.0% | 100.0% | approved 2026-10-27 |
| Protection of Adjoining Property | 534 | ISD | 97.5% | 95.3% |  |
| Food Alert - Confirmed | 480 | ISD | 100.0% | 99.8% |  |
| Unsatisfactory Utilities - Electrical  Plumbing | 472 | ISD | 99.2% | 99.2% |  |
| Unsanitary Conditions - Food | 436 | ISD | 99.1% | 99.1% |  |
| Park Improvement Requests | 417 | PARK | 99.0% | 96.9% |  |
| Construction Debris | 404 | PWDx | 96.5% | 96.0% |  |
| Illegal Vending | 357 | PWDx | 95.7% | 94.1% |  |
| Knockdown Replacement | 317 | PWDx | 95.2% | 94.6% |  |
| Space Savers | 316 | PWDx | 97.1% | 95.9% |  |
| Pavement Marking Inspection | 309 | BTDT | 98.3% | 95.8% |  |
| Exceeding Terms of Permit | 292 | ISD | 95.8% | 93.8% |  |
| Maintenance - Homeowner | 277 | ISD | 98.2% | 97.1% |  |
| Food Alert - Unconfirmed | 273 | ISD | 100.0% | 99.6% |  |
| Request for Litter Basket Installation | 252 | PWDx | 95.9% | 93.2% |  |
| No Utilities Residential - Water | 224 | ISD | 98.7% | 98.7% |  |
| Cross Metering - Sub-Metering | 223 | ISD | 100.0% | 100.0% |  |
| Bed Bugs | 215 | ISD | 100.0% | 100.0% | approved 2026-10-27 |
| Litter Basket Maintenance | 205 | PWDx | 97.9% | 92.2% |  |
| Illegal Occupancy | 200 | ISD | 100.0% | 99.0% |  |
| Illegal Rooming House | 186 | ISD | 99.5% | 98.9% |  |
| Egress | 178 | ISD | 96.0% | 95.5% |  |
| Notification | 157 | ISD | 96.1% | 94.3% |  |
| Sidewalk Repair | 151 | PWDx | 99.3% | 98.0% |  |
| Squalid Living Conditions | 145 | ISD | 95.8% | 95.2% |  |
| Tree in Park | 137 | PARK | 100.0% | 99.3% |  |
| No Utilities Residential - Electricity | 133 | ISD | 100.0% | 100.0% |  |
| Plumbing | 129 | ISD | 100.0% | 100.0% |  |
| Bicycle Issues | 100 | BTDT | 100.0% | 100.0% |  |
| Unsanitary Conditions - Employees | 97 | ISD | 100.0% | 100.0% |  |
| Pole Compliance | 80 | PWDx | 100.0% | 100.0% |  |
| Fire in Food Establishment | 76 | ISD | 100.0% | 100.0% |  |
| Parking Meter Repairs | 75 | BTDT | 100.0% | 100.0% | approved 2026-10-27 |
| Zoning | 69 | ISD | 97.1% | 97.1% |  |
| Poor Ventilation | 66 | ISD | 98.4% | 95.5% |  |
| Pavement Marking Maintenance | 64 | BTDT | 100.0% | 100.0% | approved 2026-10-27 |
| Upgrade Existing Lighting | 59 | PWDx | 100.0% | 93.2% |  |
| Cemetery Maintenance Request | 58 | PARK | 100.0% | 100.0% |  |
| Install New Lighting | 57 | PWDx | 98.1% | 91.2% |  |
| Request for Snow Plowing (Emergency Responder) | 51 | PWDx | 100.0% | 94.1% |  |
| Overcrowding | 50 | ISD | 100.0% | 100.0% |  |
| Rat Bite | 32 | ISD | 100.0% | 100.0% |  |
| No Utilities - Food Establishment - Water | 31 | ISD | 100.0% | 100.0% |  |
| Planting | 30 | PARK | 100.0% | 100.0% |  |

## 1c. Exact-queue mappings that need a close look (20)

One queue had 90% to 95% of the type's requests.

| Type | Requests | Queue | Queue share | Decision |
|---|---:|---|---:|---|
| New Tree Requests | 4,895 | PARK_New Tree Requests | 90.1% | |
| Sewage/Septic Back-Up | 92 | ISD_Housing (INTERNAL) | 90.2% | |
| Mechanical | 21 | ISD_Building (INTERNAL) | 90.5% | |
| Install New Lighting | 57 | PWDx_Street Light_Install New Lighting | 90.6% | |
| Work Hours-Loud Noise Complaints | 416 | PWDx_Work Hours-Loud Noise Complaints | 90.7% | |
| Maintenance - Homeowner | 277 | ISD_Building (INTERNAL) | 92.0% | |
| Overcrowding | 50 | ISD_Housing (INTERNAL) | 92.0% | |
| Egress | 178 | ISD_Building (INTERNAL) | 92.1% | |
| Park Improvement Requests | 417 | PARK_Park Improvement Requests | 92.2% | |
| Building Inspection Request | 1,230 | ISD_Building (INTERNAL) | 92.7% | |
| Knockdown Replacement | 317 | PWDx_Street Light Knockdown Replacement | 92.7% | |
| Squalid Living Conditions | 145 | ISD_Housing (INTERNAL) | 93.1% | |
| Contractors Complaint | 2,027 | ISD_Building (INTERNAL) | 93.1% | |
| Rodent Activity | 8,950 | ISD_Environmental Services (INTERNAL) | 93.2% | |
| Poor Ventilation | 66 | ISD_Housing (INTERNAL) | 93.8% | |
| Occupying W/Out A Valid CO/CI | 17 | ISD_Building (INTERNAL) | 94.1% | |
| Exceeding Terms of Permit | 292 | ISD_Building (INTERNAL) | 94.4% | |
| Bridge Maintenance | 21 | PWDx_Bridge Maintenance | 94.7% | |
| Illegal Dumping | 6,151 | PWDx_Code Enforcement | 94.8% | |
| Construction Debris | 404 | PWDx_Code Enforcement | 94.8% | |

## 1d. Clear-cut exact-queue mappings (70)

| Type | Requests | Queue | Queue share | Decision |
|---|---:|---|---:|---|
| Parking Enforcement | 119,925 | BTDT_Parking Enforcement | 99.3% | |
| Improper Storage of Trash (Barrels) | 39,920 | PWDx_Code Enforcement | 96.7% | |
| Mattress_Pickup | 36,547 | PWDx_WM_Mattress_Pickup | 100.0% | |
| Schedule a Bulk Item Pickup | 25,116 | PWDx_Schedule a Bulk Item Pickup | 100.0% | |
| Missed Trash/Recycling/Yard Waste/Bulk Item | 23,181 | PWDx_Missed Trash\Recycling\Yard Waste\Bulk Item | 99.0% | |
| Poor Conditions of Property | 17,001 | PWDx_Code Enforcement | 97.9% | |
| Schedule a Bulk Item Pickup SS | 12,755 | PWDx_Schedule a Bulk Item Pickup | 100.0% | |
| Abandoned Vehicles | 9,432 | BTDT_AVRS Interface Queue | 97.5% | |
| Unsatisfactory Living Conditions | 5,229 | ISD_Housing (INTERNAL) | 98.0% | |
| Sticker Request | 4,666 | PWDx_Sticker Request | 100.0% | |
| Unshoveled Sidewalk | 4,202 | PWDx_Code Enforcement | 97.0% | |
| General Lighting Request | 2,081 | PWDx_Street Light_General Lighting Request | 96.3% | |
| Work w/out Permit | 1,762 | ISD_Building (INTERNAL) | 98.4% | |
| Tree Emergencies | 1,726 | PARK_Tree Emergencies | 97.1% | |
| Heat - Excessive  Insufficient | 1,669 | ISD_Housing (INTERNAL) | 99.8% | |
| Working Beyond Hours | 1,237 | ISD_Building (INTERNAL) | 98.6% | |
| Unsanitary Conditions - Establishment | 1,184 | ISD_Health (INTERNAL) | 98.1% | |
| Maintenance Complaint - Residential | 1,050 | ISD_Housing (INTERNAL) | 96.2% | |
| Mice Infestation - Residential | 776 | ISD_Housing (INTERNAL) | 96.7% | |
| Major System Failure | 584 | PWDx_Major System Failure | 96.0% | |
| Chronic Dampness/Mold | 575 | ISD_Housing (INTERNAL) | 99.8% | |
| Protection of Adjoining Property | 534 | ISD_Building (INTERNAL) | 96.0% | |
| Food Alert - Confirmed | 480 | ISD_Health (INTERNAL) | 100.0% | |
| Unsatisfactory Utilities - Electrical  Plumbing | 472 | ISD_Housing (INTERNAL) | 97.7% | |
| Unsanitary Conditions - Food | 436 | ISD_Health (INTERNAL) | 98.6% | |
| Illegal Vending | 357 | PWDx_Code Enforcement | 95.7% | |
| Food Alert - Unconfirmed | 273 | ISD_Health (INTERNAL) | 100.0% | |
| Request for Litter Basket Installation | 252 | PWDx_Request for Litter Basket Installation | 95.5% | |
| No Utilities Residential - Water | 224 | ISD_Housing (INTERNAL) | 97.3% | |
| Cross Metering - Sub-Metering | 223 | ISD_Housing (INTERNAL) | 100.0% | |
| Bed Bugs | 215 | ISD_Housing (INTERNAL) | 99.5% | |
| No Utilities Residential - Electricity | 133 | ISD_Housing (INTERNAL) | 97.7% | |
| Bicycle Issues | 100 | BTDT_BostonBikes | 98.0% | |
| Unsanitary Conditions - Employees | 97 | ISD_Health (INTERNAL) | 100.0% | |
| Pole Compliance | 80 | PWDx_STRL Pole Compliance | 98.8% | |
| Fire in Food Establishment | 76 | ISD_Health (INTERNAL) | 96.0% | |
| Parking Meter Repairs | 75 | BTDT_Broken Meter Complaints | 100.0% | |
| Zoning | 69 | ISD_Building (INTERNAL) | 95.7% | |
| Pavement Marking Maintenance | 64 | BTDT_Pavement Marking_Maintenance | 96.9% | |
| Cemetery Maintenance Request | 58 | PARK_Cemetery Maintenance Request | 98.3% | |
| Rat Bite | 32 | ISD_Environmental Services (INTERNAL) | 96.9% | |
| No Utilities - Food Establishment - Water | 31 | ISD_Health (INTERNAL) | 100.0% | |
| No Utilities Residential - Gas | 29 | ISD_Housing (INTERNAL) | 96.4% | |
| Scanning Overcharge | 28 | ISD_Weights and Measures (INTERNAL) | 100.0% | |
| Rental Unit Delivery Conditions | 27 | ISD_Housing (INTERNAL) | 96.3% | |
| Lead | 27 | ISD_Housing (INTERNAL) | 100.0% | |
| Misc. Snow Complaint | 25 | PWDx_Snow Cases | 96.0% | |
| Phone Bank Service Inquiry | 23 | BTDT_OPC_Phone Bank Service | 100.0% | |
| Item Price Missing | 22 | ISD_Weights and Measures (INTERNAL) | 95.5% | |
| No Utilities - Food Establishment - Flood | 19 | ISD_Health (INTERNAL) | 100.0% | |
| Unit Pricing Wrong/Missing | 16 | ISD_Weights and Measures (INTERNAL) | 100.0% | |
| Carbon Monoxide | 15 | ISD_Housing (INTERNAL) | 100.0% | |
| Valet Parking Problems | 14 | BTDT_Parking Lot_Valet Parking Problems | 100.0% | |
| Private Parking Lot Complaints | 11 | BTDT_Parking Lot_PrivateParkingLotComplaints | 100.0% | |
| No Price on Gas/Wrong Price | 10 | ISD_Weights and Measures (INTERNAL) | 100.0% | |
| Pickup/Clear Conduit | 10 | PWDx_Street Light_Pickup_Clear Conduit | 100.0% | |
| Product Short Measure | 8 | ISD_Weights and Measures (INTERNAL) | 100.0% | |
| Student Overcrowding | 5 | ISD_Housing (INTERNAL) | 100.0% | |
| Walk-In Service Inquiry | 5 | BTDT_OPC_Walk-In Service | 100.0% | |
| No Utilities - Food Establishment - Electricity | 5 | ISD_Health (INTERNAL) | 100.0% | |
| Short Measure - Gas | 4 | ISD_Weights and Measures (INTERNAL) | 100.0% | |
| Scale Not Visible | 4 | ISD_Weights and Measures (INTERNAL) | 100.0% | |
| News Boxes | 3 | PWDx_News Boxes | 100.0% | |
| Big Buildings Recycling (INTERNAL) | 3 | PWDx_WM_Mattress_Pickup | 100.0% | |
| Utility Call-In | 3 | PWDx_Utility Call-In | 100.0% | |
| Capital Improvement Long Term | 2 | PARK_Park Improvement Requests | 100.0% | |
| Water in Gas - High Priority | 2 | ISD_Weights and Measures (INTERNAL) | 100.0% | |
| Follow-Up | 1 | ISD_Administrative | 100.0% | |
| Oil Truck - No Receipt | 1 | ISD_Weights and Measures (INTERNAL) | 100.0% | |
| Sign Shop WO | 1 | BTDT_Sign Shop Clerical | 100.0% | |

## 1e. Location-based routing labels (8)

No single queue reached 90%, but most requests went to District or Region queues, so the
assistant says "assigned by location" instead of naming a queue. Confirm the label makes sense.

| Type | Dept | Share in District/Region queues | Decision |
|---|---|---:|---|
| CE Collection | PWDx | 98.0% | approved 2026-10-27 (routing label only) |
| Ground Maintenance | PARK | 85.8% | approved 2026-10-27 (routing label only) |
| Pick up Dead Animal | PWDx | 95.5% | approved 2026-10-27 (routing label only) |
| Request for Snow Plowing | PWDx | 89.9% | approved 2026-10-27 (routing label only) |
| Request for Snow Plowing (Emergency Responder) | PWDx | 91.7% | approved 2026-10-27 (routing label only) |
| Requests for Street Cleaning | PWDx | 82.8% | approved 2026-10-27 (routing label only) |
| Snow/Ice Control | PWDx | 100.0% | approved 2026-10-27 (routing label only) |
| Space Savers | PWDx | 85.6% | approved 2026-10-27 (routing label only) |

## 1f. Types not mapped (31)

These always go to triage. The rules held them back, but check that none of them is a mistake.
**Near misses:** 9 of them reached 80% or more for an in-scope department but fell short
of 90%: Request for Pothole Repair (83.7%); Sidewalk Repair (Make Safe) (89.9%); Empty Litter Basket (88.4%); Contractor Complaints (87.0%); Student Move-in Issues (89.8%); Parks General Request (84.6%); Illegal Posting of Signs (87.6%); Municipal Parking Lot Complaints (82.8%); Mosquitoes (West Nile) (88.2%).
Mapping one of these would mean overriding the 90% rule for it, which is a spec change.

| Type | Requests | Top dept | Handled share | All-requests share | Decision |
|---|---:|---|---:|---:|---|
| Request for Pothole Repair | 22,448 | PWDx | 83.7% | 75.4% | approve retaining not_nominated (2026-10-27) |
| Needle Pickup | 18,149 | GEN | 99.9% | 99.8% | approve retaining not_nominated (2026-10-27) |
| Sidewalk Repair (Make Safe) | 11,281 | PWDx | 89.9% | 85.0% | approve retaining not_nominated (2026-10-27) |
| Animal Generic Request | 6,899 | INFO | 65.0% | 0.2% | approve retaining not_nominated (2026-10-27) |
| Empty Litter Basket | 5,768 | PWDx | 88.4% | 83.8% | approve retaining not_nominated (2026-10-27) |
| Graffiti Removal | 4,362 | PROP | 98.7% | 96.8% | approve retaining not_nominated (2026-10-27) |
| PWD Graffiti | 2,850 | PWDx | 78.1% | 68.5% | approve retaining not_nominated (2026-10-27) |
| Contractor Complaints | 2,631 | PWDx | 87.0% | 84.3% | approve retaining not_nominated (2026-10-27) |
| General Comments For a Program or Policy | 1,754 | PWDx | 48.4% | 47.1% | approve retaining not_nominated (2026-10-27) |
| Catchbasin | 1,207 | BWSC | 98.2% | 96.8% | approve retaining not_nominated (2026-10-27) |
| Parks Lighting/Electrical Issues | 914 | PARK | 54.3% | 44.0% | approve retaining not_nominated (2026-10-27) |
| BWSC General Request | 618 | BWSC | 97.9% | 97.4% | approve retaining not_nominated (2026-10-27) |
| Utility Casting Repair | 616 | PWDx | 67.8% | 62.7% | approve retaining not_nominated (2026-10-27) |
| Sidewalk Cover / Manhole | 562 | BWSC | 96.2% | 89.0% | approve retaining not_nominated (2026-10-27) |
| General Comments For An Employee | 449 | PWDx | 63.5% | 61.3% | approve retaining not_nominated (2026-10-27) |
| Illegal Auto Body Shop | 358 | PWDx | 49.4% | 48.0% | approve retaining not_nominated (2026-10-27) |
| Parking on Front/Back Yards (Illegal Parking) | 355 | PWDx | 76.4% | 74.7% | approve retaining not_nominated (2026-10-27) |
| Traffic Signal Repair | 326 | BTDT | 76.3% | 60.1% | approve retaining not_nominated (2026-10-27) |
| Student Move-in Issues | 319 | PWDx | 89.8% | 68.7% | approve retaining not_nominated (2026-10-27) |
| Parks General Request | 302 | PARK | 84.6% | 72.5% | approve retaining not_nominated (2026-10-27) |
| Overflowing or Un-kept Dumpster | 224 | PWDx | 75.2% | 74.6% | approve retaining not_nominated (2026-10-27) |
| Illegal Posting of Signs | 206 | PWDx | 87.6% | 85.9% | approve retaining not_nominated (2026-10-27) |
| Undefined Noise Disturbance | 180 | INFO | 100.0% | 0.6% | approve retaining not_nominated (2026-10-27) |
| BWSC Pothole | 168 | BWSC | 98.8% | 95.8% | approve retaining not_nominated (2026-10-27) |
| No-Tow Complaint Confirmation | 137 | PWDx | 72.4% | 70.8% | approve retaining not_nominated (2026-10-27) |
| Trash on Vacant Lot | 117 | PWDx | 78.2% | 73.5% | approve retaining not_nominated (2026-10-27) |
| Rooftop & Mechanical Disturbances | 61 | INFO | 100.0% | 3.3% | approve retaining not_nominated (2026-10-27) |
| Pigeon Infestation | 43 | ISD | 75.9% | 51.2% | approve retaining not_nominated (2026-10-27) |
| Municipal Parking Lot Complaints | 29 | BTDT | 82.8% | 82.8% | approve retaining not_nominated (2026-10-27) |
| Mosquitoes (West Nile) | 24 | ISD | 88.2% | 62.5% | approve retaining not_nominated (2026-10-27) |
| City/State Snow Issues | 21 | INFO | 100.0% | 4.8% | approve retaining not_nominated (2026-10-27) |

## 2. Aliases and descriptions (163)

The everyday phrasings retrieval matches residents' words against. Check that each alias really
means this type and not a neighbouring one. Full descriptions are in `catalog.json`.

**There is no "reject" for aliases.** The code does not check `alias_status`: retrieval and the
classifier use every alias in `catalog.json` whatever its status. To get rid of a bad alias it
must be deleted or reworded. So the Decision here is `ok`, or the aliases to delete or reword
(for example `delete: moped left behind`).

Any alias or description change alters what the classifier is shown, so the recorded answers no
longer match: `CATALOG_VERSION` is bumped and the test, dev, and demo classifications are
re-recorded live (a few dollars of API use), and the intake scores may move.

| Type | Aliases | Decision |
|---|---|---|
| Abandoned Bicycle | abandoned bicycle; bike left for months; abandoned scooter; moped left behind; old bike nobody has moved; bicycle looks abandoned | |
| Abandoned Building | abandoned building; deserted house; vacant building looks abandoned; boarded up abandoned house; empty property falling apart; nobody lives in this abandoned building | |
| Abandoned Vehicles | abandoned car; motorcycle left for months; abandoned moped or scooter; RV looks abandoned; trailer left behind; several abandoned vehicles; car nobody has moved | |
| Animal Generic Request | animal question; need help with an animal; animal concern | |
| BWSC General Request | water service question; sewer service concern; question about city water; need help with water service; water and sewer inquiry; general sewer question | |
| BWSC Pothole | pothole by water utility work; hole in road after sewer work; pothole around a sewer cover; road dip around water cover; pothole in water main repair patch; sunken pavement after water work | |
| Bed Bugs | bed bugs in my apartment; bedbug infestation; bugs in my mattress; found bed bugs; bedbugs in the bedroom; bed bugs in my building | |
| Bicycle Issues | bike lane safety concern; bicycle lane complaint; biking feels unsafe here; question about city bike programs; cycling safety issue; problem with bike lanes; general bicycle question | |
| Big Buildings Recycling (INTERNAL) | large building recycling question; apartment building recycling inquiry; recycling in a big building; recycling for large residential buildings; large property recycling request; building recycling program question | |
| Bridge Maintenance | bridge needs repair; damaged bridge railing; bridge surface is deteriorating; broken bridge handrail; bridge walkway needs maintenance; loose parts on the bridge; bridge is falling apart | |
| Building Inspection Request | building inspection request; need a building inspected; check building conditions; construction inspection needed; concerns about building safety; inspect the building | |
| CE Collection | CE collection request; CE pickup needed; follow up on CE collection; request a CE pickup; CE collection still pending | |
| Capital Improvement Long Term | park needs major improvements; long term park renovation; recreation facility needs an upgrade; request major park upgrades; park needs a complete overhaul; recreation center renovation request | |
| Carbon Monoxide | carbon monoxide concern; possible carbon monoxide leak; CO in the building; carbon monoxide alarm went off; high carbon monoxide reading; worried about carbon monoxide indoors | |
| Catchbasin | clogged storm drain; blocked catch basin; street drain not draining; broken drain grate; leaves blocking the storm drain; water pooling around the catch basin; missing catch basin cover | |
| Cemetery Maintenance Request | cemetery needs maintenance; overgrown cemetery grass; burial ground needs upkeep; trash on cemetery grounds; cemetery path needs repair; fallen branches in the cemetery; graveyard grounds are neglected | |
| Chronic Dampness/Mold | mold on the walls; apartment is always damp; mildew in my home; musty smell won't go away; mold keeps coming back; walls stay wet; black spots growing on the ceiling; persistent moisture indoors | |
| City/State Snow Issues | snow issue on city property; snow problem on state property; city or state snow responsibility; snow clearing on state land; city property needs snow cleared; who handles snow on state property | |
| Construction Debris | construction debris left outside; pile of renovation waste; discarded drywall and lumber; building rubble on the sidewalk; roofing shingles left behind; scrap wood from construction; demolition debris piled up | |
| Contractor Complaints | complaint about a contractor; contractor did poor work; construction crew causing problems; contractor left work unfinished; concern about contractor behavior; problems with hired construction workers; unhappy with contractor's work | |
| Contractors Complaint | complaint about a contractor; contractor did poor quality work; problems with my building contractor; contractor left work unfinished; unhappy with renovation contractor; report a home improvement contractor | |
| Cross Metering - Sub-Metering | paying for another apartment's electricity; my meter covers someone else's unit; shared electric meter problem; utility meters connected to wrong apartments; problem with my utility submeter; being charged for shared utilities | |
| Egress | blocked building exit; fire escape is obstructed; can't get out through exit door; stuff blocking the exit stairs; emergency exit won't open; hallway exit blocked | |
| Electrical | exposed electrical wires; outlet is sparking; unsafe wiring in my apartment; breaker keeps tripping; loose electrical socket; light switch gives me a shock; electrical panel problem | |
| Empty Litter Basket | public trash can is overflowing; street litter basket needs emptying; park garbage bin is full; please empty the sidewalk trash basket; overflowing public waste bin; trash spilling out of park basket | |
| Equipment Repair | broken playground equipment; park swing needs repair; slide is damaged; seesaw is broken; play structure needs fixing; broken equipment at the park; playground climbing frame is damaged | |
| Exceeding Terms of Permit | work exceeds the building permit; construction beyond approved permit; doing work not covered by permit; building more than the permit allows; contractor ignoring permit limits; project doesn't match approved permit | |
| Fire in Food Establishment | fire at a restaurant; restaurant kitchen had a fire; fire in a food business; report a fire at a cafe; there was a fire in the bakery; food establishment fire incident | |
| Follow-Up | follow up on my inspection complaint; checking on my existing building complaint; update on my inspection case; more information about my earlier complaint; still waiting on my inspection issue; question about an existing inspection case | |
| Food Alert - Confirmed | confirmed food safety alert; confirmed alert about unsafe food; food product has a confirmed safety alert; confirmed food contamination alert; confirmed food warning; confirmed safety alert for a food business | |
| Food Alert - Unconfirmed | possible unsafe food; unsanitary food handling; restaurant food safety concern; food may be contaminated | |
| General Comments For An Employee | complaint about a city worker; city employee was helpful; rude city staff member; compliment for a city employee; feedback about a city worker; staff member treated me poorly | |
| General Comments For a Program or Policy | feedback on a city program; complaint about city policy; suggestion for a city program; this city policy isn't working; compliment about a city program; concern about city rules | |
| General Lighting Request | street lighting request; question about streetlamps; lighting concern on my street; request for public lighting; our block needs better lighting | |
| General Traffic Engineering Request | traffic engineering concern; traffic flow needs improvement; street design feels unsafe; intersection layout is confusing; request a traffic study; cars have trouble navigating this intersection | |
| Graffiti Removal | graffiti on a wall; spray paint on public property; remove graffiti tags; someone tagged the building; graffiti on a utility box; painted scribbles on a fence | |
| Ground Maintenance | park grounds need upkeep; grass needs mowing in the park; overgrown park lawn; park landscaping needs attention; weeds in park flower beds; playground grounds need maintenance | |
| Heat - Excessive  Insufficient | no heat in my apartment; apartment is too cold; heat is turned up too high; not enough heat in my building; radiators aren't heating the rooms; my apartment is unbearably hot; landlord won't turn on the heat | |
| Illegal Auto Body Shop | illegal auto body shop; unlicensed car body repair business; unauthorized collision repair shop; someone running an illegal body shop; suspected illegal car painting business; unlicensed auto body work in garage | |
| Illegal Dumping | someone dumped trash here; illegal garbage dumping; construction debris dumped in an alley; someone left furniture on vacant land; truck unloading trash illegally; bags of rubbish dumped on public land; someone dumped an old couch | |
| Illegal Occupancy | people living in an unapproved apartment; illegal living space; someone living in a garage; basement used as an unauthorized apartment; people living in a commercial space; unapproved residential occupancy | |
| Illegal Posting of Signs | illegal signs; unauthorized posters; flyers taped to utility poles; advertisements nailed to trees; signs posted without permission; someone put ads on street poles | |
| Illegal Rooming House | illegal rooming house; unlicensed boarding house; house renting individual rooms without approval; unauthorized lodging house; rooms rented separately in unlicensed house; suspected illegal boarding house | |
| Illegal Vending | illegal street vendor; selling goods without a permit; unlicensed sidewalk seller; unauthorized vending stand; someone selling merchandise on the sidewalk; street sales without permission | |
| Improper Storage of Trash (Barrels) | trash barrels left uncovered; trash stored without proper containers; garbage bags piled around barrels; trash can lids won't close; improperly stored garbage; rubbish spilling out of bins | |
| Install New Lighting | install a new streetlight; need lighting on this street; no streetlamps on this block; request a new lamp post; add a street light here; this corner needs a light | |
| Item Price Missing | item has no price; missing price tag; products aren't marked with prices; no price on store merchandise; can't find the item price; goods missing price labels | |
| Knockdown Replacement | streetlight pole knocked down; car hit a lamp post; streetlamp lying on the ground; replace a fallen light pole; street light knocked over; lamp post down after a crash | |
| Lead | possible lead paint; lead hazard in my apartment; peeling paint may contain lead; concern about lead in the house; suspected lead paint dust; old window paint might have lead | |
| Litter Basket Maintenance | public trash basket is full; overflowing sidewalk litter bin; street trash can needs emptying; broken public garbage bin; litter basket needs cleaning; public wastebasket is damaged; trash spilling from a street basket | |
| Maintenance - Homeowner | maintenance problems in my own home; my house needs repairs; homeowner repair concerns; upkeep issues in my house; poor conditions in my owner occupied home | |
| Maintenance Complaint - Residential | my apartment needs repairs; landlord isn't maintaining the building; rental home in disrepair; poor upkeep in my apartment building; housing maintenance complaint; repairs aren't getting done in my apartment | |
| Major System Failure | major system breakdown; a major system has stopped working; serious system failure; major system malfunction | |
| Mattress_Pickup | mattress pickup; get rid of an old mattress; collect my mattress; need a mattress picked up; throwing away a bed mattress; schedule mattress collection | |
| Mechanical | building mechanical equipment problem; mechanical installation concern; problem with building machinery; mechanical equipment isn't working properly; mechanical system complaint | |
| Mice Infestation - Residential | mice in my apartment; mouse infestation at home; mice running around the kitchen; mouse droppings in my house; mice in the walls; my building is infested with mice; keep finding mice in my rental | |
| Misc. Snow Complaint | other snow complaint; general snow concern; miscellaneous snow problem; snow issue in my neighborhood; question about a snow problem | |
| Missed Trash/Recycling/Yard Waste/Bulk Item | my trash wasn't picked up; recycling collection skipped my bin; yard waste bags were left behind; missed garbage pickup; leaf bags weren't collected; bulk item pickup was missed; my couch wasn't picked up; they skipped our recycling | |
| Missing Sign | missing traffic sign; parking sign is gone; street sign disappeared; sign missing from pole; there used to be a sign here; road sign is missing | |
| Mosquitoes (West Nile) | mosquito problem; too many mosquitoes around here; worried about West Nile virus; mosquitoes swarming near my home; getting bitten by mosquitoes; mosquito infestation; West Nile mosquito concern | |
| Municipal Parking Lot Complaints | city parking lot complaint; problem at municipal parking lot; public parking lot needs attention; issues with the city parking lot; complaint about city owned parking | |
| Needle Pickup | used needle on the ground; discarded syringe; needles on the sidewalk; found a hypodermic needle; please pick up these syringes; used needles in the park | |
| New Sign  Crosswalk or Pavement Marking | need a new traffic sign; request a crosswalk; add a stop sign; new lane markings needed; paint a crosswalk here; request new road markings; this intersection needs a pedestrian crossing | |
| New Tree Requests | request a new tree; plant a tree on my street; need a sidewalk tree; new street tree request; please plant more trees; empty tree pit needs a tree | |
| News Boxes | newspaper box complaint; problem with newspaper rack; damaged news box; broken newspaper vending box; abandoned newspaper dispenser; news rack blocking the sidewalk | |
| No Price on Gas/Wrong Price | gas price not posted; wrong price on gas pump; gas station sign price is wrong; pump price doesn't match the sign; no price displayed for gasoline; charged more than the posted gas price | |
| No Utilities - Food Establishment - Electricity | restaurant has no electricity; power out at food shop; cafe operating without power; grocery store lost electricity; no power in the restaurant; bakery has an electrical outage | |
| No Utilities - Food Establishment - Flood | restaurant is flooded; water flooding the food shop; flooded grocery store; cafe has floodwater inside; bakery kitchen is flooding; standing floodwater in the restaurant | |
| No Utilities - Food Establishment - Sewer | restaurant sewer not working; sewage backing up in food shop; grocery store has a sewer backup; cafe has no working sewer; restaurant drains backing up with sewage; bakery has sewage coming up | |
| No Utilities - Food Establishment - Water | restaurant has no running water; water shut off at food shop; cafe operating without water; grocery store has no water; bakery taps have no water; restaurant water service is out | |
| No Utilities Residential - Electricity | no electricity in my apartment; power shut off in my home; my apartment has no power; electric service disconnected at home; no electric service in the house; electricity is off in my building | |
| No Utilities Residential - Gas | no gas in my apartment; gas service shut off at home; my house has no gas service; gas disconnected in my building; residential gas service is off; no gas supply to my home | |
| No Utilities Residential - Water | no water in my apartment; water shut off in my building; my house has no running water; nothing comes out of the faucets; water service disconnected at home; all my taps are dry | |
| No-Tow Complaint Confirmation | confirm my no tow complaint; confirmation that car was not towed; follow up on no tow complaint; vehicle still hasn't been towed; car reported but not towed; no tow complaint confirmation | |
| Notification | fire incident notification; notice of sewer overflow; water main break notification; water main shutoff notice; notification about a building fire; sanitary sewer overflow notification | |
| Occupying W/Out A Valid CO/CI | building occupied without occupancy certificate; no valid certificate of inspection; people living there without occupancy approval; business open without inspection certificate; occupancy certificate has expired; building in use without valid certificates | |
| Oil Truck - No Receipt | oil truck left no receipt; no receipt for heating oil delivery; oil driver didn't give me a receipt; missing fuel oil delivery slip; heating oil delivered without a ticket; never got my oil delivery receipt | |
| Overcrowding | too many people living in apartment; overcrowded house; too many tenants in one unit; people packed into a small apartment; too many people sharing one bedroom; overcrowded rental unit | |
| Overflowing or Un-kept Dumpster | overflowing dumpster; trash spilling out of dumpster; garbage piled above dumpster rim; dumpster area is a mess; poorly maintained garbage dumpster; trash container overflowing onto the ground; dumpster is filthy and neglected | |
| PWD Graffiti | graffiti needs removing; spray paint on public property; paint over graffiti; power wash graffiti off; graffiti on a control cabinet; stickers and flyers need removing; unwanted writing on a wall | |
| Park Improvement Requests | park needs improvements; request new park benches; add more shade in the park; park renovation request; improve the park paths; suggest upgrades to the playground | |
| Parking Enforcement | illegally parked car; car blocking my driveway; someone parked in a no parking zone; double parked vehicle; car parked in the bike lane; parking in a handicap spot without permit; car blocking the fire hydrant; car parked in resident parking without permit | |
| Parking Meter Repairs | broken parking meter; meter won't take coins; parking meter screen is blank; meter won't accept my card; parking pay station not working; meter didn't give me parking time; parking meter buttons are stuck | |
| Parking on Front/Back Yards (Illegal Parking) | car parked on the front lawn; cars parked in the backyard; illegal parking in a yard; neighbor parks on the grass; vehicles stored in the front yard; backyard being used as a parking lot | |
| Parks General Request | general question about a park; weeds in the park; park grounds need attention; overgrown weeds by the park path; concern about park upkeep; I have a request about the park | |
| Parks Lighting/Electrical Issues | park lights are out; park lamp keeps flickering; broken light pole in the park; ball field floodlights not working; playground lights won't turn on; exposed electrical wires in the park; park walkway is dark; park electrical box is damaged | |
| Pavement Marking Inspection | please inspect the road markings; check the crosswalk markings; are these lane lines marked correctly; request inspection of painted street lines; check placement of the stop line; have someone assess the pavement markings | |
| Pavement Marking Maintenance | faded crosswalk stripes; lane lines need repainting; stop line paint has worn away; road markings are hard to see; repaint the bike lane markings; parking space lines are faded; painted turn arrow is worn off; street stripes need touching up | |
| Pest Infestation - Residential | cockroaches in my apartment; bugs all over my rental; roaches in the kitchen; pests in my building; my apartment has an insect infestation | |
| Phone Bank Service Inquiry | transportation phone bank question; question about transportation telephone service; can't reach transportation by phone; transportation phone service inquiry; need help contacting transportation by phone; question about the transportation call service | |
| Pick up Dead Animal | dead animal pickup; dead squirrel on the sidewalk; dead rat in the street; remove an animal carcass; dead bird in the park; there's a dead raccoon by the curb; dead skunk on the road | |
| Pickup/Clear Conduit | pick up conduit; clear away conduit; conduit needs removal; electrical tubing left behind; remove leftover conduit pipe; there's conduit that needs clearing | |
| Pigeon Infestation | pigeon infestation; too many pigeons around here; pigeons nesting on the building; pigeon droppings everywhere; flock of pigeons roosting; pigeons have taken over the ledge; pigeon poop buildup | |
| Planting | park planting request; plant flowers in the park; new plants for the flower beds; park garden needs planting; request shrubs for a landscaped area; empty planting beds in the park | |
| Plumbing | plumbing problems; leaking pipe under the sink; toilet won't flush; bathtub drain is backed up; broken faucet; sink won't drain; water leaking from plumbing | |
| Pole Compliance | pole compliance concern; utility pole may violate requirements; check whether this pole is compliant; pole installation doesn't look compliant; concern about pole placement rules; pole not meeting standards | |
| Poor Conditions of Property | property is a mess; trash all over the yard; debris piled outside the building; neglected property; junk covering the front yard; rubbish around the property; move in trash left outside | |
| Poor Ventilation | poor ventilation in my apartment; no airflow in the room; bathroom exhaust fan doesn't work; stuffy apartment with no fresh air; air vents aren't working; not enough ventilation indoors; kitchen exhaust isn't venting | |
| Private Parking Lot Complaints | private parking lot complaint; problem with a paid parking lot; parking lot operator complaint; private lot parking dispute; complaint about parking lot fees; problems at a commercial parking lot; private parking lot conditions | |
| Product Short Measure | package weighs less than the label says; short weight on groceries; got less product than I paid for; bottle contains less than advertised; product quantity doesn't match the label; short measure on a purchase; package is underweight | |
| Protection of Adjoining Property | construction next door threatens my property; protect my house during neighboring construction; demolition next door could damage my house; neighboring excavation puts my foundation at risk; construction damage to adjoining property; protection for buildings beside construction | |
| Public Works General Request | general public works help; cones left in the street | |
| Rat Bite | a rat bit me; rat bite; my child was bitten by a rat; someone got bitten by a rat; rat bit my hand; bitten by a rodent that looked ratlike | |
| Recycling Cart Return | return my recycling cart; take back my recycling bin; I no longer need this recycling cart; remove an extra recycling barrel; unwanted recycling cart pickup; give back the recycling bin | |
| Rental Unit Delivery Conditions | apartment not ready when I moved in; rental unit dirty at move in; new apartment delivered in poor condition; landlord handed over an unsafe apartment; rental wasn't habitable when I got keys; problems with apartment condition at move in | |
| Request for Litter Basket Installation | need a public trash can here; install a litter basket; put a garbage bin on this corner; street needs a trash barrel; request a new sidewalk trash can; no public wastebasket on this block | |
| Request for Pothole Repair | pothole in the road; big hole in the street; sinkhole opening in pavement; asphalt patch is breaking apart; road surface has a deep hole; please fix this pothole; street pavement is caving in | |
| Request for Recycling Cart | I need a recycling bin; request a recycling cart; get a recycling barrel; need a bin for recyclables; please send a recycling container; request a wheeled recycling tote | |
| Request for Snow Plowing | my street needs plowing; road still covered in snow; snowplow missed our street; please plow this road; street hasn't been plowed; snow blocking the roadway; need another pass with the plow | |
| Request for Snow Plowing (Emergency Responder) | ambulance needs the street plowed; snow blocking fire truck access; emergency responders need snow cleared; plow road for emergency vehicle access; police vehicle blocked by unplowed snow; snowplow needed for ambulance access | |
| Requests for Directional or Roadway Changes | make this street one way; change the direction of traffic; request a two way street; change the street layout; change the lane configuration; roadway design change request | |
| Requests for Street Cleaning | street needs sweeping; trash scattered along the curb; please clean our street; weeds growing along the curb; gutter full of dirt and debris; street needs power washing; litter all over the road | |
| Requests for Traffic Signal Studies or Reviews | intersection needs a traffic light; review the traffic signal timing; green light is too short; red light lasts too long; study traffic lights at this intersection; stoplights need better coordination; request a new stoplight | |
| Roadway Repair | road surface is crumbling; street needs repaving; damaged asphalt on the road; pavement is cracked and uneven; rough stretch of roadway; street surface needs repair; road pavement is breaking apart | |
| Rodent Activity | rats running around outside; rat burrows in the yard; rodent droppings near the trash; rats around the dumpsters; seeing rats during the day; signs of a rodent infestation | |
| Rooftop & Mechanical Disturbances | rooftop equipment is too loud; noisy air conditioning unit; roof fan keeps rattling; constant humming from building machinery; mechanical equipment shaking the building; loud ventilation fan on the roof; rooftop machinery keeping me awake | |
| Scale Not Visible | cannot see the scale; store scale display is hidden; weight display faces away from customers; deli scale is not visible; cannot read the checkout scale; produce scale screen is blocked; cannot see what my purchase weighs | |
| Scanning Overcharge | item scanned at the wrong price; charged more than the shelf price; sale price not applied at checkout; register price higher than price tag; scanner overcharged me; receipt price higher than advertised; groceries rang up too high | |
| Schedule a Bulk Item Pickup | schedule a bulk pickup; pick up an old couch; need a dresser hauled away; arrange pickup for a recliner; large furniture trash pickup; get rid of a bookcase; schedule collection of bulky items | |
| Schedule a Bulk Item Pickup SS | book a bulky item pickup; need my old sofa picked up; schedule furniture collection; pick up a large dresser; throwing away an old recliner; arrange pickup for a bookcase; large household item collection request | |
| Sewage/Septic Back-Up | sewage backing up; septic tank backup; sewage coming up through floor drain; toilet backing up with sewage; wastewater backing into basement; septic waste overflowing | |
| Short Measure - Gas | gas pump shorting me; paid for more gas than received; pump shows more gas than delivered; gas station giving less fuel; incorrect gallons at gas pump; fuel pump under dispensing | |
| Short Term Rental | short term rental complaint; Airbnb rental concern; unregistered vacation rental; apartment rented out by the night; short stay rental issue; Vrbo property complaint | |
| Sidewalk Cover / Manhole | missing manhole cover; loose utility cover; broken sidewalk access cover; manhole lid out of place; metal cover rocking underfoot; open utility hole in sidewalk; sidewalk cover is cracked | |
| Sidewalk Repair | cracked sidewalk; crumbling concrete walkway; sidewalk needs repair; broken pavement on sidewalk; sidewalk surface wearing away; damaged sidewalk slabs | |
| Sidewalk Repair (Make Safe) | sidewalk is a tripping hazard; loose sidewalk bricks; dangerous broken sidewalk; raised pavement catching my feet; weeds making sidewalk unsafe; hole in sidewalk needs making safe; sidewalk bricks sticking up | |
| Sign Repair | bent stop sign; missing street name sign; parking sign knocked down; traffic sign hanging loose; faded road sign; sign pole leaning over; can't read the parking sign | |
| Sign Shop WO | sign shop work request; traffic sign work order; street sign shop request; parking sign work order; transportation sign shop job | |
| Snow/Ice Control | street covered in snow; road needs plowing; ice making street slippery; street needs salt; snow and ice buildup | |
| Space Savers | chair saving a parking spot; cones holding street parking; space saver left in street; trash barrel reserving parking space; someone blocking parking with furniture; bucket saving a spot; objects used to claim street parking | |
| Squalid Living Conditions | filthy living conditions; unsanitary apartment; home full of garbage; human waste inside the apartment; my home is dangerously dirty; squalor inside a house | |
| Sticker Request | request a sticker; need a public works sticker; how do I get a sticker; public works sticker request; can I get a replacement sticker | |
| Street Light Knock Downs | streetlight knocked down; fallen lamp post; light pole lying on the ground; car hit a streetlight pole; streetlamp fell over; street light pole toppled | |
| Street Light Outages | streetlight out; streetlamp not working; lamp post light is dark; the light on my corner keeps flickering; street lights off on my block; gas streetlight not lighting; streetlight keeps going out | |
| StreetLight Pole WO | streetlight pole needs work; lamp post base needs attention; concrete around light pole needs repair; brickwork around streetlamp needs repair; light pole maintenance request; streetlamp pole needs repairs | |
| Student Move-in Issues | student move in problems; college move in issues; problems during student moving day; students moving in causing problems; trouble with college move ins; student move in disruption | |
| Student Overcrowding | overcrowded student apartment; too many students living together; student rental is overcrowded; students packed into a small apartment; too many student tenants; crowded college student housing | |
| Traffic Signal Inspection | traffic signal inspection request; please inspect the traffic lights; stoplight needs an inspection; check the intersection signals; request a traffic light safety check; have these traffic signals been inspected | |
| Traffic Signal Repair | traffic light not working; broken stoplight; traffic signal stuck on red; intersection lights are out; traffic light keeps flashing; damaged signal head; traffic light needs repair | |
| Transportation General Request | general transportation question; transportation concern; question about city traffic; transportation department request; help with a transportation issue; general traffic concern | |
| Trash on Vacant Lot | trash on empty lot; garbage in vacant property; rubbish piled on unused land; empty lot full of litter; debris dumped on vacant lot; the vacant lot is covered in junk | |
| Tree Emergencies | tree about to fall; large limb hanging dangerously; fallen tree blocking the road; tree splitting and falling over; broken branch about to drop; tree fell across the sidewalk | |
| Tree Maintenance Requests | tree needs trimming; overgrown street tree; branches need pruning; tree needs routine care; please cut back these tree branches; street tree needs maintenance | |
| Tree in Park | tree problem in the park; playground tree needs attention; park tree needs trimming; unhealthy tree at the playground; branches over the park path; tree in the tot lot | |
| Undefined Noise Disturbance | loud noise somewhere nearby; unidentified noise disturbance; I can't tell where noise comes from; constant noise in the neighborhood; something loud is keeping me awake; unknown source of loud noise | |
| Unit Pricing Wrong/Missing | unit price missing; wrong price per ounce; shelf label missing price per pound; cost per unit calculated wrong; no price per ounce listed; unit pricing on shelf is incorrect | |
| Unsafe Dangerous Conditions | unsafe conditions in building; dangerous conditions on property; safety hazard inside the building; this property has dangerous hazards; building conditions feel unsafe; hazardous conditions around the premises | |
| Unsanitary Conditions - Employees | food worker not washing hands; employee handling food with dirty hands; cook coughing on food; server touching food after handling money; food handler has dirty clothing; worker sneezing into food | |
| Unsanitary Conditions - Establishment | filthy restaurant kitchen; dirty food preparation counters; unsanitary grocery store; restaurant equipment covered in grime; food shop floors are filthy; dirty dishes used at restaurant | |
| Unsanitary Conditions - Food | mold on food being sold; spoiled food at restaurant; food has something foreign in it; rotten meat for sale; food stored in dirty containers; food left uncovered and contaminated | |
| Unsatisfactory Living Conditions | unsafe living conditions; unhealthy conditions in my apartment; rental home in poor condition; my apartment is not safe to live in; unsanitary housing; poorly maintained living space | |
| Unsatisfactory Utilities - Electrical  Plumbing | faulty wiring in my apartment; plumbing problems in my building; electrical outlets don't work; unsafe electrical system; pipes and fixtures aren't working properly; bad electrical or plumbing conditions | |
| Unshoveled Sidewalk | unshoveled sidewalk; sidewalk covered in snow; icy walkway; snow hasn't been cleared from the sidewalk; can't walk through snow on sidewalk; sidewalk needs shoveling | |
| Upgrade Existing Lighting | upgrade existing streetlights; brighter street lighting needed; replace old streetlamps with better lights; improve the lighting on my street; lamp posts need brighter lights; existing street lights aren't bright enough | |
| Utility Call-In | calling about utility work; utility work notification; report planned utility work; utility company work call; notice of utility work; calling in a utility job | |
| Utility Casting Repair | broken utility cover; damaged manhole frame; loose metal access cover; utility cover needs repair; cracked manhole cover; metal cover rocks when cars pass | |
| Valet Parking Problems | valet parking problem; valet cars blocking the street; valet taking up parking spaces; valet stand causing traffic problems; valet parking in unauthorized spaces; complaint about valet service parking | |
| Walk-In Service Inquiry | walk in transportation question; in person parking service inquiry; transportation office visit question; asking about transportation services in person; walk in service information; parking question at the counter | |
| Water in Gas - High Priority | water in gasoline; gas station sold watered down gas; water mixed into my fuel; gasoline contaminated with water; water in gas from the pump; bought gas with water in it | |
| Work Hours-Loud Noise Complaints | construction noise late at night; work starting too early; loud roadwork outside allowed hours; crews working noisily overnight; construction work hours complaint; loud equipment waking me up | |
| Work w/out Permit | construction without a permit; unpermitted building work; renovations with no permit; remodeling without permits; they are building without a permit; no permit posted for construction | |
| Working Beyond Hours | construction after hours; building work late at night; construction starting too early; workers working past allowed hours; renovation work outside permitted hours; they are still drilling at midnight | |
| Zoning | possible zoning violation; is this property use allowed; business operating in a residential zone; building too close to property line; addition exceeds zoning height limit; questions about zoning rules; too many units for this zone | |

## 3a. Test messages (40)

Check that the expected type is what a 311 operator would pick, and that the scripted
clarification answer is realistic. Alternates are other types that also count as correct.

| ID | Category | Message | Expected type | Clarification answer | Alternates | Decision |
|---|---|---|---|---|---|---|
| t01 | clear | The street light outside 45 Centre St has been out for three nights. | Street Light Outages |  |  | |
| t02 | clear | A car is parked in front of my driveway and I can't get out. | Parking Enforcement |  |  | |
| t03 | clear | My trash wasn't picked up this morning. The whole street got collected except our house. | Missed Trash/Recycling/Yard Waste/Bulk Item |  |  | |
| t04 | clear | I need to schedule a pickup for an old couch and a dresser. | Schedule a Bulk Item Pickup |  | Schedule a Bulk Item Pickup SS | |
| t05 | clear | There are rats running around the alley behind our building. | Rodent Activity |  |  | |
| t06 | clear | We have no heat in our apartment and the landlord won't fix it. | Heat - Excessive  Insufficient |  | Unsatisfactory Living Conditions | |
| t07 | clear | Someone dumped a pile of construction debris and old furniture on the side of the road overnight. | Illegal Dumping |  | Construction Debris | |
| t08 | clear | Please come pick up my old mattress. | Mattress_Pickup |  |  | |
| t09 | clear | There's a car on our street that hasn't moved in a month. Flat tires and no license plates. | Abandoned Vehicles |  |  | |
| t10 | clear | Bed bugs in my apartment building. Every unit is getting them. | Bed Bugs |  |  | |
| t11 | clear | The parking meter on Newbury St took my coins and won't give me any time. | Parking Meter Repairs |  |  | |
| t12 | clear | A huge tree branch is cracked and hanging over the sidewalk. It looks like it could fall any minute. | Tree Emergencies |  |  | |
| t13 | paraphrase | streetlite broke on my block, its pitch black at nite | Street Light Outages |  |  | |
| t14 | paraphrase | people are putting lawn chairs and cones in the street to save parking spots after the snow | Space Savers |  |  | |
| t15 | paraphrase | the crosswalk paint is basically gone at the corner by the school | Pavement Marking Maintenance |  |  | |
| t16 | paraphrase | mold keeps growing on my bathroom ceiling no matter what we do | Chronic Dampness/Mold |  |  | |
| t17 | paraphrase | the sidewalk in front of the corner store was never shoveled and it's a sheet of ice | Unshoveled Sidewalk |  |  | |
| t18 | paraphrase | can I get a new recycling bin? ours cracked down the middle | Request for Recycling Cart |  |  | |
| t19 | paraphrase | dead raccoon in the middle of the road on Adams St | Pick up Dead Animal |  |  | |
| t20 | paraphrase | the restaurant on the corner has mice running around the kitchen | Unsanitary Conditions - Establishment |  | Unsanitary Conditions - Food | |
| t21 | confusion | One of the lights in Franklin Park near the playground is out. | Parks Lighting/Electrical Issues |  |  | |
| t22 | confusion | The sidewalk on my street is all cracked and the slabs are uneven. | Sidewalk Repair |  | Sidewalk Repair (Make Safe) | |
| t23 | confusion | The traffic light at Mass Ave and Boylston is stuck on red. | Traffic Signal Repair |  |  | |
| t24 | confusion | The house next door leaves its trash barrels out on the sidewalk all week with the lids off. | Improper Storage of Trash (Barrels) |  |  | |
| t25 | confusion | The public trash can at the bus stop on Washington St is overflowing. | Litter Basket Maintenance |  | Empty Litter Basket | |
| t26 | confusion | Huge pothole on Tremont St near the Park Street T stop. It almost blew out my tire. | Request for Pothole Repair |  |  | |
| t27 | missing_context | There's a light out. | Street Light Outages | It's a street light on the sidewalk in front of my house on Dorchester Ave. |  | |
| t28 | missing_context | Something needs to be picked up. | Pick up Dead Animal | A dead cat in the street outside my house. |  | |
| t29 | missing_context | It's really bad in my apartment. | Mice Infestation - Residential | We have mice everywhere and the landlord does nothing. | Pest Infestation - Residential | |
| t30 | missing_context | There's a problem with a tree. | Tree Maintenance Requests | It's a street tree on the sidewalk and the branches need trimming. It's not an emergency. |  | |
| t31 | missing_context | Car problem on my street. | Parking Enforcement | A car is double parked and blocking traffic right now. |  | |
| t32 | multiple_issues | The street light is out and there's also a huge pile of trash dumped next to it. | Street Light Outages | The street light, please. |  | |
| t33 | multiple_issues | My heat is broken and there are bedbugs in the bedroom. | Heat - Excessive  Insufficient | The heat. It's freezing in here. |  | |
| t34 | multiple_issues | There are rats in the alley and my trash wasn't picked up either. | Rodent Activity | The rats. |  | |
| t35 | out_of_scope | Someone broke into my car last night and stole my laptop. | *(triage)* |  |  | |
| t36 | out_of_scope | My water bill seems way too high this month. | *(triage)* |  |  | |
| t37 | out_of_scope | The 39 bus has been late every day this week. | *(triage)* |  |  | |
| t38 | out_of_scope | How do I register to vote in Boston? | *(triage)* |  |  | |
| t39 | empty | *(empty)* | *(triage)* |  |  | |
| t40 | empty | *(empty)* | *(triage)* |  |  | |

## 3b. Dev messages (18)

Check that the expected type is what a 311 operator would pick, and that the scripted
clarification answer is realistic. Alternates are other types that also count as correct.

| ID | Category | Message | Expected type | Clarification answer | Alternates | Decision |
|---|---|---|---|---|---|---|
| d01 | clear | The lamp post on my corner flickers on and off all night. | Street Light Outages |  |  | |
| d02 | clear | Somebody parked in the handicap spot without a placard. | Parking Enforcement |  |  | |
| d03 | clear | Recycling didn't get collected on our street today. | Missed Trash/Recycling/Yard Waste/Bulk Item |  |  | |
| d04 | clear | I need to get rid of an old recliner and a broken table. | Schedule a Bulk Item Pickup |  | Schedule a Bulk Item Pickup SS | |
| d05 | clear | Rat burrows all along the fence behind the apartment complex. | Rodent Activity |  |  | |
| d06 | paraphrase | apartment is freezing, the radiators have been cold for days | Heat - Excessive  Insufficient |  |  | |
| d07 | paraphrase | cockroaches all over my kitchen and the landlord won't call an exterminator | Pest Infestation - Residential |  |  | |
| d08 | paraphrase | a bike has been locked to the rack for months, it's missing both wheels | Abandoned Bicycle |  |  | |
| d09 | paraphrase | the lane lines on Columbus Ave are so faded you can't see them at night | Pavement Marking Maintenance |  |  | |
| d10 | confusion | The stop sign at my corner got knocked over. | Sign Repair |  | Missing Sign | |
| d11 | confusion | The lights at the park's tennis courts don't work. | Parks Lighting/Electrical Issues |  |  | |
| d12 | confusion | There's a deep pothole right outside my house. | Request for Pothole Repair |  |  | |
| d13 | missing_context | There's an issue on my block. | Illegal Dumping | Someone dumped a pile of old furniture on the sidewalk. |  | |
| d14 | missing_context | I need help with my apartment. | Chronic Dampness/Mold | There's mold all over the bedroom walls. |  | |
| d15 | multiple_issues | The street light is out and the sidewalk is broken. | Sidewalk Repair | The sidewalk. Someone tripped on it yesterday. | Sidewalk Repair (Make Safe) | |
| d16 | out_of_scope | I lost my wallet on the Red Line this morning. | *(triage)* |  |  | |
| d17 | out_of_scope | What time does City Hall open on Saturdays? | *(triage)* |  |  | |
| d18 | empty | *(empty)* | *(triage)* |  |  | |

## 4. Spec 10.1 and 10.2

`docs/architecture.md` sections 10.1 ("Team decisions still open") and 10.2 ("Defaults for team
review") list the questions from before the build. Most were settled and logged in
`docs/decisions.md`. Decide: mark each one resolved with a pointer to its decision, or leave the
frozen text as it is.

## 5. Report title

`docs/report.md` is titled "(draft)". Andrew and Nicholas remove it when the report is final.

## 6. Spec 10.4 logistics

The forum check and the code-freeze date are listed as open in `docs/review_guide.md`. Record the
outcomes when they are done.

## After the review

1. Claude sets each status in `catalog.json` to `approved` or `rejected` and rebuilds the catalog.
2. Claude sets `ACCEPT_PROVISIONAL_APPROVALS = False` in `src/boston311/config.py`.
3. Claude reruns the tests, `run_all`, and the notebook, and reports any change in results.
4. Claude removes the "pending team review" wording from the docs, the notebook, and the code
   comments, records the review in `docs/decisions.md`, and deletes this checklist.
