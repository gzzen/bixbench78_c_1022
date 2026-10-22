#!/usr/bin/env bash
# Path: scripts/run_c.sh
# Purpose: Run C level(s) over one frozen B generation (having the sibling grader score B if needed), then export predictions.
set -euo pipefail
cd "$(dirname "$0")/.."
grader="../bixbench78_grader/score.py"   # private sibling repository; this checkout never grades
usage="Usage: scripts/run_c.sh B_TAG [SCORING_JSON]   (B_TAG as in analysis/<B_TAG>_generation.json;
without SCORING_JSON, uses analysis/<B_TAG>_scoring.json, asking $grader to create it if missing)"
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
  if [[ $# -ge 2 ]]; then
    echo "no B scoring at $scoring" >&2; echo "$usage" >&2; exit 2
  fi
  if [[ ! -f "$grader" ]]; then
    echo "no B scoring at $scoring and no grader at $grader" >&2; echo "$usage" >&2; exit 2
  fi
  mkdir -p "results/${b_tag}"
  # Always re-export: a stale b.jsonl must never be scored.
  python scripts/export_predictions.py --generation "$generation" --condition b \
    --output "results/${b_tag}/b.jsonl" --provenance "results/${b_tag}/b.provenance.json" \
    --source-run "$b_tag"
  python "$grader" --predictions "results/${b_tag}/b.jsonl" \
    --provenance "results/${b_tag}/b.provenance.json" --output "$scoring"
fi
model_args=()
[[ -n "${MODEL:-}" ]] && model_args+=(--model "$MODEL")
[[ -n "${REASONING_EFFORT:-}" ]] && model_args+=(--repair-reasoning-effort "$REASONING_EFFORT")
mkdir -p "logs/${b_tag}" "results/${b_tag}"
extra_args=()
[[ "${ALLOW_NO_LOCKED:-0}" == 1 ]] && extra_args+=(--allow-no-locked)
for level in "${levels[@]}"; do
  # Preflight (no model calls) shows how many B questions are answered and locked before any paid call.
  python "conditions/c/${level}/runner.py" \
    --parent-generation "$generation" --parent-scoring "$scoring" "${model_args[@]}" \
    --run-root "runs/${b_tag}_${level}" --output "analysis/${b_tag}_${level}_generation.json" \
    2>&1 | tee -a "logs/${b_tag}/${level}.log"
  python "conditions/c/${level}/runner.py" --execute "${extra_args[@]}" \
    --parent-generation "$generation" --parent-scoring "$scoring" \
    --workers "${WORKERS:-2}" --timeout "${TIMEOUT:-3600}" "${model_args[@]}" \
    --run-root "runs/${b_tag}_${level}" \
    --output "analysis/${b_tag}_${level}_generation.json" \
    --report "reports/${b_tag}_${level^^}_GENERATION.md" \
    2>&1 | tee -a "logs/${b_tag}/${level}.log"
  python scripts/export_predictions.py \
    --generation "analysis/${b_tag}_${level}_generation.json" --condition c \
    --output "results/${b_tag}/${level}.jsonl" \
    --provenance "results/${b_tag}/${level}.provenance.json" \
    --source-run "${b_tag}_${level}"
done
