#!/usr/bin/env python3
"""Team-wide day-by-day rollup since business launch, for the Pipeline Health trend charts.
Usage: python3 build_daily.py raw/opp_page1.json raw/opp_page2.json -- raw/calls_alltime_page1.json raw/calls_alltime_page2.json -- raw/stripe_charges.json
Writes daily.partial.json (merged into data.json by build_leaderboard.py).

This recomputes independently from the raw files (not from calls/pipeline/stripe.partial.json),
so build_leaderboard.py can use it as a genuine second, independent reconcile check: the sum
of every day here must equal the already-computed allTime totals, or the build fails.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

from lib import (CLOSER_BY_ID, STAGE_MAP, BOOKED_STAGES, SHOWED_STAGES, LAUNCH_DATE,
                  compute_windows, is_test_contact, load_opportunities, load_calls, to_la_date)


def split_args(argv):
    """Split argv on the literal "--" separators into 3 groups: opp paths, call paths, stripe path."""
    groups, cur = [], []
    for a in argv:
        if a == "--":
            groups.append(cur)
            cur = []
        else:
            cur.append(a)
    groups.append(cur)
    if len(groups) != 3:
        print('usage: build_daily.py <opp pages...> -- <call pages...> -- <stripe_charges.json>')
        sys.exit(1)
    return groups[0], groups[1], groups[2]


def blank_day():
    return {"callsBooked": 0, "callsHeld": 0, "noShow": 0, "showed": 0, "won": 0,
            "cashCents": 0, "outboundCalls": 0, "inboundCalls": 0, "totalCalls": 0}


def main():
    opp_paths, call_paths, stripe_paths = split_args(sys.argv[1:])
    opps = load_opportunities(opp_paths)
    calls = load_calls(call_paths)
    with open(stripe_paths[0], encoding="utf-8") as f:
        charges = json.load(f).get("charges", [])

    now_utc = datetime.now(timezone.utc)
    today = compute_windows(now_utc)["day"]["start"]
    launch = datetime.strptime(LAUNCH_DATE, "%Y-%m-%d").date()
    today_d = datetime.strptime(today, "%Y-%m-%d").date()

    days = {}
    d = launch
    while d <= today_d:
        days[d.isoformat()] = blank_day()
        d += timedelta(days=1)

    for o in opps:
        stage_key = STAGE_MAP.get(o.get("pipelineStageId"))
        if stage_key is None:
            continue
        contact = o.get("contact") or {}
        if is_test_contact(contact.get("email"), o.get("name")):
            continue
        if not CLOSER_BY_ID.get(o.get("assignedTo")):
            continue  # team-wide rollup still means the 3 closers, same roster as the leaderboard
        date_str = to_la_date(o.get("lastStageChangeAt"))
        if date_str not in days:
            continue
        row = days[date_str]
        if stage_key in BOOKED_STAGES:
            row["callsBooked"] += 1
        if stage_key == "callHeld":
            row["callsHeld"] += 1
        if stage_key == "noShow":
            row["noShow"] += 1
        if stage_key in SHOWED_STAGES:
            row["showed"] += 1
        if stage_key == "closedWon":
            row["won"] += 1

    for m in calls:
        if not CLOSER_BY_ID.get(m.get("userId")):
            continue  # setters/VAs/admins excluded, same roster rule as build_calls.py
        date_str = to_la_date(m.get("dateAdded"))
        if date_str not in days:
            continue
        row = days[date_str]
        direction = m.get("direction")
        if direction == "outbound":
            row["outboundCalls"] += 1
        elif direction == "inbound":
            row["inboundCalls"] += 1
        row["totalCalls"] += 1

    email_to_closer = {}
    for o in opps:
        if o.get("pipelineStageId") != "043f4a69-e187-481c-b43b-a7dd9ac34775":
            continue
        contact = o.get("contact") or {}
        email = (contact.get("email") or "").lower()
        if not email or is_test_contact(email, o.get("name")):
            continue
        if CLOSER_BY_ID.get(o.get("assignedTo")):
            email_to_closer[email] = True

    for ch in charges:
        if ch.get("amount", 0) < 100:
            continue
        email = (ch.get("billing_email") or "").lower()
        if email not in email_to_closer:
            continue  # unattributed cash is reported separately by build_stripe.py, not double-counted here
        date_str = to_la_date(ch.get("created"))
        if date_str not in days:
            continue
        days[date_str]["cashCents"] += ch["amount"]

    daily = [{"date": d, **days[d]} for d in sorted(days.keys())]

    # Internal sanity: showed+noShow can never exceed booked, for any day.
    for row in daily:
        if row["showed"] + row["noShow"] > row["callsBooked"]:
            print("RECONCILE FAIL (daily): %s showed+noShow > callsBooked" % row["date"])
            sys.exit(1)

    out = {"launchDate": LAUNCH_DATE, "asOf": today, "daily": daily}
    with open("daily.partial.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("OK daily.partial.json written. %d days, %d total won, %d total calls" % (
        len(daily), sum(r["won"] for r in daily), sum(r["totalCalls"] for r in daily)))


if __name__ == "__main__":
    main()
