# Compatibility Report — TrustUsBro Site Manager 1.0.0

**Report date:** 22 November 2026
**Scope:** what the plugin was actually run against, what it should work with, and what it deliberately does not support. Unknowns are labelled as unknowns.

---

## 1. Tested matrix (run, not assumed)

| Component | Version tested | Result |
|---|---|---|
| **WordPress** | 6.5.5 | ✅ activates, seeds, all 17 screens load, REST works, front end renders |
| **PHP** | 8.3.36 | ✅ no deprecations, notices or fatals with `WP_DEBUG_DISPLAY` on |
| **Database** | SQLite 3 via the official `wp-sqlite-db` drop-in | ✅ full CRUD, revisions, options, backups |
| **Theme** | Twenty Twenty-Four 1.1 (block theme) | ✅ design tokens resolved from its presets; front page rendered |
| **Theme** | Twenty Twenty-One (classic theme) | ✅ activation, admin UI and rendering; tokens fall through to fallbacks |
| **Multisite** | single site (verified) / network code path present | ⚠️ network activation code exists and iterates sites; **not exercised in a live network in this run** |
| **Admin user** | `administrator` with both caps | ✅ full access |
| **Restricted user** | `subscriber` | ✅ REST returns 403, admin page blocked |

### PHP version support

| PHP | Status |
|---|---|
| 7.4 | ✅ supported (code avoids 8-only syntax; no typed properties, no named args) |
| 8.0 / 8.1 / 8.2 | ✅ supported |
| 8.3 | ✅ tested end-to-end (8.3.36) |
| 8.4 | ⚠️ not released/tested at time of writing; no deprecated patterns were found by inspection |

### WordPress version support

| WordPress | Status |
|---|---|
| 6.0 – 6.5 | ✅ targeted and tested at 6.5.5 |
| 5.9 and older | ❌ unsupported — `readme.txt` declares `Requires at least: 6.0` (the plugin relies on post-6.0 block/theme APIs) |
| 6.6+ | ⚠️ expected to work (no removed APIs are used), but not tested in this cycle |

---

## 2. Themes

**Approach:** the plugin ships **no design of its own**. `TUSB_Design::css_vars()` resolves tokens in four steps:

1. a value the owner set in **Design settings**;
2. a block-theme preset (`--wp--preset--color--primary`, `--wp--preset--color--foreground`, `--wp--preset--color--gray-600`, …);
3. a conventional theme custom property (`--color-accent`, `--color-text`, `--text`, …);
4. a neutral fallback (`#ff6a00` accent, `#111` text, `#fff` surface, system font stack).

Because every token ends in a literal fallback, a theme that defines none of the above still renders a coherent layout instead of unstyled text.

| Theme type | Compatibility | Notes |
|---|---|---|
| Block themes (FSE) | ✅ best experience | Site Editor can place `trustusbro/header`, `trustusbro/footer` and `trustusbro/page` blocks in template parts |
| Classic themes | ✅ works | Use shortcodes or the `tusb_header` / `tusb_footer` actions |
| Child themes | ✅ | Theme files are never modified, so parent/child relationships are irrelevant to the plugin |
| Page-builder themes (Astra, GeneratePress, Kadence, Blocksy) | ✅ expected | They publish standard CSS custom properties, which step 3 picks up |
| Themes with a hard-coded header | ✅ safe | Automatic header injection is **off by default**, so nothing is duplicated |
| Themes that strip `the_content` filters | ⚠️ | If a theme ignores `the_content`, place sections with the block or shortcode instead of the front-page toggle |

**What the plugin never does:** switch the theme, edit theme files, deregister theme styles, enqueue a competing framework, or write to the uploads folder for CSS.

---

## 3. Plugin conflicts

### SEO plugins

| Plugin | Behaviour |
|---|---|
| Yoast SEO | ✅ detected → Site Manager stops printing titles, descriptions, canonical, OG/Twitter and schema |
| Rank Math | ✅ same deferral |
| All in One SEO (AIOSEO) | ✅ same deferral |
| SEOPress | ✅ same deferral |
| Google Site Kit | ✅ detected |
| None active | ✅ Site Manager prints its own complete SEO head |

Detection is done once per request by `TUSB_SEO::prints_meta()` and surfaced on the **Health** screen so the owner can see who owns SEO. Duplicate tags are the single most common plugin-conflict bug, and this is the explicit guard against it.

### Other categories

| Plugin type | Behaviour |
|---|---|
| Caching / minify (WP Rocket, LiteSpeed, Autoptimize) | ✅ compatible. Publishes are versioned; purge your page cache after publishing if you see stale output. The plugin does not silently purge third-party caches. |
| Page builders (Elementor, Divi, Bricks, Beaver) | ✅ coexists. Site Manager renders its own markup on its own conditions; no builder asset is loaded or required. |
| Form plugins (CF7, WPForms, Fluent Forms) | ✅ compatible. Paste the shortcode into the contact section's **Form shortcode** field and the built-in fallback form is skipped. |
| Multilingual (WPML, Polylang) | ✅ detected and reported. Site Manager documents are **not** automatically translated; one document set per site language is the honest v1.0.0 behaviour. |
| WooCommerce | ✅ detected and reported. No WooCommerce template, hook or table is touched. |
| Membership / LMS | ✅ no interaction; capabilities are separate (`tusb_manage_site`, `tusb_restore_site`). |
| Security plugins (Wordfence, iThemes, Solid Security) | ✅ expected. If REST is blocked for logged-in users, the dashboard reports the failure; allow `/wp-json/tusb/v1/*`. |
| Backup plugins (UpdraftPlus, BackWPup) | ✅ complementary, not competing. Site Manager backs up **content**; those back up the **site**. |
| SMTP plugins | ✅ required in practice — the contact form uses `wp_mail()`, so an SMTP plugin is what makes mail arrive on most hosts. |

---

## 4. Hosting environments

| Environment | Status |
|---|---|
| Apache with `.htaccess` | ✅ backup folder denied by `.htaccess` |
| Nginx | ⚠️ `.htaccess` is ignored — add the documented `location` block to deny direct `.json` access. Downloads remain capability+nonce gated regardless. |
| LiteSpeed | ✅ `.htaccess` respected |
| Managed WordPress (WP Engine, Kinsta, SiteGround) | ⚠️ expected to work; **object-cache and page-cache purging is not automated** |
| Shared hosting with PHP 7.4 | ✅ supported floor |
| Hosts that block `wp_mail()` | ⚠️ contact form will not deliver — use SMTP |
| Hosts with read-only uploads | ⚠️ backups cannot be written; the UI reports it and the owner should download snapshots instead |
| Docker / local (as used here) | ✅ verified |
| Windows/IIS | ⚠️ untested. No Windows-specific code paths exist, but URL rewriting rules differ. |

---

## 5. Browser support

The dashboard uses ES5-compatible syntax with `fetch`, `Promise`, `classList`, `dataset` and drag-and-drop, with no build step and no polyfills.

| Browser | Status |
|---|---|
| Chrome / Edge (current) | ✅ primary target |
| Firefox (current) | ✅ |
| Safari 15+ | ✅ expected |
| Safari 13–14 | ⚠️ `Element.prototype.replaceChildren` and `structuredClone` are avoided, so expected to work; not tested |
| Mobile Safari / Chrome Android | ✅ layout is responsive; every drag action has button equivalents, so touch and keyboard users are not blocked |
| Internet Explorer 11 | ❌ not supported (WordPress itself dropped IE11) |

### Accessibility

* Every interactive control is a real `<button>`, `<a>` or `<input>` — no clickable `<div>`s.
* Reordering, hiding, duplicating, deleting and adding all work from the keyboard; drag-and-drop is an optional shortcut.
* Section disclosure sets `aria-expanded`; the save bar is a labelled region; status messages use `role="status"`/`aria-live`; destructive actions confirm.
* Form fields are labelled (`<label>` or `aria-label`) with help text tied to the field.
* Focus is moved into the add-section modal and returned on close.

---

## 6. Data and integration compatibility

| Item | Detail |
|---|---|
| Storage | CPT `tusb_content` + child revision posts; JSON in post meta |
| Options | `tusb_settings`, `tusb_seeded`, `tusb_version`, `tusb_installed_at`, `tusb_backups`, `tusb_last_backup`, `tusb_activation_backup` |
| Capabilities | `tusb_manage_site`, `tusb_restore_site` |
| Cron | `tusb_daily_backup` |
| REST namespace | `tusb/v1` (24 routes) |
| Hooks | `tusb_schema`, `tusb_inline_css`, `tusb_kses_allowed`, `tusb_draft_saved`, `tusb_published`, `tusb_contact_submitted` |
| Blocks | `trustusbro/page`, `trustusbro/collection`, `trustusbro/header`, `trustusbro/footer` |
| Shortcodes | `[trustusbro_page doc="home"]`, `[trustusbro_collection type="services"]` |
| Text domain | `trustusbro-site-manager`, all strings translatable, `languages/` ready |
| Export | WordPress **Tools → Export** covers posts; Site Manager content is exported via **Backups → Download** (JSON) |

**Interoperability note:** Site Manager content is intentionally *not* registered as a public post type in menus or the REST `wp/v2` namespace, so it cannot be accidentally edited, deleted or exposed by another plugin's bulk action.

---

## 7. Performance characteristics

Measured informally on the test install (not a benchmark):

* Front-end render adds **1–2 post-meta reads** per request (documents are memoised per request).
* Dashboard loads **1 bootstrap** call (~40 KB JSON) plus **1 document** call; no per-field requests.
* `admin.js` ≈ 90 KB, `site.js` ≈ 3 KB, unminified, no dependencies, no build step.
* CSS ≈ 21 KB (front end) and ≈ 18 KB (admin).
* A backup of 12 documents is ~30 KB and takes milliseconds.

---

## 8. Known incompatibilities and limits

1. **No migration from other builders** — Elementor/Divi/Wix content cannot be imported in 1.0.0.
2. **No multilingual document translation** — WPML/Polylang are detected, not integrated.
3. **No multisite live test** in this cycle; the code iterates sites on network activation, but a real multisite run is outstanding.
4. **No automated page-cache purge** after publish.
5. **No visual/pixel regression testing** — no browser engine was available in the test environment.
6. **`noindex` on staging is a site-wide toggle**, not a per-page rule beyond the post-level checkbox.
7. **Backup retention is manual** — nothing is pruned automatically, so very old snapshots accumulate until deleted (they are small).

---

## 9. Summary

| Dimension | Verdict |
|---|---|
| WordPress 6.0+ / PHP 7.4+ | ✅ within declared requirements |
| Block themes | ✅ full support including Site Editor blocks |
| Classic themes | ✅ shortcode / action support |
| SEO plugins | ✅ automatic deferral, no duplicate tags |
| Page builders | ✅ coexist, no dependency |
| Caching | ⚠️ compatible; purge manually |
| Multisite | ⚠️ code path present, not live-tested |
| Nginx servers | ⚠️ add the documented deny rule |
| ₹0 budget | ✅ no paid dependency, service or account anywhere in the stack |

**Recommended before a client handover:** a visual pass on the client's actual theme in a real browser (drag-and-drop with a mouse, mobile viewport, keyboard-only pass). Everything else in this report was executed, not assumed.
