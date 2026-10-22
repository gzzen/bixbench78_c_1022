<!-- Path: `conditions/c/c_blind/README.md`; Purpose: c_blind = c_single + parent-blind contract (C-v4.1). -->
# c_blind (C-v4.1 two-stage)

`BlindRepair(SingleRepair)`: everything `c_single` does (so the semantic audit is
required), with its own repair prompt (`QUESTION_REPAIR_PROMPT`) and one added step
before the repair:

- **Blind contract** (`blind_contract.py`, `BLIND_CONTRACT_PROMPT`): a separate
  `blind_contracts/<qid>/` workspace with only `question_only.json` and capsule data. It
  returns the seven-field contract (`semantic_contract.schema.json`); every
  `explicit_constraints` entry must be a verbatim span of the question. The contract is
  handed to the repair as `blind_contract.json`. Failure → repair skipped, B kept.

Two agent calls per rescue target.

```bash
python conditions/c/c_blind/runner.py --parent-generation analysis/<B_TAG>_generation.json --parent-scoring <scoring.json> [--execute]
```

No historical c_blind runs exist in the frozen package.
