<!-- Path: `conditions/c/README.md`; Purpose: overview of the C hierarchy c_minimal ⊂ c_single ⊂ c_blind. -->
# Condition C: question-local rescue over a frozen B parent

C is a **feedback-assisted** condition. It never reruns B. It reads one frozen B
generation and that generation's post-freeze private scoring, keeps every B Yes
(correct, accepted and resolved) unchanged, and gives each other question one
isolated repair. A repair that is invalid, abstains, or is stopped by the policy
guard keeps the frozen B answer. Final score = B compliant correct + C rescues.

This is a port of `solver/conditions/c/` from the frozen
`ngch_78_frozen_release_20261021` package (Codex) to this checkout's OpenCode v2
per-attempt Docker boundary. Prompts are byte-identical to the source.

## Hierarchy

The source's three `--policy` values are strictly nested; each level adds one step
to its parent. Prompts are the exception: every level supplies its own.

```text
c_minimal  (C-v6, source "minimal")   frozen-B packet → 1 repair call → validation → fallback
   └─ c_single  (C-v5, "single")      + analysis/semantic_audit.json must pass validate_audit
        └─ c_blind  (C-v4.1, "blind") + parent-blind semantic contract call before the repair
```

| Level | Class | Calls / question | Prompt |
|---|---|---|---|
| `c_minimal` | `MinimalRepair` | 1 | `MINIMAL_REPAIR_PROMPT` |
| `c_single` | `SingleRepair(MinimalRepair)` | 1 | `SINGLE_REPAIR_PROMPT` |
| `c_blind` | `BlindRepair(SingleRepair)` | 2 | `QUESTION_REPAIR_PROMPT` + `BLIND_CONTRACT_PROMPT` |

The five selected G+C seeds in the frozen package were all produced by **c_minimal**
(prompt sha256 `60d92664…`, pinned by `c_minimal/test_c_minimal.py`). c_single and
c_blind have no historical runs, so results from them are new measurements.

## Layout

```text
conditions/c/
├── c_minimal/              base level: every core feature
│   ├── parent.py           load/verify frozen B + scoring; Yes lock; per-question packets
│   ├── agent_call.py       one isolated OpenCode call (Docker + gateway + live guard); token usage
│   ├── pipeline.py         MinimalRepair: the repair pipeline and its two extension hooks
│   ├── rescue_main.py      CLI, protocol + code snapshot of the level lineage, thread pool, freeze, report
│   ├── repair/             repair rules (diagnosis, repair_policy; unchanged from source)
│   ├── repair_result.schema.json, prompts.py, runner.py, config.json
│   └── test_*.py           fixtures, policy, pipeline, parent, CLI, export (offline)
├── c_single/               pipeline.py (SingleRepair), semantic_audit.py, prompts.py, runner.py, config.json, test
└── c_blind/                pipeline.py (BlindRepair), blind_contract.py, semantic_contract.schema.json,
                            prompts.py, runner.py, config.json, test
```

Imports only go up the hierarchy: `c_blind` → `c_single` → `c_minimal` → `common`,
`conditions.b`. A run snapshots the code of its level and every ancestor
(`protocol.json` → `lineage`, `sources`, `code_snapshot/`).

## Per-question pipeline (`MinimalRepair.run_question`)

1. Fresh `repair_questions/<qid>/` workspace with `question_only.json` and capsule `data/`.
2. Hook `pre_repair`: nothing in c_minimal/c_single. In c_blind, a separate
   `blind_contracts/<qid>/` call with no parent artifacts produces the contract; it must
   quote the question verbatim. Failure → repair skipped, B kept.
3. Hand over frozen B evidence: `repair_packet.json` (B answer, verdict `no`, controller
   diagnostics), `primary_*.json`, B `analysis/scripts/`, small intermediate tables.
4. One OpenCode call with the level's prompt and `repair_result.schema.json`.
5. Validate: JSON schema → no-op normalization → repair policy (≤3 dimensions, 2–3
   interpretations, rerun with persisted `analysis/scripts` source) → unresolved falls
   back to B → result shape → grounding → path/inline-code audit.
6. Hook `post_validate`: nothing in c_minimal; c_single (and so c_blind) requires a valid
   `analysis/semantic_audit.json`.
7. Any failure or policy interruption → frozen B answer. No retry.

## Run

Prerequisites: a frozen B generation from `conditions/b/runner.py` and its post-freeze
scoring (`status: completed_posthoc_after_freeze`). This checkout never grades: the private
sibling repository `../bixbench78_grader/` holds the answer key and scores the exported B
predictions (DeepSeek for `llm_verifier` questions). Its output records the B generation's
`source_generation_sha256`; `load_parent` rejects a scoring made for any other B generation.

```bash
# 1. Export frozen B and have the sibling grader score it -> analysis/<B_TAG>_scoring.json
python scripts/export_predictions.py --generation analysis/<B_TAG>_generation.json --condition b \
  --output results/<B_TAG>/b.jsonl --provenance results/<B_TAG>/b.provenance.json --source-run <B_TAG>
python ../bixbench78_grader/score.py --predictions results/<B_TAG>/b.jsonl \
  --provenance results/<B_TAG>/b.provenance.json --output analysis/<B_TAG>_scoring.json

# 2. Preflight: no model calls; prints locked/target counts, model and default paths.
python conditions/c/c_minimal/runner.py \
  --parent-generation analysis/<B_TAG>_generation.json --parent-scoring analysis/<B_TAG>_scoring.json

# 3. One-question paid pilot with its own paths, then full runs + export:
python conditions/c/c_minimal/runner.py --execute --limit 1 --run-root runs/pilot_c_minimal \
  --output analysis/pilot_c_minimal_generation.json --report reports/PILOT_C_MINIMAL.md \
  --parent-generation analysis/<B_TAG>_generation.json --parent-scoring analysis/<B_TAG>_scoring.json
VERSION=all scripts/run_c.sh <B_TAG>    # c_minimal, c_single, c_blind
```

`run_c.sh B_TAG [SCORING_JSON]` picks up where things stand. A level whose generation exists is
reported as completed and skipped. An interrupted level continues in its run root with
`--resume`: of the rescue targets in the B scoring, those that finished (their
`run_manifest.json` was written) are kept and the rest restart in clean workspaces. A level not
yet started runs from scratch. While no level of the
B run has started, B is re-exported and re-scored with `../bixbench78_grader/score.py` (skipped
when `SCORING_JSON` is given) and the parent registry is rebuilt; once one has started, that
scoring and registry are reused, since the started runs are bound to them. `FRESH=1` deletes the
selected levels' runs and outputs first.

A C run lives next to its B parent, at `runs/<B_TAG>_<level>` (for example
`runs/hard_isolated_<id>_b_c_minimal`), so `scripts/pack_run_artifacts.py <experiment_id>`
and `cleanup_run_artifacts.py` pick it up with the B run. The archive includes C's run-root
records (`protocol.json`, `prompt_snapshot.json`, `code_snapshot/`) and its
`frozen_parent_packets/`, `repair_questions/` and `blind_contracts/` workspaces. C output is
selected by B's private verdicts, so every C file is marked `feedback_assisted` in
`PACK_MANIFEST.json`, and `answer_blind` is false whenever any is packed. Scoring files stay
excluded as before.

Model and effort default to the parent B manifest (B and C were matched historically);
override with `--model` / `--repair-reasoning-effort`. All levels share
`analysis/<B_TAG>_c_parent.json`, so they repair exactly the same questions.
`--execute` refuses an existing output file, and a nonempty run root unless `--resume` is given.

Tests (offline, from the checkout root):

```bash
python -m unittest conditions.c.c_minimal.test_parent conditions.c.c_minimal.test_rescue_main \
  conditions.c.c_minimal.test_repair_policy conditions.c.c_minimal.test_c_minimal \
  conditions.c.c_minimal.test_export conditions.c.c_minimal.test_pack_run_artifacts \
  conditions.c.c_single.test_c_single conditions.c.c_blind.test_c_blind
```

## Differences from the Codex source

- Agent: `opencode run` inside the per-attempt Docker boundary instead of `codex exec`;
  the final JSON is taken from the last assistant message and schema-validated.
- The live answer-blind guard can stop a call; that counts as a failed repair (no retry).
- Network: the source's blind-contract phase ran without network; here every call uses
  the shared gateway's scientific allowlist.
- The older capsule-level C-v4 code (`execute_core`, in-process evaluator) is not ported.
- A B capsule with no `capsule_result.json` gets an unresolved primary that keeps its
  capsule identity (the source crashed), so the prompts' reconstruction path can run.
