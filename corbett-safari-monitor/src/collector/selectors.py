"""Selector configuration loader and date-template formatter.

Refuses to fabricate or guess DOM selectors: live extraction only executes after
an operator has verified the post-gate DOM via `scripts/inspect_portal.py` and
marked `verified: true` in `config/selectors.json`.

Supports all three real navigation layouts a calendar/safari SPA may use:
1. Calendar click -> all zone cards (`date_cell_template` + `calendar_next_month_selector`).
2. Direct date URL -> all zone cards (`date_url_template` with `{date}`).
3. Per-zone URLs per date (`zone_url_templates`, e.g. `?eventName=DhikalaZone&date={date}`),
   usable either standalone OR alongside (1)/(2) to include Dhikala Canter automatically.
4. Optional zone dropdown (`zone_dropdown_selector` + `zone_dropdown_options`) + calendar date.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


def format_date_template(template: str, iso_date: str, zone_id: str = "") -> str:
    """Expand date placeholders in a calendar selector or URL template.

    Supported placeholders:
      - `{date}`            -> `2026-12-05` (ISO YYYY-MM-DD)
      - `{yyyy}`            -> `2026`
      - `{mm}`              -> `12`
      - `{dd}`              -> `05`
      - `{day}`             -> `5`  (no leading zero)
      - `{month}`           -> `12` (no leading zero)
      - `{dmy}`             -> `05-12-2026` (common Indian format)
      - `{dmy_slash}`       -> `05/12/2026`
      - `{aria_date}`       -> `December 5, 2026` (Flatpickr / React DayPicker)
      - `{short_aria_date}` -> `Dec 5, 2026`
      - `{zone_id}`         -> optional portal zone identifier
    """
    d = date.fromisoformat(iso_date)
    month_full = d.strftime("%B")
    month_short = d.strftime("%b")
    return template.format(
        date=d.isoformat(),
        yyyy=f"{d.year:04d}",
        mm=f"{d.month:02d}",
        dd=f"{d.day:02d}",
        day=str(d.day),
        month=str(d.month),
        dmy=f"{d.day:02d}-{d.month:02d}-{d.year:04d}",
        dmy_slash=f"{d.day:02d}/{d.month:02d}/{d.year:04d}",
        aria_date=f"{month_full} {d.day}, {d.year}",
        short_aria_date=f"{month_short} {d.day}, {d.year}",
        zone_id=zone_id,
    )


@dataclass(frozen=True)
class SelectorConfig:
    """Validated selector mapping for reading publicly displayed availability."""

    verified: bool
    verified_at: str | None
    verified_by: str | None
    unit_validated: bool
    capacity_displayed_on_portal: bool
    tourist_instructions_close: str
    important_info_acknowledge: str
    date_picker_trigger: str
    date_cell_template: str
    date_url_template: str = ""
    calendar_next_month_selector: str = ""
    date_status_selector: str = ""
    zone_card_selector: str = ""
    zone_name_selector: str = ""
    zone_id_attribute: str = ""
    zone_expand_selector: str = ""
    zone_dropdown_selector: str = ""
    zone_dropdown_options: tuple[str, ...] = ()
    zone_url_templates: dict[str, str] = field(default_factory=dict)
    morning_availability_selector: str = ""
    morning_capacity_selector: str = ""
    afternoon_availability_selector: str = ""
    afternoon_capacity_selector: str = ""
    source_section_label: str = "calendar_zone_availability"

    def validate_for_collection(self) -> tuple[bool, str | None]:
        """Return `(is_ready, reason_if_not_ready)`.

        Enforces both slot extraction selectors AND a real date-switching rule so the
        collector can never accidentally read the same static date 30 times in a row.
        """
        if not self.verified:
            return (
                False,
                "Selector configuration is not yet verified (`verified: false`). "
                "Per Phase 1 compliance rules, selectors are never guessed. Run "
                "`python scripts/inspect_portal.py --interactive` once in a local browser "
                "to confirm selectors and set `verified: true`.",
            )

        has_calendar_date = bool(self.date_cell_template.strip())
        has_date_url = "{date" in self.date_url_template or any(
            tok in self.date_url_template for tok in ("{dmy}", "{dd}", "{day}")
        )
        has_zone_urls = bool(self.zone_url_templates) and all(
            any(tok in tpl for tok in ("{date}", "{dmy}", "{dd}", "{day}"))
            for tpl in self.zone_url_templates.values()
            if tpl.strip()
        )

        if not (has_calendar_date or has_date_url or has_zone_urls):
            return (
                False,
                "Selector config is missing automatic date navigation (`date_cell_template`, "
                "`date_url_template` with `{date}`, or `zone_url_templates` with `{date}`). "
                "Refusing to run so a single date is never duplicated across all 30 days.",
            )

        session_required = {
            "morning_availability_selector": self.morning_availability_selector,
            "afternoon_availability_selector": self.afternoon_availability_selector,
        }
        missing_sessions = [k for k, v in session_required.items() if not v.strip()]
        if missing_sessions:
            return (
                False,
                f"Verified selector config is missing required fields: {', '.join(missing_sessions)}",
            )

        # When reading multi-zone pages (calendar click or single date URL without zone dropdown),
        # require zone_card_selector and zone_name_selector.
        uses_multi_zone_page = (has_calendar_date or has_date_url) and not (
            self.zone_dropdown_selector.strip() and self.zone_dropdown_options
        )
        if uses_multi_zone_page:
            card_required = {
                "zone_card_selector": self.zone_card_selector,
                "zone_name_selector": self.zone_name_selector,
            }
            missing_cards = [k for k, v in card_required.items() if not v.strip()]
            if missing_cards:
                return (
                    False,
                    f"Verified selector config is missing required fields: {', '.join(missing_cards)}",
                )

        return True, None


def load_selector_config(path: Path) -> SelectorConfig:
    """Load selector config from `path`, or return an unverified placeholder if absent."""
    if not path.exists():
        return SelectorConfig(
            verified=False,
            verified_at=None,
            verified_by=None,
            unit_validated=False,
            capacity_displayed_on_portal=False,
            tourist_instructions_close="",
            important_info_acknowledge="",
            date_picker_trigger="",
            date_cell_template="",
        )

    raw = json.loads(path.read_text(encoding="utf-8"))
    unit_cfg = raw.get("unit_validation") or {}
    consent_cfg = raw.get("consent_modals") or {}
    nav_cfg = raw.get("navigation") or {}
    avail_cfg = raw.get("availability") or {}

    raw_zone_urls = nav_cfg.get("zone_url_templates") or {}
    zone_urls = {
        str(k).strip(): str(v).strip()
        for k, v in raw_zone_urls.items()
        if str(k).strip() and str(v).strip()
    }
    raw_dropdown_opts = nav_cfg.get("zone_dropdown_options") or []
    dropdown_opts = tuple(str(x).strip() for x in raw_dropdown_opts if str(x).strip())

    unit_validated = bool(unit_cfg.get("jeep_slots_confirmed_meaning"))
    return SelectorConfig(
        verified=bool(raw.get("verified", False)),
        verified_at=raw.get("verified_at"),
        verified_by=raw.get("verified_by"),
        unit_validated=unit_validated,
        capacity_displayed_on_portal=bool(unit_cfg.get("capacity_displayed_on_portal", False)),
        tourist_instructions_close=str(consent_cfg.get("tourist_instructions_close", "")),
        important_info_acknowledge=str(consent_cfg.get("important_info_acknowledge", "")),
        date_picker_trigger=str(nav_cfg.get("date_picker_trigger", "")),
        date_cell_template=str(nav_cfg.get("date_cell_template", "")),
        date_url_template=str(nav_cfg.get("date_url_template", "")),
        calendar_next_month_selector=str(nav_cfg.get("calendar_next_month_selector", "")),
        date_status_selector=str(nav_cfg.get("date_status_selector", "")),
        zone_card_selector=str(nav_cfg.get("zone_card_selector", "")),
        zone_name_selector=str(nav_cfg.get("zone_name_selector", "")),
        zone_id_attribute=str(nav_cfg.get("zone_id_attribute", "")),
        zone_expand_selector=str(nav_cfg.get("zone_expand_selector", "")),
        zone_dropdown_selector=str(nav_cfg.get("zone_dropdown_selector", "")),
        zone_dropdown_options=dropdown_opts,
        zone_url_templates=zone_urls,
        morning_availability_selector=str(avail_cfg.get("morning_availability_selector", "")),
        morning_capacity_selector=str(avail_cfg.get("morning_capacity_selector", "")),
        afternoon_availability_selector=str(avail_cfg.get("afternoon_availability_selector", "")),
        afternoon_capacity_selector=str(avail_cfg.get("afternoon_capacity_selector", "")),
        source_section_label=str(
            avail_cfg.get("source_section_label", "calendar_zone_availability")
        ),
    )
