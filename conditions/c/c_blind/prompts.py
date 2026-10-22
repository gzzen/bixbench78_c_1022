# Path: conditions/c/c_blind/prompts.py
# Purpose: c_blind (C-v4.1) solver-visible prompts: parent-blind contract and repair.
# Copied byte-for-byte from the frozen source conditions/c/runner.py; do not edit.

BLIND_CONTRACT_PROMPT = """Read question_only.json and inspect only local data/ if needed.
Derive the seven-field semantic contract directly from the question and raw
data. Do not compute an answer. Do not guess unstated filters, thresholds,
denominators, grouping or design choices: label unspecified choices as ambiguous.
explicit_constraints must contain verbatim spans copied from the question.
Use non-login shells, workspace-relative paths and $TMPDIR. Persist any
Python/R inspection code under analysis/scripts; never use inline programs.
Start with sed -n '1,200p' question_only.json and rg --files data. Do not use
shell for loops or parent-directory exclusion globs for file discovery; use
local rg queries or a persisted inspection script. The contract is provisional:
record uncertainties as questions to investigate, not as a veto on later repair.
Never inspect parent directories, other experiments, answer keys or old results.
Return the required JSON contract; no answer and no additional prose."""


QUESTION_REPAIR_PROMPT = """\
Read blind_contract.json first, then repair_packet.json. B3 is the frozen parent. Imported scientific
artifacts and executable sources are available at the local paths recorded in
the packet; use them as evidence and adapt scripts locally.
The blind contract contains provisional hypotheses, not authoritative facts.
An unspecified detail is a research obligation, not an automatic reason to
abstain: inspect raw metadata, documentation and the permitted public paper
before deciding whether it is truly unidentifiable. Do not blindly preserve
either B3 or the blind contract. Never invent missing thresholds or select
an interpretation using evaluator correctness.
Persist all new Python/R task code, including data inspection, under
analysis/scripts before execution. Do not use python -c, Python heredocs, or
Rscript -e for task calculations. Use non-login shells so agent_bix is retained.
Use $TMPDIR for temporary files and logs; never literal /tmp or /var/tmp.
For a changed resolved answer, declare one or a tightly coupled set of up to
three changed dimensions, 2-3 supported
interpretations, reran_analysis=true, and the executed analysis/scripts source.
For an abstention, return unresolved with no candidates, changed_dimensions=[],
reran_analysis=false, computation_required=false, source_files=[] unless a
persisted analysis really ran. If an inspection/validation script actually ran,
set reran_analysis=true, computation_required=true and list its persisted path,
even when abstaining. Do not report reran_analysis=false after running a script.
Grounding and semantic_audit.json are metadata, not executed source files.

This is a question-local conservative repair. The imported B result is frozen.
You are repairing exactly one question after a private yes/no verdict of `no`.
Return exactly one result in `results` and exactly one matching `repair_records`
entry. Do not return or rewrite results for any other question.

Preserve the imported B candidate unless one independently defensible workflow
decision is wrong. You may change at most three tightly coupled dimensions from:
scope_filter, entity_mapping, aggregation_denominator, statistical_method,
unit_precision_type, or external_resource_version. A multi-dimension repair
must explain why the dimensions are causally linked and must compare three
plausible semantic interpretations. A repair must be supported by the question wording,
supplied capsule data/schema/metadata, or permitted public scientific resources;
the `no` verdict does not reveal the correct answer. If no defensible correction
exists, return this question unresolved with an empty changed_dimensions list.
You may use the controller_diagnostics in primary_provenance.json as local
execution/grounding evidence; it is not evaluator feedback and does not reveal
the answer.

Treat declared dimensions as explicit semantic deltas. Independently audit
all parent decisions rather than assuming they are correct. Any additional
evidence-backed correction must be declared; do not silently change it.
In particular, a scope/filter repair must
not silently change observation unit, estimator, or requested output scale.
Before selecting a repair, explicitly check these common but general semantic
forks against the question and capsule evidence:
- storage row/event versus biologically meaningful entity;
- requested population/denominator and explicit filter scope;
- outcome/metric identity (including similarly named severity fields);
- count, proportion, frequency, ratio, odds ratio, and percent scale;
- raw versus filtered objects and record versus unique entity/event counts;
- raw p versus adjusted p and shrunken versus unshrunken estimates.
Do not add a covariate, filter, deduplication, or external method merely because
it is available in metadata; require direct evidence that the question calls
for it.

If the imported B result for this question is unresolved or has no candidate
(for example because its capsule run failed), you may reconstruct a resolved
answer from the supplied capsule evidence in this one call. Treat that as a
missing-result reconstruction, not permission to alter any other question:
rerun the relevant computation, declare its source files, and use an empty
changed_dimensions list. If the evidence is insufficient, remain unresolved.

Before locking a non-trivial repair, briefly compare two or three plausible
semantic interpretations (especially population/denominator, observation
unit, filter scope, metric, or estimator).  Record each interpretation and a
short evidence basis in the repair record's optional `interpretations` field,
then select only the evidence-supported one.  Do not turn this into a full
analysis plan or enumerate answer candidates.

If computation is needed, persist the complete program under
`analysis/scripts/` before executing it, and list that path in source_files.
The repair workspace may contain copied B scripts under the local
`analysis/scripts/` directory. Never execute an absolute path from imported B
provenance or from another workspace; adapt commands to the current workspace
and invoke only local relative paths.
Isolation is strict: work only in the current workspace and its `data/` link.
Never inspect parent directories (`..`), `/mnt/files1`, sibling run roots, or
historical experiments. Do not search outside the workspace. Public scientific
resources may be queried only through the permitted network client; do not
write downloaded content outside the workspace (use `analysis/` if needed).
Write `analysis/grounding.json` in the standard B wrapper shape:
`{"capsule_uuid":"...","questions":[{...}]}`. The one questions item must
contain exactly this question's `question_id`, `grounding_status`,
`selection_rationale`, and the seven semantic fields: `data_object`,
`observation_unit`, `comparison`, `metric_or_outcome`, `unit_or_scale`,
`denominator_or_population`, `method_or_estimator`. Do not use aliases such as
dataset, population, entity, filter, statistic, or metric. Every field must be
present and non-empty. grounding_status is a separate status vocabulary:
use resolved for a resolved computation, partially_resolved for partial
grounding, and unresolved for abstention. Never write matched, unsupported,
contradicted or ambiguous into grounding_status; those belong only in
semantic_audit.json. For an unresolved result, set grounding_status to
`unresolved` and all seven semantic fields to the literal `unresolved`.
Before returning, write analysis/semantic_audit.json with question_id, fields
(a list of exactly seven objects, one per semantic field named above; each
object has field, status, evidence), and answer_contract_check (nonempty text).
Statuses: matched, unsupported, contradicted, ambiguous. Compare the blind
contract, exact wording, raw-data evidence and B3 grounding. Reproducing a
parent number only proves reproducibility, not correctness. Explicit words
such as median, adjusted, proportion and across all comparisons are constraints,
not optional interpretations. Identify ambiguity honestly; do not invent a
threshold or scientific assumption to get a replacement answer. The blind
contract is also fallible: revise it only with explicit evidence in this audit.
In answer_contract_check explain whether the result answers the requested
quantity, comparison, scale and estimator. Return one canonical candidate only.
Preserve the selected semantic contract in the actual computation. Do not use
evaluator feedback, answer keys, enumeration, retry, or multihead exploration.
"""
