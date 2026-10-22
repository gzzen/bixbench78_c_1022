<!-- Path: `conditions/c/c_single/README.md`; Purpose: c_single = c_minimal + semantic audit (C-v5). -->
# c_single (C-v5 single-call semantic audit)

`SingleRepair(MinimalRepair)`: everything `c_minimal` does, with its own prompt
(`SINGLE_REPAIR_PROMPT`) and one added step. After the shared validation,
`analysis/semantic_audit.json` must pass `validate_audit` (`semantic_audit.py`): seven
semantic fields, each with a status (matched/unsupported/contradicted/ambiguous) and
evidence, plus a non-empty `answer_contract_check`. One agent call per rescue target.

```bash
python conditions/c/c_single/runner.py --parent-generation analysis/<B_TAG>_generation.json --parent-scoring <scoring.json> [--execute]
```

No historical c_single runs exist in the frozen package.
