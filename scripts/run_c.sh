#!/usr/bin/env bash
# Path: scripts/run_c.sh
# Purpose: Run, or continue, the C level(s) over a frozen B run and export them; report levels already completed.
set -euo pipefail
cd "$(dirname "$0")/.."
grader="../bixbench78_grader/score.py"   # private sibling repository; this checkout never grades
usage="Usage: scripts/run_c.sh B_TAG [SCORING_JSON]   (B_TAG as in analysis/<B_TAG>_generation.json)
Completed levels are reported and skipped, an interrupted level continues where it stopped
(finished questions are kept), and a level not yet started runs from scratch. B is exported and
scored by the sibling grader only while no C level of this B run has started (unless SCORING_JSON
is given); afterwards that scoring is reused, because the started runs are bound to it.
FRESH=1 deletes the selected levels' runs and outputs first."
b_tag="${1:?$usage}"
[[ "$b_tag" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "invalid B_TAG" >&2; exit 2; }
generation="analysis/${b_tag}_generation.json"
version="${VERSION:-c_minimal}"
all_levels=(c_minimal c_single c_blind)
case "$version" in
  all) levels=("${all_levels[@]}") ;;
  c_minimal|c_single|c_blind) levels=("$version") ;;
  *) echo "VERSION must be c_minimal, c_single, c_blind or all" >&2; exit 2 ;;
esac
[[ -f "$generation" ]] || { echo "no frozen B generation at $generation" >&2; exit 2; }

completed() { [[ -f "analysis/${b_tag}_$1_generation.json" ]]; }
started() { completed "$1" || [[ -n "$(ls -A "runs/${b_tag}_$1" 2>/dev/null)" ]]; }
export_level() {
  python scripts/export_predictions.py \
    --generation "analysis/${b_tag}_$1_generation.json" --condition c \
    --output "results/${b_tag}/$1.jsonl" \
    --provenance "results/${b_tag}/$1.provenance.json" \
    --source-run "${b_tag}_$1"
}

mkdir -p "logs/${b_tag}" "results/${b_tag}"
if [[ "${FRESH:-0}" == 1 ]]; then
  for level in "${levels[@]}"; do
    rm -rf "runs/${b_tag}_${level}"
    rm -f "analysis/${b_tag}_${level}_generation.json" "reports/${b_tag}_${level^^}_GENERATION.md" \
          "results/${b_tag}/${level}.jsonl" "results/${b_tag}/${level}.provenance.json" "logs/${b_tag}/${level}.log"
  done
fi

pending=()
for level in "${levels[@]}"; do
  if completed "$level"; then
    [[ -f "results/${b_tag}/${level}.jsonl" ]] || export_level "$level"
    echo "C ${level} for ${b_tag} has already completed: analysis/${b_tag}_${level}_generation.json, results/${b_tag}/${level}.jsonl"
  else
    pending+=("$level")
  fi
done
if [[ ${#pending[@]} -eq 0 ]]; then
  echo "Nothing to run: every requested C level for ${b_tag} has completed (FRESH=1 to redo)."
  exit 0
fi

any_started=0
for level in "${all_levels[@]}"; do started "$level" && any_started=1; done
if [[ $# -ge 2 ]]; then
  scoring="$2"
  [[ -f "$scoring" ]] || { echo "no B scoring at $scoring" >&2; exit 2; }
else
  scoring="analysis/${b_tag}_scoring.json"
  if (( any_started )); then
    [[ -f "$scoring" ]] || { echo "C has started for ${b_tag} but $scoring is missing; rerun with FRESH=1 (VERSION=all)" >&2; exit 2; }
    echo "Reusing $scoring: C runs of ${b_tag} already started against it."
  else
    [[ -f "$grader" ]] || { echo "no grader at $grader" >&2; exit 2; }
    python scripts/export_predictions.py --generation "$generation" --condition b \
      --output "results/${b_tag}/b.jsonl" --provenance "results/${b_tag}/b.provenance.json" \
      --source-run "$b_tag"
    rm -f "$scoring"
    python "$grader" --predictions "results/${b_tag}/b.jsonl" \
      --provenance "results/${b_tag}/b.provenance.json" --output "$scoring"
  fi
fi
# The registry is derived from the scoring; rebuild it only while nothing is bound to it.
(( any_started )) || rm -f "analysis/${b_tag}_c_parent.json"

model_args=()
[[ -n "${MODEL:-}" ]] && model_args+=(--model "$MODEL")
[[ -n "${REASONING_EFFORT:-}" ]] && model_args+=(--repair-reasoning-effort "$REASONING_EFFORT")
extra_args=()
[[ "${ALLOW_NO_LOCKED:-0}" == 1 ]] && extra_args+=(--allow-no-locked)
for level in "${pending[@]}"; do
  tag="${b_tag}_${level}"
  if started "$level"; then
    echo "C ${level} for ${b_tag} did not complete; continuing runs/${tag}."
  else
    echo "C ${level} for ${b_tag} has not started; running it."
  fi
  rm -f "reports/${b_tag}_${level^^}_GENERATION.md" "results/${b_tag}/${level}.jsonl" "results/${b_tag}/${level}.provenance.json"
  # Preflight (no model calls) logs answered, locked and already-finished counts before any paid call.
  python "conditions/c/${level}/runner.py" \
    --parent-generation "$generation" --parent-scoring "$scoring" "${model_args[@]}" \
    --run-root "runs/${tag}" --output "analysis/${tag}_generation.json" \
    2>&1 | tee -a "logs/${b_tag}/${level}.log"
  python "conditions/c/${level}/runner.py" --execute --resume "${extra_args[@]}" \
    --parent-generation "$generation" --parent-scoring "$scoring" \
    --workers "${WORKERS:-2}" --timeout "${TIMEOUT:-3600}" "${model_args[@]}" \
    --run-root "runs/${tag}" \
    --output "analysis/${tag}_generation.json" \
    --report "reports/${b_tag}_${level^^}_GENERATION.md" \
    2>&1 | tee -a "logs/${b_tag}/${level}.log"
  export_level "$level"
done
echo "Finished: results/${b_tag}"
