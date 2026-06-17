#!/usr/bin/env bash
# Launch Projector Monitor using the bundled venv (Tk 9.0, not system Tk 8.5)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/.venv/bin/python3" "$DIR/main.py" "$@"
