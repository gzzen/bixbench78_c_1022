# Native/B 78-question generation code — clean checkout

Answer-blind generation code only. This directory contains no generated
output, reports, frozen predictions, diagnostics, run workspaces, or staging
files. It also contains no answer key or scorer. Frozen, exported predictions
are scored by the private sibling repository `../bixbench78_grader/` (answer key
plus DeepSeek grader), which scripts call by relative path only after freeze.

- `conditions/`: Native and B runners, prompts, schemas and protocols; C rescue
  levels over a frozen, privately scored B run (`conditions/c/`)
- `common/`: isolation boundary, host gateway, OpenCode adapter and tests
- `environment/`: `agent_bix` Conda environment specification
- `scripts/`: run (`run_native.sh`, `run_b.sh`, `run_c.sh`), continue, progress, export and recovery tools
- `protocols/`: experiment substrate notes

Fresh generation uses OpenCode v2 with either the direct DeepSeek API
(`deepseek/deepseek-flash`) or an OpenAI Responses relay
(`openai-relay/gpt-5.6-sol`). See [OPENCODE_DEEPSEEK.md](OPENCODE_DEEPSEEK.md)
for setup, credentials, diagnostics and run commands.

Restore the public `data/` tree as a sibling of this directory before
generating; the code resolves `data/` relative to this directory's parent.
Runs create `analysis/`, `reports/`, `results/`, `runs/` and `logs/` here,
and `.gitignore` keeps them out of Git.

Condition C (`conditions/c/`) is feedback-assisted. It reads a frozen B generation
plus that run's post-freeze scoring (made by `../bixbench78_grader/score.py`) and
repairs only the
B-No questions in isolated OpenCode calls. Its three levels are nested:
`c_minimal` (base, holds the core) ⊂ `c_single` (+ semantic audit) ⊂ `c_blind`
(+ parent-blind contract). See [conditions/c/README.md](conditions/c/README.md).
