"""Shared constants and helpers for the Sales Leaderboard build scripts.
Single place for facts that must stay identical across build_calls.py, build_pipeline.py,
build_stripe.py and build_leaderboard.py, so they can never drift apart.
"""
import json
import os
from datetime import datetime, timedelta, timezone

LOCATION_ID = "61bBcrk5Fi4BuTWwvW0P"
PIPELINE_ID = "PJbkfqE3g4KRP8i9ZeLb"
TZ_NAME = "America/Los_Angeles"
LA_OFFSET_HOURS = -7  # PDT (America/Los_Angeles daylight time; this account's operating window is northern-hemisphere summer)
LA = timezone(timedelta(hours=LA_OFFSET_HOURS))

# The full closer roster, active and offboarded, lives in roster.json (not here), so
# onboarding or offboarding a closer is a one-line data edit, never a code change.
# CLOSERS = everyone who ever held the role, active or not: attribution (matching a
#   pipeline opp's assignedTo, a call log's userId, a Stripe charge's contact email)
#   always checks the full roster, so a departed closer's historical numbers are never
#   silently reclassified as "unowned" the day they're offboarded.
# ACTIVE_CLOSERS = only status:"active": this is who appears as a ranked row on the
#   Leaderboard/Scorecard/Leaders strip. build_leaderboard.py folds any offboarded
#   closer's real historical contribution into team totals, disclosed as its own line
#   in the audit panel, never silently dropped and never silently hidden.
# James Wellington is an agency-admin calendar flag, not a seated closer, and was never
# added to this roster on purpose (same exclusion the AIFS dashboard documents).
_ROSTER_PATH = os.path.join(os.path.dirname(__file__), "roster.json")
with open(_ROSTER_PATH, encoding="utf-8") as _f:
    CLOSERS = json.load(_f)["closers"]
ACTIVE_CLOSERS = [c for c in CLOSERS if c.get("status") == "active"]
CLOSER_BY_ID = {c["id"]: c for c in CLOSERS}
ACTIVE_KEYS = {c["key"] for c in ACTIVE_CLOSERS}

# The business's marketing launch date, same account and same date as the AIFS CRO
# dashboard. "All time" means since this date, not since the pipeline's oldest record.
LAUNCH_DATE = "2026-06-15"

# The 5 user-facing toggle windows (scorecard + leaderboard share these).
WINDOW_KEYS = ("day", "week", "month", "quarter", "allTime")
# Trailing-period comparisons used only to compute trend arrows, never shown as tabs.
# No "previous all time" exists, so allTime has no entry here.
PREV_OF = {"day": "prevDay", "week": "prevWeek", "month": "prevMonth", "quarter": "prevQuarter"}
# Every window build_calls.py / build_pipeline.py / build_stripe.py must bucket into.
ALL_WINDOW_KEYS = WINDOW_KEYS + tuple(PREV_OF.values())

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

# Board display order + labels for the pipeline funnel chart (Pipeline Health page).
STAGE_DISPLAY = [
    ("newUnworked", "New, Unworked"),
    ("contacted", "Contacted"),
    ("callBooked", "Call Booked"),
    ("rescheduling", "Rescheduling"),
    ("noShow", "No Show"),
    ("apptCancelled", "Appt Cancelled"),
    ("callHeld", "Call Held"),
    ("highPriority", "High Priority"),
    ("closedWon", "Closed Won"),
    ("longTermNurture", "Long-Term Nurture"),
    ("lost", "Lost"),
]

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
    """Read one or more raw export-messages-by-location (channel=Call) page dumps.
    Deduplicates by message id: the upstream cursor has occasionally misbehaved, forcing
    a pull to be split into overlapping date windows instead of clean cursor pages, so
    this makes the whole pipeline robust to any overlap rather than double-counting."""
    seen = set()
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        d = raw.get("data", raw)
        for m in d.get("messages") or []:
            mid = m.get("id")
            if mid is not None and mid in seen:
                continue
            if mid is not None:
                seen.add(mid)
            out.append(m)
    return out


def compute_windows(now_utc):
    """Given the current aware UTC datetime, return LA-local calendar window boundaries.
    Day = today. Week = this calendar week, Monday to Sunday. Month = this calendar month.
    Quarter = this calendar quarter. AllTime = since the business launch date.
    All bounds are inclusive date strings (YYYY-MM-DD) in America/Los_Angeles.
    """
    today = now_utc.astimezone(LA).date()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)
    month_start = today.replace(day=1)

    def add_month(d, n):
        m = d.month - 1 + n
        y = d.year + m // 12
        m = m % 12 + 1
        return d.replace(year=y, month=m, day=1)

    month_end = add_month(month_start, 1) - timedelta(days=1)

    quarter_start_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = today.replace(month=quarter_start_month, day=1)
    quarter_end = add_month(quarter_start, 3) - timedelta(days=1)
    quarter_num = quarter_start_month // 3 + 1

    launch = datetime.strptime(LAUNCH_DATE, "%Y-%m-%d").date()

    def fmt(d):
        return "{} {}".format(d.strftime("%b"), d.day)

    # Trailing-period comparisons, for trend arrows only (never a visible tab).
    prev_day = today - timedelta(days=1)
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start - timedelta(days=1)
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    prev_quarter_end = quarter_start - timedelta(days=1)
    prev_quarter_start_month = ((prev_quarter_end.month - 1) // 3) * 3 + 1
    prev_quarter_start = prev_quarter_end.replace(month=prev_quarter_start_month, day=1)

    return {
        "day": {"start": today.isoformat(), "end": today.isoformat(),
                "label": "{}, {}".format(today.strftime("%a"), fmt(today))},
        "week": {"start": week_start.isoformat(), "end": week_end.isoformat(),
                 "label": "{} - {}".format(fmt(week_start), fmt(week_end))},
        "month": {"start": month_start.isoformat(), "end": month_end.isoformat(),
                  "label": today.strftime("%B %Y")},
        "quarter": {"start": quarter_start.isoformat(), "end": quarter_end.isoformat(),
                    "label": "Q{} {}".format(quarter_num, today.year)},
        "allTime": {"start": launch.isoformat(), "end": today.isoformat(),
                    "label": "Since launch, {}".format(fmt(launch))},
        "prevDay": {"start": prev_day.isoformat(), "end": prev_day.isoformat(),
                    "label": "Yesterday"},
        "prevWeek": {"start": prev_week_start.isoformat(), "end": prev_week_end.isoformat(),
                     "label": "Last week"},
        "prevMonth": {"start": prev_month_start.isoformat(), "end": prev_month_end.isoformat(),
                      "label": "Last month"},
        "prevQuarter": {"start": prev_quarter_start.isoformat(), "end": prev_quarter_end.isoformat(),
                        "label": "Last quarter"},
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


def pct_num(numer, denom):
    """Same as pct() but returns a float (0-100) or None, for sorting/leader picks."""
    if not denom:
        return None
    return 100.0 * numer / denom


def rate2(numer, denom):
    if not denom:
        return "awaiting"
    return "{:.1f}%".format(100.0 * numer / denom)
