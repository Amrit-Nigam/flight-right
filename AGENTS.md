# Flight Right: repository editing rules

This is the maintained home for shared project-editing rules. These instructions
apply to every agent working in the repository root or any subdirectory.

## Read before every task

1. Read this file before investigating, editing, testing or reporting on the project.
   Re-read it when the user says rules have changed. When work is delegated, give
   the worker this path and require it to read these rules too.
2. Read applicable subdirectory instructions and relevant context in
   [docs/CLAUDE.md](docs/CLAUDE.md). This file governs shared editing rules; the
   context document also contains historical decisions and change logs. Historical
   experiment statements are not new instructions.
3. Higher-priority system/developer instructions and the user's current instructions
   take precedence. Existing authorization remains valid; do not request it again.
4. Preserve unrelated work already in the working tree. Commit/push only when the
   user authorizes it; a past publication does not authorize every future task.

## Evaluation and report maintenance

### Canonical files

| File | Purpose |
| --- | --- |
| [docs/evaluation.md](docs/evaluation.md) | Single current cross-model comparison: keep only each model's latest best supported results, how achieved, and served/candidate status. Historical/superseded numbers belong in the individual model files. |
| `docs/evaluations/<model>.md` | Complete experiment history for that model, including every experiment, configuration, result and original evidence. Keep every entry; update its old numbers only when the same experiment produces verified better results. |
| [docs/evaluations/source_inventory.json](docs/evaluations/source_inventory.json) | Evidence paths, model ownership, checksums, preservation and cleanup records. |
| [scripts/consolidate_evaluations.py](scripts/consolidate_evaluations.py) | Evidence ingestion, publication, verification and restoration tooling. |

Append another iteration to its existing model ledger. Give a genuinely distinct
model/checkpoint its own clearly named ledger and register it with the inventory
and tooling. Link related models without copying their entire histories. Do not
create competing permanent "latest", "final" or "new evaluation" pages.

The two report types have different update rules:

- **Complete comparison (`docs/evaluation.md`):** update/replace superseded summary
  results so only the latest best supported numbers for each model remain. Do not
  accumulate historical comparisons or every experiment in this file.
- **Individual model files:** keep every experiment and its numbers. Add new
  experiments; do not delete existing experiment entries. The only exception to
  retaining old result figures is a verified improvement from the **same experiment**:
  update that experiment's existing numbers and associated date/artifact/evidence
  references to the improved result. Keep the experiment entry itself and all
  other experiments intact.

An improved-result update must refer to the same recorded experiment on a comparable
dataset/split and metric basis, using its stated selection criteria and acceptance
checks. A different configuration, dataset or experiment is a new entry, not an
excuse to overwrite a previous experiment. Record the update reason and supporting
evidence; keep original raw evidence bytes/checksums intact. Worse or incomparable
reruns must not replace the existing better result. Do not assemble a result row
from the best individual metrics of different runs/checkpoints.

### Record the experiment and its outcome

When training, fine-tuning, evaluating or testing a model, or changing its features,
preprocessing, decoder, calibration, thresholds or evaluation harness, update the
affected ledger before declaring the work complete. Include unsuccessful, rejected,
interrupted and unselected trials as well as successful ones.

For each experiment, record as applicable:

- Identifier, date/time, purpose, baseline and hypothesis.
- Exact model/checkpoint, artifact SHA-256 and relevant code/source version.
- Dataset/corpus identity, sample counts, split construction and exclusions.
- Seeds, hyperparameters, features, preprocessing, decoder settings, calibration,
  operating threshold and the precise change from the baseline.
- Validation/test metrics with definitions, units and denominators; confusion
  counts, per-seed results or uncertainty where measured. Record hardware/timing
  conditions when making performance claims.
- Selection method, checks passed/failed, rejection reason and deployment status.
- Original report/evidence references, limitations, contamination/overlap and any
  repeated use of an already inspected test set.

Use "not measured", "not run" or "not applicable" when appropriate. Passing tests
is not evidence of an accuracy improvement. Copied scores and cached re-scoring
must not be presented as new inference or fresh latency measurements.

### Update the current comparison

After verifying results, update `docs/evaluation.md` to show only each affected
model's latest best supported numbers and the configuration that achieved them.
Replace superseded summary figures and remove obsolete comparison/history sections
from this complete comparison file; retain their experiment history in the relevant
individual model file. Link to that history instead of copying it into the summary.
State the measurement date and served/candidate status. If the best supported
configuration is undeployed, say so; do not imply it is currently served. If a number
was not remeasured, say so and do not assign it a fresh measurement date.

Use the recorded validation-selection method and acceptance checks to identify the
best supported configuration. Never choose a model, seed or threshold by maximizing
its test score. Retain rejected/unselected results in history. Publishing evaluation
results does not authorize replacing served weights or changing alert behavior.

Keep classifier-only and full-chain scores separate. Likewise distinguish top-1
accuracy from best-of-K coverage, raw from normalized speech error, real from
synthetic audio, and different corpora/splits. Do not rank incomparable measurements.

### Preserve evidence and useful artifacts

Preserve every experiment entry in the individual model reports and retain original
evidence bytes/checksums. Only the same-experiment improvement exception above
allows updating an existing experiment's recorded result figures. If a historical
result is wrong for another reason, add an explicit correction with its reason and
supporting evidence instead of silently altering the old entry. The complete
comparison is a current summary and does not need to preserve superseded figures.

The earlier preserve-and-delete procedure applied to the old historical source files
used to create these consolidated reports during the initial cleanup. It is **not**
a recurring requirement to back up, archive, commit or delete reports before adding
new experiments. Routine maintenance adds new experiments to individual histories,
updates the same experiment's numbers only for a verified improvement, and updates
the complete comparison to its latest best results. It must not delete individual
experiment entries or automatically delete report files. Dated run outputs may be
retained as supporting evidence and registered in the inventory; they are not
competing maintained evaluation pages.

Before retiring model weights, record their configuration, source/data provenance,
actual results and selection/rejection reason in the model ledger. Preserve served
models, useful selected candidates, original datasets and required evaluation inputs.
If usefulness is uncertain, preserve the file and explain the uncertainty. Git does
not back up ignored weights or datasets. Separate authorization to clean model/data
artifacts does not authorize deleting experiment entries from individual reports.

For shared artifacts, follow [ml_pipeline/artifact_registry.json](ml_pipeline/artifact_registry.json)
and [ml_pipeline/artifact_paths.py](ml_pipeline/artifact_paths.py). Update consumers
before removing copies and retain checksum pins. Similar names, shapes or sizes do
not prove equivalence. For packages differing only in metadata, verify and record
model-content/prediction equivalence and both complete-file hashes first.

### Use the tooling carefully and verify

Before ingestion/publication, check that the maintenance script supports the model,
report schema and new result selection. Extend it when necessary. Do not blindly
run a publisher that drops experiment entries from individual histories, changes
their old numbers outside the same-experiment improvement exception, restores stale
selections or overwrites unrelated additions. It may replace the complete comparison
with the current best results, provided the model histories retain the experiments.
Update the tooling first or edit the reports according to these rules without it.
Preserve concurrent/unrelated edits to ledgers and reports.

```powershell
venv\Scripts\python.exe scripts/consolidate_evaluations.py --ingest REPORT_PATH --models MODEL_KEY
venv\Scripts\python.exe scripts/consolidate_evaluations.py --verify
venv\Scripts\python.exe scripts/consolidate_evaluations.py --restore ORIGINAL_PATH
```

`--ingest` also refreshes the current comparison: inspect its selection and writing
logic first. Use it only when it preserves individual experiment histories, respects
the same-experiment improvement exception and keeps the complete comparison limited
to the latest best results.
Register new model keys/formats before ingestion. Restore historical inputs only
when needed; do not overwrite existing files or leave restored copies as competing
maintained reports.

Check ledger values against source reports, verify evidence hashes and references,
and confirm that every existing individual experiment entry remains, with old numbers
changed only for a documented same-experiment improvement. Confirm that the complete
comparison contains only the latest best supported results for each model. Test
affected consumers. Run the verifier when the tooling supports all affected records;
add missing support rather than claiming an unrecognized model was verified.
Run checks appropriate to code changes without retraining for a documentation edit.

Report which evaluation files changed, what produced the numbers, what was checked,
any unresolved limitation, and whether weights, deployment or the recorded headline
changed. Never invent a new score.

## Adding or changing rules later

When the user asks any agent to add/change a project-editing rule, edit this file.
Update the relevant section or add a clearly named one. Keep rules specific to the
user's request; do not invent extra approval requirements. Keep `CLAUDE.md`, the
README and other entry points as pointers rather than copying this policy into
several files. Log substantive rule changes in `docs/CLAUDE.md` while preserving
unrelated project history.
