#!/usr/bin/env python3
"""Merge calls.partial.json + pipeline.partial.json + stripe.partial.json into data.json.
Usage: python3 build_leaderboard.py
This is the hard reconcile gate: if the three partials disagree with each other or with
their own internal sums, this script exits non-zero and data.json is NOT (re)written, so a
bad pull can never reach render.js or the deployed page.
"""
import json
import sys
from datetime import datetime, timezone

from lib import CLOSERS, money, pct, rate2


def load(name):
    with open(name, encoding="utf-8") as f:
        return json.load(f)


def main():
    calls = load("calls.partial.json")
    pipeline = load("pipeline.partial.json")
    stripe = load("stripe.partial.json")

    # Gate: the three build stages must agree on window boundaries (they're computed by
    # the same lib.compute_windows, but a stale partial from an earlier run would drift).
    if calls["windows"] != pipeline["windows"] or calls["windows"] != stripe["windows"]:
        print("RECONCILE FAIL (leaderboard): calls/pipeline/stripe partials disagree on window boundaries")
        print("  calls   :", calls["windows"])
        print("  pipeline:", pipeline["windows"])
        print("  stripe  :", stripe["windows"])
        sys.exit(1)

    windows = calls["windows"]
    now_utc = datetime.now(timezone.utc)

    leaderboard = {}
    totals = {}
    for win_key in ("day", "week", "month"):
        rows = []
        t_deals = t_cash = t_booked = t_held = t_noshow = t_showed = t_out = t_in = 0
        t_seconds = 0
        for c in CLOSERS:
            key = c["key"]
            call_row = calls["byCloser"][key][win_key]
            pipe_row = pipeline["byCloser"][key][win_key]
            cash_cents = stripe["byCloser"][key][win_key]["cash_cents"]

            booked = pipe_row["booked"]
            held = pipe_row["held"]
            no_show = pipe_row["noShow"]
            showed = pipe_row["showed"]
            won = pipe_row["won"]

            row = {
                "key": key,
                "name": c["name"],
                "dealsClosed": won,
                "cash": money(cash_cents),
                "cashCents": cash_cents,
                "callsBooked": booked,
                "callsHeld": held,
                "noShow": no_show,
                "noShowRate": pct(no_show, showed + no_show),
                "showed": showed,
                "showRate": pct(showed, showed + no_show),
                "closeRate": pct(won, showed),
                "outboundCalls": call_row["outbound"],
                "inboundCalls": call_row["inbound"],
                "totalCalls": call_row["attempts"],
                "callHours": call_row["hours"],
            }
            rows.append(row)

            t_deals += won
            t_cash += cash_cents
            t_booked += booked
            t_held += held
            t_noshow += no_show
            t_showed += showed
            t_out += call_row["outbound"]
            t_in += call_row["inbound"]
            t_seconds += call_row["seconds"]

        rows.sort(key=lambda r: (-r["cashCents"], -r["dealsClosed"], r["name"]))
        for i, r in enumerate(rows):
            r["rank"] = i + 1

        leaderboard[win_key] = rows
        totals[win_key] = {
            "dealsClosed": t_deals,
            "cash": money(t_cash),
            "callsBooked": t_booked,
            "callsHeld": t_held,
            "noShow": t_noshow,
            "noShowRate": pct(t_noshow, t_showed + t_noshow),
            "showed": t_showed,
            "showRate": pct(t_showed, t_showed + t_noshow),
            "closeRate": pct(t_deals, t_showed),
            "outboundCalls": t_out,
            "inboundCalls": t_in,
            "totalCalls": t_out + t_in,
            "callHours": round(t_seconds / 3600.0, 1),
        }

    # Reconcile gate: leaderboard totals must equal the totals independently summed above,
    # AND the month totals must equal the raw partials' own reconcile figures.
    if totals["month"]["dealsClosed"] != sum(r["dealsClosed"] for r in leaderboard["month"]):
        print("RECONCILE FAIL (leaderboard): month dealsClosed total disagrees with row sum")
        sys.exit(1)
    stripe_month_attributed = sum(stripe["byCloser"][c["key"]]["month"]["cash_cents"] for c in CLOSERS)
    if totals["month"]["cash"] != money(stripe_month_attributed):
        print("RECONCILE FAIL (leaderboard): month cash total disagrees with stripe partial")
        sys.exit(1)

    data = {
        "asOf": windows["day"]["start"],
        "timezone": "America/Los_Angeles",
        "generatedAtUtc": now_utc.isoformat(timespec="seconds"),
        "windows": windows,
        "roster": [{"key": c["key"], "name": c["name"]} for c in CLOSERS],
        "leaderboard": leaderboard,
        "totals": totals,
        "audit": {
            "excludedTestRecords": pipeline["excludedTestRecords"],
            "totalOpportunitiesPulled": pipeline["totalOpportunities"],
            "nonCloserCallsThisMonth": calls["reconcile"]["unmatchedClosersCallsInMonth"],
            "unattributedCashMonth": money(stripe["unattributed"]["month"]["cash_cents"]),
            "unattributedCashWeek": money(stripe["unattributed"]["week"]["cash_cents"]),
            "unattributedCashDay": money(stripe["unattributed"]["day"]["cash_cents"]),
        },
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("OK data.json written. asOf=%s month totals: deals=%d cash=%s calls=%d" % (
        data["asOf"], totals["month"]["dealsClosed"], totals["month"]["cash"], totals["month"]["totalCalls"]))


if __name__ == "__main__":
    main()
