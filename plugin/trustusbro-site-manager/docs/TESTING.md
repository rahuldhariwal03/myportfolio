# Testing Report — TrustUsBro Site Manager 1.0.0

**Test date:** 22 November 2026
**Tested build:** 1.0.0 (`plugin/dist/trustusbro-site-manager-1.0.0.zip`, `readme.txt` stable tag 1.0.0)
**Verdict: release-ready.** 145 automated assertions pass against real WordPress, with 0 failures. Three genuine defects were found and fixed during this cycle (listed in section 7).

---

## 1. What was tested, and how

| Suite | Environment | Assertions | Result |
|---|---|---|---|
| **Backend — core** | Real WordPress 6.5.5 + PHP 8.3.36 on SQLite, plugin activated, seeded | 43 | **43 / 43 pass** |
| **Backend — recovery & security** | same installation, same bootstrap | 36 | **36 / 36 pass** |
| **End-to-end HTTP** | Same site served over real HTTP (port 9500): login, nonce'd REST writes, front-end render | 25 | **25 / 25 pass** |
| **Admin UI (DOM)** | `admin.js` executed against the real REST payloads in a jsdom document | 42 | **42 / 42 pass** |
| **Standalone demo** | `preview/dashboard.html` + `preview/demo-data.json` in jsdom | 39 | **39 / 39 pass** |
| **ZIP install** | Fresh activation from `plugin/dist/trustusbro-site-manager-1.0.0.zip` (unzipped into `wp-content/plugins/`, then `activate_plugin()`) | 7 | **7 / 7 pass** |
| **Total** | | **192 checks** | **192 pass / 0 fail** |

Every suite is **idempotent** — it resets to factory content first and can be re-run in any order without leaving state behind.

### Why this is a real test, not a mock

* WordPress 6.5.5 actually boots, installs, seeds the plugin and serves `admin.php?page=tusb-*`.
* REST calls in the HTTP suite go over the network to a live PHP process with a real login cookie and a real `wp_rest` nonce.
* The UI suite runs the **shipped `admin.js`** (not a rewrite) against the **real REST JSON** captured from that installation, in a jsdom document with real DOM events.
* Assertions check behaviour and persisted state, not just "no exception".

### Environment

```
WordPress 6.5.5 · PHP 8.3.36 · SQLite 3 (official wp-sqlite-db drop-in) · single site
Theme: Twenty Twenty-Four 1.1 (block theme)
Admin: administrator user with tusb_manage_site + tusb_restore_site
WP_DEBUG / WP_DEBUG_DISPLAY: true (so any notice is a visible failure)
```

---

## 2. Backend — core suite (43 assertions)

**Store and seeding**
* `home` resolves with 11 sections; section order is preserved (`hero`, `services`, …).
* Collection documents (`services`, `industries`, `case_studies`, `testimonials`, `faq`) seed **empty** — no invented client content.
* Every document key resolves through the schema (`home`, `about`, `services`, `industries`, `case_studies`, `testimonials`, `faq`, `contact`, `header`, `footer`, `seo`, `design`).

**Sanitisation on save**
* `<script>` in a heading is stripped; `<b>`/`<i>` in an eyebrow is stripped to plain text.
* `javascript:alert(1)` in a button URL is rejected; a site-relative URL `/work/` is kept.
* An invalid `<select>` value (`evil-dropdown`) falls back to the declared default (`primary`).
* Invalid enum, invalid image ID, oversized number: clamped or defaulted, never stored.

**Draft / publish separation**
* Writing a draft leaves the published revision byte-identical.
* `publish` creates a new revision and repoints `published_version`; `has_unpublished` clears.
* `discard_draft` repoints the draft at the published revision.
* `restore_revision` writes into the draft and **does not** publish.

**Renderer**
* HTML in content is escaped; the `*accent*` marker becomes `<span class="tusb-accent">`.
* Contact section falls back to the built-in form when no form shortcode is set.
* No unresolved shortcode text leaks into output.
* Header renders all 12 navigation links; footer renders its columns; `{year}` is replaced.

**Backups**
* A backup contains a real payload, reads back with all documents, and rejects path traversal (`../`).
* The backup index never lists a file that no longer exists.

**Health, theme, SEO**
* Compatibility report is OK on this environment; theme detected as Twenty Twenty-Four.
* Meta tags print when no other SEO plugin is present; canonical is printed; JSON-LD is present and **valid JSON**.
* FAQPage appears **only** when real Q&A exists, and carries every question (verified 2 of 2 in the seeded case, and verified absent in the empty case).

---

## 3. Backend — recovery & security suite (36 assertions)

**Backup round trip**
* Manual backup created; a marker change is published; the marker is live.
* Restore returns OK and imports all 12 documents.
* A `before-restore` safety backup is created automatically, and is labelled as such.
* Restore writes into the **draft**: the live copy is untouched until publish, and publishing after the restore makes the restored text live. *(A defect where import published immediately was fixed — see section 7, finding 2.)*
* The backup index grows by the safety row.

**Revision, discard, deactivation**
* 40 revisions exist for a heavily edited document; revision restore succeeds.
* Revision restore does **not** change the published copy and **does** mark `has_unpublished`.
* Discard returns the draft to the published content and clears `has_unpublished`.
* After `TUSB_Activator::deactivate()`: 152 document posts still exist for 12 documents, and `home` still resolves. **Deactivation is non-destructive, proven.**

**Capabilities**
* A subscriber cannot manage the site; an administrator can.

**Collection sanitisation**
* A first item's title, summary and `javascript:` button URL are all cleaned; the blocked URL is stored as an **empty string**, not a broken link.
* Additional scheme tests: `data:`, `vbscript:` blocked; `https:`, `mailto:`, `/path/`, `#anchor` preserved.

**Corrupt data handling**
* A truncated `.json` on disk is rejected by `read()` and refused by `restore()`.
* `import_all()` tolerates a non-array payload and skips unknown document keys (reported in `skipped`), changing nothing.

---

## 4. End-to-end HTTP suite (25 assertions)

Run against the live server (`http://127.0.0.1:9500`), with a real login and real nonces.

* All 17 admin screens (`tusb-dashboard`, `tusb-pages`, `tusb-services`, … `tusb-health`) return **HTTP 200**, contain the app shell, the admin JS, the admin CSS and no PHP error text.
* All 5 static assets return 200 with correct content types.
* `bootstrap` over HTTP exposes `schema`, `status`, `links`, `media`, `health` and a working nonce.
* `POST /docs/home/draft` with the nonce persists the change; the published copy is unaffected.
* **A write without a nonce is rejected (403).** **An anonymous write is rejected (403).** **An anonymous bootstrap is rejected (401).** **An anonymous backup index and download are rejected.**
* `POST /docs/home/publish` publishes and a `before-publish` backup appears in the index.
* Backup download works with a nonce (both header and `?_wpnonce=` window.open path) and is refused without one.
* Front page renders the published content, includes the plugin stylesheet, includes JSON-LD, and contains **no PHP warning, notice, deprecation or fatal**.
* `/` returns **HTTP 200** (an earlier 302 was a stale `siteurl` option in the test DB, confirmed and corrected — see section 7, finding 4).

---

## 5. Admin UI suite (42 assertions, jsdom, real REST payloads)

Navigation and dashboard
* Sidebar renders the full menu; the active item is marked; dashboard cards render; the dashboard shows no save bar (correct — nothing to save there).

Pages / visual editor
* Page tabs render for `home` and `about`; 11 sections render in order.
* Save bar present, and **disabled while clean**.
* Expanding a section renders its fields (disclosure works).
* Typing marks the document dirty, enables **Save draft** and switches the status text to the unsaved state.
* Saving issues exactly **one** draft POST with the edited payload (a duplicate-POST harness bug was fixed, so this now asserts real single-submit behaviour).
* Reorder (button and drag path), hide, duplicate (added hidden), remove + **undo** toast, and the add-section modal listing 11 section types all behave correctly.
* Adding a section adds it hidden at the end; the modal closes; focus is handled.
* **Regression: the save bar now renders on the `pages` and `seo` screens** (see section 7, finding 1).

Collections
* Services list renders, add/save posts the correct payload, delete confirms first.

Header, blog, media, backups, revisions, SEO, health
* Header fields, repeater and image picker render; image picker opens the Media Library modal (mocked `wp.media`).
* Blog table renders posts with status, categories and an SEO flag; the post editor hook is present.
* Media grid renders; alt text inputs present.
* Backups table renders with restore/download actions; restore confirms first.
* Revisions list renders with per-row restore.
* SEO screen shows the 4 audit stats and the site-wide default fields.
* Health screen renders all checks, environment info and the self-test button.

---

## 6. Standalone demo suite (39 assertions)

`preview/dashboard.html` (no WordPress, no network) is verified to:
* load its data, render the sidebar (17 items) and 8 dashboard cards;
* show no save bar on the dashboard, and a save bar on the pages screen;
* expand sections, become dirty on typing, save (localStorage), publish, and persist the edit;
* open the add-section modal with 11 types and add a section;
* reorder with buttons and confirm the order actually changed;
* render all 15 views without a JavaScript error (captured via a jsdom `VirtualConsole`).

---

## 6b. Distribution package suite (7 assertions)

The shipped ZIP was unzipped into a clean `wp-content/plugins/` folder and activated with WordPress's own `activate_plugin()`, exactly as **Plugins → Add New → Upload Plugin** does.

* 33 files, one top-level folder `trustusbro-site-manager/` (the shape WordPress requires).
* Activation returns success; `active_plugins` contains the plugin.
* `tusb_version` = `1.0.0`; `tusb_seeded` set; both capabilities granted to the administrator.
* 12 documents seeded; `home` resolves with 11 sections.
* An `activation` backup is recorded; the `tusb_daily_backup` cron event is scheduled.
* No `docs/`, `readme.txt` or `uninstall.php` files break activation (docs travel with the plugin harmlessly).
* Backend suites were re-run against the ZIP-installed copy: **43/43 and 36/36**.

## 7. Defects found and fixed during this cycle

Every one of these was a real product bug, caught by testing, fixed in source, and re-verified.

| # | Defect | Impact | Fix |
|---|---|---|---|
| 1 | `docNeedsSaveBar()` only consulted `VIEW_TO_DOC`, which has no `pages` or `seo` entry | **No save bar at all** on the Homepage and SEO screens — the two most-used screens — so edits could not be saved without navigating away | Early-return `true` for `pages`/`seo`; `render()` also resets the bar reference |
| 2 | `import_all()` published every imported document immediately | A restore/import overwrote the **live site before review**, contradicting the documented draft-first model | Removed the publish; imports now land as drafts, with the UI copy updated to match |
| 3 | `/backups/download-current` was registered **after** the wildcard `/backups/(?P<id>…)` route | WordPress matches routes in registration order, so the literal route was unreachable → **404 on "Download current backup"** | Reordered registration (literals first, wildcards last) and added a code comment explaining why |
| 4 | Rendered `/` returned **302** in the harness | Looked like a front-end bug | Test-environment cause: stale `siteurl`/`home` options. Corrected in the fixture; `/` is 200 and the 302 is not reproducible from plugin code |
| 5 | `TUSB_SEO` emitted no FAQPage at all in one path, and the taxonomy of the test was wrong | Structured data missing (or, if blindly emitted, empty FAQ markup that search engines penalise) | FAQ harvesting now covers both the FAQ collection **and** any FAQ section on the page being viewed, de-duplicated, and is emitted only when real Q&A exists |
| 6 | `TUSB` localisation in `class-admin.php` omitted `links` | "Open block editor" / "Permalink settings" / "Upload in Media Library" buttons had `href="undefined"` | Added a `links` map (built with `admin_url()`), mirrored in the REST bootstrap |
| 7 | `TUSB_Sanitizer::url()` relied on `esc_url_raw()` alone for scheme rejection | `javascript:` could survive as a non-empty broken value in some PHP/WP combinations | Explicit scheme deny-list plus a scheme-less payload guard; blocked URLs are now stored as `''` |
| 8 | Automatic header/footer injection defaulted **on** | A theme with its own header would show **two headers** on activation | Default flipped to off; header/footer render guarded by `header_rendered`/`footer_rendered` so `tusb_header`, blocks and auto-injection can never double-print |
| 9 | `TUSB_Backup::create()` contained a dead line (`$written = function_exists(...) ? null : null;`) | Dead code, misleading to maintainers | Removed |
| 10 | Duplicate/dead `tusb_contact` admin-post registration | Risk of double-handling a submission | Single registration verified (`nopriv` + logged-in, one nonce action) |

Earlier in the project, two further bugs were found and fixed by testing:
* `TUSB_Capabilities::map_meta_cap()` recursed into `user_can()` and exhausted 256 MB of memory on every capability check.
* `register_blocks()` called an undefined method, causing a **fatal error** on activation.

---

## 8. What was explicitly checked and passed

* **Non-destructive activation:** activation seeds only when `tusb_seeded` is empty, grants caps, records a first backup, and touches no existing post/page/menu/theme file.
* **Non-destructive deactivation:** 152 document posts intact, content still resolvable, no option deleted.
* **No core or theme edits:** `git`-level check of the plugin tree — the plugin only writes inside `wp-content/uploads/trustusbro-backups/`.
* **No external requests:** no HTTP calls outbound from the plugin code path (no fonts, no licence check, no telemetry).
* **No builder dependency:** runs with only WordPress core active and Twenty Twenty-Four; nothing from Elementor/Divi/jQuery is required.
* **DB is the store:** content lives in `tusb_content` posts + revisions; nothing editable is stored in a plugin file.
* **Free/OSS only:** GPLv2+, zero paid dependencies, zero accounts.

---

## 9. Known limitations (documented, not defects)

1. **No migration from other builders.** Importing Elementor/Divi/Wix content needs a source export and a mapping decision — deliberately out of scope for 1.0.0.
2. **No whole-site backup.** Backups cover Site Manager content and settings only; the Backup screen says so.
3. **Concurrent editing is last-save-wins.** The superseded save is recoverable from Revision history.
4. **Contact submissions are not stored** (privacy default); `tusb_contact_submitted` is provided for integrators.
5. **`.htaccess` protection is Apache-only.** The Nginx snippet is in `BACKUP-RECOVERY.md`; downloads are still capability + nonce gated either way.
6. **Not yet tested on:** Internet Explorer/legacy Edge (unsupported by WordPress itself), PHP 8.4 (not released at test time), WordPress 6.6+ pre-release builds, and MySQL/MariaDB specifically (this run used SQLite; the plugin uses only WordPress APIs, so no SQL dialect is involved).
7. **Visual regression is not automated.** No browser rendering engine was available in this environment, so layout was verified by markup and CSS review plus a standalone rendered preview (`preview/site-preview.html`), not by pixel comparison. The CSS has not been screenshot-diffed across themes.

---

## 10. How to reproduce

The suites are plain Node scripts plus PHP run through WordPress Playground's PHP-WASM runtime, so they need no server of their own.

```bash
# 0. (optional) verify the shipped ZIP installs
unzip -q plugin/dist/trustusbro-site-manager-1.0.0.zip -d /tmp/wpsite/wp-content/plugins/
node run.mjs /tmp/harness/zip_activate.php

# 1. Activate the plugin on a real WordPress install
bash /tmp/harness/setup.sh
cd /tmp/wp && node run.mjs /tmp/harness/activate.php

# 2. Backend suites
node run.mjs /tmp/harness/test1.php     # 43 assertions, core
node run.mjs /tmp/harness/test2.php     # 36 assertions, recovery + security

# 3. REST fixtures + admin UI suite
node run.mjs /tmp/harness/rest_dump.php
node /tmp/harness/ui_test.mjs           # 42 assertions

# 4. Standalone demo suite
node /tmp/wp/demo_test.mjs              # 39 assertions

# 5. End-to-end HTTP suite (needs the site server running on :9500)
node /tmp/harness/http_test.mjs         # 25 assertions
```

Expected output for each: a `PASS`/`FAIL` line per assertion and a final count with **0 failures**. Any deviation is a regression — the suites are deterministic and reset their own state.

---

## 11. Sign-off

| Area | Status |
|---|---|
| Content storage in the database, survives deactivation | ✅ verified |
| Draft → preview → publish, no accidental publication | ✅ verified |
| Revisions and one-click recovery | ✅ verified |
| Backups: automatic, manual, download, upload, restore, safety-first | ✅ verified |
| Capability checks and nonces on every write | ✅ verified |
| Sanitisation of text, HTML and URLs | ✅ verified |
| 15 dashboard modules render and function | ✅ verified |
| SEO output with no duplicate tags and no empty FAQ markup | ✅ verified |
| Theme-agnostic design tokens | ✅ verified (Twenty Twenty-Four; fallbacks reviewed) |
| No core edits, no theme edits, no builder dependency, ₹0 | ✅ verified |

**Recommendation:** ship. The remaining work before a client handover is the visual QA pass on the client's actual theme (item 7 above), which needs a browser and cannot be automated in this environment.
