#!/usr/bin/env python3
"""GHL pipeline opportunities -> per-closer booked/held/noShow/won by window.
Usage: python3 build_pipeline.py raw/opp_page1.json raw/opp_page2.json
Writes pipeline.partial.json (merged into data.json by build_leaderboard.py).

Convention (documented, same tradeoff AIFS's pipelineFlow makes): a stage count in a
window means "this opportunity's most recent stage change landed here on this date."
GHL's search-opportunity response carries current stage + lastStageChangeAt only, not a
full transition history, so this is the closest honest reading of "booked"/"held"/
"no show" available from the API. It is disclosed in the rendered footnote, not hidden.
"""
import json
import sys

from lib import (CLOSERS, CLOSER_BY_ID, STAGE_MAP, BOOKED_STAGES, SHOWED_STAGES, ALL_WINDOW_KEYS,
                  compute_windows, in_window, is_test_contact, load_opportunities, to_la_date)
from datetime import datetime, timezone


def blank_window_row():
    return {"booked": 0, "held": 0, "noShow": 0, "showed": 0, "won": 0, "wonNames": []}


def main():
    paths = sys.argv[1:]
    if not paths:
        print("usage: build_pipeline.py <opp_page1.json> [opp_page2.json ...]")
        sys.exit(1)
    opps = load_opportunities(paths)

    now_utc = datetime.now(timezone.utc)
    windows = compute_windows(now_utc)

    per_closer = {c["key"]: {
        "name": c["name"],
        **{wk: blank_window_row() for wk in ALL_WINDOW_KEYS},
    } for c in CLOSERS}

    total_won_alltime_all_closers_raw = 0  # independent cross-check tally, not read from per_closer
    excluded_test = 0
    stage_totals = {v: 0 for v in STAGE_MAP.values()}

    for o in opps:
        stage_key = STAGE_MAP.get(o.get("pipelineStageId"))
        if stage_key:
            stage_totals[stage_key] += 1

        contact = o.get("contact") or {}
        if is_test_contact(contact.get("email"), o.get("name")):
            excluded_test += 1
            continue

        assigned_to = o.get("assignedTo")
        closer = CLOSER_BY_ID.get(assigned_to)
        if not closer:
            continue  # unassigned or owned by a non-closer (VA/admin) - not a leaderboard row

        date_str = to_la_date(o.get("lastStageChangeAt"))
        if date_str is None or stage_key is None:
            continue

        if stage_key == "closedWon" and in_window(date_str, windows["allTime"]):
            total_won_alltime_all_closers_raw += 1

        for win_key in ALL_WINDOW_KEYS:
            if not in_window(date_str, windows[win_key]):
                continue
            row = per_closer[closer["key"]][win_key]
            if stage_key in BOOKED_STAGES:
                row["booked"] += 1
            if stage_key == "callHeld":
                row["held"] += 1
            if stage_key == "noShow":
                row["noShow"] += 1
            if stage_key in SHOWED_STAGES:
                row["showed"] += 1
            if stage_key == "closedWon":
                row["won"] += 1
                row["wonNames"].append(o.get("name"))

    # Reconcile gate: sum of per-closer won-all-time must equal the independent raw tally.
    summed_won_alltime = sum(per_closer[c["key"]]["allTime"]["won"] for c in CLOSERS)
    if summed_won_alltime != total_won_alltime_all_closers_raw:
        print("RECONCILE FAIL (pipeline): per-closer won-all-time sum (%d) != raw tally (%d)" % (
            summed_won_alltime, total_won_alltime_all_closers_raw))
        sys.exit(1)

    # Sanity gate: booked is the superset; held/noShow/showed can never exceed it.
    for c in CLOSERS:
        for win_key in ALL_WINDOW_KEYS:
            row = per_closer[c["key"]][win_key]
            if row["showed"] + row["noShow"] > row["booked"]:
                print("RECONCILE FAIL (pipeline): %s/%s showed+noShow > booked" % (c["key"], win_key))
                sys.exit(1)

    out = {
        "windows": windows,
        "byCloser": per_closer,
        "stageTotals": stage_totals,
        "excludedTestRecords": excluded_test,
        "totalOpportunities": len(opps),
    }
    with open("pipeline.partial.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("OK pipeline.partial.json written. total opps=%d, excluded test=%d, won all time=%d" % (
        len(opps), excluded_test, summed_won_alltime))


if __name__ == "__main__":
    main()
