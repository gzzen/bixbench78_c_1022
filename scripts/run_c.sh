#!/usr/bin/env bash
# Path: scripts/run_c.sh
# Purpose: Run C level(s) over one frozen, privately scored B generation, then export predictions.
set -euo pipefail
cd "$(dirname "$0")/.."
b_tag="${1:?Usage: scripts/run_c.sh B_TAG SCORING_JSON   (B_TAG as in analysis/<B_TAG>_generation.json)}"
scoring="${2:?Usage: scripts/run_c.sh B_TAG SCORING_JSON}"
[[ "$b_tag" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "invalid B_TAG" >&2; exit 2; }
generation="analysis/${b_tag}_generation.json"
version="${VERSION:-c_minimal}"
case "$version" in
  all) levels=(c_minimal c_single c_blind) ;;
  c_minimal|c_single|c_blind) levels=("$version") ;;
  *) echo "VERSION must be c_minimal, c_single, c_blind or all" >&2; exit 2 ;;
esac
model_args=()
[[ -n "${MODEL:-}" ]] && model_args+=(--model "$MODEL")
[[ -n "${REASONING_EFFORT:-}" ]] && model_args+=(--repair-reasoning-effort "$REASONING_EFFORT")
mkdir -p "logs/${b_tag}" "results/${b_tag}"
for level in "${levels[@]}"; do
  python "conditions/c/${level}/runner.py" --execute \
    --parent-generation "$generation" --parent-scoring "$scoring" \
    --workers "${WORKERS:-2}" --timeout "${TIMEOUT:-3600}" "${model_args[@]}" \
    --run-root "runs/c/${b_tag}_${level}" \
    --output "analysis/${b_tag}_${level}_generation.json" \
    --report "reports/${b_tag}_${level^^}_GENERATION.md" \
    2>&1 | tee -a "logs/${b_tag}/${level}.log"
  python scripts/export_predictions.py \
    --generation "analysis/${b_tag}_${level}_generation.json" --condition c \
    --output "results/${b_tag}/${level}.jsonl" \
    --provenance "results/${b_tag}/${level}.provenance.json" \
    --source-run "${b_tag}_${level}"
done
