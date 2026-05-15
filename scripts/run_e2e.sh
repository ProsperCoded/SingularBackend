#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

./.venv/bin/python scripts/bootstrap_db.py
./.venv/bin/python -m pytest tests/e2e -q
