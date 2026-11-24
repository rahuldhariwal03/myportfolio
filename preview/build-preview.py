#!/usr/bin/env python3
"""Regenerate the standalone front-end preview from a live plugin export.

Usage (from the repository root):

    python3 preview/build-preview.py

Inputs
    preview/site-render.json   {"header": "...", "body": "...", "footer": "...", "tokens": {...}}
                               written by the harness (`tusb-fixtures/demo/site-render.json`)

Output
    preview/site-preview.html  a self-contained page: the plugin's real markup plus
                               assets/css/site.css verbatim, with no WordPress loaded.

The only things this file fakes are the two things a theme normally provides: the
block-theme colour presets that the design tokens resolve against, and a minimal
reset. Everything else is the plugin's own output.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDER = os.path.join(ROOT, "preview", "site-render.json")
CSS = os.path.join(ROOT, "plugin", "trustusbro-site-manager", "assets", "css", "site.css")
OUT = os.path.join(ROOT, "preview", "site-preview.html")

if not os.path.exists(RENDER):
    sys.exit("Missing %s — export it from the running plugin first." % RENDER)

render = json.load(open(RENDER, encoding="utf-8"))
css = open(CSS, encoding="utf-8").read()
tokens = "\n".join("\t%s: %s;" % (k, v) for k, v in render["tokens"].items())

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>TrustUsBro — rendered website (standalone preview)</title>
<meta name="robots" content="noindex" />
<style>
/*
 * Standalone preview of the plugin's front-end output.
 *
 * The header, page sections and footer below are the real markup the plugin
 * prints, and the stylesheet near the bottom is assets/css/site.css verbatim.
 * WordPress is not loaded, so the two things a theme normally provides are
 * imitated here: the block-theme colour presets the design tokens resolve
 * against, and a minimal reset.
 */
:root {{
\t/* What Twenty Twenty-Four exposes; the tokens fall through to their own
\t   fallbacks if a different theme publishes different preset names. */
\t--wp--preset--color--foreground: #111111;
\t--wp--preset--color--background: #ffffff;
\t--wp--preset--color--base: #ffffff;
\t--wp--preset--color--base-2: #f4f4f4;
\t--wp--preset--color--contrast: #111111;
\t--wp--preset--color--primary: #ff6a00;
\t--wp--preset--color--gray-600: #6b6b6b;

\t/* Design tokens, exactly as TUSB_Design::css_vars() emits them. */
{tokens}
}}

/* Minimal theme baseline (a real theme replaces this). */
*, *::before, *::after {{ box-sizing: border-box; }}
html {{ -webkit-text-size-adjust: 100%; scroll-behavior: smooth; }}
body {{ margin: 0; font-family: var(--tusb-font-body, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif); color: var(--tusb-color-text); background: var(--tusb-color-bg); line-height: 1.6; font-size: 16px; }}
img {{ max-width: 100%; height: auto; display: block; }}
h1, h2, h3, h4 {{ color: var(--tusb-color-heading); line-height: 1.12; margin: 0; letter-spacing: -0.02em; }}
p {{ margin: 0; }}
ul, ol {{ margin: 0; padding: 0; }}
button {{ font: inherit; }}
a {{ color: var(--tusb-color-accent); }}

.preview-note {{
\tposition: sticky; top: 0; z-index: 999; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between;
\tpadding: 9px 18px; background: #111; color: #fff; font-size: 12.5px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}
.preview-note strong {{ color: #fff; }}
.preview-note .tag {{ display: inline-block; margin-right: 8px; padding: 2px 7px; background: #ff6a00; color: #111; font-size: 10px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }}
.preview-note a {{ color: #fff; text-underline-offset: 3px; }}

/* --- assets/css/site.css, verbatim --- */
{css}
</style>
</head>
<body>
<div class="preview-note">
\t<span><span class="tag">Preview</span><strong>Real plugin markup and CSS</strong> for the published &ldquo;Home&rdquo; document — rendered without WordPress so the design is visible on its own.</span>
\t<span><a href="./dashboard.html">&larr; Back to the dashboard demo</a></span>
</div>
{header}
<main id="tusb-main" class="tusb-main">
{body}
</main>
{footer}
</body>
</html>
"""

html = TEMPLATE.format(
    tokens=tokens,
    css=css,
    header=render["header"],
    body=render["body"],
    footer=render["footer"],
)
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(html)

print("wrote %s (%d bytes)" % (OUT, len(html)))
