#!/usr/bin/env bash
# Build Projector Monitor.app — run once, produces dist/Projector Monitor.app
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "→ Installing PyInstaller..."
.venv/bin/pip install pyinstaller --quiet

echo "→ Converting icon to .icns..."
rm -rf icon.iconset icon.icns
mkdir icon.iconset
for px in 16 32 64 128 256 512; do
    sips -z $px $px icon.png --out "icon.iconset/icon_${px}x${px}.png"    > /dev/null
    sips -z $((px*2)) $((px*2)) icon.png --out "icon.iconset/icon_${px}x${px}@2x.png" > /dev/null
done
iconutil -c icns icon.iconset
rm -rf icon.iconset

echo "→ Building Projector Monitor.app..."
.venv/bin/pyinstaller \
    --windowed \
    --name "Projector Monitor" \
    --icon icon.icns \
    --noconfirm \
    --clean \
    --collect-all certifi \
    main.py

echo ""
echo "✓  dist/Projector Monitor.app"
echo "   Drag to /Applications or run it directly."
