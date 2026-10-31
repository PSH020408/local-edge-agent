"""Time and date tools.

Design rule: all calendar arithmetic happens here, in code. The model only
chooses a tool and reads a finished, human-readable answer back. Evaluation
(docs/benchmarks.md, Runs 3-4) showed that both qwen3:8b and qwen3:14b pick
the right tool but then get calendar math wrong when they do it themselves.

Docstrings are sent to the model as tool descriptions, so they are written
for the model: what the tool does, when to use it, and input examples.
"#" comments are for human readers only and are never sent to the model.
"""

from __future__ import annotations

import calendar
import difflib
import os
import re
from datetime import date as Date
from datetime import datetime, timedelta
from datetime import time as Time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from .tools import ToolRegistry

# Models often pass city names instead of IANA zone names.
CITY_ALIASES = {
    "seoul": "Asia/Seoul", "korea": "Asia/Seoul", "busan": "Asia/Seoul",
    "tokyo": "Asia/Tokyo", "osaka": "Asia/Tokyo", "japan": "Asia/Tokyo",
    "beijing": "Asia/Shanghai", "shanghai": "Asia/Shanghai", "china": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong", "taipei": "Asia/Taipei", "singapore": "Asia/Singapore",
    "bangkok": "Asia/Bangkok", "hanoi": "Asia/Bangkok", "jakarta": "Asia/Jakarta",
    "delhi": "Asia/Kolkata", "new delhi": "Asia/Kolkata", "mumbai": "Asia/Kolkata", "india": "Asia/Kolkata",
    "dubai": "Asia/Dubai", "moscow": "Europe/Moscow", "istanbul": "Europe/Istanbul",
    "london": "Europe/London", "uk": "Europe/London", "dublin": "Europe/Dublin",
    "paris": "Europe/Paris", "berlin": "Europe/Berlin", "madrid": "Europe/Madrid",
    "rome": "Europe/Rome", "amsterdam": "Europe/Amsterdam", "zurich": "Europe/Zurich",
    "new york": "America/New_York", "nyc": "America/New_York", "boston": "America/New_York",
    "washington": "America/New_York", "toronto": "America/Toronto", "chicago": "America/Chicago",
    "denver": "America/Denver", "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles", "seattle": "America/Los_Angeles",
    "vancouver": "America/Vancouver", "mexico city": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo", "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne",
    "auckland": "Pacific/Auckland", "honolulu": "Pacific/Honolulu", "hawaii": "Pacific/Honolulu",
    "utc": "UTC", "gmt": "UTC",
}

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WEEKDAY_LOOKUP = {name: i for i, name in enumerate(WEEKDAYS)} | {name[:3]: i for i, name in enumerate(WEEKDAYS)}
_UNITS = {"day": "days", "week": "weeks", "month": "months", "year": "years"}

DATE_INPUT_HELP = (
    "Use 'today', 'now', 'tomorrow', 'yesterday', 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM', 'HH:MM', '9:30 AM', "
    "'tomorrow 3 PM', or a phrase supported by resolve_date (e.g. 'next friday')."
)

# Time of day with an optional day: "9:30 AM", "3 pm", "14:05:10", "today 9:30 AM",
# "tomorrow at 14:00", "2026-11-02 3:15 PM", "9:30 AM tomorrow". Run 7: "9:30 AM" was rejected.
_TIME = r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?(?::(?P<s>\d{2}))?\s*(?P<ampm>[ap]\.?\s?m\.?)?"
_DAY = r"(?P<day>today|tomorrow|yesterday|\d{4}-\d{2}-\d{2})"
_DAY_THEN_TIME = re.compile(rf"(?:{_DAY}\s+(?:at\s+)?)?{_TIME}")
_TIME_THEN_DAY = re.compile(rf"{_TIME}\s+{_DAY}")


# ---------- time zones ----------

# Run 5: qwen3:8b passed timezone="user" after reading "Empty means the user's local time".
_LOCAL_WORDS = {"", "local", "user", "me", "my", "here", "home", "current", "mine", "default", "system"}


def _zone(name: str) -> ZoneInfo | None:
    """Return a ZoneInfo, or None for the Mac's local time zone."""
    name = name.strip()
    if name.lower() in _LOCAL_WORDS:
        return None
    key = CITY_ALIASES.get(name.lower(), name)
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError):
        matches = difflib.get_close_matches(key, sorted(available_timezones()), n=3)
        hint = f" Did you mean: {', '.join(matches)}?" if matches else ""
        raise ValueError(
            f"unknown time zone '{name}'. Use an IANA name like 'America/New_York' or a major city name, "
            f"or leave it empty for the user's local time.{hint}"
        ) from None


def _local_zone_name() -> str:
    # The TZ environment variable overrides the system setting when present.
    env = os.environ.get("TZ", "").lstrip(":")
    if env and "/" in env:
        return env
    # On macOS /etc/localtime is a symlink into the zoneinfo database.
    try:
        target = os.readlink("/etc/localtime")
        if "zoneinfo/" in target:
            return target.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return datetime.now().astimezone().tzname() or "local"


def _zone_label(moment: datetime, zone: ZoneInfo | None) -> str:
    offset = moment.strftime("%z")
    offset = f"UTC{offset[:3]}:{offset[3:]}" if offset else "UTC"
    name = zone.key if zone else _local_zone_name()
    return f"{name} ({moment.tzname()}, {offset})"


def _now(zone: ZoneInfo | None = None) -> datetime:
    return datetime.now(zone).replace(microsecond=0) if zone else datetime.now().astimezone().replace(microsecond=0)


# ---------- parsing and formatting ----------

def _parse_clock(text: str, today: datetime) -> datetime | None:
    """Parse a time of day with an optional day. Returns None if text is not a time."""
    match = _DAY_THEN_TIME.fullmatch(text) or _TIME_THEN_DAY.fullmatch(text)
    if not match or not (match.group("m") or match.group("ampm")):
        return None  # "15" alone is not a time; "15:00" and "3 pm" are
    hour, minute, second = int(match.group("h")), int(match.group("m") or 0), int(match.group("s") or 0)
    ampm = (match.group("ampm") or "").replace(".", "").replace(" ", "")
    if ampm:
        if not 1 <= hour <= 12:
            raise ValueError(f"'{text}': hour must be 1-12 with AM/PM")
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError(f"'{text}' is not a valid time of day")
    day = match.group("day") or "today"
    base = {
        "today": today,
        "tomorrow": today + timedelta(days=1),
        "yesterday": today - timedelta(days=1),
    }.get(day) or datetime.strptime(day, "%Y-%m-%d")
    return base.replace(hour=hour, minute=minute, second=second)


def _parse(value: str) -> tuple[datetime, bool]:
    """Parse a date input. Returns (naive local datetime, has_time)."""
    raw = value.strip()
    v = raw.lower()
    today = datetime.combine(Date.today(), Time())
    if v in ("", "today"):
        return today, False
    if v == "now":
        return datetime.now().replace(microsecond=0), True
    if v == "tomorrow":
        return today + timedelta(days=1), False
    if v == "yesterday":
        return today - timedelta(days=1), False
    if re.fullmatch(r"\d{9,11}", v):  # Unix timestamp
        return datetime.fromtimestamp(int(v)), True
    clock = _parse_clock(v, today)
    if clock is not None:
        return clock, True
    for fmt, has_time in (
        ("%Y-%m-%d", False),
        ("%Y/%m/%d", False),
        ("%Y-%m-%d %H:%M", True),
        ("%Y-%m-%d %H:%M:%S", True),
        ("%Y-%m-%dT%H:%M", True),
        ("%Y-%m-%dT%H:%M:%S", True),
    ):
        try:
            return datetime.strptime(raw, fmt), has_time
        except ValueError:
            continue
    try:  # fall back to relative phrases such as "next friday"
        start, _, _ = _resolve(raw, Date.today())
        return datetime.combine(start, Time()), False
    except ValueError:
        raise ValueError(f"cannot read date '{value}'. {DATE_INPUT_HELP}") from None


def _fmt(moment: datetime | Date, has_time: bool = False) -> str:
    if has_time:
        # Give both 24-hour and 12-hour forms so the model never converts in its head.
        clock = "%H:%M:%S" if moment.second else "%H:%M"
        twelve = moment.strftime(("%I:%M:%S" if moment.second else "%I:%M") + " %p").lstrip("0")
        return moment.strftime(f"%Y-%m-%d {clock}") + f" ({twelve}, {moment:%A})"
    return moment.strftime("%Y-%m-%d (%A)")


def _add_months(moment: datetime, months: int) -> datetime:
    # Clamp to the last day of the month: Jan 31 + 1 month = Feb 28/29.
    total = moment.month - 1 + months
    year, month = moment.year + total // 12, total % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def _plural(n: int, unit: str) -> str:
    return f"{n} {unit}" if abs(n) == 1 else f"{n} {unit}s"


def _ymd_between(a: Date, b: Date) -> tuple[int, int, int]:
    """Whole years, months and days from a to b (a <= b)."""
    years = months = 0
    start = datetime.combine(a, Time())
    end = datetime.combine(b, Time())
    while _add_months(start, (years + 1) * 12) <= end:
        years += 1
    while _add_months(start, years * 12 + months + 1) <= end:
        months += 1
    days = (end - _add_months(start, years * 12 + months)).days
    return years, months, days


# ---------- relative date phrases ----------

def _resolve(expression: str, ref: Date) -> tuple[Date, Date | None, str]:
    """Return (date, optional end date for ranges, rule used)."""
    text = re.sub(r"\s+", " ", expression.strip().lower().replace("the ", "")).strip()
    week_start = ref - timedelta(days=ref.weekday())  # weeks run Monday-Sunday

    fixed = {
        "today": (0, "today"),
        "tomorrow": (1, "today + 1 day"),
        "yesterday": (-1, "today - 1 day"),
        "day after tomorrow": (2, "today + 2 days"),
        "day before yesterday": (-2, "today - 2 days"),
    }
    if text in fixed:
        offset, rule = fixed[text]
        return ref + timedelta(days=offset), None, rule

    m = re.fullmatch(r"(?:(this|next|last|coming|previous) )?([a-z]+)", text)
    if m and m.group(2) in _WEEKDAY_LOOKUP:
        modifier, target = m.group(1) or "coming", _WEEKDAY_LOOKUP[m.group(2)]
        if modifier == "this":
            return week_start + timedelta(days=target), None, "'this <weekday>' = that weekday in the current Monday-Sunday week"
        if modifier == "next":
            return week_start + timedelta(days=7 + target), None, "'next <weekday>' = that weekday in the following Monday-Sunday week"
        if modifier == "last":
            return week_start + timedelta(days=target - 7), None, "'last <weekday>' = that weekday in the previous Monday-Sunday week"
        if modifier == "coming":
            ahead = (target - ref.weekday()) % 7 or 7
            return ref + timedelta(days=ahead), None, "'coming <weekday>' = the first such weekday after today"
        behind = (ref.weekday() - target) % 7 or 7
        return ref - timedelta(days=behind), None, "'previous <weekday>' = the most recent such weekday before today"

    m = re.fullmatch(r"(this|next|last) weekend", text)
    if m:
        shift = {"this": 0, "next": 7, "last": -7}[m.group(1)]
        saturday = week_start + timedelta(days=5 + shift)
        return saturday, saturday + timedelta(days=1), f"'{m.group(1)} weekend' = Saturday-Sunday of the {'current' if shift == 0 else 'following' if shift > 0 else 'previous'} Monday-Sunday week"

    m = re.fullmatch(r"(start|beginning|end) of (?:(this|next|last) )?(week|month|year)", text)
    if m:
        edge, which, unit = m.group(1), m.group(2) or "this", m.group(3)
        shift = {"this": 0, "next": 1, "last": -1}[which]
        if unit == "week":
            start = week_start + timedelta(weeks=shift)
            end = start + timedelta(days=6)
        elif unit == "month":
            start = _add_months(datetime.combine(ref.replace(day=1), Time()), shift).date()
            end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
        else:
            start = Date(ref.year + shift, 1, 1)
            end = Date(ref.year + shift, 12, 31)
        return (end if edge == "end" else start), None, f"{edge} of {which} {unit} (weeks run Monday-Sunday)"

    m = re.fullmatch(r"(?:in )?(\d+) (day|week|month|year)s?(?: (ago|later|from now|from today))?", text)
    if m and (text.startswith("in ") or m.group(3)):
        n, unit, direction = int(m.group(1)), m.group(2), m.group(3)
        sign = -1 if direction == "ago" else 1
        moment = datetime.combine(ref, Time())
        if unit in ("month", "year"):
            moment = _add_months(moment, sign * n * (12 if unit == "year" else 1))
        else:
            moment += timedelta(days=sign * n * (7 if unit == "week" else 1))
        return moment.date(), None, f"today {'-' if sign < 0 else '+'} {_plural(n, unit)}"

    raise ValueError(
        f"unsupported expression '{expression}'. Supported: today, tomorrow, yesterday, "
        "day after tomorrow, day before yesterday, <weekday>, this/next/last/coming/previous <weekday>, "
        "this/next/last weekend, start/end of this/next/last week/month/year, in N days/weeks/months/years, "
        "N days/weeks/months/years ago."
    )


# ---------- tools ----------

def register_time_tools(registry: ToolRegistry) -> None:
    @registry.register
    def get_current_time(timezone: str = "") -> str:
        """Get the current date, time and weekday. Use for any question about now or today, including in other cities.

        Args:
            timezone: Only for another city: IANA name ('America/New_York') or city ('London'). Omit this argument for local time.
        """
        zone = _zone(timezone)
        now = _now(zone)
        return f"{now:%Y-%m-%d %H:%M:%S} ({now:%A}), {_zone_label(now, zone)}"

    @registry.register
    def convert_timezone(time: str, from_timezone: str = "", to_timezone: str = "") -> str:
        """Convert a time from one time zone to another. Example: 3 PM in London to Seoul time.

        Args:
            time: 'HH:MM' or '3 PM' (today), 'YYYY-MM-DD HH:MM', or 'now'.
            from_timezone: IANA name or city. Omit for the user's local time zone.
            to_timezone: IANA name or city. Omit for the user's local time zone.
        """
        src, dst = _zone(from_timezone), _zone(to_timezone)
        if src is None and dst is None:
            raise ValueError("give at least one of from_timezone or to_timezone")
        raw = time.strip().lower()
        if raw == "now":
            moment = _now(src)
        else:
            # A bare clock time ("15:00", "3 PM") means that time today in the source zone.
            naive = _parse_clock(raw, datetime.combine(_now(src).date(), Time()))
            if naive is None:
                naive, has_time = _parse(time)
                if not has_time:
                    raise ValueError("include a time, e.g. '15:00' or '2026-11-02 15:00'")
            moment = naive.replace(tzinfo=src) if src else naive.astimezone()
        converted = moment.astimezone(dst) if dst else moment.astimezone()
        return (
            f"{moment:%Y-%m-%d %H:%M} ({moment:%A}) {_zone_label(moment, src)} = "
            f"{converted:%Y-%m-%d %H:%M} ({converted:%A}) {_zone_label(converted, dst)}"
        )

    @registry.register
    def add_to_date(
        date: str = "today",
        years: int = 0,
        months: int = 0,
        weeks: int = 0,
        days: int = 0,
        hours: float = 0,
        minutes: float = 0,
        start_is_day_one: bool = False,
    ) -> str:
        """Add or subtract time from a date or a clock time. Use for "100 days from today", "3 months ago", "2 weeks after 2026-12-01", "now plus 90 minutes", "leave at 9:30 AM and drive 5.625 hours". Use negative numbers to go back.

        Args:
            date: Start. 'today', 'now', 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM', '9:30 AM', 'tomorrow 14:00'. To add hours or minutes, the start must include a time of day.
            years: Years to add.
            months: Months to add.
            weeks: Weeks to add.
            days: Days to add.
            hours: Hours to add. Fractions are fine, e.g. 5.625.
            minutes: Minutes to add. Fractions are fine.
            start_is_day_one: True for Korean-style anniversaries where the start date counts as day 1 (the 100th day is 99 days later).
        """
        start, has_time = _parse(date)
        if (hours or minutes) and not has_time:
            # Run 7: "today" + 5.625 hours silently started from midnight and returned 05:37.
            raise ValueError(
                f"'{date}' has no time of day, so adding hours or minutes would start from midnight. "
                "Give a start time such as '9:30 AM', 'today 14:00' or 'now'."
            )
        result = _add_months(start, years * 12 + months)
        day_offset = weeks * 7 + days - (1 if start_is_day_one and (weeks or days) else 0)
        result += timedelta(days=day_offset, hours=hours, minutes=minutes)
        show_time = has_time or bool(hours or minutes)

        parts = [
            _plural(n, unit)
            for n, unit in ((years, "year"), (months, "month"), (weeks, "week"), (days, "day"), (hours, "hour"), (minutes, "minute"))
            if n
        ]
        change = ", ".join(parts) or "nothing"
        answer = f"{_fmt(start, show_time)} + {change} = {_fmt(result, show_time)}"
        if start_is_day_one and (weeks or days):
            answer += f" (Korean-style count: {_fmt(start)} is day 1)"
        return answer

    @registry.register
    def date_difference(end: str, start: str = "today") -> str:
        """Count the time between two dates. Use for D-day, "how many days until Christmas", "weeks left this year", age, or anniversaries.

        Args:
            end: Target date. 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM', 'today', 'now' or a phrase like 'end of this year'.
            start: Starting date. Defaults to today. Use a birth date here to compute age.
        """
        a, a_time = _parse(start)
        b, b_time = _parse(end)
        future = b >= a
        lo, hi = (a, b) if future else (b, a)
        total_days = (hi.date() - lo.date()).days
        weeks, rest = divmod(total_days, 7)
        years, months, days = _ymd_between(lo.date(), hi.date())

        direction = "later" if future else "earlier"
        dday = f"D-{total_days}" if future else f"D+{total_days}"
        lines = [
            f"From {_fmt(a, a_time)} to {_fmt(b, b_time)} ({direction}):",
            f"- {_plural(total_days, 'day')} ({dday})",
            f"- {_plural(weeks, 'week')} and {_plural(rest, 'day')}",
            f"- {_plural(years, 'year')}, {_plural(months, 'month')} and {_plural(days, 'day')} (full years = international age)",
        ]
        if a_time or b_time:
            seconds = int((hi - lo).total_seconds())
            lines.append(f"- {seconds // 3600} hours and {(seconds % 3600) // 60} minutes in total")
        if future:
            lines.append(f"- Korean-style count (start date = day 1): {_fmt(b)} is day {total_days + 1}")
        return "\n".join(lines)

    @registry.register
    def date_info(date: str = "today") -> str:
        """Facts about one date: weekday, week number, day of year, last day of the month, quarter, leap year, and days left in its month/quarter/year counted from that date. For "days until X" use date_difference.

        Args:
            date: The date to describe, usually 'today'. Also 'YYYY-MM-DD', a Unix timestamp, or a phrase like 'next friday'.
        """
        moment, _ = _parse(date)
        d = moment.date()
        iso_year, iso_week, _ = d.isocalendar()
        days_in_year = 366 if calendar.isleap(d.year) else 365
        day_of_year = d.timetuple().tm_yday
        month_end = d.replace(day=calendar.monthrange(d.year, d.month)[1])
        quarter = (d.month - 1) // 3 + 1
        quarter_start = Date(d.year, 3 * quarter - 2, 1)
        quarter_end_month = 3 * quarter
        quarter_end = Date(d.year, quarter_end_month, calendar.monthrange(d.year, quarter_end_month)[1])
        midnight = datetime.combine(d, Time()).astimezone()
        return "\n".join(
            [
                _fmt(d),
                f"- ISO week: {iso_year}-W{iso_week:02d} (weeks run Monday-Sunday)",
                f"- Day {day_of_year} of {days_in_year}; {days_in_year - day_of_year} days left in the year after {d}",
                f"- {d:%B %Y} has {month_end.day} days; last day {_fmt(month_end)}; {(month_end - d).days} days left in the month after {d}",
                f"- Quarter: Q{quarter} ({quarter_start} to {quarter_end}); {(quarter_end - d).days} days left in the quarter after {d}",
                f"- Leap year: {'yes' if calendar.isleap(d.year) else 'no'}",
                f"- Unix timestamp at local midnight: {int(midnight.timestamp())}",
            ]
        )

    @registry.register
    def resolve_date(expression: str, reference: str = "today") -> str:
        """Turn a relative date phrase into an exact date. Use for "next Friday", "this weekend", "end of next month", "in 3 weeks". Translate the user's words to English first.

        Args:
            expression: English phrase, e.g. 'next friday', 'coming monday', 'this weekend', 'end of this month', 'in 3 weeks', '10 days ago'.
            reference: Date the phrase is relative to. Defaults to today.
        """
        ref, _ = _parse(reference)
        start, end, rule = _resolve(expression, ref.date())
        if end is not None:
            return f"'{expression}' = {_fmt(start)} to {_fmt(end)}. Rule: {rule}. Reference: {_fmt(ref.date())}."
        return f"'{expression}' = {_fmt(start)}. Rule: {rule}. Reference: {_fmt(ref.date())}."
