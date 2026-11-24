=== TrustUsBro Site Manager ===
Contributors: trustusbro
Tags: site manager, visual editor, page builder, seo, backups, revisions
Requires at least: 6.0
Tested up to: 6.5
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Edit your homepage, header, footer and site content from one beginner-friendly dashboard — with drafts, preview, revisions and backups. No page builder required.

== Description ==

TrustUsBro Site Manager gives a non-technical site owner one clear place to edit a website:
**TrustUsBro → Overview** in the WordPress admin.

Every screen works the same way:

1. Change something.
2. Press **Save draft**. Visitors still see the current site.
3. Press **Publish changes**. A backup and a revision are created first.

That is the whole model. There is no page builder to learn, no shortcode syntax to memorise, and no way to break the live site by accident: a draft is never visible to visitors, and every publish is reversible.

**What you can edit without a developer**

* **Homepage & pages** — drag sections (hero, services, industries, philosophy, process, case studies, testimonials, FAQ, call to action, contact, free text) into any order, hide them, duplicate them, or add new ones. Click a section title to open its fields.
* **Header & footer** — logo text or image, navigation links, buttons, four footer columns, social links, copyright line.
* **Collections** — services, industries, case studies, testimonials and FAQ entries: add, reorder, hide, duplicate and delete cards.
* **Contact details** — address, phone, email, hours, map link, social profiles, and a working contact form.
* **Media** — alt text editing, usage tracking and "replace everywhere" without deleting files.
* **Blog** — native WordPress posts and categories, kept in the familiar editor.
* **SEO** — titles, descriptions, Open Graph, canonical URLs, schema.org JSON-LD and a sitemap, with automatic detection of other SEO plugins so no tag is ever printed twice.
* **Design settings** — optional overrides for colours, fonts, radius and spacing. Everything you leave empty inherits your active theme.
* **Backups & recovery** — automatic backup before every publish, plus daily and on-demand snapshots. One-click restore, and restore always takes a safety backup first.
* **Revision history** — every save is a version you can compare against and restore into the draft.

**Built to be safe on a real site**

* Content is stored in the WordPress database (custom post type + revisions), **never** only inside plugin files. Deactivating or deleting the plugin does not touch your content.
* The plugin never edits WordPress core, never edits your theme, and never switches your theme.
* Activation and deactivation are non-destructive. Nothing is deleted on deactivation.
* Every write goes through a capability check (`tusb_manage_site`, `tusb_restore_site`), a nonce, and a schema-driven sanitiser that strips scripts, blocks `javascript:` URLs and rejects invalid select values.
* Draft and published copies are separate, so a mistake cannot reach visitors until you publish — and a publish is always preceded by a backup.
* Design tokens read from the active theme first, so the plugin looks like *your* site, not a bundled design.

**Free and open source**

No paid tier, no account, no external service, no telemetry, no upsell. Everything runs inside your own WordPress installation. GPLv2 or later.

== Installation ==

1. In WordPress go to **Plugins → Add New → Upload Plugin**.
2. Choose `trustusbro-site-manager-1.0.0.zip` and press **Install Now**.
3. Press **Activate**.
4. Open **TrustUsBro → Overview**. A welcome panel explains the three-step editing model.
5. Optional: open **TrustUsBro → Design settings** and tick *Use Site Manager sections for the front page* if you want the plugin to own the front-page layout. Leave it off if your theme already renders the front page.

There is no build step, no `composer install`, no `npm install`, and no external account to create. The ZIP is ready to upload.

== Frequently Asked Questions ==

= Will I lose content if I deactivate the plugin? =

No. All content lives in the `tusb_content` custom post type and its revisions, inside your WordPress database. Deactivating the plugin leaves every post, revision, backup file and setting in place.

= Does it work with my theme? =

It is theme-agnostic. Design tokens are read from the active theme (block-theme presets, CSS custom properties, filters), and everything unresolved falls back to a neutral value. It does not switch or modify your theme. Tested with block themes (Twenty Twenty-Four), classic themes and child themes.

= Do I need Elementor or another page builder? =

No, and none is required or bundled. The dashboard is a custom React-free admin application built on the WordPress REST API.

= Where do I place the editable sections? =

Any of these, whichever suits your theme:

* **TrustUsBro → Design settings →** *Use Site Manager sections for the front page* (automatic).
* The **TrustUsBro page sections** block (`trustusbro/page`) or the **TrustUsBro header/footer** blocks, placed in the Site Editor.
* The shortcodes `[trustusbro_page doc="home"]` and `[trustusbro_collection type="services"]`.

The header and footer are only injected automatically when you explicitly turn on *Render the header and footer from Site Manager*, so an approved theme header is never duplicated.

= Does it conflict with Yoast, Rank Math or All in One SEO? =

No. Site Manager detects them and stops printing its own titles, descriptions, canonical tags and schema, so you never get duplicate tags. It also detects WooCommerce, WPML/Polylang, caching plugins and multisite, and reports the result under **Health & help**.

= Can two people edit at once? =

Yes, but a draft is a single shared document. If two editors save the draft, the second save wins and the first is still available in **Revision history**. Editing the same document simultaneously is not recommended.

= Is anything sent to an external server? =

No. No telemetry, no remote API calls, no licence check. The only outbound requests are the ones WordPress itself makes.

= Can I move content to another site? =

Yes. **Backups → Download** produces a JSON snapshot, including all documents and settings, that you can upload on another installation with **Backups → Upload & restore**.

== Screenshots ==

1. Overview — what needs attention and shortcuts into every screen.
2. Homepage & pages — drag-and-drop sections with an expandable field editor.
3. Header — logo, navigation and buttons.
4. Services — repeatable cards with reorder, hide and duplicate.
5. SEO — site-wide defaults and a live audit of missing metadata.
6. Backups — automatic and manual snapshots with one-click restore.
7. Health & help — compatibility checks and plain-language answers.

== Changelog ==

= 1.0.0 =
* First release: 15 dashboard modules, draft/preview/publish workflow, revisions, backups, media tools, SEO output, capability and nonce hardening, compatibility detection.

== Upgrade Notice ==

= 1.0.0 =
Initial release. Back up before installing on a live site — as you should with any plugin.
