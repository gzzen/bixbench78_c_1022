<!-- Path: `conditions/c/protocol.md`; Purpose: shared protocol for every C level (frozen-parent rescue). -->
# C protocol: failure-triggered rescue over a frozen B parent

1. **Parent.** One B generation from `conditions/b/runner.py` with freeze status
   `frozen_before_private_scoring`, and its private scoring with status
   `completed_posthoc_after_freeze`. Every frozen artifact hash is re-verified and the
   scoring must cover exactly the generation's questions. B is never rerun.
2. **Lock.** A question is locked when its B verdict is correct, accepted and resolved.
   Locked results are final and never shown to a repair. All other questions are rescue
   targets with feedback `no`. Only these booleans are read from scoring; ideal answers
   never enter this checkout or any workspace. The locked/rescue split is written once to
   a parent registry and must match for every level run on that parent.
3. **Levels.** `c_minimal` ⊂ `c_single` ⊂ `c_blind`. Each level runs every step of its
   parent plus one more: `c_single` requires `analysis/semantic_audit.json`; `c_blind`
   first runs a parent-blind contract call. Each level has its own prompt.
4. **Repair.** Each target gets a fresh workspace and at most `max_calls_per_question`
   agent calls (c_minimal/c_single: 1, c_blind: 2). Each call is one OpenCode session in a
   network-none Docker container behind the host gateway, with the live answer-blind guard.
   There is no retry, including after a policy interruption.
5. **Evidence.** The repair sees the question, capsule data, the frozen B answer and
   grounding for that question only, controller diagnostics, B's `analysis/scripts/`, and
   small B intermediate tables. It never sees the B conversation or sibling verdicts.
6. **Acceptance.** A changed answer must declare 1–3 dimensions from `scope_filter`,
   `entity_mapping`, `aggregation_denominator`, `statistical_method`,
   `unit_precision_type`, `external_resource_version`; record 2–3 interpretations; rerun
   a persisted `analysis/scripts` program with execution evidence; and write valid
   grounding. A missing B answer may be reconstructed with no declared dimensions under
   the same rules.
7. **Fallback.** Abstention, invalid output, failed validation, timeout or policy
   interruption keeps the frozen B answer for that question only.
8. **Freeze and score.** Protocol, prompt and a code snapshot of the level and all its
   ancestors are written before the first call and re-verified after the last.
   `scripts/export_predictions.py --condition c` emits B rows for locked questions and C
   answers only for accepted, non-fallback rescues; private compliant scoring of that file
   equals B compliant correct + C rescue successes.
9. **Reporting.** Report C as `feedback-assisted`, separately from open-loop conditions,
   with level, lineage, parent, locked count, targets, replacements, agent calls, runtime.
