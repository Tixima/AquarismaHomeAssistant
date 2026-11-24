#!/usr/bin/env bash
# Kopiert diesen Ordner nach dist/. Veröffentlicht nichts.
# Der Ordner selbst ist bereits der Marketplace-Baum.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/.." && pwd)"
dest="$root/dist"
rm -rf "$dest"
mkdir -p "$dest/docs"
cp -R "$root/custom_components" "$dest/custom_components"
cp "$root/hacs.json" "$root/README.md" "$dest/"
cp "$root/docs/aquarisma.markdown" "$root/docs/submission.md" "$root/docs/development.md" "$root/docs/index.md" "$dest/docs/"
echo "Paket liegt in $dest"
