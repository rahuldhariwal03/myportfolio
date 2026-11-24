# TrustUsBro Site Manager — Installation Guide

**Plugin version:** 1.0.0
**Requires:** WordPress 6.0 or newer · PHP 7.4 or newer · MySQL 5.6+ / MariaDB 10.1+ (or SQLite via the official drop-in)
**Cost:** ₹0. No paid tier, no account, no external service, no telemetry.
**Time to install:** about 3 minutes.

---

## 1. Before you start (2 minutes, do not skip)

1. **Take a backup of the site** — files *and* database. Use your host's backup button or a free plugin (UpdraftPlus, WPvC BackWPup). This is standard practice for any new plugin, and it is the only step the Site Manager itself cannot do for you on first install.
2. **Note your theme name** — *Appearance → Themes*. Site Manager never changes or edits your theme; it only reads its colours and fonts.
3. **Check your PHP version** — *Tools → Site Health → Info → Server*. You need 7.4 or newer.
4. **Have an Administrator login ready.** Site Manager grants access only to roles that can `manage_options` (Administrator) by default.

> **Never installed a plugin before?** You only need section 2. Sections 3–5 are for hosts that block uploads or for developers.

---

## 2. Install from the ZIP (the normal way)

1. Log in to `/wp-admin`.
2. Go to **Plugins → Add New**.
3. Press **Upload Plugin** at the top of the page.
4. Press **Choose File** and select `trustusbro-site-manager-1.0.0.zip` (in this repository it lives in `plugin/dist/`).
5. Press **Install Now**. Wait for "Plugin installed successfully."
6. Press **Activate Plugin**.

You will land back on the Plugins screen with a new notice: *"TrustUsBro Site Manager is ready. Open Site Manager."* Press it.

If your host shows a "Are you sure you want to do this?" screen after pressing Install Now, that is normal on some managed hosts — press **Continue**.

---

## 3. First run

When the plugin activates it:

* registers the `tusb_content` custom post type and its revision storage,
* seeds a **complete, editable starter document set** (homepage sections, about page, header, footer, contact details, SEO defaults, design settings) **once**,
* creates the capability `tusb_manage_site` for Administrators,
* schedules the daily backup cron event.

**It does not touch a single existing post, page, menu, media item, setting or theme file.**

Open **TrustUsBro → Overview**. You will see:

| Area | What it is for |
|---|---|
| **Homepage & pages** | Drag sections, click to edit their text, hide or duplicate them |
| **Services / Industries / Case studies / Testimonials / FAQ** | Repeatable cards used by the sections above |
| **Header / Footer** | Logo, navigation, buttons, footer columns, social links |
| **Contact details** | Address, phone, email, hours, map, form settings |
| **Blog** | Native WordPress posts and categories |
| **SEO** | Titles, descriptions, sitemap, structured data |
| **Media** | Alt text, usage, replace-everywhere |
| **Design settings** | Optional colour/font/spacing overrides |
| **Backups / Revision history** | Recovery |
| **Health & help** | Compatibility checks and plain-language answers |

### Decide where the sections appear

By default **nothing on your live site changes** after activation. You choose one of these, whichever fits your theme:

**Option A — let Site Manager own the front page (easiest).**
1. **Settings → Reading** → *Your homepage displays* → **A static page** → choose your Home page (any page; you do not need to edit its content).
2. **TrustUsBro → Design settings** → tick **Use Site Manager sections for the front page**.
3. Press **Save draft**, then **Publish changes**.
4. Visit your site. The Home page now renders the sections from Site Manager, inside your theme's normal template (header, footer, sidebar and styling are untouched).

**Option B — place the blocks yourself (most control).**
1. **Appearance → Editor** (Site Editor, block themes) or **Pages → your page → Edit**.
2. Insert the block **TrustUsBro page sections** and choose `home` (or `about`) in the block settings.
3. For the chrome, insert **TrustUsBro header** and **TrustUsBro footer** into your header/footer template parts.
4. Site Manager's automatic header/footer injection stays off, so nothing is duplicated.

**Option C — shortcodes (works with any classic theme).**

```
[trustusbro_page doc="home"]
[trustusbro_page doc="about"]
[trustusbro_collection type="services"]
[trustusbro_collection type="testimonials"]
```

**Option D — use Site Manager only for content, keep your design.**
Leave both front-page options off and use the collection shortcodes or blocks inside your existing layout. The header/footer screens still work as a reference for your text, and the SEO and backup modules are useful on their own.

### Want to change the header and footer too?

**TrustUsBro → Design settings → Render the header and footer from Site Manager** — off by default on purpose. Only turn it on after confirming your theme header is not needed (or after removing it), otherwise you will see two headers. The blocks and `tusb_header` / `tusb_footer` actions are the safe alternatives.

---

## 4. Manual install (FTP or file manager)

Use this when **Plugins → Add New → Upload Plugin** is disabled by the host.

1. Unzip `trustusbro-site-manager-1.0.0.zip` on your computer. You get one folder: `trustusbro-site-manager/`.
2. Connect with FTP/SFTP or your host's file manager.
3. Upload that folder to `wp-content/plugins/`, so the file `wp-content/plugins/trustusbro-site-manager/trustusbro-site-manager.php` exists.
4. Go to **Plugins** in wp-admin, find **TrustUsBro Site Manager**, press **Activate**.

Common gotcha: uploading the ZIP itself into `wp-content/plugins/` does nothing — WordPress needs the *unzipped folder*.

---

## 5. WP-CLI install

```bash
wp plugin install /path/to/trustusbro-site-manager-1.0.0.zip --activate
wp option get tusb_version          # confirms activation
wp tusb status 2>/dev/null || true  # optional: only if you added the CLI helper
```

To install on every site of a multisite network, use `wp plugin activate trustusbro-site-manager --network` and then open **TrustUsBro** on the site you want to edit. Content is per-site; backups are per-site.

---

## 6. Verify the install (60 seconds)

Do these five checks. Each one takes seconds and tells you the truth about the installation.

1. **Dashboard loads.** TrustUsBro → Overview shows cards and no PHP error.
2. **A save round-trips.** Homepage & pages → expand *Hero* → change one word → **Save draft** → the bar says *"Draft saved. Not live yet."*
3. **The live site is unchanged.** Open your site in a new tab. The draft word is *not* there. That is correct.
4. **Publishing is reversible.** Press **Publish changes**. Reload the site: the word is there. Go to **Backups** and confirm a backup named *before-publish* exists.
5. **Health is green.** **TrustUsBro → Health & help**. All rows should say OK. Anything else lists exactly what to fix.

Also check **Tools → Site Health → Info** if your host is unusual — Site Manager adds its own checks to *Site Health → Status*.

---

## 7. Uninstalling / removing

| Action | What happens to your content |
|---|---|
| **Deactivate** | Nothing is deleted. Content, revisions, settings and backup files stay. The front end no longer renders Site Manager sections (your theme's own content returns). |
| **Delete** (from the Plugins screen) | The plugin files are removed. Your content posts, revisions, options and backup files remain in the database/uploads. |
| **Delete + purge data** | Opt-in only. `uninstall.php` returns immediately unless you explicitly run `wp option update tusb_purge_on_uninstall 1` **before** deleting the plugin. Then it removes the `tusb_content` posts and revisions, the plugin options, its cron event, the granted capabilities and the backup files. Off by default, and there is no UI toggle — deleting content should always be a deliberate command-line decision. |

Backup files live in `wp-content/uploads/trustusbro-backups/` and are never removed automatically.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "The plugin could not be activated because it triggered a fatal error" | PHP older than 7.4, or a conflicting plugin | Check PHP version; deactivate other plugins one at a time |
| Dashboard is empty/blank | A security plugin blocking the REST API | Allow `/wp-json/tusb/v1/*` for logged-in users; the Health screen names the blocker |
| "You do not have permission to manage this website" | Your role lacks `tusb_manage_site` | Log in as Administrator, or grant the capability to your role |
| Sections do not show on the site | No placement method chosen | Section 3, Options A–D |
| Two headers appear | Automatic header injection turned on while the theme also prints one | Turn off *Render the header and footer from Site Manager* |
| Draft saves but the button stays disabled | The document had no changes | Edit a field first; the bar enables on the first change |
| Backups screen says "uploads not writable" | Host permissions | Make `wp-content/uploads` writable (755/775) or use **Download** and store the JSON elsewhere |
| Duplicate SEO tags | Another SEO plugin plus Site Manager output | Health screen shows which plugin; Site Manager normally defers automatically |
| Contact form mail never arrives | Host blocks `wp_mail()` | Install a free SMTP plugin (WP Mail SMTP) — Site Manager uses standard `wp_mail()` |

Still stuck? **TrustUsBro → Health & help** has a self-test that reports PHP, memory, upload limits, theme, active plugins and detected conflicts. Copy that block when asking for help.

---

## 9. Security notes

* Every state-changing request requires the `tusb_manage_site` capability (restore requires `tusb_restore_site`) **and** a valid REST nonce.
* All text passes a schema-driven sanitiser: tags are stripped, `javascript:` and `data:` URLs are rejected, select values are validated against a whitelist, URLs accept only `http`, `https`, `mailto`, `tel` and site-relative paths.
* Backup files are stored outside the plugin, protected by `.htaccess` (Apache), an `index.php` guard, and a non-guessable filename; downloads require a capability check and a nonce.
* No SQL is written by hand — the plugin uses WordPress APIs (`WP_Query`, `wp_insert_post`, `update_post_meta`, options API).
* The plugin never calls `eval`, never writes to core or theme directories, and never modifies `wp-config.php`.

Full detail: `docs/COMPATIBILITY.md` and `docs/TESTING.md`.
