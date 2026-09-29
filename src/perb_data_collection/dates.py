"""Dates read off a board's own document, with their precision kept.

WHAT THIS FILE IS FOR
---------------------
A board order says when it was issued: "DATE: June 29, 2026", "this
seventeenth day of March, 2026", "Filed March 6, 2017". A listing often says
only the year. Writing the year as January 1 and calling it a date is how an
order issued on June 29 came to read as a New Year's Day order, so every date
here travels with its precision (``day`` / ``month`` / ``year``) and with the
raw text it was read from.

A date outside a plausible window is not a date. Typed years like 3036 or 5003
reach the warehouse as the newest record on file and push every real row down,
so :func:`bounded` refuses anything before 1935 (the NLRA) or more than a year
past today, and says so instead of returning a value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

EARLIEST_YEAR = 1935

MONTHS: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
_MONTH_ABBR = {name[:3]: num for name, num in MONTHS.items()}

_ORDINAL_WORDS: dict[str, int] = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
    "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
    "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
    "twentieth": 20, "thirtieth": 30,
}
_ORDINAL_TENS = {"twenty": 20, "thirty": 30}
_ORDINAL_UNITS = {
    w: n for w, n in _ORDINAL_WORDS.items() if n < 10
}

_MONTH_ALT = "|".join(MONTHS)
_ORDINAL_WORD_ALT = (
    r"(?:(?:twenty|thirty)[\s-]+(?:first|second|third|fourth|fifth|sixth|"
    r"seventh|eighth|ninth)|" + "|".join(sorted(_ORDINAL_WORDS, key=len, reverse=True)) + r")"
)

# "June 29, 2026", "June 29 2026", "June 29th, 2026"
_MONTH_DAY_YEAR_RE = re.compile(
    rf"\b(?P<month>{_MONTH_ALT})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<year>\d{{4}})\b",
    re.I,
)
# "29th day of June, 2026", "this seventeenth day of March, 2026"
_DAY_OF_MONTH_RE = re.compile(
    rf"\b(?P<day>\d{{1,2}}(?:st|nd|rd|th)?|{_ORDINAL_WORD_ALT})\s+day\s+of\s+"
    rf"(?P<month>{_MONTH_ALT}),?\s+(?:A\.?\s*D\.?\s+)?(?P<year>\d{{4}})\b",
    re.I,
)
# "6/29/2026"
_NUMERIC_RE = re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})\b")


@dataclass(frozen=True)
class DateHit:
    """One date read from text: ISO value, precision, raw span and offset."""

    iso: str
    precision: str
    raw: str
    start: int = 0


def bounded(year: int, *, today: date | None = None, horizon_years: int = 1) -> bool:
    """True when ``year`` is inside the plausible window for a board record.

    ``horizon_years`` is how far past today a date may fall: one year for an
    order, a filing or a certification; longer for a contract's expiry, which
    is normally in the future.
    """
    today = today or date.today()
    return EARLIEST_YEAR <= year <= today.year + horizon_years


def _ordinal_day(token: str) -> int | None:
    token = token.lower().replace("-", " ").strip()
    digits = re.match(r"(\d{1,2})", token)
    if digits:
        return int(digits.group(1))
    if token in _ORDINAL_WORDS:
        return _ORDINAL_WORDS[token]
    parts = token.split()
    if len(parts) == 2 and parts[0] in _ORDINAL_TENS and parts[1] in _ORDINAL_UNITS:
        return _ORDINAL_TENS[parts[0]] + _ORDINAL_UNITS[parts[1]]
    return None


def _make(
    year: int, month: int, day: int, raw: str, start: int, today: date | None, horizon_years: int = 1
) -> DateHit | None:
    if not bounded(year, today=today, horizon_years=horizon_years):
        return None
    try:
        value = date(year, month, day)
    except ValueError:
        return None
    return DateHit(value.isoformat(), "day", re.sub(r"\s+", " ", raw).strip()[:80], start)


def find_dates(text: str, *, today: date | None = None, horizon_years: int = 1) -> list[DateHit]:
    """Every day-precision date in ``text`` inside the plausible window, in order."""
    hits: list[DateHit] = []
    for match in _MONTH_DAY_YEAR_RE.finditer(text):
        hit = _make(
            int(match.group("year")),
            MONTHS[match.group("month").lower()],
            int(match.group("day")),
            match.group(0),
            match.start(),
            today,
            horizon_years,
        )
        if hit:
            hits.append(hit)
    for match in _DAY_OF_MONTH_RE.finditer(text):
        day = _ordinal_day(match.group("day"))
        if day is None:
            continue
        hit = _make(
            int(match.group("year")),
            MONTHS[match.group("month").lower()],
            day,
            match.group(0),
            match.start(),
            today,
            horizon_years,
        )
        if hit:
            hits.append(hit)
    for match in _NUMERIC_RE.finditer(text):
        hit = _make(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            match.group(0),
            match.start(),
            today,
            horizon_years,
        )
        if hit:
            hits.append(hit)
    hits.sort(key=lambda h: h.start)
    return hits


def date_after(
    text: str,
    anchors: tuple[str, ...],
    *,
    window: int = 400,
    today: date | None = None,
) -> DateHit | None:
    """The first date within ``window`` characters after the LAST anchor match.

    Anchors are regex fragments such as ``r"IT IS SO ORDERED"`` or
    ``r"BY ORDER OF THE"``. The last match is used because an order's closing
    block follows the body, and a body can quote the same phrase from an
    earlier order.
    """
    best: DateHit | None = None
    for anchor in anchors:
        matches = list(re.finditer(anchor, text, flags=re.I))
        if not matches:
            continue
        match = matches[-1]
        segment = text[match.end() : match.end() + window]
        found = find_dates(segment, today=today)
        # A same-line anchor ("DATE: June 29, 2026", "this seventeenth day of
        # March, 2026") puts the date inside the anchor's own span as well.
        if not found:
            found = find_dates(text[match.start() : match.end() + window], today=today)
        if found:
            hit = found[0]
            hit = DateHit(hit.iso, hit.precision, hit.raw, match.end() + hit.start)
            if best is None or hit.start > best.start:
                best = hit
    return best


def year_only(year_text: str, *, today: date | None = None) -> DateHit | None:
    """A year with nothing finer, as ``precision='year'``. Never a January 1 date."""
    match = re.fullmatch(r"\s*(\d{4})\s*", year_text or "")
    if not match:
        return None
    year = int(match.group(1))
    if not bounded(year, today=today):
        return None
    return DateHit(str(year), "year", year_text.strip(), 0)


def parse_month_abbr_stamp(month_abbr: str, day: str, year: str) -> date | None:
    """``Jul 25 2025``-style e-filing stamps."""
    month = _MONTH_ABBR.get(month_abbr[:3].lower())
    if not month:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None
