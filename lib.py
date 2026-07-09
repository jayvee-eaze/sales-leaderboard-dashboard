"""Shared constants and helpers for the Sales Leaderboard build scripts.
Single place for facts that must stay identical across build_calls.py, build_pipeline.py,
build_stripe.py and build_leaderboard.py, so they can never drift apart.
"""
import json
from datetime import datetime, timedelta, timezone

LOCATION_ID = "61bBcrk5Fi4BuTWwvW0P"
PIPELINE_ID = "PJbkfqE3g4KRP8i9ZeLb"
TZ_NAME = "America/Los_Angeles"
LA_OFFSET_HOURS = -7  # PDT (America/Los_Angeles daylight time; this account's operating window is northern-hemisphere summer)
LA = timezone(timedelta(hours=LA_OFFSET_HOURS))

# The three seated closers who own pipeline opportunities. James Wellington is an
# agency-admin calendar flag, not a seated closer, and is excluded on purpose.
CLOSERS = [
    {"id": "KyR0lFZOC0l0GQHM6SLv", "key": "caleb", "name": "Caleb Chase"},
    {"id": "rHJOq1QChy55u6ZfczJ1", "key": "matthew", "name": "Matthew Burns"},
    {"id": "Z3WFuyTIWmoZMmzNJrRl", "key": "dan", "name": "Dan Baldasso"},
]
CLOSER_BY_ID = {c["id"]: c for c in CLOSERS}

STAGE_MAP = {
    "b9bfc681-76ef-4402-a7b8-428e39788582": "newUnworked",
    "910d1097-8955-4f62-9c79-eaafc3963a22": "contacted",
    "a774b303-1cba-4279-b5d5-d06ae8eca597": "callBooked",
    "58b9e8fb-3e0f-4273-84d7-2a11c7bc0b59": "rescheduling",
    "8dec9a2c-863a-45d4-8495-f7dc8c17704b": "noShow",
    "fe83e23b-7a54-4906-95fd-3415a8824a32": "apptCancelled",
    "55f294c8-14a8-4734-83e3-9cb8d537c419": "callHeld",
    "a402364a-ad70-40af-b310-bfbce676ef45": "highPriority",
    "043f4a69-e187-481c-b43b-a7dd9ac34775": "closedWon",
    "a3bd42d8-305d-4307-aba7-b1da1658acbc": "longTermNurture",
    "368b91ca-95f0-48f8-89e2-6074426b983b": "lost",
}

# Stages that mean "a call was booked and its outcome, whatever it was, is now known
# or still pending" - the full universe booked-call denominator.
BOOKED_STAGES = {"callBooked", "rescheduling", "noShow", "apptCancelled", "callHeld", "highPriority", "closedWon"}
# Stages that mean the prospect actually showed up to the call.
SHOWED_STAGES = {"callHeld", "highPriority", "closedWon"}

TEST_DOMAINS = {"tothemoondigital.com.au", "amala.agency", "eazeconsulting.com", "eazepay.com"}


def is_test_contact(email, opp_name=""):
    email = (email or "").lower()
    name = (opp_name or "").lower()
    if "+test" in email or "+medtest" in email:
        return True
    if "test" in name:
        return True
    domain = email.split("@")[-1] if "@" in email else ""
    return domain in TEST_DOMAINS


def parse_iso(ts):
    """Parse a GHL/Stripe ISO8601 UTC timestamp into an aware UTC datetime."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def to_la_date(ts):
    """Convert an ISO8601 UTC timestamp (or epoch seconds) to a YYYY-MM-DD date string in LA time."""
    dt = parse_iso(ts)
    if dt is None:
        return None
    return dt.astimezone(LA).date().isoformat()


def load_opportunities(paths):
    """Read one or more raw search-opportunity page dumps, return the flat opportunities list."""
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        d = raw.get("data", raw)
        opps = d.get("opportunities") or d.get("data", {}).get("opportunities") or []
        out.extend(opps)
    return out


def load_calls(paths):
    """Read one or more raw export-messages-by-location (channel=Call) page dumps."""
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        d = raw.get("data", raw)
        out.extend(d.get("messages") or [])
    return out


def compute_windows(now_utc):
    """Given the current aware UTC datetime, return LA-local calendar window boundaries.
    Day = today. Week = this calendar week, Monday to Sunday. Month = this calendar month.
    All bounds are inclusive date strings (YYYY-MM-DD) in America/Los_Angeles.
    """
    today = now_utc.astimezone(LA).date()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)
    month_start = today.replace(day=1)
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    month_end = next_month - timedelta(days=1)

    def fmt(d):
        return "{} {}".format(d.strftime("%b"), d.day)

    return {
        "day": {"start": today.isoformat(), "end": today.isoformat(),
                "label": "{}, {}".format(today.strftime("%a"), fmt(today))},
        "week": {"start": week_start.isoformat(), "end": week_end.isoformat(),
                 "label": "{} - {}".format(fmt(week_start), fmt(week_end))},
        "month": {"start": month_start.isoformat(), "end": month_end.isoformat(),
                  "label": today.strftime("%B %Y")},
    }


def in_window(date_str, window):
    if date_str is None:
        return False
    return window["start"] <= date_str <= window["end"]


def money(cents):
    return "${:,.2f}".format(cents / 100.0)


def pct(numer, denom):
    if not denom:
        return "awaiting"
    return "{:.0f}%".format(100.0 * numer / denom)


def rate2(numer, denom):
    if not denom:
        return "awaiting"
    return "{:.1f}%".format(100.0 * numer / denom)
