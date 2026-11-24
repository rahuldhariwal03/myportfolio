# Backup & Recovery Instructions

Everything you need to protect the content edited in TrustUsBro Site Manager, and to get it back after a mistake.

Read this once, before you need it. Recovery is easy; recovery *without* a backup is not.

---

## 1. What is protected — and what is not

| Protected by Site Manager backups | **Not** protected — use a host or whole-site plugin |
|---|---|
| All homepage and page sections | WordPress posts and pages (except Site Manager documents) |
| Header, footer, contact details | Uploads other than referenced image IDs |
| Services, industries, case studies, testimonials, FAQ | Users, roles, comments |
| SEO defaults, design tokens, placement settings | Plugins, themes, WordPress core |
| The draft/published version pointers | WooCommerce orders, form entries |

Site Manager backups are **content snapshots**, not full-site backups. They are small (tens of KB), fast, and easy to move between sites. For disaster recovery of the whole installation, keep a host-level backup (daily) or UpdraftPlus (free) as well. The Backups screen states this plainly so nobody relies on the wrong tool.

---

## 2. When backups happen automatically

| Trigger | Reason label | Created when |
|---|---|---|
| Plugin activation | `activation` | The first state, before any seeding is edited |
| **Before every publish** | `before-publish` | Every single time you press *Publish changes* |
| Daily | `scheduled` | WP-Cron event `tusb_daily_backup` |
| Manual | `manual` | **Backups → Create backup now** |
| Before every restore | `before-restore` | So the restore itself is reversible |
| Health self-test | `self-test` | Proves the backup path works |

The `before-publish` backup is the important one: it means *every published change can be undone*, even if you never made a manual backup.

Publishing a document also records a per-document snapshot labelled `before-publish-<doc>` (for example `before-publish-home`). The reasons differ deliberately: the per-document row lets you roll back one page, the whole-site row lets you roll back everything published in that action.

---

## 3. Where backups live

```
wp-content/uploads/trustusbro-backups/
├── index.php                       # silence-is-golden guard
├── .htaccess                       # denies direct .json access on Apache
├── 20261122-090952-dXHD.json       # the snapshots
└── 20261123-101500-AB12.json
```

* **Outside the plugin folder**, so updating or deleting the plugin never removes them.
* **Not web-readable**: `.htaccess` denial, an `index.php` guard, and a non-guessable ID + timestamped filename. Downloads go through WordPress with a capability check and a nonce.
* **Nginx users:** `.htaccess` is ignored. Add this to your server block:

```nginx
location ~* /wp-content/uploads/trustusbro-backups/.*\.json$ {
    deny all;
    return 403;
}
```

* **Disk use:** each snapshot is roughly 30–120 KB for a typical site. Daily backups for a year are single-digit megabytes. Nothing is pruned automatically; old snapshots are cheap but you should still delete ones you no longer want (the Backups screen has a delete action, which asks for confirmation).

---

## 4. Creating a backup manually

**Backups → Create backup now.** It appears at the top of the list within a second, with its size and document count.

Do this before:

* installing or updating any other plugin or theme,
* changing permalinks or the site URL,
* handing the site to a new editor,
* a seasonal campaign where you will hide/show many sections,
* any work you cannot describe to the owner in one sentence.

You cannot "back up too often" here — the snapshots are tiny.

---

## 5. Restoring

**Backups → the row you want → Restore.**

What happens, in order:

1. The plugin validates the snapshot (structure, version, checksum where present).
2. It creates a **`before-restore` safety backup** of the current state. *If that backup cannot be written, the restore is cancelled* — you can never end up with neither the old nor the new state.
3. It writes the snapshot's documents back into the **draft** layer. The published copy is not touched by the restore itself.
4. It applies the snapshot's settings and reports how many documents were imported, plus which were skipped or failed.
5. You review the result, then press **Publish changes** to make it live (that publish takes its own `before-publish` backup).

So recovery is always a two-step, inspect-then-publish operation. That is deliberate: a single click can never silently overwrite the live site.

Because step 2 runs first, a restore is itself reversible — the `before-restore` row appears at the top of the list and can be restored in turn.

> **Restoring settings too.** A snapshot includes SEO and design settings. If you only wanted the homepage back, check the sections afterwards and re-apply any design change made since the snapshot.

---

## 6. Recovering from specific situations

### "I published a mistake 5 minutes ago"
1. **Backups** → the newest `before-publish` row.
2. **Restore** (loads the snapshot into the draft).
3. **Publish changes** — confirm on the front end.

Time: under a minute. No developer needed.

### "I deleted a section and already published"
Same as above. The `before-publish` snapshot from that publish contains the section.

### "I deleted a section but have not published"
**Revision history →** the version before your delete → **Restore** (loads it into the draft) → publish.

### "The whole dashboard looks wrong after a plugin update"
1. Deactivate Site Manager. Your front-end content is untouched — the site falls back to your theme's own content.
2. **Backups** still exist in `uploads/trustusbro-backups/`.
3. Reactivate, then restore the snapshot from before the update.

### "The site is broken and I cannot reach wp-admin"
Site Manager is very unlikely to be the cause (it does not touch core, theme or `wp-config.php`), but:
1. Rename `wp-content/plugins/trustusbro-site-manager/` via FTP — the plugin deactivates automatically.
2. Check whether the site recovers. If yes, the plugin is involved; restore a backup after fixing access.
3. If no, the cause is elsewhere (theme, another plugin, host) — restore your whole-site backup.

### "I need to move content to a new site"
1. **Backups → Create backup now → Download**. You get `20261122-090952-dXHD.json`.
2. On the new site: install and activate Site Manager, then **Backups → Upload & restore** → choose the file. (An `before-import` safety backup is taken first; unknown document keys are skipped rather than guessed.)
3. Review the imported drafts, then **Publish changes**.

The file is plain UTF-8 JSON. It contains no passwords, no user records and no server paths — just content and settings.

### "Something was edited by the wrong person"
**Revision history** shows the author of every save. Restore the version from before their change, and review capabilities under **Users** (`tusb_manage_site` for editors, `tusb_restore_site` for whoever may restore).

---

## 7. What to do if the backup folder is not writable

Symptom: *"The backup file could not be written. Check that wp-content/uploads is writable."*

1. Check permissions on `wp-content/uploads` — typically `755` (or `775` with a group-writable setup).
2. Check the owner matches the PHP user (`www-data`, `nginx`, or your host's user).
3. If your host blocks writes there, work around it:
   * **Backups → Download** after each session and keep the JSON on your computer or in cloud storage.
   * Ask the host to allow `wp-content/uploads/trustusbro-backups/`.
4. Verify the fix with **Health & help → Self-test** ("Create and read a backup").

A failed backup **never** blocks editing: if a `before-publish` backup cannot be written, the publish reports it. Treat that warning seriously — you are publishing without a safety net.

---

## 8. Long-term policy (recommended)

| Frequency | Action | Kept for |
|---|---|---|
| Every publish | automatic `before-publish` | as long as you keep the row |
| Daily | automatic `scheduled` | 30 days, then delete old rows manually |
| Before any plugin/theme install | manual | until the change is verified |
| Monthly | **Download** one snapshot off-site | 12 months |
| Before major redesign | manual + download | indefinitely |

Two rules worth following:

1. **One backup off the server.** A backup on the same disk does not survive a dead disk.
2. **Test a restore once.** On staging, restore an old snapshot and publish it. Knowing the procedure before a crisis is worth more than the backup itself.

---

## 9. Deleting backups

The Backups screen deletes a snapshot (with confirmation) and removes the file. Deleting a snapshot cannot affect content — it is a copy, not the source.

Purging everything happens only through the opt-in uninstall path:

```bash
wp option update tusb_purge_on_uninstall 1
wp plugin uninstall trustusbro-site-manager
```

Without that option, deleting the plugin leaves every snapshot in place. That is deliberate: the safe default is to keep data.

---

## 10. Verification checklist

Use this to prove backups work on your installation. Five minutes, once.

- [ ] **Backups** lists at least one `activation` snapshot.
- [ ] Press **Create backup now** → a new row appears with a sane size.
- [ ] Press **Download** → the `.json` file opens and contains `"documents"`.
- [ ] Make a harmless change (edit one word) → **Publish changes** → confirm a `before-publish` row exists.
- [ ] **Restore** that `before-publish` row → a `before-restore` row appears too, the draft shows the old word, the live site still shows the new one → **Publish changes** → the old word is live again.
- [ ] **Health & help → Self-test** passes all five steps.
- [ ] `https://yoursite.com/wp-content/uploads/trustusbro-backups/` does **not** list files, and a direct `.json` URL returns 403 (Apache) — or the Nginx rule from section 3 is in place.

If any box is unticked, do not rely on the feature until it is.
