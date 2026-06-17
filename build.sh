#!/usr/bin/env bash
# Build Projector Monitor.app — run once, produces dist/Projector Monitor.app
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "→ Installing PyInstaller..."
.venv/bin/pip install pyinstaller --quiet

echo "→ Building Projector Monitor.app..."
.venv/bin/pyinstaller \
    --windowed \
    --name "Projector Monitor" \
    --noconfirm \
    --clean \
    --collect-all certifi \
    main.py

echo ""
echo "✓  dist/Projector Monitor.app"
echo "   Drag to /Applications or run it directly."
