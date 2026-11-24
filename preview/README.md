# Standalone preview

Two self-contained pages that show the plugin working **without WordPress**. Open them directly in a browser (double-click) or serve the folder:

```bash
cd preview && python3 -m http.server 9600
```

| File | What it is |
|---|---|
| `dashboard.html` | The **real Site Manager interface**, re-implemented as one dependency-free HTML file so the click-to-edit and drag-and-drop behaviour can be tried before installing anything. Data comes from `demo-data.json` (a genuine export of the plugin's REST payload); edits are kept in `localStorage` only and never leave the browser. |
| `site-preview.html` | The **real front-end output** for the published `home` document: the plugin's own header, sections and footer markup, plus `assets/css/site.css` verbatim. Regenerate with `python3 build-preview.py`. |
| `demo-data.json` | REST export: bootstrap, all 12 documents, blog list, backups, SEO report. |
| `site-render.json` | Rendered header/body/footer HTML and the emitted design tokens. |
| `build-preview.py` | Rebuilds `site-preview.html` from `site-render.json` + the shipped stylesheet. |

## What the demo is and is not

* **Is:** the same screens, the same fields, the same validation messages, the same draft → publish model, running against real exported content.
* **Is not:** a WordPress install. Media uploads, real saving to a database, mail delivery and multi-user editing are only available in the plugin. The banner at the top says so, and the image fields say so when clicked.

## Trying it (2 minutes)

1. Open `dashboard.html`.
2. **Homepage & pages** → click **Hero** → change the heading.
3. Watch the bottom bar turn orange (*Unsaved changes*) → **Save draft** → visit the site preview: your change is **not** there.
4. **Publish changes** → open `site-preview.html` (regenerated from the published state, so it shows the original copy; the live behaviour is described in the plugin).
5. Drag a section by its ⠿ handle, or use ↑ / ↓.
6. **+ Add section** → pick a type → it is added hidden at the bottom.
7. Edit a section → **✕ Remove** → press **Undo** in the toast.

## Verification

The demo is covered by an automated jsdom suite (39 assertions: navigation, save bar states, dirty tracking, save/publish persistence, section reorder, add-section modal, remove + undo, and all 15 views rendering with zero JavaScript errors). See `plugin/trustusbro-site-manager/docs/TESTING.md`.
