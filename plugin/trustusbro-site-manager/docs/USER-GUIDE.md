# TrustUsBro Site Manager — User Guide

Written for the person who edits the website, not the person who built it.
No code, no jargon. If a term is unavoidable it is explained the first time it appears.

---

## The only three things you need to remember

1. **Change something.**
2. **Save draft.** Your visitors still see the old site. Nothing is public yet.
3. **Publish changes.** Now everyone sees it — and a backup was made first, so you can always go back.

You cannot break the live site by typing in a box. The live site only changes when you press **Publish changes**, and that button never runs without first taking a backup.

---

## Getting around

Every screen has the same layout:

```
┌─────────────┬──────────────────────────────────────────────┐
│  Site       │  Screen title           what it is for        │
│  Manager    ├──────────────────────────────────────────────┤
│  menu       │                                              │
│             │   the actual editing area                    │
│  Overview   │                                              │
│  Homepage   │                                              │
│  Services   │                                              │
│  ...        │                                              │
│             ├──────────────────────────────────────────────┤
│  View site  │  Draft saved. Not live yet.  [Save] [Publish] │
└─────────────┴──────────────────────────────────────────────┘
```

* The **bar at the bottom** is your status. It tells you, in plain words, whether your changes are live, saved as a draft, or not saved at all.
* A **● dot** next to a menu item means that area has unpublished changes. It is not an error — it is a reminder.
* If you try to leave a screen with unsaved changes, you are asked first. Your work is not thrown away silently.

### The bottom bar, explained

| It says | What it means | What to do |
|---|---|---|
| **All changes are live.** (green) | The published site matches what you see | Nothing |
| **Unsaved changes in this browser.** (orange) | You typed something that is not saved yet | Press **Save draft** |
| **Draft saved. Not live yet — press Publish changes.** (orange) | Your work is safe, visitors cannot see it | Review it, then press **Publish changes** |
| **Saving…** | A save is in flight | Wait a second |

**Save draft** is greyed out until you actually change something. That is normal, not a fault.

Keyboard shortcut: **Ctrl/Cmd + S** saves a draft.

---

## Editing the homepage

**TrustUsBro → Homepage & pages**

The page is a vertical list of **sections**: Hero, Services, Industries, Philosophy, Process, Case studies, Testimonials, FAQ, Call to action, Contact, Free text.

### Reordering

* **Drag** a section by its ⠿ handle to a new position, **or**
* use the **↑ / ↓** buttons (faster, and the only way on a touch screen or with a keyboard).
* Press **Save draft** afterwards. Reordering is a change like any other.

### Opening a section

Click the **section title**. The fields open underneath. Click again to close.

### The four buttons on every section

| Button | Meaning |
|---|---|
| **◉ / ○** | Visible / hidden. Hidden sections stay in the list and keep their text, but do not appear on the site. Great for seasonal content. |
| **↑ / ↓** | Move up or down one place |
| **⧉** | Duplicate (the copy is added **hidden** so you do not accidentally publish two identical blocks) |
| **✕** | Remove. You are asked to confirm, and an **Undo** button appears in the toast for a few seconds |

### Adding a section

Press **+ Add section**, choose a type, and it is added at the **bottom, hidden**. Edit it, then press ◉ to show it, then publish. Nothing new ever appears on the live site without that explicit step.

### Editing text

Most fields are ordinary boxes: type and it is preserved as you go.

* **Eyebrow** — the small label above a heading.
* **Heading** — the big line. Wrap a word in `*asterisks*` to make it the accent colour, e.g. `We build *brands* that work`.
* **Body** — the paragraph. Line breaks are kept.
* **Buttons** — a label plus a link. Links can be a full address (`https://…`), an email (`mailto:`), a phone number (`tel:`) or a path on your own site (`/contact/`).
* **Image** — **Choose image** opens the WordPress Media Library. **Remove** takes the picture out without deleting the file.

Fields marked with a small helper line under them explain the format. If a field asks for a number, it means a number in pixels or a percentage, and the help line says which.

### Repeating groups (buttons, process steps, footer columns…)

Anything with a **+ Add** button at the bottom is a repeating group. Each row has the same four controls (↑ ↓ ⧉ ✕). Add as many as you need; remove the ones you do not.

---

## Editing services, industries, case studies, testimonials and FAQ

**TrustUsBro → Services** (and the four screens under it)

These are **collections**: repeatable cards used wherever that content is shown on the site.

1. Press **+ Add service** (or industry, case study, testimonial, question).
2. Fill in the fields. Only the ones marked as needed matter to the layout; the rest can stay empty.
3. Drag ⠿ to reorder, ◉ to hide a card, ⧉ to duplicate, ✕ to delete.
4. **Save draft**, then **Publish changes**.

A collection with no items makes its section disappear from the site instead of showing an empty box. That is intentional — an empty area looks broken, an absent one does not.

**FAQ specifically:** every question and answer in a visible FAQ card is also published as proper FAQ structured data, which is what makes your questions eligible for expanded search results. Questions hidden in the dashboard are left out of that data too.

---

## Header and footer

**TrustUsBro → Header**
* **Logo text** and, optionally, an **image** (upload a transparent PNG or SVG if you can; the text is used when no image is chosen).
* **Navigation links** — a repeating group. Add, remove, reorder. Keep it to about six items; more than that crowds a phone screen.
* **Header button** — the one call to action in the top bar (e.g. "Start a project").
* **Sticky header** — keeps the bar at the top while scrolling.

**TrustUsBro → Footer**
* Up to **four link columns**, each with a heading and its own links.
* **Social links** — a repeating group; each row is a network, an accessible label and a profile URL.
* **Contact details and legal links** — email, phone, address and a small list of legal links (privacy, terms).
* **Copyright line** — `{year}` and `{site}` are replaced automatically, so the date never goes stale.

> The header and footer from this screen only appear if you have chosen to use them (see the installation guide, *Option B* or *Option D*). If your theme already has its own header, this screen is still useful for holding the wording, and you can switch over whenever you want.

---

## Contact details and the form

**TrustUsBro → Contact details**

Address, phone, email, opening hours, map link, social profiles. What you type here is used by the contact section and the footer, so you only maintain it in one place.

The contact section is where the form settings live, and it renders a **working form** whenever no other form plugin is handling it:

* **Show the form** (toggle) — off if you use Contact Form 7, WPForms, Fluent Forms etc.
* **Form heading** — the line above the fields.
* **Form shortcode** — paste another plugin's shortcode here and that form is used instead of the built-in one.

The built-in form asks for name, email, an optional phone and a message. It checks a security nonce, uses a hidden honeypot field, allows one submission per IP per minute, validates the fields server-side, and sends with `wp_mail()` to your notification address. Responses come back as a plain success or error message after the page reloads. Nothing is stored in the database.

If the message never arrives, it is almost always the host blocking PHP mail. Install a free SMTP plugin (WP Mail SMTP) and it will start working — the Site Manager side is already correct.

---

## Blog

**TrustUsBro → Blog**

This screen lists your articles and their status, categories and whether their SEO title and description are filled in.

* **+ New article** opens the normal WordPress editor. The blog deliberately stays native, so URLs, feeds, categories, comments and your sitemap keep behaving exactly as WordPress intends.
* **SEO title** and **description** are edited in the editor's own sidebar under *Site Manager SEO*.
* **Missing** in the SEO column means a search result for that article will use a generic title. Worth fixing on your five best articles.

---

## SEO

**TrustUsBro → SEO**

Two parts:

1. **A live audit** (top of the screen): how many articles and pages you have, how many are missing SEO titles, descriptions or image alt text. Click through the numbers and fix them.
2. **Site-wide defaults**: title pattern, description, social sharing image, indexing toggle.

What the plugin prints for you, without any setup: page titles, meta descriptions, canonical URLs, Open Graph and Twitter card tags, and schema.org structured data (Organization, WebSite, WebPage, Article and FAQPage).

**It never changes an existing URL.** Permalinks are shown for information only.

**If another SEO plugin is active** (Yoast, Rank Math, All in One SEO), Site Manager detects it and stops printing its own tags, so you never get duplicates. The Health screen tells you which plugin it deferred to.

---

## Media

**TrustUsBro → Media**

* **Alt text** — write what the image shows, for people using a screen reader and for image search. Images without it are flagged in the SEO audit.
* **Usage** — which sections or cards reference the image, in draft and published.
* **Replace everywhere** — swap the picture in every place it is used, in one action. The original file is kept, never deleted.
* **Upload** — opens the normal Media Library, with WordPress's own file-type and size validation.

---

## Design settings

**TrustUsBro → Design settings**

Optional overrides: accent colour, text colour, background, heading and body fonts, corner radius, container width, section spacing.

**Leave a field empty to inherit your theme.** That is the recommended default: the site then matches whatever your theme does, and a future theme refresh carries the design with it. Only set a value when you specifically want the Site Manager area to differ.

Three toggles worth knowing:

| Toggle | Effect |
|---|---|
| **Use Site Manager sections for the front page** | Makes the Home page render the sections from this dashboard |
| **Render the header and footer from Site Manager** | Injects the header/footer automatically. Off by default to avoid a duplicate header |
| **Indexing** (on the SEO screen) | Adds `noindex` site-wide — use only on staging |

---

## Backups

**TrustUsBro → Backups**

Backups are taken automatically:

* on **activation** (the very first state),
* **before every publish** (this is your undo button for a bad publish),
* **daily** via WP-Cron,
* whenever you press **Create backup now**.

Each row shows when, why, how big, and who triggered it. Two actions:

* **Download** — saves a `.json` file containing every document and setting. Keep one off-site; it is also how you move content to another site.
* **Restore** — puts that snapshot back. **A safety backup of the current state is created first**, so a restore is itself undoable.

Backups are stored in `wp-content/uploads/trustusbro-backups/`, outside the plugin folder, so updating or deleting the plugin does not remove them.

---

## Revision history

**TrustUsBro → Revision history**

Every save creates a version. Each row shows the time, who made it, and a short summary. Press **Restore** on any row to load that version into the **draft**.

Restoring a revision does **not** change the live site. It changes your working copy; you still press **Publish changes** when you are happy. That is deliberate — recovery should never be able to publish by accident.

---

## Health & help

**TrustUsBro → Health & help**

* **Checks** — PHP version, WordPress version, database writes, uploads folder, memory limit. Anything not OK says exactly what to do.
* **Environment** — theme name and version, PHP, memory, upload limit, detected plugins.
* **Conflicts** — other SEO plugins, caching plugins, multilingual plugins, page builders.
* **Self-test** — runs five real checks against your installation and reports pass/fail with timings: reading a document, saving a draft, creating and re-reading a backup, reaching the media library, and reading the SEO report. The only write is an extra draft revision labelled *Self-test*; your published site is not touched.
* **FAQ answers** in plain language for the five things owners actually ask.

---

## Common tasks, step by step

### Change the homepage headline
1. **Homepage & pages** → click the **Hero** section title.
2. Edit **Heading**. Use `*asterisks*` for the accent word.
3. **Save draft**. Open the site in another tab — unchanged, as expected.
4. **Publish changes**. Reload the site. Done. If you regret it: **Backups** → the *before-publish* snapshot → **Restore** → **Publish changes**.

### Hide a section for a while
1. **Homepage & pages** → press **◉** on the section so it becomes **○**.
2. **Publish changes**.

The text is kept. Press ◉ again whenever you want it back.

### Reorder the homepage
1. Drag by ⠿, or use ↑ / ↓.
2. **Publish changes**.

### Add a new service
1. **Services** → **+ Add service** → fill in the title, one-line summary and details.
2. Drag it where you want it in the list.
3. **Publish changes**.

### Fix a typo that is already live
1. Find the word (Homepage & pages, or the relevant collection).
2. Change it → **Save draft** → **Publish changes**.

A backup is taken automatically as part of the publish.

### Update the copyright year
Nothing to do. `{year}` in the footer is replaced with the current year automatically.

### Change a photo
1. Open the section that shows the photo.
2. **Choose image** → pick the new one from the Media Library → **Use this image**.
3. **Save draft** → **Publish changes**.
4. The old file is still in the Media Library; nothing is deleted.

### Hand the site to someone else
1. **Users → Add New** → give them the **Editor** role (Editors can manage Site Manager content but cannot restore backups by default).
2. For restore rights, an Administrator must grant `tusb_restore_site`.
3. Point them at this guide.

### Move the site's content to a new installation
1. **Backups** → **Create backup now** → **Download**.
2. On the new site, install and activate the plugin.
3. **Backups** → **Upload & restore** → choose the file.

---

## If something looks wrong

| What you see | What to do |
|---|---|
| "You do not have permission to manage this website" | Ask an Administrator to give your account the right role, or log in as Administrator |
| Publish does nothing | Check the bottom bar: if it says *Unsaved changes*, press **Save draft** first, then **Publish changes** |
| My change is not on the site | Is the bar orange? Then it is a draft — press **Publish changes**. Is the section hidden (○)? |
| The site shows two headers | **Design settings** → turn off **Render the header and footer from Site Manager** |
| The homepage looks empty | The sections are not placed yet — see the installation guide, section 3 |
| An error toast appeared | Read it; it names the field. Nothing was published. Try again, and if it repeats, open **Health & help → Self-test** |
| I published a mistake | **Backups** → the *before-publish* row → **Restore** → **Publish changes** |
| Everything is broken | Deactivate the plugin. Your content is untouched; the site returns to your theme's own content. Then reinstall and report the Health screen output |

Nothing in this plugin deletes content when you deactivate it. That is a promise, and it is covered in the testing report.
