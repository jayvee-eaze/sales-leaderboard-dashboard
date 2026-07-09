#!/usr/bin/env python3
"""Stripe succeeded charges -> per-closer cash collected by day/week/month.
Usage: python3 build_stripe.py raw/stripe_charges.json raw/opp_page1.json raw/opp_page2.json
Joins each charge's billing email to a Closed-Won opportunity's contact email to find the
owning closer (same join key GHL uses natively: contact -> opportunity -> assignedTo).
Writes stripe.partial.json (merged into data.json by build_leaderboard.py).

Rule (same as AIFS): cash is ALWAYS the Stripe figure, never GHL's flat close-won stamp.
Excludes charges under $1 (card/link verification charges, not real sales).
"""
import json
import sys

from lib import CLOSER_BY_ID, CLOSERS, compute_windows, in_window, is_test_contact, load_opportunities, to_la_date
from datetime import datetime, timezone


def blank_window_row():
    return {"cash_cents": 0, "sales": 0}


def main():
    if len(sys.argv) < 2:
        print("usage: build_stripe.py <stripe_charges.json> [opp_page1.json opp_page2.json ...]")
        sys.exit(1)
    stripe_path = sys.argv[1]
    opp_paths = sys.argv[2:]

    with open(stripe_path, encoding="utf-8") as f:
        stripe_raw = json.load(f)
    charges = stripe_raw.get("charges", [])

    opps = load_opportunities(opp_paths) if opp_paths else []
    # contact email -> closer key, restricted to real (non-test) Closed-Won opps
    email_to_closer = {}
    for o in opps:
        if o.get("pipelineStageId") != "043f4a69-e187-481c-b43b-a7dd9ac34775":  # closedWon
            continue
        contact = o.get("contact") or {}
        email = (contact.get("email") or "").lower()
        if not email or is_test_contact(email, o.get("name")):
            continue
        closer = CLOSER_BY_ID.get(o.get("assignedTo"))
        if closer:
            email_to_closer[email] = closer["key"]

    now_utc = datetime.now(timezone.utc)
    windows = compute_windows(now_utc)

    per_closer = {c["key"]: {
        "name": c["name"],
        "day": blank_window_row(), "week": blank_window_row(), "month": blank_window_row(),
    } for c in CLOSERS}
    unattributed = {"day": blank_window_row(), "week": blank_window_row(), "month": blank_window_row()}
    window_total_cents = {"day": 0, "week": 0, "month": 0}

    for ch in charges:
        if ch.get("amount", 0) < 100:  # exclude sub-$1 verification charges
            continue
        date_str = to_la_date(ch.get("created"))
        if date_str is None:
            continue
        email = (ch.get("billing_email") or "").lower()
        closer_key = email_to_closer.get(email)
        for win_key in ("day", "week", "month"):
            if not in_window(date_str, windows[win_key]):
                continue
            window_total_cents[win_key] += ch["amount"]
            if closer_key:
                row = per_closer[closer_key][win_key]
            else:
                row = unattributed[win_key]
            row["cash_cents"] += ch["amount"]
            row["sales"] += 1

    # Reconcile gate: attributed + unattributed must equal the raw window total, to the cent.
    for win_key in ("day", "week", "month"):
        summed = sum(per_closer[c["key"]][win_key]["cash_cents"] for c in CLOSERS) + unattributed[win_key]["cash_cents"]
        if summed != window_total_cents[win_key]:
            print("RECONCILE FAIL (stripe): %s attributed+unattributed (%d) != window total (%d)" % (
                win_key, summed, window_total_cents[win_key]))
            sys.exit(1)

    out = {
        "windows": windows,
        "byCloser": per_closer,
        "unattributed": unattributed,
        "windowTotalCents": window_total_cents,
    }
    with open("stripe.partial.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("OK stripe.partial.json written. month total cash=$%.2f, unattributed=$%.2f" % (
        window_total_cents["month"] / 100.0, unattributed["month"]["cash_cents"] / 100.0))


if __name__ == "__main__":
    main()
