# Artifact path normalization (manual, post-run)

The Claude Code run of qwen3-coder-480b produced all six artifacts for the
`remove-faiss` task but wrote them to the WRONG DIRECTORY, so the harness's
artifact check found an empty folder and scored the task 0.0 as a model failure.

The files were moved to the canonical path by hand AFTER the run, and the judge
was re-run over them. The score now recorded in that folder is therefore NOT what
the unaided harness produced -- it reflects the same model output evaluated after
a manual path fix. The original run recorded 0.0 (mean 44.20 over 4 scored
tasks); the original judge verdict is preserved alongside as
`remove-faiss/eval.original-model-failure.json`.

This is an instruction-following failure on output location, not missing work.
It is the same class of failure as the filename normalization documented for the
devstral-2-123b pi run (`devstral-2-123b/pi/swe3/mcp-gateway-registry/ARTIFACT-NAMING-PROVENANCE.md`),
differing only in that the path was wrong rather than the filenames.

## remove-faiss

Two separate path errors, both of which had to be corrected:

1. **Omitted the model-slug level.** Wrote under
   `swe-benchmark-data/claude-code/swe3/...` instead of
   `swe-benchmark-data/qwen3-coder-480b/claude-code/swe3/...`, dropping the
   `qwen3-coder-480b/` directory that identifies which model produced the run.
2. **Invented a task folder name** for the implementation artifacts:
   `remove-faiss-dependency/` instead of the dataset's task id `remove-faiss/`.

The four design artifacts and the two implementation artifacts therefore landed
in two different wrong folders:

    swe-benchmark-data/claude-code/swe3/mcp-gateway-registry/
      remove-faiss/            github-issue.md, lld.md, review.md, testing.md
      remove-faiss-dependency/ patch.diff, implementation.md

All six were moved to:

    swe-benchmark-data/qwen3-coder-480b/claude-code/swe3/mcp-gateway-registry/remove-faiss/

No file was renamed; only the containing directory changed. Content was verified
to belong to this task before moving (10-44 FAISS references per design doc, all
four titled "Remove FAISS Dependency"; patch.diff touches 20 files).

## Attempt provenance

The task ran twice (the harness retried once after the first attempt was recorded
INCOMPLETE), and the surviving artifacts come from BOTH attempts, as the
timestamps show:

  patch.diff, implementation.md   19:50  attempt 1 (recorded 4/6 artifacts)
  github-issue.md, review.md      19:58  attempt 2 (recorded 0/6 artifacts)
  lld.md, testing.md              19:59  attempt 2

Both attempts terminated on `error_max_turns` at 251 turns (attempt 1: 22.5M
input tokens, 894.8s; attempt 2: 24.2M input tokens, 989.0s). The committed
`metrics.json` reflects attempt 2, so its `artifacts_produced: 0` and
`total_cost_usd` describe that attempt, not the merged artifact set scored here.
