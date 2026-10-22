<!-- Path: `conditions/c/c_minimal/README.md`; Purpose: c_minimal, the base C level (C-v6). -->
# c_minimal (C-v6 minimal evidence-backed repair)

Base level of the C hierarchy and home of every core feature: frozen-parent loading
(`parent.py`), the isolated OpenCode call (`agent_call.py`), the repair pipeline
(`pipeline.py`, class `MinimalRepair`), the repair rules (`repair/`) and the shared CLI
(`rescue_main.py`). `c_single` and `c_blind` subclass `MinimalRepair` and override only
their prompt and one hook each (`post_validate`, `pre_repair`).

One agent call per rescue target with `MINIMAL_REPAIR_PROMPT`: find the smallest
coherent correction supported by the wording, data or documentation, use documented
defaults for omitted details instead of abstaining, and rerun only the selected analysis.
No semantic-audit file is required.

This is the level behind all five selected G+C seeds in `ngch_78_frozen_release_20261021`
(`runs/c/*/protocol.json`: `repair_prompt_sha256` `60d926643dfb…7032586`). Those runs used
Codex with `gpt-5.6-terra`/medium; this port uses OpenCode, so it is a new experiment.

```bash
python conditions/c/c_minimal/runner.py --parent-generation analysis/<B_TAG>_generation.json --parent-scoring <scoring.json> [--execute]
```
