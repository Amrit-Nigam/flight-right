# Flight Right — project instructions

The full instructions live in **[docs/CLAUDE.md](docs/CLAUDE.md)**. This file exists only
so they load automatically: Claude Code reads `CLAUDE.md` from the repository root and does
not look inside `docs/`.

@docs/CLAUDE.md

---

**If the import above did not resolve — that is, if you cannot see the operating rules, the
status table, the decisions log and the change log — then read `docs/CLAUDE.md` in full
before doing anything else.** It is long and it is the single source of truth for this
project. Do not act on the sections below alone; they are a summary kept deliberately short,
and the real file governs.

## The three things that matter most

1. **The headline metric is the percentage of conflicts caught with at least three minutes
   of warning. It is 95.1%** (270 of 284; 94.0% until 26 Sep 2026, when the classifier gained the
   dialled-altitude inputs). Lead every progress report with it and say whether it moved.
2. **Stop and ask Archit** before changing what a model predicts, what a label means, or any
   threshold that affects when a controller gets alerted. Bug fixes, refactors and diagnostic
   experiments are yours to decide.
3. **No change is finished until it is logged** in plain English in Section 15 of
   `docs/CLAUDE.md`: which file, what it was, what it is now, why, and whether the headline
   number moved.

## Where things are

| Path | What it is |
|---|---|
| `docs/CLAUDE.md` | Full project instructions — operating rules, decisions log, change log |
| `docs/ISSUES.md` | Known issues, found by testing the running system. Nothing fixed yet |
| `docs/PROJECT_STATUS.md` | Plain-English status and file-by-file walkthrough |
| `docs/RUNNING.md` | How to run the backend, the dashboard and the database |
| `docs/evaluation.md` | Every metric beside the baseline it has to beat |
| `docs/ablation.md` | The generated ablation table (plan Phase 8) — never edit by hand; run `ml_pipeline/utils/ablation.py` |
| `docs/claims.md` | What may and may not be claimed, each number with its source |
| `docs/DECISIONS_FOR_ARCHIT.md` | Everything measured and waiting on Archit's decision or hands |
| `README.md` | The public GitHub front page |
