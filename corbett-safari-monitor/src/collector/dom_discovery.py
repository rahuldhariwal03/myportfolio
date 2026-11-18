"""DOM candidate selector discovery from a locally inspected HTML page.

Helps a beginner turn a real rendered page from `scripts/inspect_portal.py` into a
draft `suggested_selectors.json` WITHOUT guessing blindly:
- Inspects only elements ACTUALLY present in the captured HTML/URL for:
  1. The 8 official Corbett zone names (multi-zone cards, `<select>` dropdowns,
     or single-zone URLs like `?eventName=DhikalaZone&date=2026-11-18`).
  2. Morning and Afternoon availability elements.
  3. Calendar date-cell templates AND Next-Month navigation button (so the
     rolling 30-day scan crosses month boundaries automatically).
- Always emits `"verified": false` together with the exact sample text matched on
  screen so the operator confirms it before automated runs begin.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

from src.collector.parser import normalize_zone_name

KNOWN_ZONE_NAMES: tuple[str, ...] = (
    "bijrani",
    "jhirna",
    "dhela",
    "garjia",
    "garjiya",
    "durgadevi",
    "durga devi",
    "sonanadi",
    "pakhro",
    "dhikala",
)

_MORNING_RE = re.compile(r"\bmorning\b", re.IGNORECASE)
_AFTERNOON_RE = re.compile(r"\b(afternoon|evening)\b", re.IGNORECASE)
_ISO_DATE_VAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_DATE_VAL_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_FULL_MONTH_ARIA_RE = re.compile(
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}"
)
_SHORT_MONTH_ARIA_RE = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}"
)

_GENERIC_UTILITY_CLASS_RE = re.compile(
    r"^(active|selected|open|hover|focus|disabled|hidden|block|inline|flex|grid|table|"
    r"relative|absolute|fixed|sticky|container|row|col|col-\d+|w-\S+|h-\S+|p[xytblr]?-\S+|"
    r"m[xytblr]?-\S+|gap-\S+|space-\S+|items-\S+|justify-\S+|text-\S+|font-\S+|bg-\S+|"
    r"border\S*|rounded\S*|shadow\S*|opacity-\S+|transition\S*|duration-\S+|cursor-\S+|"
    r"overflow-\S+|z-\S+|leading-\S+|tracking-\S+|min-\S+|max-\S+)$",
    re.IGNORECASE,
)


def _selector_for_tag(tag: Tag) -> str:
    """Build a concise CSS selector from semantic attributes/classes (skipping utility classes)."""
    for attr in ("data-testid", "data-cy", "data-role"):
        val = tag.get(attr)
        if val and isinstance(val, str):
            return f"{tag.name}[{attr}='{val}']"
    tag_id = tag.get("id")
    if tag_id and isinstance(tag_id, str) and not re.search(r"\d{3,}", tag_id):
        return f"{tag.name}#{tag_id}"
    semantic_classes = [
        c
        for c in (tag.get("class") or [])
        if isinstance(c, str) and c and not _GENERIC_UTILITY_CLASS_RE.match(c)
    ]
    if semantic_classes:
        return f"{tag.name}.{'.'.join(semantic_classes[:2])}"
    return tag.name


def _detect_calendar_selectors(soup: BeautifulSoup) -> tuple[str, str]:
    """Detect `(date_cell_template, calendar_next_month_selector)` from actual DOM elements."""
    date_cell_template = ""

    for attr_name in ("data-date", "data-day", "data-value", "data-iso", "title"):
        if isinstance(soup.find(attrs={attr_name: _ISO_DATE_VAL_RE}), Tag):
            date_cell_template = f"[{attr_name}='{{date}}']"
            break
        if isinstance(soup.find(attrs={attr_name: _DMY_DATE_VAL_RE}), Tag):
            date_cell_template = f"[{attr_name}='{{dmy}}']"
            break

    if not date_cell_template:
        aria_full = soup.find(attrs={"aria-label": _FULL_MONTH_ARIA_RE})
        if isinstance(aria_full, Tag):
            if "flatpickr-day" in (aria_full.get("class") or []):
                date_cell_template = ".flatpickr-day[aria-label='{aria_date}']"
            else:
                date_cell_template = f"{aria_full.name}[aria-label*='{{aria_date}}']"
        else:
            aria_short = soup.find(attrs={"aria-label": _SHORT_MONTH_ARIA_RE})
            if isinstance(aria_short, Tag):
                date_cell_template = f"{aria_short.name}[aria-label*='{{short_aria_date}}']"

    next_month_selector = ""
    known_next_classes = (
        "flatpickr-next-month",
        "rdp-nav_button_next",
        "rdp-button_next",
        "react-datepicker__navigation--next",
        "fc-next-button",
        "calendar-next",
        "next-month",
    )
    for cls in known_next_classes:
        el = soup.find(class_=cls)
        if isinstance(el, Tag):
            next_month_selector = f".{cls}"
            break

    if not next_month_selector:
        aria_next = soup.find(
            ["button", "a", "span"],
            attrs={"aria-label": re.compile(r"next\s+month|go\s+to\s+next\s+month", re.IGNORECASE)},
        )
        if isinstance(aria_next, Tag):
            exact_label = str(aria_next.get("aria-label", "")).strip()
            if exact_label:
                next_month_selector = f"{aria_next.name}[aria-label='{exact_label}']"

    return date_cell_template, next_month_selector


def _detect_zone_dropdown(soup: BeautifulSoup) -> tuple[str, list[str]]:
    """Detect a `<select>` dropdown containing official Corbett safari zone names."""
    for sel_tag in soup.find_all("select"):
        if not isinstance(sel_tag, Tag):
            continue
        matched_opts: list[str] = []
        for opt in sel_tag.find_all("option"):
            txt = " ".join(opt.get_text(" ", strip=True).split())
            if not txt:
                continue
            canon = normalize_zone_name(txt).lower()
            if canon in KNOWN_ZONE_NAMES:
                matched_opts.append(txt)
        if len(matched_opts) >= 2:
            return _selector_for_tag(sel_tag), matched_opts
    return "", []


def _detect_url_templates(final_url: str) -> tuple[str, dict[str, str]]:
    """Inspect the captured live URL for `?date=YYYY-MM-DD` and `?eventName=...` parameters."""
    if not final_url:
        return "", {}

    templated = ""
    if re.search(r"([?&]date=)\d{4}-\d{2}-\d{2}", final_url):
        templated = re.sub(r"([?&]date=)\d{4}-\d{2}-\d{2}", r"\g<1>{date}", final_url)
    elif re.search(r"([?&]date=)\d{2}-\d{2}-\d{4}", final_url):
        templated = re.sub(r"([?&]date=)\d{2}-\d{2}-\d{4}", r"\g<1>{dmy}", final_url)

    if not templated:
        return "", {}

    parsed = urlparse(final_url)
    qs = parse_qs(parsed.query)
    for param_name in ("eventName", "zone", "zoneName", "safariZone"):
        vals = qs.get(param_name)
        if vals:
            raw_zone = vals[0].strip()
            canonical = normalize_zone_name(raw_zone)
            if canonical:
                return "", {canonical: templated}

    return templated, {}


def discover_candidate_selectors(
    html: str,
    portal_url: str = "https://safari.corbettgov.org/",
    final_url: str | None = None,
) -> dict[str, Any]:
    """Inspect real rendered HTML and propose a draft selector config + matched evidence."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    # Locate leaf-ish elements whose text matches an official Corbett zone name (excluding <option>)
    zone_name_hits: list[tuple[Tag, str]] = []
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag) or tag.name in {"option", "select", "title"}:
            continue
        direct_text = " ".join(tag.get_text(" ", strip=True).split())
        if not direct_text or len(direct_text) > 50:
            continue
        lowered = direct_text.lower()
        for z in KNOWN_ZONE_NAMES:
            if lowered in {z, f"{z} zone", f"{z} canter", f"{z} safari"}:
                zone_name_hits.append((tag, direct_text))
                break

    card_selectors: Counter[str] = Counter()
    name_selectors: Counter[str] = Counter()
    morning_selectors: Counter[str] = Counter()
    afternoon_selectors: Counter[str] = Counter()
    zone_id_attrs: Counter[str] = Counter()
    matched_samples: list[dict[str, str | None]] = []

    for name_tag, zone_label in zone_name_hits:
        name_selectors[_selector_for_tag(name_tag)] += 1

        chosen_card: Tag | None = None
        cursor: Tag | None = name_tag.parent if isinstance(name_tag.parent, Tag) else None
        for _ in range(5):
            if cursor is None or cursor.name in {"body", "html", "[document]"}:
                break
            block_text = " ".join(cursor.get_text(" ", strip=True).split())
            if len(block_text) > 900:
                break
            if _MORNING_RE.search(block_text) or _AFTERNOON_RE.search(block_text):
                chosen_card = cursor
                break
            cursor = cursor.parent if isinstance(cursor.parent, Tag) else None

        if chosen_card is None and isinstance(name_tag.parent, Tag):
            chosen_card = name_tag.parent
        if chosen_card is None:
            continue

        card_selectors[_selector_for_tag(chosen_card)] += 1
        for attr_name in chosen_card.attrs:
            if attr_name.startswith("data-") and "zone" in attr_name.lower():
                zone_id_attrs[attr_name] += 1

        m_sel, m_sample = _find_session_value_element(chosen_card, _MORNING_RE)
        a_sel, a_sample = _find_session_value_element(chosen_card, _AFTERNOON_RE)
        if m_sel:
            morning_selectors[m_sel] += 1
        if a_sel:
            afternoon_selectors[a_sel] += 1

        matched_samples.append(
            {
                "zone_name": normalize_zone_name(zone_label),
                "raw_zone_label": zone_label,
                "morning_sample": m_sample,
                "afternoon_sample": a_sample,
            }
        )

    date_cell_template, next_month_selector = _detect_calendar_selectors(soup)
    dropdown_selector, dropdown_options = _detect_zone_dropdown(soup)
    date_url_template, zone_url_templates = _detect_url_templates(final_url or "")

    # Fallback for single-zone page (`?eventName=DhikalaZone&date=...` or dropdown)
    if not morning_selectors and not afternoon_selectors and soup.body:
        m_sel, m_sample = _find_session_value_element(soup.body, _MORNING_RE)
        a_sel, a_sample = _find_session_value_element(soup.body, _AFTERNOON_RE)
        if m_sel:
            morning_selectors[m_sel] += 1
        if a_sel:
            afternoon_selectors[a_sel] += 1
        if (m_sample or a_sample) and not matched_samples and zone_url_templates:
            z_only = next(iter(zone_url_templates.keys()))
            matched_samples.append(
                {
                    "zone_name": z_only,
                    "raw_zone_label": z_only,
                    "morning_sample": m_sample,
                    "afternoon_sample": a_sample,
                }
            )

    best_card = card_selectors.most_common(1)[0][0] if card_selectors else ""
    best_name = name_selectors.most_common(1)[0][0] if name_selectors else ""
    best_morning = morning_selectors.most_common(1)[0][0] if morning_selectors else ""
    best_afternoon = afternoon_selectors.most_common(1)[0][0] if afternoon_selectors else ""
    best_zone_attr = zone_id_attrs.most_common(1)[0][0] if zone_id_attrs else ""

    return {
        "found_zones_count": len(matched_samples),
        "matched_samples": matched_samples[:12],
        "navigation_detected": bool(date_cell_template or date_url_template or zone_url_templates),
        "suggested_config": {
            "_comment": (
                "Auto-suggested from your local inspection snapshot. Confirm `matched_samples` "
                "match what you see on screen before approving `verified: true`."
            ),
            "verified": False,
            "verified_at": None,
            "verified_by": None,
            "portal_url": portal_url,
            "unit_validation": {
                "jeep_slots_confirmed_meaning": None,
                "canter_slots_confirmed_meaning": None,
                "capacity_displayed_on_portal": any(
                    "/" in str(s.get("morning_sample") or "")
                    or "/" in str(s.get("afternoon_sample") or "")
                    for s in matched_samples
                ),
            },
            "consent_modals": {
                "tourist_instructions_close": "",
                "important_info_acknowledge": "",
            },
            "navigation": {
                "date_picker_trigger": "",
                "date_cell_template": date_cell_template,
                "calendar_next_month_selector": next_month_selector,
                "date_url_template": date_url_template,
                "date_status_selector": "",
                "zone_card_selector": best_card,
                "zone_name_selector": best_name,
                "zone_id_attribute": best_zone_attr,
                "zone_expand_selector": "",
                "zone_dropdown_selector": dropdown_selector,
                "zone_dropdown_options": dropdown_options,
                "zone_url_templates": zone_url_templates,
            },
            "availability": {
                "morning_availability_selector": best_morning,
                "morning_capacity_selector": "",
                "afternoon_availability_selector": best_afternoon,
                "afternoon_capacity_selector": "",
                "source_section_label": "calendar_zone_availability",
            },
        },
    }


def _find_session_value_element(
    card: Tag, session_re: re.Pattern[str]
) -> tuple[str | None, str | None]:
    """Find the child element inside `card` carrying the Morning or Afternoon slot value."""
    keyword = "morning" if "morning" in session_re.pattern else "afternoon"

    # 1. Check semantic class / data-attribute named after morning/afternoon
    for el in card.find_all(True):
        if not isinstance(el, Tag):
            continue
        classes_str = " ".join(el.get("class") or []).lower()
        attrs_str = " ".join(f"{k}={v}" for k, v in el.attrs.items() if isinstance(v, str)).lower()
        txt = " ".join(el.get_text(" ", strip=True).split())
        if (keyword in classes_str or keyword in attrs_str) and 0 < len(txt) <= 50:
            if re.search(r"\d+|full|sold|closed|booked", txt, re.IGNORECASE):
                return _selector_for_tag(el), txt

    # 2. Check sibling of a "Morning" / "Afternoon" label element
    for el in card.find_all(True):
        if not isinstance(el, Tag):
            continue
        txt = " ".join(el.get_text(" ", strip=True).split())
        if session_re.fullmatch(txt.rstrip(":-– ")):
            sib = el.find_next_sibling()
            if isinstance(sib, Tag):
                sib_txt = " ".join(sib.get_text(" ", strip=True).split())
                if 0 < len(sib_txt) <= 50:
                    return _selector_for_tag(sib), sib_txt

    return None, None
