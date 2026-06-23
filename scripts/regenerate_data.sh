#!/usr/bin/env bash
# Regenerate all synthetic CSV datasets.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source .venv/bin/activate
export PYTHONPATH=.

echo "Generating data/transactions.csv (150 rows)…"
python -m src.data_generation.generate_transactions

echo "Generating data/complaints.csv (100 rows)…"
python -m src.data_generation.generate_complaints

echo ""
echo "Done. Files written:"
ls -lh data/transactions.csv data/complaints.csv
echo ""
echo "SOP knowledge base (not generated, lives in data/sops/):"
ls data/sops/*.md | wc -l | xargs echo "  markdown files:"
