# Phase 1: Official Website Inspection & Technical Implementation Proposal

**Inspected Date:** 2026-11-18 (UTC)  
**Target Portal:** `https://safari.corbettgov.org/` (*"Booking Portal of corbettgov.org"*)  
**Companion Official Pages Inspected:**
- `https://corbettgov.org/` (main Corbett Tiger Reserve site)
- `https://booking.corbettgov.org/` and `https://booking.corbettgov.org/canter`
- `https://safari.corbettgov.org/robots.txt`
- `https://corbettgov.org/junglesafari`, `/pricing`, `/process`, `/faq`, `/terms`, `/privacy`, `/ipranges`
- Zone detail pages (`/jhirna`, `/dhela`, `/bijrani`, `/garjiya`, `/dhikala`, `/durgadevi`, `/sonanadi`, `/pakhro`)

---

## 1. Portal Routing & Visible Architecture

1. **Single-Page Booking Application (SPA):**
   - `https://booking.corbettgov.org/` (linked from `corbettgov.org` for **Jeep Safari**) redirects directly to `https://safari.corbettgov.org/`.
   - `https://booking.corbettgov.org/canter` (linked for **Dhikala Canter Safari**) redirects to `https://safari.corbettgov.org/?eventName=DhikalaZone&date=2026-11-15`.
   - Night Stay bookings are hosted on a separate subdomain (`https://stays.corbettgov.org/`) and are outside the scope of day-safari monitoring.
   - The official Terms of Use identify **Zipr** as the ticketing partner (also referred to on `/process` as *eCorbett Ver 3.0*).

2. **Initial DOM Shell (Pre-Gate):**
   - On first load without JavaScript execution and granted browser location permission, `https://safari.corbettgov.org/` renders:
     - Top header counters (`0 | Pay | 0`) and `Loading...` placeholders — confirming that the calendar, zone cards, and Morning/Afternoon slot counts are rendered dynamically client-side rather than in static HTML.
     - **Tourist Advisory Modal (English + Hindi):** *"Mobile Phone Restriction – Corbett Tiger Reserve"* (Hon'ble Supreme Court order dated 17 Nov 2025 in WP(C) No. 202/1995, I.A. No. 20650/2023) plus mandatory printed permit + original ID requirement, dismissible via close (`x`).
     - **Consent & Policy Notice Modal (English + Hindi):** *"Important Information"* (non-refundable terms, monsoon **T + 7 Days** window notice, *"Vehicle Selection & Allocation"* up to 3 days before trip) with *"Don't show this again"* and *"Book Tickets!"* acknowledgment controls.
     - **Mandatory Location Verification Modal:** *"Location verification required — To protect your account and meet regulatory requirements, we must verify your location before you can continue. Your coordinates are encrypted and never shared with third parties."* accompanied by an *"Okay!"* button and browser-specific help links for enabling location in Chrome, Firefox, Safari, and Edge.
     - **Department Pause / Maintenance Modal Container:** *"All bookings have been paused by the department! — The system is undergoing schedules updates and will be available soon. Please wait! The page will automatically load the latest updates in 00:05s."*
     - **Client Clock-Skew Error Modal Container:** OS-specific instructions to turn on automatic date, time, and timezone synchronization and press *Retry*.

3. **No Public API Assumed:**
   - No documented public read-only availability API is published on `corbettgov.org` or `safari.corbettgov.org`.
   - In accordance with project rules, no undocumented internal API endpoints or guessed CSS selectors are hardcoded.

---

## 2. Official Safari Zones, Sessions & Data Semantics

Across `https://corbettgov.org/`, `/junglesafari`, `/pricing`, and `/process`, Corbett Tiger Reserve publishes **8 official tourism zones**:

| Zone Name | Entry Gate | Day Safari Mode | Published Operating Season | Observed `source_zone_identifier` | Pre-Gate Capacity Status |
|---|---|---|---|---|---|
| **Jhirna** | Dhela | Day Jeep Permit (max 6 pax/jeep) | Throughout year (weather permitting) | `NULL` (verify post-gate) | 30 jeeps/shift noted on `/jhirna`; must verify on live portal |
| **Dhela** | Dhela | Day Jeep Permit (max 6 pax/jeep) | Throughout year | `NULL` (verify post-gate) | `NULL` until displayed on portal |
| **Bijrani** | Amdanda | Day Jeep Permit (max 6 pax/jeep) | 15 Oct – 30 June | `NULL` (verify post-gate) | `NULL` until displayed on portal |
| **Garjia** | Garjiya / Ringora | Day Jeep Permit (max 6 pax/jeep) | Throughout year (`/`) / 15 Oct – 30 June (`/pricing`) | `NULL` (verify post-gate) | `NULL` until displayed on portal |
| **Durgadevi** | Durgadevi | Day Jeep Permit (max 6 pax/jeep) | 15 Nov – 15 June | `NULL` (verify post-gate) | `NULL` until displayed on portal |
| **Sonanadi** | Vatanvasa (Kotdwar) | Day Jeep Permit (max 6 pax/jeep) | 15 Nov – 15 June | `NULL` (verify post-gate) | `NULL` until displayed on portal |
| **Pakhro** | Pakhro (Kotdwar) | Day Jeep Permit (max 6 pax/jeep) | 15 Nov – 15 June | `NULL` (verify post-gate) | `NULL` until displayed on portal |
| **Dhikala** | Dhangari | **Day Canter Seat only** (16-seater shared bus; no day Jeep permits) | 15 Nov – 15 June | `DhikalaZone` (verified via official `/canter` redirect) | 16 seats/canter; shift total `NULL` until displayed on portal |

### Key Analytical & Validation Rules Derived from Inspection

1. **Sessions:** Two daily sessions — `morning` and `afternoon` (winter/summer clock times vary slightly by season; the portal uses *"Morning"* and *"Afternoon"* permits per `/process`).
2. **Unit Comparability Warning (Jeep Permits vs. Canter Seats):**
   - The 7 Jeep zones issue **per-vehicle (Gypsy) permits** (1 permit = 1 vehicle, up to 6 visitors).
   - **Dhikala** day visits issue **individual Canter seats** (not Jeep permits).
   - Therefore, raw displayed values (`raw_displayed_value`) are always preserved verbatim, and the dashboard separates or flags unit types (`jeep_permit` vs. `canter_seat`) when showing *"Total observed available slots, where comparable"*.
3. **Booking Window Variability:**
   - Standard season: opens progressively up to **45 days in advance** (so a rolling 30-day window fits completely inside the standard window).
   - Monsoon season: restricted to **T + 7 days** (explicitly stated in the `safari.corbettgov.org` Important Information notice). Dates 8–30 days out during monsoon must be recorded as `window_not_open` with `available_slots = NULL`, **never as `0`**.
   - Seasonal zone closures (e.g., Dhikala, Durgadevi, Sonanadi, Pakhro closed 16 June – 14 Nov; Bijrani closed 1 July – 14 Oct) must be recorded as `zone_closed` with `available_slots = NULL`, **never as `0`**.

---

## 3. Access Controls, Terms of Use & Collection Limitations

Our inspection identified five concrete limitations that govern legitimate collection:

| Control / Policy | Evidence Found on Official Site | Compliant System Behaviour |
|---|---|---|
| **Browser Location Verification** | `safari.corbettgov.org` renders *"Location verification required"* before loading availability. | **Never spoof coordinates.** Collector runs on a local operator machine (`PLAYWRIGHT_HEADLESS=false`) using genuine OS/browser permission. If the location modal blocks the page, the collector stops, saves a screenshot, logs `status = 'blocked'`, and reports `location_verification_required`. |
| **Consent & Advisory Notices** | Tourist Instructions & Important Information modals appear on entry. | Acknowledged transparently only through standard visible close/confirm interactions in an authorized browser session; never suppressed via script injection. |
| **Cloud / S2S IP Restrictions & Anti-Bot Terms** | `corbettgov.org/terms` (Clause 10 & Session Recording), `/privacy` (Section 6), and `/ipranges` explicitly restrict Server-to-Server traffic, cloud IPs (AWS, GCP, Azure, Oracle Cloud, IBM Bluemix), and automated bots/abuse. | **Do not deploy unattended collectors on cloud VMs.** Confirm compliance with CTR terms (or request written research permission via `support@corbettgov.org`) before enabling scheduled runs. Operate only from an authorized local machine at ultra-low frequency (max 2 read-only views/day) with polite 4–8s pacing. |
| **Portal Operating Hours & Maintenance Pauses** | `corbettgov.org/faq` states the portal runs **05:30 AM – 11:30 PM IST**. `safari.corbettgov.org` also includes a *"All bookings have been paused by the department!"* screen. | Scheduler and collector enforce the 05:30–23:30 IST window. If a pause screen, clock-skew prompt, CAPTCHA, or HTTP block appears, collection halts cleanly and records `blocked` / `portal_paused` without retrying aggressively. |
| **Post-Gate DOM Selectors Not Visible Without Location Verification** | Calendar and slot elements load client-side only after genuine browser location verification (and cloud sandboxes cannot access the portal). | `config/selectors.example.json` ships with `"verified": false` (zero fabricated selectors). An interactive read-only Playwright inspector (`scripts/inspect_portal.py`) lets the local operator inspect the live post-gate DOM, capture visible labels, and populate verified selectors in `config/selectors.json` before enabling live extraction. |
| **Read-Only Boundary** | `/process` documents a 180-second waiting period on Visitor Details, ID uploads, WhatsApp OTP, and payment. | Collector implements a strict `ReadOnlyGuard` that blocks any interaction with cart, visitor details, ID upload, OTP, reserve, book, or payment elements/URLs. |

---

## 4. Technical Implementation Architecture

```
corbett-safari-monitor/
├── app.py                        # Streamlit 5-page dashboard (Overview, Zones, Changes, Trends, Monitoring)
├── config/selectors.example.json # Selector contract (verified=false until confirmed via inspect_portal.py)
├── docs/phase1_website_inspection.md
├── scripts/
│   ├── inspect_portal.py         # Phase 1: Authorized local Playwright DOM inspector (read-only)
│   ├── init_db.py                # Phase 2: Creates SQLite schema, triggers, indexes & 8 official CTR zones
│   ├── seed_demo_data.py         # Phase 2: Creates isolated, clearly labeled [DEMO] sample test database
│   ├── run_collector.py          # Phase 3–5: Runs compliant Playwright collection + snapshot + change calc
│   └── run_scheduler.py          # Phase 7: Configurable Asia/Kolkata morning & evening scheduler
├── src/
│   ├── config.py                 # Environment-driven configuration (.env)
│   ├── date_window.py            # Rolling 30-day window (Asia/Kolkata) & portal hours check
│   ├── database/                 # Modular DB backend (SQLite now, PostgreSQL/Supabase ready) + immutable snapshots
│   ├── collector/                # Compliance/gate detector, read-only guard, raw/parsed value parser, Playwright runner
│   ├── analytics/                # Consecutive, morning/evening, daily, 24h, capacity %, lead-time & health metrics
│   ├── api_ready/                # Clean read-only service functions prepared for future FastAPI endpoints
│   ├── scheduler/                # APScheduler service (configurable IST morning & evening runs)
│   └── dashboard/                # Streamlit UI theme & all 5 analytics/monitoring pages + CSV downloads
└── tests/                        # Phase 8: Automated pytest suite for schema, changes, edge cases & collector
```

### Key Architectural Safeguards
1. **Strict Separation of Live vs. Demo Data:** `data/corbett_monitor.db` contains only schema, the 8 official zones, and genuine collection attempts/logs. Demonstration test records live in a separate `data/demo_corbett_monitor.db` file with `is_demo = 1` and a prominent banner on every dashboard page.
2. **Immutable Historical Snapshots:** Enforced both in repository code and via SQLite `BEFORE UPDATE` and `BEFORE DELETE` database triggers on `availability_snapshots` and `change_events`.
3. **NULL-Safe Raw vs. Interpreted Values:** Every snapshot stores `raw_displayed_value` verbatim; `available_slots` is populated only when the string unambiguously represents a non-negative slot count. Missing, failed, closed, paused, or malformed values are stored as `NULL` and skipped (never treated as `0`) during change calculations.
4. **Neutral Analytical Language:** Slot decreases are always labeled **Availability Reductions** (never *"Confirmed Bookings"*), reflecting that cancellations, quota releases, weather closures, and departmental holds can all shift displayed counts.
