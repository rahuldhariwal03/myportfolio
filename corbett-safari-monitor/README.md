# Corbett Safari Availability Monitoring & Intelligence System

A private, low-cost, **strictly read-only** Python research and analytics application for tracking and analyzing publicly displayed day-safari availability on the official Jim Corbett Tiger Reserve portal (`https://safari.corbettgov.org/`).

> **Strict Read-Only & Compliance Boundary**
> - This application **never** performs safari bookings, reservations, cart additions, visitor-detail submissions, OTP steps, or payments.
> - It **never** spoofs browser location coordinates, bypasses consent notices, solves CAPTCHAs, ignores maintenance screens, or evades IP/access controls.
> - Demonstration test data is stored in a **completely separate file** (`data/demo_corbett_monitor.db`) labeled `[DEMO]` and never contaminates your live database (`data/corbett_monitor.db`).

---

## 1. Phase 1 Inspection Summary (What Is Actually on the Official Portal)

Before writing any code, we inspected `https://safari.corbettgov.org/`, `https://corbettgov.org/`, `https://booking.corbettgov.org/`, `/pricing`, `/process`, `/faq`, `/terms`, `/privacy`, and `/ipranges`. Full details are in [`docs/phase1_website_inspection.md`](docs/phase1_website_inspection.md):

1. **Routing & Dynamic App:** `booking.corbettgov.org` redirects directly to `https://safari.corbettgov.org/` (*Booking Portal of corbettgov.org*, Zipr / eCorbett v3.0). `/canter` redirects to `https://safari.corbettgov.org/?eventName=DhikalaZone&date=...`. Calendar and slot counts render dynamically client-side (no public read-only API exists).
2. **8 Official Zones & Unit Comparability:**
   - **7 Day Jeep Permit Zones:** Bijrani, Jhirna, Dhela, Garjia, Durgadevi, Sonanadi, Pakhro (1 Gypsy permit = up to 6 visitors).
   - **1 Day Canter Seat Zone:** Dhikala (`DhikalaZone` — 16-seater shared bus, seats booked individually; no day Jeep permits).
   - Jeep permits and Canter seats are tracked with separate unit metadata so unlike numbers are never mixed together.
3. **Observed Access Controls & Limitations:**
   - **Consent & Advisory Modals:** Supreme Court mobile-phone prohibition notice + non-refundable & monsoon **T + 7 days** policy modal.
   - **Mandatory Location Verification Gate:** Portal requires genuine browser location verification before rendering calendar/zone availability.
   - **Operating Hours & Maintenance:** Portal operates **05:30 AM – 11:30 PM IST** (`corbettgov.org/faq`) and includes a departmental pause/maintenance screen plus a system clock-sync check.
   - **Cloud/S2S IP Restrictions:** `corbettgov.org/terms` (Clause 10) and `/ipranges` explicitly restrict AWS, GCP, Azure, Oracle Cloud, and automated S2S abuse. **Do not deploy unattended collectors on cloud servers** — review the Terms of Use (or obtain written permission from `support@corbettgov.org`) and run only locally with genuine browser permissions at low frequency.
   - **No Invented Selectors:** Because post-gate DOM elements are visible only after genuine local browser location verification, `config/selectors.example.json` starts with `"verified": false`. Use `scripts/inspect_portal.py` locally to confirm the exact visible selectors before enabling live collection.

---

## 2. Project Structure

```text
corbett-safari-monitor/
├── app.py                             # Streamlit 5-page responsive dashboard
├── setup_and_run.bat                  # Step 1 (Windows): One-click install & dashboard launcher
├── setup_and_run.sh                   # Step 1 (macOS/Linux): One-click install & dashboard launcher
├── 2_calibrate_live_portal.bat        # Step 2 (Windows): One-time consent/location & selector setup
├── 3_collect_live_data_now.bat        # Step 3 (Windows): Run hands-free 30-day live collection now
├── 4_start_daily_scheduler.bat        # Step 4 (Windows): Automatic morning & evening IST scheduler
├── requirements.txt                   # Python dependencies
├── .env.example                       # Configurable environment template
├── .streamlit/config.toml             # Dashboard server & theme settings
├── config/
│   └── selectors.example.json         # Selector template (verified=false until confirmed)
├── docs/
│   └── phase1_website_inspection.md   # Full Phase 1 website inspection & compliance audit
├── scripts/
│   ├── inspect_portal.py              # Phase 1: Interactive read-only Playwright inspector
│   ├── init_db.py                     # Phase 2: Initialize schema, triggers & 8 official zones
│   ├── seed_demo_data.py              # Phase 2: Generate isolated [DEMO] sample test database
│   ├── run_collector.py               # Phase 3–5: Run one compliant collection + change check
│   └── run_scheduler.py               # Phase 7: Twice-daily configurable Asia/Kolkata scheduler
├── src/
│   ├── config.py                      # .env configuration loader & validation
│   ├── date_window.py                 # Rolling 30-day window (Asia/Kolkata) & hours check
│   ├── database/                      # Modular DB backend (SQLite now; Postgres/Supabase ready)
│   ├── collector/                     # Gate detector, read-only guard, raw parser, Playwright
│   ├── analytics/                     # Change detection, lead-time trends, monitoring & CSV
│   ├── api_ready/                     # Read-only query service prepared for future FastAPI
│   ├── scheduler/                     # APScheduler configurable morning & evening jobs
│   └── dashboard/                     # Streamlit theme + all 5 dashboard pages
└── tests/                             # Phase 8: 53 automated pytest tests
```

---

## 3. Step-by-Step Setup (Beginner Friendly)

### Fastest Way (One Command)

- **Windows:** Open `corbett-safari-monitor` and double-click **`setup_and_run.bat`** (or run `setup_and_run.bat` in Command Prompt).
- **macOS / Linux:** Run **`bash setup_and_run.sh`** inside `corbett-safari-monitor/`.

This automatically creates `.venv`, installs dependencies, downloads Playwright Chromium, creates `.env`, initializes the database, and launches the dashboard at `http://localhost:8501`.

### Manual Commands (Step by Step)

#### Step 1: Open the project folder and create a virtual environment

```bash
cd corbett-safari-monitor
python3 -m venv .venv
source .venv/bin/activate        # On Windows PowerShell: .venv\Scripts\Activate.ps1
```

### Step 2: Install Python dependencies and Playwright Chromium

```bash
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

### Step 3: Create your `.env` configuration file

```bash
cp .env.example .env
```

Open `.env` in any text editor to adjust collection times if needed (no code changes required):

```env
COLLECTION_TIMEZONE=Asia/Kolkata
MORNING_COLLECTION_TIME=07:30
EVENING_COLLECTION_TIME=19:30
MONITORING_WINDOW_DAYS=30
```

### Step 4: Initialize the live database (and optional demo test database)

```bash
# Creates data/corbett_monitor.db with all 6 tables, indexes, immutability triggers & 8 zones
python scripts/init_db.py

# Optional: creates a SEPARATE data/demo_corbett_monitor.db labeled [DEMO] to test charts/tables
python scripts/seed_demo_data.py --reset
```

### Step 5: Launch the Streamlit Dashboard

```bash
streamlit run app.py
```

Open the displayed URL (default `http://localhost:8501`) in your browser. Use the sidebar to move across all 5 pages and switch between **Live Database (Real Only)** and **Demo / Sample Test Data [DEMO]**:

1. **Overview** — Latest collection timestamp & freshness indicator, active window date count, 8 official zones, comparable Jeep permit vs Canter seat totals, daily reduction/increase, success rate.
2. **Zone-Wise Availability** — `Zone | Date | Morning | Afternoon | Total available` with date, date-range, zone, and session filters + heatmap + CSV export.
3. **Daily Changes** — Reductions, increases, net change, rolling 24-hour movement, morning vs evening comparison, zone-wise movement chart + CSV export.
4. **Historical Trends** — Availability over time, zone & session comparisons, weekday vs weekend patterns, lead-time analysis (`30, 20, 15, 10, 5, 1` days before safari), and descriptive research intelligence.
5. **Collection Monitoring** — Manual run button, schedule preview, run history, missing dates/zones audit, diagnostic error logs & screenshots, and CSV report export center.

---

## 4. Authorized Local Portal Calibration & Automatic 30-Day Collection

### Step A: One-time portal calibration (saves location permission & confirms selectors)

- **Windows:** Double-click **`2_calibrate_live_portal.bat`**
- **macOS / Linux:**
  ```bash
  .venv/bin/python scripts/inspect_portal.py --interactive
  ```

This opens `https://safari.corbettgov.org/` in a visible local Chromium window (strictly read-only, persistent local profile in `data/browser_profile/`). Accept the declaration notice (tick *"Don't show this again"*), click **Allow** on the real browser location prompt, click one open safari date so zone numbers appear, then press **ENTER** in the terminal and type **`yes`** if the preview table matches (or approve inside Dashboard → `5. Collection Monitoring → Setup Checklist & Selector Approval`).

### Step B: Quick 2-day test, then automatic 30-day collection

```bash
# Preview today's rolling 30-day window (Asia/Kolkata)
python scripts/run_collector.py --preview-window

# Quick 2-day test (~15 seconds) to verify automatic date switching
python scripts/run_collector.py --type manual --days 2

# Full automatic 30-day collection (or double-click 3_collect_live_data_now.bat on Windows)
python scripts/run_collector.py --type manual
```

If a declaration or location prompt ever appears on a future local run, the collector waits up to `CONSENT_WAIT_SECONDS=60` for you to click Accept/Allow and then automatically scans all 30 dates (including month-end calendar rollover) and all zones hands-free.

### Step C: Twice-daily automatic scheduler (`Asia/Kolkata`)

```bash
# Preview next morning & evening fire times and their rolling 30-day date windows
python scripts/run_scheduler.py --show-schedule

# Start morning & evening scheduler (or double-click 4_start_daily_scheduler.bat on Windows)
python scripts/run_scheduler.py
```

---

## 5. Run Automated Tests

```bash
pytest -v
```

Covers rolling 30-day windows (`Dec 1 → Dec 1–30`, `Dec 2 → Dec 2–31`, `Dec 3 → Dec 3–Jan 1`), schema constraints, duplicate prevention, snapshot immutability triggers, interrupted-run recovery, the exact `40 → 32 → 25` change walkthrough (`8`, `7`, total `15`), `NULL` safety, capacity adjustments, invalid/price/negative text rejection, access-gate halting + diagnostic screenshots, read-only guards, CSV export integrity, and all 5 Streamlit pages.

---

## 6. Database Migration & Future Read-Only API Readiness

- **PostgreSQL / Supabase Migration:** Install `pip install 'psycopg[binary]>=3.2.0'` and change `DATABASE_URL=postgresql://user:pass@host:5432/dbname` in `.env`. Both SQLite and PostgreSQL schemas are provided in `src/database/schema.py`, and backend switching is handled automatically in `src/database/backend.py`.
- **Future Read-Only FastAPI Layer:** `src/api_ready/read_service.py` already exposes clean, read-only methods returning stored observations and exact capture timestamps for future `GET /api/zones`, `GET /api/availability`, `GET /api/availability/{date}`, `GET /api/changes/daily`, and `GET /api/history` endpoints (no public API or booking endpoint is enabled in v1).

---

## 7. Verification Status (Honest Testing Report)

| Component | Verification Status |
|---|---|
| Phase 1 official website inspection (`safari.corbettgov.org` & `corbettgov.org`) | Verified against live public HTML & policy pages |
| Phase 2 SQLite schema, 6 tables, indexes, `UNIQUE` & immutability triggers | Tested & passing (`pytest`) |
| Phase 3 collector logic, gate halting, retry, screenshots & read-only guard | Tested against realistic stub/HTML fixtures (`pytest`); **post-location-gate live DOM extraction requires local Chromium + genuine user location permission + verified `config/selectors.json`** |
| Phase 4 append-only historical snapshot preservation | Tested & passing (`pytest`) |
| Phase 5 consecutive, morning/evening, daily, 24h & validated capacity % changes | Tested & passing (`pytest`) |
| Phase 6 5-page Streamlit dashboard, filters, Plotly charts & CSV exports | Tested via Streamlit `AppTest` + running live preview |
| Phase 7 configurable `Asia/Kolkata` morning/evening scheduler | Tested & passing (`pytest` + CLI verification) |
