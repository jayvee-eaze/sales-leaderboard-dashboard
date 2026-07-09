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

from lib import CLOSERS, WINDOW_KEYS, PREV_OF, STAGE_DISPLAY, BOOKED_STAGES, money, pct, pct_num


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


def pick_leader(rows, numeric_key, display_key, require_positive=False):
    """Highest numeric_key among rows where it isn't None (and, if require_positive, > 0);
    ties broken by name. None if no row qualifies."""
    candidates = [r for r in rows if r.get(numeric_key) is not None and (not require_positive or r[numeric_key] > 0)]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (-r[numeric_key], r["name"]))
    top = candidates[0]
    return {"key": top["key"], "name": top["name"], "value": top[display_key]}


def build_badges(row, leaders_win, career_top_cash_key, career_first_deal_keys):
    """Every badge here is a real, computed condition against already-reconciled numbers,
    never an invented label. 'Leading'/'Best Show Rate'/etc only fire when there's a real
    signal (a positive value), so a field of zeros never gets awarded a fake achievement."""
    badges = []
    if row["rank"] == 1 and row["cashCents"] > 0:
        badges.append("Leading")
    if career_top_cash_key and row["key"] == career_top_cash_key:
        badges.append("Top Closer")
    if row["key"] in career_first_deal_keys:
        badges.append("First Deal")
    top_show = leaders_win.get("topShowRate")
    if top_show and row["key"] == top_show["key"] and row["showRateNum"] is not None:
        badges.append("Best Show Rate")
    most_active = leaders_win.get("mostActive")
    if most_active and row["key"] == most_active["key"] and row["totalCalls"] > 0:
        badges.append("Most Active")
    top_booked = leaders_win.get("topBooked")
    if top_booked and row["key"] == top_booked["key"] and row["callsBooked"] > 0:
        badges.append("Most Booked")
    return badges


def fmt_date_short(iso_date):
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    return "{} {}".format(dt.strftime("%b"), dt.day)


def compute_daily_insights(daily):
    """Narrative one-liners for the Pipeline Health charts, entirely derived from the
    same daily[] rollup the charts are drawn from (same data, same numbers, just also
    described in words). Every branch has a well-formed fallback for thin/no data."""
    n = len(daily)
    total_booked = sum(d["callsBooked"] for d in daily)
    active_days = sum(1 for d in daily if d["totalCalls"] > 0)
    best_day = max(daily, key=lambda d: d["callsBooked"]) if daily else None
    last7 = daily[-7:]
    last7_booked = sum(d["callsBooked"] for d in last7)

    if total_booked == 0 or not best_day or best_day["callsBooked"] == 0:
        booked_note = "No calls booked yet since launch."
    else:
        booked_note = "{} calls booked since launch, {} in the last 7 days. Busiest day: {} with {}.".format(
            total_booked, last7_booked, fmt_date_short(best_day["date"]), best_day["callsBooked"])

    resolved_days = [d for d in daily if (d["showed"] + d["noShow"]) > 0]
    if not resolved_days:
        show_note = "No calls have been resolved as showed or no-show yet."
    else:
        rates = [100.0 * d["showed"] / (d["showed"] + d["noShow"]) for d in resolved_days]
        recent = rates[-7:]
        show_note = "Show rate has ranged {:.0f}% to {:.0f}% across the {} days with a resolved call, averaging {:.0f}% recently.".format(
            min(rates), max(rates), len(resolved_days), sum(recent) / len(recent))

    total_cash = sum(d["cashCents"] for d in daily)
    cash_days = [i for i, d in enumerate(daily) if d["cashCents"] > 0]
    if not cash_days:
        cash_note = "No cash collected yet since launch."
    else:
        last_idx = cash_days[-1]
        days_since = (n - 1) - last_idx
        if len(cash_days) == 1:
            tail = "That sale closed today." if days_since == 0 else "No cash collected in the {} day{} since.".format(
                days_since, "" if days_since == 1 else "s")
            cash_note = "{} collected total, entirely from one sale on {}. {}".format(
                money(total_cash), fmt_date_short(daily[last_idx]["date"]), tail)
        else:
            cash_note = "{} collected total across {} days with a sale, most recently {}.".format(
                money(total_cash), len(cash_days), fmt_date_short(daily[last_idx]["date"]))

    return {
        "callsBookedNote": booked_note,
        "showRateNote": show_note,
        "cashNote": cash_note,
        "totalCallsBooked": total_booked,
        "bestDay": {"label": fmt_date_short(best_day["date"]), "value": best_day["callsBooked"]} if best_day else None,
        "activeDays": active_days,
        "totalDays": n,
    }


def compute_funnel_insights(stage_totals, funnel_total):
    booked_universe = sum(stage_totals.get(k, 0) for k in BOOKED_STAGES)
    closed_won = stage_totals.get("closedWon", 0)
    new_unworked = stage_totals.get("newUnworked", 0)
    lead_note = "{} of {} opportunities ({}) are still New, Unworked.".format(
        new_unworked, funnel_total, pct(new_unworked, funnel_total))
    if booked_universe == 0:
        close_note = "No opportunities have reached Call Booked or further yet."
    else:
        close_note = "Of the {} opportunities that reached Call Booked or further, {} {} closed ({}).".format(
            booked_universe, closed_won, "has" if closed_won == 1 else "have", pct(closed_won, booked_universe))
    return {"leadNote": lead_note, "closeNote": close_note}


def build_gap_note(row, rows_sorted):
    """Gap-to-next-rank copy, entirely derived from real cash figures already on the row."""
    if sum(r["cashCents"] for r in rows_sorted) == 0:
        return "No cash collected yet this window"
    if row["rank"] == 1:
        if len(rows_sorted) > 1:
            gap = row["cashCents"] - rows_sorted[1]["cashCents"]
            if gap > 0:
                return "Leading by " + money(gap)
        return "Setting the pace"
    leader = rows_sorted[0]
    gap = leader["cashCents"] - row["cashCents"]
    if gap > 0:
        return money(gap) + " to pass " + leader["name"]
    return "Tied with " + leader["name"]


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
                "topCash": pick_leader(rows, "cashCents", "cash", require_positive=True),
                "topCloseRate": pick_leader(rows, "closeRateNum", "closeRate"),
                "topShowRate": pick_leader(rows, "showRateNum", "showRate"),
                "mostActive": pick_leader(
                    [dict(r, totalCallsNum=r["totalCalls"]) for r in rows], "totalCallsNum", "totalCalls", require_positive=True),
                "topBooked": pick_leader(
                    [dict(r, callsBookedNum=r["callsBooked"]) for r in rows], "callsBookedNum", "callsBooked", require_positive=True),
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

    # Career-wide (all-time) facts, attached to every window's rows regardless of which
    # window is being viewed: these are permanent achievements, not window-scoped ones.
    career_top_cash = leaders["allTime"]["topCash"]
    career_top_cash_key = career_top_cash["key"] if career_top_cash else None
    career_first_deal_keys = {r["key"] for r in leaderboard["allTime"] if r["dealsClosed"] > 0}

    for win_key in WINDOW_KEYS:
        for row in leaderboard[win_key]:
            row["badges"] = build_badges(row, leaders[win_key], career_top_cash_key, career_first_deal_keys)
            row["gapNote"] = build_gap_note(row, leaderboard[win_key])

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
    funnel = [{"key": k, "label": label, "count": pipeline["stageTotals"].get(k, 0),
               "pct": pct(pipeline["stageTotals"].get(k, 0), pipeline["totalOpportunities"])}
              for k, label in STAGE_DISPLAY]
    funnel_total = sum(f["count"] for f in funnel)
    if funnel_total != pipeline["totalOpportunities"]:
        print("RECONCILE FAIL (leaderboard): funnel stage sum (%d) != total opportunities pulled (%d)" % (
            funnel_total, pipeline["totalOpportunities"]))
        sys.exit(1)

    daily_insights = compute_daily_insights(daily["daily"])
    funnel_insights = compute_funnel_insights(pipeline["stageTotals"], funnel_total)

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
        "dailyInsights": daily_insights,
        "funnel": funnel,
        "funnelTotal": funnel_total,
        "funnelInsights": funnel_insights,
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
