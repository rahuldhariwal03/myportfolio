# TrustUsBro Site Manager — Feature Guide

A complete, honest inventory of what the plugin does, how each feature works, and what it deliberately does **not** do. Written for the person who needs to evaluate or maintain the plugin.

Plugin version 1.0.0 · WordPress 6.0+ · PHP 7.4+ · GPLv2 or later · ₹0

---

## 1. The 15 dashboard modules

Everything lives under the admin menu **TrustUsBro** (`admin.php?page=tusb-*`). One shell, one navigation, one save bar.

| # | Module | Menu slug | What it edits | Storage |
|---|---|---|---|---|
| 1 | **Visual Homepage Editor** | `tusb-pages` | Page documents (`home`, `about`): ordered, hideable, duplicable sections with per-type fields | `tusb_content` post per document |
| 2 | **Header** | `tusb-header` | Logo, tagline, navigation repeater, header button, sticky toggle | `header` document |
| 3 | **Footer** | `tusb-footer` | Logo, description, social repeater, up to 3 link columns, contact, legal links, copyright with `{year}` | `footer` document |
| 4 | **Services** | `tusb-services` | Repeatable service cards (title, summary, icon, price note, link, visibility) | `services` collection |
| 5 | **Industries** | `tusb-industries` | Industry cards | `industries` collection |
| 6 | **Case Studies** | `tusb-case-studies` | Case study cards (client, result, quote, image, link) | `case_studies` collection |
| 7 | **Testimonials** | `tusb-testimonials` | Quote, author, role, company, avatar, rating, visibility | `testimonials` collection |
| 8 | **FAQ** | `tusb-faq` | Question/answer pairs, visibility, order | `faq` collection |
| 9 | **Contact Info** | `tusb-contact` | Address, phone, email, hours, map link, social, form recipient | `contact` record |
| 10 | **Media Library** | `tusb-media` | Alt text, usage map, replace-everywhere, upload | WordPress attachments |
| 11 | **Blog** | `tusb-blog` | Native posts: list, status, categories, per-post SEO fields | `wp_posts` (`post`) |
| 12 | **SEO** | `tusb-seo` | Site defaults + live audit of missing titles/descriptions/alt text | `seo` record + options |
| 13 | **Design Settings** | `tusb-design` | Optional token overrides: colours, fonts, radius, widths, spacing, placement toggles | `design` record |
| 14 | **Backup & Recovery** | `tusb-backups` | Create, list, download, upload, restore snapshots | JSON files + `tusb_backups` option |
| 15 | **Revision History** | `tusb-revisions` | Every saved version, restore-into-draft | Revision child posts |
| — | **Health & Help** | `tusb-health` | Compatibility checks, environment, self-test, plain-language answers | Read-only |

Plus **Overview** (`tusb-dashboard`): what needs attention, unpublished-changes summary, shortcuts, and the three-step editing model.

---

## 2. Draft → preview → publish

This is the core safety model, and it is enforced in the data layer, not just the UI.

```
                 save_draft                      publish
  editor  ───────────────────▶  revision (draft)  ─────────▶  revision (published)
     ▲                                │                            │
     │  discard_draft                 │ restore_revision           │ visitors read this
     └──────────── published ◀────────┘                            │
                                                                   ▼
                                                            before-publish backup
```

* **Draft** and **published** are two separate revisions of the same document. The database keeps both.
* Writing a draft **never** touches the published revision.
* Publishing copies the draft into a **new** revision, flips the `published_version` pointer, and first creates a `before-publish-<doc>` backup.
* Discarding repoints draft at published.
* Restoring a revision writes it into the **draft** — never straight to live.
* Visitors read only the published pointer, resolved through a memoised store.

Consequences a site owner feels: no white-screen half-published states, an always-available previous version, and a one-click undo for a bad publish.

### Preview

* **Preview link** on every document renders it through `templates/preview.php` with the theme's own head/footer, gated behind `tusb_manage_site` + nonce.
* **"See it on the website"** deep-links to the live section anchor.
* Draft previews for logged-in editors do not affect anonymous visitors.

---

## 3. Click-to-edit

* Every field is a real form control, labelled, keyboard reachable, with a help line where the format matters.
* Section titles act as disclosure buttons (`aria-expanded`), so the page stays scannable with 20+ sections.
* Text fields save on an input debounce into an in-memory working copy; nothing is written until **Save draft**.
* Images use the native Media Library modal (`wp.media`) — no custom uploader, no new attack surface.
* Accent styling: `*word*` inside a heading renders as an accent-coloured span, sanitised server-side to a single `<span class="tusb-accent">`.

---

## 4. Drag and drop — and a keyboard path for everything

* Sections and collection cards are reorderable by dragging the ⠿ handle.
* **Every drag action has a button equivalent**: ↑ / ↓ on each row.
* Drag is never the only way to do anything: reorder, hide, duplicate, delete and add all have buttons, all reachable by Tab, all announced in the accessible name ("Move *Hero* up").
* Drop targets highlight; the dragged row dims; Escape cancels the add-section modal.

---

## 5. Content storage — the database, always

| What | Where | Survives deactivate? | Survives delete? |
|---|---|---|---|
| Documents, sections, cards | `tusb_content` CPT (one post per document, JSON in post meta) | yes | yes |
| Revisions | child posts of the same CPT | yes | yes |
| Draft / published pointers | post meta `draft_version` / `published_version` | yes | yes |
| Settings, seed flags, backpointer | options (`tusb_settings`, `tusb_seeded`, `tusb_version`, …) | yes | yes |
| Backups | `wp-content/uploads/trustusbro-backups/*.json` | yes | yes |

Nothing a site owner writes is ever stored in a plugin file. Updating the plugin cannot lose content. Only an explicit `wp option update tusb_purge_on_uninstall 1` followed by deletion removes data — and that is documented as irreversible.

---

## 6. Design tokens — theme-agnostic by construction

No hard-coded brand design ships with the plugin. `TUSB_Design::css_vars()` emits CSS custom properties that resolve in this order:

1. A value the owner typed in **Design settings**.
2. A block-theme preset (`--wp--preset--color--primary`, `--wp--preset--color--foreground`, …).
3. A conventional theme custom property (`--color-accent`, `--text`, …).
4. A neutral fallback (`#ff6a00` accent, `#111` text, `#fff` surface, system font stack).

That means: on Twenty Twenty-Four it looks like Twenty Twenty-Four; on a client's classic theme it inherits their CSS variables; on a theme with neither it degrades to something clean rather than broken. `tusb_design_tokens` is filterable for developers.

Deliberately **not** done: no theme file is edited, no theme is switched, no CSS is written to disk, and no bundled Google Fonts (no third-party requests, no GDPR question).

---

## 7. SEO

Printed by the plugin when no other SEO plugin is active:

* `<title>` with a configurable pattern (`%title% — %site%`), per-post override,
* `meta description` (length-aware, from the document or the post excerpt),
* `rel="canonical"` (never rewrites existing URLs),
* Open Graph (`og:title/description/image/url/type/site_name`, `article:*` on posts),
* Twitter card,
* `robots` directives incl. per-post `noindex` and staging-wide noindex,
* schema.org JSON-LD `@graph`: **Organization, WebSite, WebPage, Article, FAQPage**,
* sitemap reference in `robots.txt`.

**Duplicate-tag protection:** `TUSB_SEO::prints_meta()` detects Yoast SEO, Rank Math, All in One SEO, SEOPress and Site Kit, and yields to them. Health shows which plugin was detected.

**FAQPage correctness:** the graph includes FAQPage only when at least one visible question *and* answer exists, harvested from both the FAQ collection and any FAQ section on the page being viewed, de-duplicated, capped at 10. No empty or invisible markup — empty FAQ data is a search-engine penalty, not a feature.

---

## 8. Media

* Alt-text editor per attachment, saved with `wp_update_post`.
* **Usage map:** scans documents (draft and published) for an attachment ID, so you know what breaks before replacing.
* **Replace everywhere:** swaps the ID in every document, keeps the old file, never deletes.
* Uploads go through `wp_handle_upload` — WordPress's own type, size and permission checks.
* Missing alt text is surfaced in the SEO audit rather than silently ignored.

---

## 9. Blog

Blog stays native on purpose:

* Posts, categories, tags, comments, feeds, sitemaps and permalinks keep working exactly as WordPress intends.
* The dashboard shows a table with status, categories and whether SEO title/description exist.
* `editor-seo.js` adds the Site Manager SEO fields to the block editor sidebar and the classic editor, using `registerPlugin`-free vanilla DOM injection so it works with or without a build.
* Editing a post never touches Site Manager documents and vice versa.

---

## 10. Contact form

* Rendered inside the contact section, with three settings on that section: **show form**, **form heading**, **form shortcode**. Paste another form plugin's shortcode and that form replaces the built-in one entirely.
* Built-in fallback: a plain `<form>` posting to `admin-post.php` with `action=tusb_contact`.
* Server-side handler registered once on `admin_post_{nopriv_,}tusb_contact` — one handler, one nonce action (`tusb_contact`).
* Validation: name required, `is_email()` on the address, message required; everything passed through `sanitize_text_field` / `sanitize_email` / `sanitize_textarea_field`.
* Spam: a honeypot field (`tusb_website`) that is hidden from people and answered by bots, plus a one-per-minute-per-IP transient throttle.
* Sends with `wp_mail()` to the **notification email** in Contact details (falling back to the admin email), with `Reply-To` set to the visitor; the visitor is redirected back to a sanitised `tusb_redirect` URL with `?tusb_sent=ok|error` and sees a plain status line.
* Provides `tusb_contact_submitted` for integrations (free CRM plugins, Sheets bridges).
* Does **not** store submissions in the database (no PII retention by default) — a deliberate privacy choice; hook `tusb_contact_submitted` if you need storage.
* No JavaScript is required for the form to work — it degrades to a normal POST.

---

## 11. Backups and recovery

| Trigger | Reason key | Notes |
|---|---|---|
| Activation | `activation` | First state, so setup can be undone |
| Before every publish | `before-publish` | The undo button for a bad publish |
| Daily | `scheduled` | `tusb_daily_backup` WP-Cron |
| Manual | `manual` | Backup & Recovery → Create |
| Before a restore | `before-restore` | Makes restore itself reversible |

* Format: pretty-printed JSON — documents, settings, media references, plugin version, user, checksum.
* Download/upload, so content is portable between installations.
* Filename is non-guessable; the directory has `.htaccess` denial + `index.php`; downloads require capability **and** nonce.
* Restore validates the payload, takes a `before-restore` backup, then imports the snapshot's documents into the **draft** and applies its settings. Nothing is published by the restore; the owner publishes after reviewing. The safety row makes the restore itself undoable.
* `backups/upload` takes a `before-import` safety backup and skips document keys the schema does not know, instead of creating mystery content.
* Restoring a **revision** follows the same rule: it loads one version into the draft and never publishes.

Full operational detail: `docs/BACKUP-RECOVERY.md`.

---

## 12. Revision history

* Every save creates a revision post with author, timestamp, action label and the full document JSON.
* Listing shows the version number, time, author, action label and size; the full payload is available for comparison via `GET /tusb/v1/docs/<doc>/revisions`.
* Restore writes the revision into the **draft**, and publishing after a restore behaves like any other publish (preceded by a `before-publish` backup).
* Retention: the last 30 revisions per document are kept (`TUSB_Content_Store::prune_revisions( $doc_key, $keep )`); pruning only ever removes revision children, never documents. Call it with a larger `$keep` from your own code if you need a longer history.

---

## 13. Security model

| Threat | Control |
|---|---|
| Unauthorised editing | `tusb_manage_site` capability, checked on the admin page, every REST route and every write |
| Unauthorised restore | separate `tusb_restore_site` capability |
| CSRF | `wp_rest` nonce on every mutating request; form nonce on the contact form; `admin_post` nonce on preferences |
| XSS in stored content | schema-driven sanitiser: `wp_kses` allowlist, tags stripped, attributes whitelisted, `javascript:`/`data:`/`vbscript:` rejected, URLs restricted to http/https/mailto/tel/relative |
| XSS in URLs / images | `esc_url_raw` on save, `esc_url` on output |
| SQL injection | no hand-written SQL; WordPress APIs only |
| Path traversal in backups | `basename()` + whitelist regex on IDs; `path_for()` rejects anything with `..` or separators (tested) |
| Enum tampering | select values validated against the declared option list, invalid → default (tested) |
| Privilege escalation | role caps granted only on activation to administrator/editor; `map_meta_cap` never recurses (a recursion bug was found and fixed during testing) |
| Information disclosure | REST route errors return 403/404 without leaking internals; backups never served from the plugin URL |
| Fatals taking the site down | every module boots defensively inside try/catch; a fatal in one module is reported in Health instead of white-screening |

Verified by automated tests — see `docs/TESTING.md`.

---

## 14. Compatibility

* **WordPress 6.0 – 6.5.5** tested; `Requires at least: 6.0`.
* **PHP 7.4 – 8.3** tested (8.3.36 in the harness). No deprecated dynamic properties, no `create_function`, no short-array-in-attribute tricks.
* **Block themes** (Twenty Twenty-Four), **classic themes** (Twenty Twenty-One), child themes.
* **Multisite:** network activation supported; content and backups are per-site.
* **Translations:** all strings in one text domain, `languages/` ready, `wp_set_script_translations` for JS.
* **RTL:** the admin CSS uses logical properties where it matters; the site CSS uses no directional hard-coding beyond `margin-inline`.
* **Page builders:** no dependency, no conflict; Elementor/Divi/Bricks can coexist because Site Manager renders its own markup on its own conditions.
* **Caching:** publishes bump a content version used in cache keys; documented purge guidance for page caches.

Details and the tested matrix: `docs/COMPATIBILITY.md`.

---

## 15. Performance

* Documents are resolved once per request and memoised; a typical page does 1–2 post-meta reads.
* The dashboard loads **one** bootstrap REST call plus one document call; no per-field requests.
* Assets are enqueued only on `tusb-*` admin screens and on the front end only when a Site Manager block/shortcode/section actually renders.
* `admin.js` and `site.js` are dependency-free, unminified, and total ~110 KB combined — no jQuery, no framework, no build step.
* Backups are written with `LOCK_EX` and streamed for download; no full-site serialisation.

---

## 16. What the plugin deliberately does not do

Being explicit here has saved more projects than any feature list:

1. **No page builder.** It does not let you build arbitrary layouts pixel by pixel. It edits a defined, safe section set. Need full freedom? Use Gutenberg on pages — it is right there.
2. **No theme switching or theme editing.** Your approved design stays yours.
3. **No data migration from another builder.** Importing Elementor/Divi/Wix content requires the source export and a mapping decision; that is a project, not a button, and it is out of scope for v1.0.0.
4. **No e-commerce.** WooCommerce is detected, never modified.
5. **No member accounts, no LMS, no bookings.**
6. **No external SaaS, no telemetry, no licence server.** Everything is on your server.
7. **No database-wide backup.** Backups cover Site Manager content and settings. For whole-site backups use your host or UpdraftPlus — this plugin says so on the Backup screen rather than pretending otherwise.
8. **No multi-editor real-time collaboration.** Last save wins, and the loser is in Revision history.
9. **No contact-form submission storage** by default (privacy), and no anti-spam service beyond a honeypot and nonce.

---

## 17. Extensibility (for developers)

```php
// Add a document type, a section type, or an extra field: filter the schema.
add_filter( 'tusb_schema', function ( array $schema ) { return $schema; } );

// Add or change the inline CSS variables (per-client accent, extra tokens).
add_filter( 'tusb_inline_css', function ( $css, array $vars ) {
    return $css . 'body{--tusb-color-accent:#0057ff}';
}, 10, 2 );

// Widen or narrow the HTML allowlist used when saving rich text.
add_filter( 'tusb_kses_allowed', function ( array $allowed ) { return $allowed; } );

// React to a draft save / a publish (cache purge, CDN, notification).
add_action( 'tusb_draft_saved', function ( $doc_key, $revision_id, $content ) { … }, 10, 3 );
add_action( 'tusb_published', function ( $doc_key, $publish_id ) { … }, 10, 2 );

// Store contact submissions yourself.
add_action( 'tusb_contact_submitted', function ( $sent, $fields ) { … }, 10, 2 );
```

REST surface (namespace `tusb/v1`):
`bootstrap`, `health`, `docs/<doc>`, `docs/<doc>/draft`, `docs/<doc>/publish`, `docs/<doc>/discard`, `docs/<doc>/revisions`, `docs/<doc>/restore`, `media`, `media/update`, `media/replace`, `backups`, `backups/<id>`, `backups/<id>/restore`, `backups/<id>/download`, `backups/download-current`, `backups/upload`, `blog`, `blog/post`, `blog/category`, `seo`, `nav-menus`, `demo` (load starter content).

---

## 18. Deliverables map

| Deliverable | Where |
|---|---|
| Installable plugin ZIP | `plugin/dist/trustusbro-site-manager-1.0.0.zip` |
| Installation instructions | `docs/INSTALLATION.md` |
| User docs | `docs/USER-GUIDE.md` |
| Feature guide | `docs/FEATURE-GUIDE.md` (this file) |
| Testing report | `docs/TESTING.md` |
| Backup & recovery instructions | `docs/BACKUP-RECOVERY.md` |
| Standalone HTML preview | `preview/dashboard.html` + `preview/site-preview.html` |
| Compatibility report | `docs/COMPATIBILITY.md` |
