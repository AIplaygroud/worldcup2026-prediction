#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
cp database/eventflow/raw_sources/source_notes_template.csv database/eventflow/raw_sources/source_notes.csv
python scripts/run_source_fusion_pipeline.py --match-id 66456908 --home Mexico --away "South Korea"
head -n 5 database/eventflow/processed/eventflow_fused_evidence.csv
