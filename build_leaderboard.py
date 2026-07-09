#!/usr/bin/env python3
"""Merge calls/pipeline/stripe/daily partials into data.json.
Usage: python3 build_leaderboard.py
This is the hard reconcile gate: if the partials disagree with each other or with their
own internal sums, this script exits non-zero and data.json is NOT (re)written, so a bad
pull can never reach render.js or the deployed page.
"""
import json
import sys
from datetime import datetime, timezone

from lib import CLOSERS, WINDOW_KEYS, PREV_OF, STAGE_DISPLAY, money, pct, pct_num


def load(name):
    with open(name, encoding="utf-8") as f:
        return json.load(f)


def trend_tag(delta_cash, delta_deals):
    score = delta_cash if delta_cash != 0 else delta_deals
    if score > 0:
        return "up"
    if score < 0:
        return "down"
    return "flat"


def signed_money(cents):
    sign = "+" if cents > 0 else ("-" if cents < 0 else "")
    return sign + money(abs(cents))


def trend_note(delta_cash, delta_deals):
    parts = []
    if delta_cash != 0:
        parts.append(signed_money(delta_cash))
    if delta_deals != 0:
        parts.append(("+" if delta_deals > 0 else "") + str(delta_deals) + (" deal" if abs(delta_deals) == 1 else " deals"))
    return ", ".join(parts) if parts else "flat vs prior period"


def pick_leader(rows, numeric_key, display_key):
    """Highest numeric_key among rows where it isn't None; ties broken by name. None if empty."""
    candidates = [r for r in rows if r.get(numeric_key) is not None]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (-r[numeric_key], r["name"]))
    top = candidates[0]
    return {"key": top["key"], "name": top["name"], "value": top[display_key]}


def main():
    calls = load("calls.partial.json")
    pipeline = load("pipeline.partial.json")
    stripe = load("stripe.partial.json")
    daily = load("daily.partial.json")

    # Gate: the three per-window build stages must agree on window boundaries.
    if calls["windows"] != pipeline["windows"] or calls["windows"] != stripe["windows"]:
        print("RECONCILE FAIL (leaderboard): calls/pipeline/stripe partials disagree on window boundaries")
        sys.exit(1)

    windows = calls["windows"]
    now_utc = datetime.now(timezone.utc)

    leaderboard = {}
    totals = {}
    leaders = {}
    ALL_KEYS = list(WINDOW_KEYS) + list(PREV_OF.values())
    raw_rows = {}  # win_key -> per-closer row, including prev windows, before trend is attached

    for win_key in ALL_KEYS:
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
            total_calls = call_row["attempts"]

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
                "showRateNum": pct_num(showed, showed + no_show),
                "closeRate": pct(won, showed),
                "closeRateNum": pct_num(won, showed),
                "outboundCalls": call_row["outbound"],
                "inboundCalls": call_row["inbound"],
                "totalCalls": total_calls,
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
        raw_rows[win_key] = rows

        if win_key in WINDOW_KEYS:
            leaderboard[win_key] = rows
            totals[win_key] = {
                "dealsClosed": t_deals,
                "cash": money(t_cash),
                "cashCents": t_cash,
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
            leaders[win_key] = {
                "topCash": pick_leader(rows, "cashCents", "cash"),
                "topCloseRate": pick_leader(rows, "closeRateNum", "closeRate"),
                "topShowRate": pick_leader(rows, "showRateNum", "showRate"),
                "mostActive": pick_leader(
                    [dict(r, totalCallsNum=r["totalCalls"]) for r in rows], "totalCallsNum", "totalCalls"),
            }

    # Attach trend deltas (day/week/month/quarter only, vs their prev-period counterpart).
    for win_key, prev_key in PREV_OF.items():
        prev_by_key = {r["key"]: r for r in raw_rows[prev_key]}
        for row in leaderboard[win_key]:
            prev = prev_by_key[row["key"]]
            delta_cash = row["cashCents"] - prev["cashCents"]
            delta_deals = row["dealsClosed"] - prev["dealsClosed"]
            row["trend"] = trend_tag(delta_cash, delta_deals)
            row["trendNote"] = trend_note(delta_cash, delta_deals)
    for row in leaderboard["allTime"]:
        row["trend"] = "na"
        row["trendNote"] = "since launch, no prior period"

    for win_key, prev_key in PREV_OF.items():
        prev_cash = sum(r["cashCents"] for r in raw_rows[prev_key])
        prev_deals = sum(r["dealsClosed"] for r in raw_rows[prev_key])
        delta_cash = totals[win_key]["cashCents"] - prev_cash
        delta_deals = totals[win_key]["dealsClosed"] - prev_deals
        totals[win_key]["trend"] = trend_tag(delta_cash, delta_deals)
        totals[win_key]["trendNote"] = trend_note(delta_cash, delta_deals)
    totals["allTime"]["trend"] = "na"
    totals["allTime"]["trendNote"] = "since launch, no prior period"

    # Reconcile gates, every display window.
    for win_key in WINDOW_KEYS:
        if totals[win_key]["dealsClosed"] != sum(r["dealsClosed"] for r in leaderboard[win_key]):
            print("RECONCILE FAIL (leaderboard): %s dealsClosed total disagrees with row sum" % win_key)
            sys.exit(1)
        stripe_attributed = sum(stripe["byCloser"][c["key"]][win_key]["cash_cents"] for c in CLOSERS)
        if totals[win_key]["cashCents"] != stripe_attributed:
            print("RECONCILE FAIL (leaderboard): %s cash total disagrees with stripe partial" % win_key)
            sys.exit(1)
        if win_key != "allTime":
            if totals[win_key]["dealsClosed"] > totals["allTime"]["dealsClosed"]:
                print("RECONCILE FAIL (leaderboard): %s dealsClosed exceeds allTime" % win_key)
                sys.exit(1)
            if totals[win_key]["callsBooked"] > totals["allTime"]["callsBooked"]:
                print("RECONCILE FAIL (leaderboard): %s callsBooked exceeds allTime" % win_key)
                sys.exit(1)
        # Leader sanity: topCash must literally be the sorted #1 row (leaderboard is cash-sorted).
        top_row = leaderboard[win_key][0]
        top_cash_leader = leaders[win_key]["topCash"]
        if top_row["cashCents"] > 0 and (not top_cash_leader or top_cash_leader["key"] != top_row["key"]):
            print("RECONCILE FAIL (leaderboard): %s topCash leader disagrees with sorted rank 1" % win_key)
            sys.exit(1)

    # Independent cross-check: the daily rollup (computed from raw files, not from the
    # partials above) must sum to the same allTime totals.
    daily_sum = {
        "callsBooked": sum(d["callsBooked"] for d in daily["daily"]),
        "callsHeld": sum(d["callsHeld"] for d in daily["daily"]),
        "noShow": sum(d["noShow"] for d in daily["daily"]),
        "won": sum(d["won"] for d in daily["daily"]),
        "cashCents": sum(d["cashCents"] for d in daily["daily"]),
        "totalCalls": sum(d["totalCalls"] for d in daily["daily"]),
    }
    checks = [
        ("callsBooked", daily_sum["callsBooked"], totals["allTime"]["callsBooked"]),
        ("callsHeld", daily_sum["callsHeld"], totals["allTime"]["callsHeld"]),
        ("noShow", daily_sum["noShow"], totals["allTime"]["noShow"]),
        ("won", daily_sum["won"], totals["allTime"]["dealsClosed"]),
        ("cashCents", daily_sum["cashCents"], totals["allTime"]["cashCents"]),
        ("totalCalls", daily_sum["totalCalls"], totals["allTime"]["totalCalls"]),
    ]
    for label, a, b in checks:
        if a != b:
            print("RECONCILE FAIL (leaderboard): daily rollup %s sum (%s) != allTime total (%s)" % (label, a, b))
            sys.exit(1)

    # Funnel: whole-board stage snapshot (board-exact, includes test records, same
    # convention as AIFS: the funnel shows what the live GHL board shows).
    funnel = [{"key": k, "label": label, "count": pipeline["stageTotals"].get(k, 0)} for k, label in STAGE_DISPLAY]
    funnel_total = sum(f["count"] for f in funnel)
    if funnel_total != pipeline["totalOpportunities"]:
        print("RECONCILE FAIL (leaderboard): funnel stage sum (%d) != total opportunities pulled (%d)" % (
            funnel_total, pipeline["totalOpportunities"]))
        sys.exit(1)

    data = {
        "asOf": windows["day"]["start"],
        "timezone": "America/Los_Angeles",
        "generatedAtUtc": now_utc.isoformat(timespec="seconds"),
        "windows": {k: windows[k] for k in WINDOW_KEYS},
        "roster": [{"key": c["key"], "name": c["name"]} for c in CLOSERS],
        "leaderboard": leaderboard,
        "totals": totals,
        "leaders": leaders,
        "daily": daily["daily"],
        "funnel": funnel,
        "funnelTotal": funnel_total,
        "audit": {
            "excludedTestRecords": pipeline["excludedTestRecords"],
            "totalOpportunitiesPulled": pipeline["totalOpportunities"],
            "nonCloserCallsAllTime": calls["reconcile"]["unmatchedClosersCallsAllTime"],
            "unattributedCashAllTime": money(stripe["unattributed"]["allTime"]["cash_cents"]),
        },
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("OK data.json written. asOf=%s all-time totals: deals=%d cash=%s calls=%d" % (
        data["asOf"], totals["allTime"]["dealsClosed"], totals["allTime"]["cash"], totals["allTime"]["totalCalls"]))


if __name__ == "__main__":
    main()
