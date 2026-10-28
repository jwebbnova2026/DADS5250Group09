"""Write the intake dev and test sets to data/eval/ (spec 4.8).

Every message below was written before any prompt or gate tuning, and the
team reviewed every message and label on 2026-10-27. None of them is used
as a retrieval alias.

Each item names its expected official request type *by name*. This script
looks the name up in the catalog, so a typo fails loudly, and fills in the
expected department, queue, and decision from the approved mappings:

* ROUTE   - the type has an approved department mapping;
* TRIAGE  - the type has no approved department mapping, the type is one of
            an overlapping pair (config.OVERLAPPING_TYPE_PAIRS), or the
            message is out of scope (no expected type);
* REJECTED - empty input.

``alternates`` lists other official types that are equally correct because
the city's own list contains near-duplicates (for example "Schedule a Bulk
Item Pickup" and "Schedule a Bulk Item Pickup SS").

Usage: python scripts/build_eval_sets.py
"""

from __future__ import annotations

import json

from boston311 import config
from boston311.agent.tools import overlapping_partner
from boston311.catalog import load_catalog

# (id, category, message, expected type name or None, clarification answer or None, alternates)
TEST = [
    # --- clear requests -------------------------------------------------------
    ("t01", "clear", "The street light outside 45 Centre St has been out for three nights.", "Street Light Outages", None, []),
    ("t02", "clear", "A car is parked in front of my driveway and I can't get out.", "Parking Enforcement", None, []),
    ("t03", "clear", "My trash wasn't picked up this morning. The whole street got collected except our house.", "Missed Trash/Recycling/Yard Waste/Bulk Item", None, []),
    ("t04", "clear", "I need to schedule a pickup for an old couch and a dresser.", "Schedule a Bulk Item Pickup", None, ["Schedule a Bulk Item Pickup SS"]),
    ("t05", "clear", "There are rats running around the alley behind our building.", "Rodent Activity", None, []),
    ("t06", "clear", "We have no heat in our apartment and the landlord won't fix it.", "Heat - Excessive  Insufficient", None, ["Unsatisfactory Living Conditions"]),
    ("t07", "clear", "Someone dumped a pile of construction debris and old furniture on the side of the road overnight.", "Illegal Dumping", None, ["Construction Debris"]),
    ("t08", "clear", "Please come pick up my old mattress.", "Mattress_Pickup", None, []),
    ("t09", "clear", "There's a car on our street that hasn't moved in a month. Flat tires and no license plates.", "Abandoned Vehicles", None, []),
    ("t10", "clear", "Bed bugs in my apartment building. Every unit is getting them.", "Bed Bugs", None, []),
    ("t11", "clear", "The parking meter on Newbury St took my coins and won't give me any time.", "Parking Meter Repairs", None, []),
    ("t12", "clear", "A huge tree branch is cracked and hanging over the sidewalk. It looks like it could fall any minute.", "Tree Emergencies", None, []),
    # --- paraphrases and informal wording -------------------------------------
    ("t13", "paraphrase", "streetlite broke on my block, its pitch black at nite", "Street Light Outages", None, []),
    ("t14", "paraphrase", "people are putting lawn chairs and cones in the street to save parking spots after the snow", "Space Savers", None, []),
    ("t15", "paraphrase", "the crosswalk paint is basically gone at the corner by the school", "Pavement Marking Maintenance", None, []),
    ("t16", "paraphrase", "mold keeps growing on my bathroom ceiling no matter what we do", "Chronic Dampness/Mold", None, []),
    ("t17", "paraphrase", "the sidewalk in front of the corner store was never shoveled and it's a sheet of ice", "Unshoveled Sidewalk", None, []),
    ("t18", "paraphrase", "can I get a new recycling bin? ours cracked down the middle", "Request for Recycling Cart", None, []),
    ("t19", "paraphrase", "dead raccoon in the middle of the road on Adams St", "Pick up Dead Animal", None, []),
    ("t20", "paraphrase", "the restaurant on the corner has mice running around the kitchen", "Unsanitary Conditions - Establishment", None, []),
    # --- easily confused types ----------------------------------------------
    ("t21", "confusion", "One of the lights in Franklin Park near the playground is out.", "Parks Lighting/Electrical Issues", None, []),
    ("t22", "confusion", "The sidewalk on my street is all cracked and the slabs are uneven.", "Sidewalk Repair", None, ["Sidewalk Repair (Make Safe)"]),
    ("t23", "confusion", "The traffic light at Mass Ave and Boylston is stuck on red.", "Traffic Signal Repair", None, []),
    ("t24", "confusion", "The house next door leaves its trash barrels out on the sidewalk all week with the lids off.", "Improper Storage of Trash (Barrels)", None, []),
    ("t25", "confusion", "The public trash can at the bus stop on Washington St is overflowing.", "Empty Litter Basket", None, []),
    ("t26", "confusion", "Huge pothole on Tremont St near the Park Street T stop. It almost blew out my tire.", "Request for Pothole Repair", None, []),
    # --- missing context (one clarification, scripted answer) -----------------
    ("t27", "missing_context", "There's a light out.", "Street Light Outages", "It's a street light on the sidewalk in front of my house on Dorchester Ave.", []),
    ("t28", "missing_context", "Something needs to be picked up.", "Pick up Dead Animal", "A dead cat in the street outside my house.", []),
    ("t29", "missing_context", "It's really bad in my apartment.", "Mice Infestation - Residential", "We have mice everywhere and the landlord does nothing.", []),
    ("t30", "missing_context", "There's a problem with a tree.", "Tree Maintenance Requests", "It's a street tree on the sidewalk and the branches need trimming. It's not an emergency.", []),
    ("t31", "missing_context", "Car problem on my street.", "Parking Enforcement", "A car is double parked and blocking traffic right now.", []),
    # --- multiple issues (resident picks one when asked) ----------------------
    ("t32", "multiple_issues", "The street light is out and there's also a huge pile of trash dumped next to it.", "Street Light Outages", "The street light, please.", []),
    ("t33", "multiple_issues", "My heat is broken and there are bedbugs in the bedroom.", "Heat - Excessive  Insufficient", "The heat. It's freezing in here.", []),
    ("t34", "multiple_issues", "There are rats in the alley and my trash wasn't picked up either.", "Rodent Activity", "The rats.", []),
    # --- out of scope -----------------------------------------------------------
    ("t35", "out_of_scope", "Someone broke into my car last night and stole my laptop.", None, None, []),
    ("t36", "out_of_scope", "My water bill seems way too high this month.", None, None, []),
    ("t37", "out_of_scope", "The 39 bus has been late every day this week.", None, None, []),
    ("t38", "out_of_scope", "How do I register to vote in Boston?", None, None, []),
    # --- empty input ------------------------------------------------------------
    ("t39", "empty", "", None, None, []),
    ("t40", "empty", "   ", None, None, []),
]

DEV = [
    ("d01", "clear", "The lamp post on my corner flickers on and off all night.", "Street Light Outages", None, []),
    ("d02", "clear", "Somebody parked in the handicap spot without a placard.", "Parking Enforcement", None, []),
    ("d03", "clear", "Recycling didn't get collected on our street today.", "Missed Trash/Recycling/Yard Waste/Bulk Item", None, []),
    ("d04", "clear", "I need to get rid of an old recliner and a broken table.", "Schedule a Bulk Item Pickup", None, ["Schedule a Bulk Item Pickup SS"]),
    ("d05", "clear", "Rat burrows all along the fence behind the apartment complex.", "Rodent Activity", None, []),
    ("d06", "paraphrase", "apartment is freezing, the radiators have been cold for days", "Heat - Excessive  Insufficient", None, []),
    ("d07", "paraphrase", "cockroaches all over my kitchen and the landlord won't call an exterminator", "Pest Infestation - Residential", None, []),
    ("d08", "paraphrase", "a bike has been locked to the rack for months, it's missing both wheels", "Abandoned Bicycle", None, []),
    ("d09", "paraphrase", "the lane lines on Columbus Ave are so faded you can't see them at night", "Pavement Marking Maintenance", None, []),
    ("d10", "confusion", "The stop sign at my corner got knocked over.", "Sign Repair", None, []),
    ("d11", "confusion", "The lights at the park's tennis courts don't work.", "Parks Lighting/Electrical Issues", None, []),
    ("d12", "confusion", "There's a deep pothole right outside my house.", "Request for Pothole Repair", None, []),
    ("d13", "missing_context", "There's an issue on my block.", "Illegal Dumping", "Someone dumped a pile of old furniture on the sidewalk.", []),
    ("d14", "missing_context", "I need help with my apartment.", "Chronic Dampness/Mold", "There's mold all over the bedroom walls.", []),
    ("d15", "multiple_issues", "The street light is out and the sidewalk is broken.", "Sidewalk Repair (Make Safe)", "The sidewalk. Someone tripped on it yesterday.", []),
    ("d16", "out_of_scope", "I lost my wallet on the Red Line this morning.", None, None, []),
    ("d17", "out_of_scope", "What time does City Hall open on Saturdays?", None, None, []),
    ("d18", "empty", "", None, None, []),
]


def expected_route(entry):
    """The routing the assistant should produce for this type.

    Same as ``entry.route()``, except that a type in an overlapping pair
    (``config.OVERLAPPING_TYPE_PAIRS``) is expected to go to TRIAGE: the two
    types describe the same problem and route differently, so a person
    decides (team review, 2026-10-27).
    """
    if overlapping_partner(entry.type) is not None:
        return None, None, None
    return entry.route()


def build(items, catalog_by_name):
    out = []
    for item_id, category, message, type_name, answer, alternates in items:
        rec = {
            "id": item_id,
            "category": category,
            "message": message,
            "clarification_answer": answer,
            "expected_type_id": None,
            "acceptable_type_ids": [],
            "expected_department": None,
            "expected_queue": None,
            "expected_decision": None,
        }
        if category == "empty":
            rec["expected_decision"] = "REJECTED"
        elif type_name is None:
            rec["expected_decision"] = "TRIAGE"
        else:
            entry = catalog_by_name[type_name]  # KeyError = typo in the type name
            rec["expected_type_id"] = entry.type_id
            rec["acceptable_type_ids"] = [entry.type_id] + [catalog_by_name[a].type_id for a in alternates]
            dept, queue, status = expected_route(entry)
            if dept is None:
                rec["expected_decision"] = "TRIAGE"
            else:
                rec["expected_decision"] = "ROUTE"
                rec["expected_department"] = dept
                rec["expected_queue"] = queue if queue else status.value
        # An alternate type is equally correct, so the decision, department,
        # and queue it would produce are acceptable too.
        decisions, depts, queues = {rec["expected_decision"]}, set(), set()
        for tid in rec["acceptable_type_ids"]:
            alt = next(e for e in catalog_by_name.values() if e.type_id == tid)
            d, q, s = expected_route(alt)
            decisions.add("ROUTE" if d else "TRIAGE")
            if d:
                depts.add(d)
                queues.add(q if q else s.value)
        rec["acceptable_decisions"] = sorted(decisions)
        rec["acceptable_departments"] = sorted(depts)
        rec["acceptable_queues"] = sorted(queues)
        out.append(rec)
    return out


def main() -> None:
    by_name = {e.type: e for e in load_catalog().values()}
    config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    for name, items in (("test", TEST), ("dev", DEV)):
        records = build(items, by_name)
        path = config.EVAL_DIR / f"{name}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {path} ({len(records)} items)")


if __name__ == "__main__":
    main()
