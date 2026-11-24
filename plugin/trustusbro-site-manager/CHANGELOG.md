# Changelog

All notable changes to TrustUsBro Site Manager. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-11-22

First release. 15 dashboard modules, draft/preview/publish workflow, revisions, backups.

### Added

**Dashboard**
* One admin menu (`TrustUsBro`, slug `tusb-dashboard`) with 17 screens, a single navigable shell and a persistent save bar.
* Client-side application on the WordPress REST API (`tusb/v1`, 24 routes) — no build step, no framework, no jQuery.
* Overview screen: unpublished-changes summary, shortcuts, and the three-step editing model explained in plain language.

**Visual editing**
* Homepage and About documents with 11 section types (hero, services, industries, philosophy, process, case studies, testimonials, FAQ, call to action, contact, free text).
* Reorder by drag handle **or** ↑/↓ buttons; hide, duplicate, remove with undo, and add a section (added hidden).
* Click-to-edit fields with per-field help text, `aria-expanded` disclosure, keyboard paths for every action.
* Collections: Services, Industries, Case studies, Testimonials, FAQ — add, reorder, hide, duplicate, delete.
* Header (logo, navigation repeater, header button, sticky) and Footer (4 columns, social, legal links, contact, `{year}` copyright).
* Contact details with a working form (nonce, honeypot, per-IP throttle, `wp_mail()`), or paste another form plugin's shortcode.
* Media: alt text, usage map, replace-everywhere without deleting files.
* Blog: native posts, categories, status and per-post SEO fields (`editor-seo.js`).
* SEO: titles, descriptions, canonical, Open Graph, Twitter cards, robots, sitemap reference, and schema.org JSON-LD (Organization, WebSite, WebPage, Article, FAQPage).
* Design settings: optional token overrides resolved against the active theme's presets and custom properties.

**Content model**
* `tusb_content` custom post type: one document post per key, revision children, `draft_version`/`published_version` pointers.
* Draft and published are separate revisions — a draft is never visible to visitors.
* Publish copies draft → new revision, after writing a `before-publish` backup.
* Revision history with restore-into-draft (never a surprise publish).
* Backups: automatic (activation, before publish, daily cron, before restore/import) and manual; JSON snapshots in `wp-content/uploads/trustusbro-backups/`, downloadable, uploadable, restorable, never pruned silently.

**Rendering**
* Blocks `trustusbro/page`, `trustusbro/collection`, `trustusbro/header`, `trustusbro/footer`.
* Shortcodes `[trustusbro_page doc="home"]`, `[trustusbro_collection type="services"]`.
* Actions `tusb_header` / `tusb_footer`.
* Optional front-page takeover and optional automatic header/footer injection — both **off by default** so no theme is ever duplicated or overridden.
* Draft preview through the theme's own head and footer, capability and nonce gated.

**Safety**
* Capabilities `tusb_manage_site` and `tusb_restore_site`, nonces on every mutating request, schema-driven sanitisation (`tusb_kses_allowed`), URL scheme deny-list, enum validation, path-traversal protection on backup paths.
* Non-destructive activation (seeds only when empty, records a first backup) and deactivation (keeps all content).
* `uninstall.php` is a no-op unless `tusb_purge_on_uninstall` is explicitly set.
* Compatibility detection for SEO plugins (automatic deferral to avoid duplicate tags), caching, multilingual, WooCommerce and page builders; checks appear in Site Health and the Health screen.
* Health screen with self-test, environment report and plain-language answers.

**Docs and deliverables**
* `README.md`, `readme.txt`, and `docs/`: installation, user guide, feature guide, testing report, backup & recovery, compatibility report.
* Interactive standalone previews (`preview/dashboard.html`, `preview/site-preview.html`).
* `build.sh` producing `dist/trustusbro-site-manager-1.0.0.zip` (41 files).

### Fixed (during the 1.0.0 test cycle)

* Save bar never rendered on the Homepage and SEO screens (`docNeedsSaveBar()` ignored views without a `VIEW_TO_DOC` entry).
* Backup restore/import published immediately instead of landing in the draft, letting a restore overwrite the live site before review.
* `/backups/download-current` was unreachable (404) because the wildcard `/backups/(?P<id>…)` route was registered first.
* `TUSB_Sanitizer::url()` could leave a `javascript:` value stored instead of rejecting it.
* Automatic header/footer injection defaulted on, which duplicated a theme's own header; guards now prevent double rendering from any combination of hooks, blocks and injection.
* FAQPage structured data was missing when the FAQ lived in a page section rather than the FAQ collection, and could be emitted without questions.
* `links` (new post, permalinks, media) were not localised, leaving three dashboard buttons with `href="undefined"`.
* Capability `map_meta_cap()` recursed and exhausted memory; `register_blocks()` called an undefined method and caused a fatal on activation (both found and fixed earlier in the cycle).

### Known limitations

* No migration from Elementor/Divi/Wix content.
* Backups cover Site Manager content and settings, not the whole site (use a host backup or UpdraftPlus as well).
* Concurrent edits are last-save-wins, with the superseded save preserved in Revision history.
* Contact submissions are not stored in the database (privacy default); hook `tusb_contact_submitted` if you need storage.
* Multilingual sites are detected, not translated per language.
* Nginx requires the documented deny rule for the backup directory (`.htaccess` is Apache-only).
