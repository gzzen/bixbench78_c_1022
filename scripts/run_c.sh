#!/usr/bin/env bash
# Path: scripts/run_c.sh
# Purpose: Re-export and re-score frozen B with the sibling grader, then run C level(s) from scratch and export them.
set -euo pipefail
cd "$(dirname "$0")/.."
grader="../bixbench78_grader/score.py"   # private sibling repository; this checkout never grades
usage="Usage: scripts/run_c.sh B_TAG [SCORING_JSON]   (B_TAG as in analysis/<B_TAG>_generation.json)
Every run overwrites the B export, the B scoring (unless SCORING_JSON is given), the C parent
registry and the selected levels' run trees and outputs."
b_tag="${1:?$usage}"
[[ "$b_tag" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "invalid B_TAG" >&2; exit 2; }
generation="analysis/${b_tag}_generation.json"
version="${VERSION:-c_minimal}"
case "$version" in
  all) levels=(c_minimal c_single c_blind) ;;
  c_minimal|c_single|c_blind) levels=("$version") ;;
  *) echo "VERSION must be c_minimal, c_single, c_blind or all" >&2; exit 2 ;;
esac
[[ -f "$generation" ]] || { echo "no frozen B generation at $generation" >&2; exit 2; }
if [[ $# -ge 2 ]]; then
  scoring="$2"
  [[ -f "$scoring" ]] || { echo "no B scoring at $scoring" >&2; exit 2; }
else
  [[ -f "$grader" ]] || { echo "no grader at $grader" >&2; exit 2; }
  scoring="analysis/${b_tag}_scoring.json"
fi
mkdir -p "logs/${b_tag}" "results/${b_tag}"
if [[ $# -lt 2 ]]; then
  python scripts/export_predictions.py --generation "$generation" --condition b \
    --output "results/${b_tag}/b.jsonl" --provenance "results/${b_tag}/b.provenance.json" \
    --source-run "$b_tag"
  rm -f "$scoring"
  python "$grader" --predictions "results/${b_tag}/b.jsonl" \
    --provenance "results/${b_tag}/b.provenance.json" --output "$scoring"
fi
# The registry is derived from the scoring; rebuild it with the scoring.
rm -f "analysis/${b_tag}_c_parent.json"
model_args=()
[[ -n "${MODEL:-}" ]] && model_args+=(--model "$MODEL")
[[ -n "${REASONING_EFFORT:-}" ]] && model_args+=(--repair-reasoning-effort "$REASONING_EFFORT")
extra_args=()
[[ "${ALLOW_NO_LOCKED:-0}" == 1 ]] && extra_args+=(--allow-no-locked)
for level in "${levels[@]}"; do
  tag="${b_tag}_${level}"
  rm -rf "runs/${tag}"
  rm -f "analysis/${tag}_generation.json" "reports/${b_tag}_${level^^}_GENERATION.md" \
        "results/${b_tag}/${level}.jsonl" "results/${b_tag}/${level}.provenance.json"
  # Preflight (no model calls) logs how many B questions are answered and locked before any paid call.
  python "conditions/c/${level}/runner.py" \
    --parent-generation "$generation" --parent-scoring "$scoring" "${model_args[@]}" \
    --run-root "runs/${tag}" --output "analysis/${tag}_generation.json" \
    2>&1 | tee "logs/${b_tag}/${level}.log"
  python "conditions/c/${level}/runner.py" --execute "${extra_args[@]}" \
    --parent-generation "$generation" --parent-scoring "$scoring" \
    --workers "${WORKERS:-2}" --timeout "${TIMEOUT:-3600}" "${model_args[@]}" \
    --run-root "runs/${tag}" \
    --output "analysis/${tag}_generation.json" \
    --report "reports/${b_tag}_${level^^}_GENERATION.md" \
    2>&1 | tee -a "logs/${b_tag}/${level}.log"
  python scripts/export_predictions.py \
    --generation "analysis/${tag}_generation.json" --condition c \
    --output "results/${b_tag}/${level}.jsonl" \
    --provenance "results/${b_tag}/${level}.provenance.json" \
    --source-run "${tag}"
done
