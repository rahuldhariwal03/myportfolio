"""Parser that separates raw displayed portal strings from validated numerical values.

Strict project rules implemented here:
1. Always keep `raw_displayed_value` verbatim alongside the parsed integer.
2. Never treat missing, blank, loading, closed, or malformed text as `0`.
3. Never confuse prices (`₹ 3380`, `Rs 3000`), dates (`2026-12-01`), percentages (`50%`),
   or negative numbers (`-2`) with available slot counts.
4. Reject `available_slots > total_capacity` as a `parse_error` with `available_slots = None`.
5. Assign `confidence = 'verified'` ONLY when slot unit meaning has been explicitly validated
   against the live portal; otherwise tag as `'unverified'`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedAvailability:
    """Structured result of interpreting one raw session availability string."""

    available_slots: int | None
    total_capacity: int | None
    raw_displayed_value: str | None
    raw_capacity_value: str | None
    collection_status: str
    confidence: str
    error_details: str | None = None


# Canonical zone-name alias mapping for the 8 official Corbett Tiger Reserve safari zones.
# Prevents accidental creation of duplicate zones when the portal shows e.g. "Bijrani Zone",
# "Garjiya" (alternate official spelling on corbettgov.org), "Durga Devi", or "DhikalaZone".
_CANONICAL_ZONE_ALIASES: dict[str, str] = {
    "bijrani": "Bijrani",
    "bijrani zone": "Bijrani",
    "bijrani safari": "Bijrani",
    "bijranizone": "Bijrani",
    "jhirna": "Jhirna",
    "jhirna zone": "Jhirna",
    "jhirna safari": "Jhirna",
    "jhirnazone": "Jhirna",
    "dhela": "Dhela",
    "dhela zone": "Dhela",
    "dhela safari": "Dhela",
    "dhelazone": "Dhela",
    "garjia": "Garjia",
    "garjia zone": "Garjia",
    "garjiya": "Garjia",
    "garjiya zone": "Garjia",
    "garjiazone": "Garjia",
    "garjiyazone": "Garjia",
    "ringora": "Garjia",
    "ringora zone": "Garjia",
    "durgadevi": "Durgadevi",
    "durgadevi zone": "Durgadevi",
    "durga devi": "Durgadevi",
    "durga devi zone": "Durgadevi",
    "durgadevizone": "Durgadevi",
    "sonanadi": "Sonanadi",
    "sonanadi zone": "Sonanadi",
    "sonanadizone": "Sonanadi",
    "pakhro": "Pakhro",
    "pakhro zone": "Pakhro",
    "pakhrozone": "Pakhro",
    "dhikala": "Dhikala",
    "dhikala zone": "Dhikala",
    "dhikalazone": "Dhikala",
    "dhikala canter": "Dhikala",
    "dhikala canter safari": "Dhikala",
}


def normalize_zone_name(raw_name: str) -> str:
    """Normalize known Corbett zone spelling/suffix variations to canonical zone names."""
    cleaned = " ".join((raw_name or "").split()).strip()
    if not cleaned:
        return ""
    key = re.sub(r"\s*[-–—(].*$", "", cleaned).strip().lower()
    if cleaned.lower() in _CANONICAL_ZONE_ALIASES:
        return _CANONICAL_ZONE_ALIASES[cleaned.lower()]
    if key in _CANONICAL_ZONE_ALIASES:
        return _CANONICAL_ZONE_ALIASES[key]
    return cleaned


def aggregate_date_operating_status(session_statuses: list[str]) -> str:
    """Derive overall `safari_dates.operating_status` from all observed sessions on that date.

    Prevents a single closed zone (e.g. Pakhro at the end of the loop) from overwriting
    an open safari date's status to `'closed'` when other zones are actively operating.
    """
    if not session_statuses:
        return "unknown"
    status_set = set(session_statuses)
    if status_set == {"success"}:
        return "open"
    if "success" in status_set:
        return "partial"
    if status_set == {"zone_closed"}:
        return "closed"
    if status_set == {"window_not_open"}:
        return "window_not_open"
    if status_set == {"portal_paused"}:
        return "paused"
    if status_set <= {"zone_closed", "window_not_open"}:
        return "closed"
    return "unknown"


_MISSING_TOKENS = {
    "",
    "-",
    "--",
    "—",
    "n/a",
    "na",
    "null",
    "none",
    "loading",
    "loading...",
    "please wait",
    "unavailable data",
    "not available",
    "unavailable",
}

_CLOSED_PATTERN = re.compile(
    r"\b(zone\s+closed|closed\s+for\s+monsoon|closed\s+for\s+season|closed|non[- ]operational|holiday)\b",
    re.IGNORECASE,
)
_WINDOW_NOT_OPEN_PATTERN = re.compile(
    r"\b(not\s+open(ed)?|opens?\s+later|booking\s+not\s+started|outside\s+window|yet\s+to\s+open)\b",
    re.IGNORECASE,
)
_PAUSED_PATTERN = re.compile(r"\b(paused|maintenance)\b", re.IGNORECASE)
_SOLD_OUT_PATTERN = re.compile(
    r"^(?:(?:morning|afternoon|evening)\s*[:\-–]\s*)?"
    r"(full|house\s*full|sold\s*out|booked\s*out|all\s+booked|"
    r"no\s+(?:slots?|permits?|seats?|tickets?|jeeps?|canters?)\s+(?:available|left))[!.]*$",
    re.IGNORECASE,
)
_CURRENCY_PATTERN = re.compile(r"(₹|\binr\b|\brs\.?\s*\d)", re.IGNORECASE)
# Reject ISO dates (2026-12-15) AND Indian/slash dates (05/12/2026, 05-12-2026, 05/12/26)
_DATE_PATTERN = re.compile(r"\b(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
_PERCENT_PATTERN = re.compile(r"\d+\s*%")
_NEGATIVE_INT_PATTERN = re.compile(r"(?<!\w)-\d+\b")
_DECIMAL_PATTERN = re.compile(r"\b\d+\.\d+\b")

# Optional leading session label (e.g. "Morning: 18 Available", "Afternoon - 12 / 30")
_SESSION_PREFIX_PATTERN = re.compile(
    r"^(?:morning|afternoon|evening)(?:\s+(?:shift|session|safari))?\s*[:\-–]\s*",
    re.IGNORECASE,
)

# Matches e.g. "18 / 30", "18/30 Available", "Full (0 / 30 permits)", "12 of 30 slots"
_FRACTION_PATTERN = re.compile(
    r"(?<!\d)(\d+)\s*(?:/|\bout\s+of\b|\bof\b)\s*(\d+)(?!\d)",
    re.IGNORECASE,
)
# Matches e.g. "24", "24 Available", "Available: 24", "Available (24)",
# "12 Permits Left", "18 Tickets Left", "Only 4 left", "0 seats"
_SLOT_WORD = (
    r"(?:available|slots?|permits?|seats?|tickets?|jeeps?|canters?|left|remaining|only|hurry!?)"
)
_LABELED_COUNT_PATTERN = re.compile(
    rf"^(?:{_SLOT_WORD}\s*[:\-]?\s*)*"
    r"\(?(\d+)\)?"
    rf"(?:\s*{_SLOT_WORD})*[!.]*$",
    re.IGNORECASE,
)


def parse_capacity_text(raw_capacity: str | None) -> tuple[int | None, str | None]:
    """Parse an optional total-capacity display string into `(capacity_int, error_reason)`."""
    if raw_capacity is None:
        return None, None
    cleaned = " ".join(raw_capacity.split())
    if cleaned.lower() in _MISSING_TOKENS:
        return None, None
    if _CURRENCY_PATTERN.search(cleaned) or _NEGATIVE_INT_PATTERN.search(cleaned) or _DECIMAL_PATTERN.search(cleaned):
        return None, f"Invalid capacity display value: {raw_capacity!r}"
    match = _LABELED_COUNT_PATTERN.match(cleaned)
    if not match:
        return None, f"Unrecognized capacity format: {raw_capacity!r}"
    value = int(match.group(1))
    if value <= 0 or value > 1000:
        return None, f"Out-of-range capacity value: {value}"
    return value, None


def parse_availability_text(
    raw_value: str | None,
    *,
    raw_capacity: str | None = None,
    unit_validated: bool = False,
    max_reasonable_slots: int = 500,
) -> ParsedAvailability:
    """Safely parse raw displayed slot text while preserving the exact source string."""
    preserved_raw = raw_value
    preserved_cap = raw_capacity
    success_confidence = "verified" if unit_validated else "unverified"

    if raw_value is None:
        return ParsedAvailability(
            available_slots=None,
            total_capacity=None,
            raw_displayed_value=None,
            raw_capacity_value=preserved_cap,
            collection_status="missing",
            confidence="not_applicable",
            error_details="Availability element missing or returned no text.",
        )

    cleaned = " ".join(raw_value.split())
    if cleaned.lower() in _MISSING_TOKENS:
        return ParsedAvailability(
            available_slots=None,
            total_capacity=None,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="missing",
            confidence="not_applicable",
            error_details=f"Non-value placeholder displayed: {cleaned!r}",
        )

    # Reject prices, dates, percentages, decimals, and negative numbers immediately
    if _CURRENCY_PATTERN.search(cleaned):
        return ParsedAvailability(
            available_slots=None,
            total_capacity=None,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="parse_error",
            confidence="low",
            error_details=f"Rejected currency/price text to avoid misinterpreting fee as slots: {cleaned!r}",
        )
    if _DATE_PATTERN.search(cleaned):
        return ParsedAvailability(
            available_slots=None,
            total_capacity=None,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="parse_error",
            confidence="low",
            error_details=f"Rejected date string in availability field: {cleaned!r}",
        )
    if _PERCENT_PATTERN.search(cleaned):
        return ParsedAvailability(
            available_slots=None,
            total_capacity=None,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="parse_error",
            confidence="low",
            error_details=f"Rejected percentage text (not a raw slot count): {cleaned!r}",
        )
    if _NEGATIVE_INT_PATTERN.search(cleaned):
        return ParsedAvailability(
            available_slots=None,
            total_capacity=None,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="parse_error",
            confidence="low",
            error_details=f"Rejected negative slot value: {cleaned!r}",
        )
    if _DECIMAL_PATTERN.search(cleaned):
        return ParsedAvailability(
            available_slots=None,
            total_capacity=None,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="parse_error",
            confidence="low",
            error_details=f"Rejected non-integer decimal value: {cleaned!r}",
        )

    # Check status labels (window not open, paused, closed) -> store NULL, NEVER 0
    if _WINDOW_NOT_OPEN_PATTERN.search(cleaned):
        return ParsedAvailability(
            available_slots=None,
            total_capacity=None,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="window_not_open",
            confidence="not_applicable",
            error_details=f"Booking window not open for this date: {cleaned!r}",
        )
    if _PAUSED_PATTERN.search(cleaned):
        return ParsedAvailability(
            available_slots=None,
            total_capacity=None,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="portal_paused",
            confidence="not_applicable",
            error_details=f"Session reported paused/maintenance: {cleaned!r}",
        )
    if _CLOSED_PATTERN.search(cleaned):
        return ParsedAvailability(
            available_slots=None,
            total_capacity=None,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="zone_closed",
            confidence="not_applicable",
            error_details=f"Zone/session marked closed: {cleaned!r}",
        )

    explicit_cap, cap_err = parse_capacity_text(raw_capacity)

    # Fraction display: "18 / 30" or "Full (0 / 30)"
    frac_matches = list(_FRACTION_PATTERN.finditer(cleaned))
    if len(frac_matches) == 1:
        avail = int(frac_matches[0].group(1))
        cap_from_frac = int(frac_matches[0].group(2))
        cap = explicit_cap if explicit_cap is not None else cap_from_frac
        if cap <= 0:
            return ParsedAvailability(
                available_slots=None,
                total_capacity=None,
                raw_displayed_value=preserved_raw,
                raw_capacity_value=preserved_cap,
                collection_status="parse_error",
                confidence="low",
                error_details=f"Zero/invalid capacity in fraction display: {cleaned!r}",
            )
        if avail > cap:
            return ParsedAvailability(
                available_slots=None,
                total_capacity=None,
                raw_displayed_value=preserved_raw,
                raw_capacity_value=preserved_cap,
                collection_status="parse_error",
                confidence="low",
                error_details=f"Displayed available slots ({avail}) exceed capacity ({cap}): {cleaned!r}",
            )
        if avail > max_reasonable_slots:
            return ParsedAvailability(
                available_slots=None,
                total_capacity=None,
                raw_displayed_value=preserved_raw,
                raw_capacity_value=preserved_cap,
                collection_status="parse_error",
                confidence="low",
                error_details=f"Implausibly large slot value ({avail} > {max_reasonable_slots}): {cleaned!r}",
            )
        return ParsedAvailability(
            available_slots=avail,
            total_capacity=cap,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap or str(cap_from_frac),
            collection_status="success",
            confidence=success_confidence,
            error_details=cap_err,
        )

    # Explicit "Full" / "Sold Out" text with zero remaining slots
    if _SOLD_OUT_PATTERN.match(cleaned):
        return ParsedAvailability(
            available_slots=0,
            total_capacity=explicit_cap,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="success",
            confidence=success_confidence,
            error_details=cap_err,
        )

    # Strip optional leading "Morning:" / "Afternoon:" label (while preserving raw_value verbatim)
    stripped_session = _SESSION_PREFIX_PATTERN.sub("", cleaned).strip()
    if stripped_session.lower() in _MISSING_TOKENS:
        return ParsedAvailability(
            available_slots=None,
            total_capacity=None,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="missing",
            confidence="not_applicable",
            error_details=f"Non-value placeholder displayed: {cleaned!r}",
        )

    # Single unambiguous slot count ("24", "24 Available", "Morning: 18 Tickets Left", "Available (24)")
    single_match = _LABELED_COUNT_PATTERN.match(stripped_session)
    if single_match:
        avail = int(single_match.group(1))
        if avail > max_reasonable_slots:
            return ParsedAvailability(
                available_slots=None,
                total_capacity=None,
                raw_displayed_value=preserved_raw,
                raw_capacity_value=preserved_cap,
                collection_status="parse_error",
                confidence="low",
                error_details=f"Implausibly large slot value ({avail} > {max_reasonable_slots}): {cleaned!r}",
            )
        if explicit_cap is not None and avail > explicit_cap:
            return ParsedAvailability(
                available_slots=None,
                total_capacity=None,
                raw_displayed_value=preserved_raw,
                raw_capacity_value=preserved_cap,
                collection_status="parse_error",
                confidence="low",
                error_details=(
                    f"Displayed available slots ({avail}) exceed capacity ({explicit_cap}): {cleaned!r}"
                ),
            )
        return ParsedAvailability(
            available_slots=avail,
            total_capacity=explicit_cap,
            raw_displayed_value=preserved_raw,
            raw_capacity_value=preserved_cap,
            collection_status="success",
            confidence=success_confidence,
            error_details=cap_err,
        )

    # Unrecognized or ambiguous text -> keep raw string, store NULL, log reason
    return ParsedAvailability(
        available_slots=None,
        total_capacity=None,
        raw_displayed_value=preserved_raw,
        raw_capacity_value=preserved_cap,
        collection_status="parse_error",
        confidence="low",
        error_details=f"Ambiguous/unvalidated text; stored raw only: {cleaned!r}",
    )
