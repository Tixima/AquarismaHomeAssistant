#!/usr/bin/env bash
# Baut einen Marketplace-Baum unter dist/. Veröffentlicht nichts.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../../.." && pwd)"
dest="$here/../dist/aquarisma-home-assistant"
rm -rf "$dest"
mkdir -p "$dest/custom_components" "$dest/docs"
cp -R "$repo/custom_components/aquarisma" "$dest/custom_components/aquarisma"
cp "$repo/hacs.json" "$dest/"
cp "$here/../README.md" "$dest/README.md"
cp "$here/../docs/aquarisma.markdown" "$here/../docs/submission.md" "$here/../docs/development.md" "$here/../docs/index.md" "$dest/docs/"
echo "Paket liegt in $dest"
