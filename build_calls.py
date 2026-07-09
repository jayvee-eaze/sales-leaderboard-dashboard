#!/usr/bin/env python3
"""GHL call log (channel=Call) -> per-closer outbound/inbound/hours by day/week/month.
Usage: python3 build_calls.py raw/calls_month.json [more_pages.json ...]
Writes calls.partial.json (merged into data.json by build_leaderboard.py).
"""
import json
import sys

from lib import CLOSERS, CLOSER_BY_ID, compute_windows, in_window, load_calls, to_la_date
from datetime import datetime, timezone


def main():
    paths = sys.argv[1:]
    if not paths:
        print("usage: build_calls.py <call_log_page.json> [...]")
        sys.exit(1)
    calls = load_calls(paths)

    now_utc = datetime.now(timezone.utc)
    windows = compute_windows(now_utc)

    per_closer = {c["key"]: {
        "name": c["name"],
        "day": {"outbound": 0, "inbound": 0, "seconds": 0, "attempts": 0},
        "week": {"outbound": 0, "inbound": 0, "seconds": 0, "attempts": 0},
        "month": {"outbound": 0, "inbound": 0, "seconds": 0, "attempts": 0},
    } for c in CLOSERS}

    unmatched_closer_calls = 0  # calls made by non-closer team members (VAs, admins) - not counted, not hidden
    total_in_month = 0

    for m in calls:
        uid = m.get("userId")
        date_str = to_la_date(m.get("dateAdded"))
        if date_str is None:
            continue
        if not in_window(date_str, windows["month"]):
            continue
        total_in_month += 1
        closer = CLOSER_BY_ID.get(uid)
        if not closer:
            unmatched_closer_calls += 1
            continue
        direction = m.get("direction")
        duration = (m.get("meta") or {}).get("call", {}).get("duration") or 0
        for win_key in ("day", "week", "month"):
            if in_window(date_str, windows[win_key]):
                bucket = per_closer[closer["key"]][win_key]
                bucket["attempts"] += 1
                if direction == "outbound":
                    bucket["outbound"] += 1
                elif direction == "inbound":
                    bucket["inbound"] += 1
                bucket["seconds"] += duration

    for key, row in per_closer.items():
        for win_key in ("day", "week", "month"):
            b = row[win_key]
            b["hours"] = round(b["seconds"] / 3600.0, 1)

    out = {
        "windows": windows,
        "byCloser": per_closer,
        "reconcile": {
            "totalCallsInMonth": total_in_month,
            "unmatchedClosersCallsInMonth": unmatched_closer_calls,
            "closerCallsInMonth": sum(row["month"]["attempts"] for row in per_closer.values()),
        },
    }
    if out["reconcile"]["closerCallsInMonth"] + unmatched_closer_calls != total_in_month:
        print("RECONCILE FAIL (calls): closer + non-closer counts do not sum to total pulled")
        sys.exit(1)

    with open("calls.partial.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("OK calls.partial.json written. total pulled (month)=%d, closer calls=%d, non-closer=%d" % (
        total_in_month, out["reconcile"]["closerCallsInMonth"], unmatched_closer_calls))


if __name__ == "__main__":
    main()
