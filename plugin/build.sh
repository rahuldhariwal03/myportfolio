#!/usr/bin/env bash
#
# Build the installable plugin ZIP.
#
#   bash build.sh
#
# Output: dist/trustusbro-site-manager-<version>.zip
#
# The archive contains exactly one top-level folder (WordPress requires this
# shape for "Plugins → Add New → Upload Plugin") and excludes editor/OS noise,
# previous builds and any local-only files.
set -euo pipefail

cd "$(dirname "$0")"

SRC="trustusbro-site-manager"
VERSION="$(grep -o "TUSB_VERSION', '[0-9.]*'" "$SRC/trustusbro-site-manager.php" | head -1 | sed "s/.*'\([0-9.]*\)'/\1/")"

if [ -z "$VERSION" ]; then
	echo "Could not read TUSB_VERSION from $SRC/trustusbro-site-manager.php" >&2
	exit 1
fi

OUT_DIR="dist"
OUT="$OUT_DIR/trustusbro-site-manager-$VERSION.zip"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

# Build a clean staging copy so nothing unwanted can slip in.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/$SRC"
cp -a "$SRC/." "$STAGE/$SRC/"

find "$STAGE" \
	\( -name '.DS_Store' -o -name 'Thumbs.db' -o -name '*.zip' -o -name '*.map' \
	   -o -name 'node_modules' -o -name '.git' -o -name '*.log' -o -name '*~' \) \
	-prune -exec rm -rf {} + 2>/dev/null || true

if command -v zip >/dev/null 2>&1; then
	( cd "$STAGE" && zip -rq "$OLDPWD/$OUT" "$SRC" -x '*/.*' )
else
	python3 - "$STAGE" "$OUT" "$SRC" <<'PY'
import os, sys, zipfile
stage, out, src = sys.argv[1], sys.argv[2], sys.argv[3]
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, dirs, files in os.walk(os.path.join(stage, src)):
        dirs.sort()
        for f in sorted(files):
            full = os.path.join(root, f)
            arc = os.path.relpath(full, stage).replace(os.sep, '/')
            z.write(full, arc)
PY
fi

FILES="$(unzip -l "$OUT" | tail -1 | awk '{print $2}')"
BYTES="$(wc -c < "$OUT" | tr -d ' ')"

echo "Built $OUT"
echo "  version: $VERSION"
echo "  files:   $FILES"
echo "  size:    $BYTES bytes"
echo
echo "Next: Plugins → Add New → Upload Plugin, or:"
echo "  wp plugin install $OUT --activate"
