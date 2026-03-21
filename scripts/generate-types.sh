#!/usr/bin/env bash
# Generate TypeScript types from Pydantic models (backend/models/analysis.py).
# Requires: root `npm install` (json-schema-to-typescript); Python venv under backend/.venv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
export PYTHONPATH=.
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q "pydantic>=2" "pydantic-to-typescript>=2"
.venv/bin/pydantic2ts \
  --module models.analysis \
  --output "$ROOT/frontend/types.ts" \
  --json2ts-cmd "$ROOT/node_modules/.bin/json2ts"
