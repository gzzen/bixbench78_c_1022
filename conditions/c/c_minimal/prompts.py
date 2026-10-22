# Path: conditions/c/c_minimal/prompts.py
# Purpose: c_minimal (C-v6) solver-visible repair prompt.
# Copied byte-for-byte from the frozen source conditions/c/runner.py; do not edit.

MINIMAL_REPAIR_PROMPT = """Read question_only.json, then repair_packet.json and
the local B3 scripts/grounding. Repair exactly this B3-No question in a fresh
context. B3 is frozen evidence, not authority; its Yes questions are not yours
to modify. Reproducing a number proves reproducibility, not correctness.

Find the smallest coherent correction justified by question wording, raw
data/metadata, package documentation or the public paper. Check biological
entity versus storage row, requested population, joins/missingness, aggregation,
denominator, metric, estimator and output scale. Explicit qualifiers must be
preserved. Verify disputed assumptions before adapting B3 code. For an omitted
implementation detail, use a documented standard default and record it; do not
mistake every unspecified parameter for an unanswerable question. Do not invent
scientific populations, thresholds or mappings when evidence cannot select one.
For real biological ambiguity, investigate the metadata/paper before abstaining.

Declare 1-3 causally linked changed_dimensions from scope_filter, entity_mapping,
aggregation_denominator, statistical_method, unit_precision_type,
external_resource_version. Explain each correction and its evidence in diagnosis
and rationale. Briefly compare 2-3 conceptual interpretations; do not manufacture
a third, compute an answer bank, enumerate candidates or select using scoring.
Rerun only the evidence-selected analysis, checking row counts, joins, bounds,
units and whether the result actually answers the question. Return one canonical
candidate. If no evidence-supported repair exists, return unresolved with no
candidates and changed_dimensions=[]. A missing B3 answer can be reconstructed
from raw data with no changed dimensions and real execution evidence.

Persist all task Python/R code in analysis/scripts before execution. No python -c,
heredocs or Rscript -e. Use non-login shells, workspace-relative paths and
$TMPDIR (never literal /tmp or /var/tmp). Use rg --files data for discovery, not
shell loops or parent-path globs. Never inspect parent/sibling directories,
historical experiments or private answers. Use only this workspace and permitted
public scientific resources; downloads stay local. Reuse only local script paths.

Return exactly one result and one repair_records entry, primary_feedback=no.
Changed computational answers require reran_analysis=true, computation_required=true
and the executed analysis/scripts paths in execution.source_files. If an inspection
script ran, these flags remain true even when abstaining. Otherwise use false,
false and []. List executed programs, not grounding or other metadata, as sources.
Write analysis/grounding.json: {capsule_uuid, questions:[one item]} containing
question_id, grounding_status (resolved/partially_resolved/unresolved), nonempty
selection_rationale and seven nonempty fields: data_object, observation_unit,
comparison, metric_or_outcome, unit_or_scale, denominator_or_population,
method_or_estimator. For abstention all seven values are literal unresolved.
No additional semantic-audit file or planning document is required.
"""
