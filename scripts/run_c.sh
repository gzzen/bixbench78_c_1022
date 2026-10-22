#!/usr/bin/env bash
# Path: scripts/run_c.sh
# Purpose: Run C level(s) over one frozen B generation (scoring it privately first if needed), then export predictions.
set -euo pipefail
cd "$(dirname "$0")/.."
usage="Usage: scripts/run_c.sh B_TAG [SCORING_JSON]   (B_TAG as in analysis/<B_TAG>_generation.json;
without SCORING_JSON, uses analysis/<B_TAG>_scoring.json, creating it from ANSWERS and EVALUATOR_DIR if missing)"
b_tag="${1:?$usage}"
[[ "$b_tag" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "invalid B_TAG" >&2; exit 2; }
generation="analysis/${b_tag}_generation.json"
scoring="${2:-analysis/${b_tag}_scoring.json}"
version="${VERSION:-c_minimal}"
case "$version" in
  all) levels=(c_minimal c_single c_blind) ;;
  c_minimal|c_single|c_blind) levels=("$version") ;;
  *) echo "VERSION must be c_minimal, c_single, c_blind or all" >&2; exit 2 ;;
esac
if [[ ! -f "$scoring" ]]; then
  if [[ $# -ge 2 || -z "${ANSWERS:-}" || -z "${EVALUATOR_DIR:-}" ]]; then
    echo "no B scoring at $scoring" >&2
    echo "$usage" >&2
    exit 2
  fi
  python scripts/score_frozen_b.py --generation "$generation" \
    --answers "$ANSWERS" --evaluator-dir "$EVALUATOR_DIR" --output "$scoring"
fi
model_args=()
[[ -n "${MODEL:-}" ]] && model_args+=(--model "$MODEL")
[[ -n "${REASONING_EFFORT:-}" ]] && model_args+=(--repair-reasoning-effort "$REASONING_EFFORT")
mkdir -p "logs/${b_tag}" "results/${b_tag}"
for level in "${levels[@]}"; do
  # The answer-key paths never reach the generation process tree.
  env -u ANSWERS -u EVALUATOR_DIR python "conditions/c/${level}/runner.py" --execute \
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
