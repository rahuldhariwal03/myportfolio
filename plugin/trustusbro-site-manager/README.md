# TrustUsBro Site Manager

A beginner-friendly WordPress plugin that puts the whole website under one dashboard: homepage sections, header, footer, services, industries, case studies, testimonials, FAQ, contact details, media, blog, SEO, design settings, backups and revision history — with a **draft → preview → publish** workflow and one-click recovery.

**Version 1.0.0** · Requires WordPress 6.0+ · PHP 7.4+ · GPLv2 or later · ₹0 (no paid tier, no account, no external service)

---

## Install

1. **Plugins → Add New → Upload Plugin** → choose `plugin/dist/trustusbro-site-manager-1.0.0.zip` → **Install Now** → **Activate**.
2. Open **TrustUsBro → Overview**.
3. Choose where the editable sections appear (see below), press **Save draft**, then **Publish changes**.

Full walkthrough, manual/FTP install, WP-CLI install and a 60-second verification checklist: **[docs/INSTALLATION.md](docs/INSTALLATION.md)**.

### Where do the sections appear?

Any one of these, whichever suits the theme:

| Method | How |
|---|---|
| **Front page** | Settings → Reading → static page, then **Design settings → Use Site Manager sections for the front page** |
| **Blocks** | Insert *TrustUsBro page sections* / *header* / *footer* in the Site Editor |
| **Shortcodes** | `[trustusbro_page doc="home"]`, `[trustusbro_collection type="services"]` |
| **Content only** | Use the collection shortcodes inside your existing layout and leave the front-page toggle off |

The plugin never switches or edits your theme. Automatic header/footer injection is **off by default** so an existing header is never duplicated.

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Install (ZIP, FTP, WP-CLI, multisite), first run, verification, troubleshooting, uninstall behaviour |
| [docs/USER-GUIDE.md](docs/USER-GUIDE.md) | Plain-language guide for the site owner: the three-step model, every screen, step-by-step common tasks |
| [docs/FEATURE-GUIDE.md](docs/FEATURE-GUIDE.md) | Complete feature inventory, storage model, security model, performance, extensibility, and what the plugin deliberately does not do |
| [docs/BACKUP-RECOVERY.md](docs/BACKUP-RECOVERY.md) | Backup triggers, where files live, restore procedure, recovery playbooks, Nginx rule, long-term policy |
| [docs/TESTING.md](docs/TESTING.md) | Testing report: 192 assertions across 6 suites, defects found and fixed, how to reproduce |
| [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) | Tested matrix, themes, plugin conflicts, hosting, browsers, accessibility, known limits |
| [readme.txt](readme.txt) | WordPress.org-format readme (description, FAQ, changelog) |

Interactive preview with no WordPress required: open `preview/dashboard.html` (dashboard demo) or `preview/site-preview.html` (rendered front end).

---

## The three-step model

```
change something  →  Save draft  →  Publish changes
                      (private)      (live + automatic backup)
```

* A draft is never visible to visitors.
* Publishing copies the draft into a new revision and first writes a `before-publish` backup.
* Every save is a restorable revision.
* Restoring a backup or a revision lands in the **draft**, so recovery is reviewable before it goes live.

---

## What is inside

```
trustusbro-site-manager.php     plugin header, bootstrap, module loading
includes/class-schema.php       single source of truth for every editable field
includes/class-content-store.php  documents, revisions, draft/publish pointers
includes/class-sanitizer.php    schema-driven sanitisation and validation
includes/class-renderer.php     front-end rendering, blocks, shortcodes, preview
includes/class-rest.php         24 REST routes under tusb/v1
includes/class-admin.php        admin menu, assets, localisation
includes/class-seo.php          titles, meta, canonical, OG/Twitter, JSON-LD, sitemap
includes/class-backup.php       snapshot, restore, download, upload, retention
includes/class-media.php        alt text, usage map, replace-everywhere
includes/class-blog.php         native posts integration
includes/class-design.php       theme-derived design tokens
includes/class-forms.php        contact-form handler
includes/class-compat.php       environment and conflict detection
includes/class-activator.php    non-destructive activation, safe deactivation
assets/{css,js}                 dependency-free admin and front-end assets (no build step)
templates/preview.php           draft preview through the theme's own head/footer
uninstall.php                   opt-in data removal (no-op by default)
```

No `composer install`, no `npm install`, no build step: the ZIP is ready to upload as-is.

---

## Build the ZIP

```bash
bash plugin/build.sh   # writes plugin/dist/trustusbro-site-manager-1.0.0.zip
```

The script zips `plugin/trustusbro-site-manager/` into a single top-level folder, excluding editor and OS noise, and prints the file count and size.

---

## Guarantees

* **Content lives in the database** (CPT `tusb_content` + revisions). Deactivating or deleting the plugin does not remove it. Data removal requires an explicit `wp option update tusb_purge_on_uninstall 1` before deletion.
* **Never edits core, never edits the theme, never switches the theme.**
* **Every write** requires `tusb_manage_site` (or `tusb_restore_site` for restores) **and** a valid nonce.
* **No external calls** — no fonts, no telemetry, no licence server.
* **No page builder required**, and none is bundled.

---

## License

GPLv2 or later — see <https://www.gnu.org/licenses/gpl-2.0.html>.
