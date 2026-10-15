# Release notes

Every tagged release, newest first. Versions follow [Semantic Versioning](https://semver.org), bare with no `v` prefix. A new dataset or a new benchmarked model is a MINOR release; a methodology change or completely new functionality is a MAJOR release; everything else is a PATCH. Releases are cut with the [release-notes skill](../../.claude/skills/release-notes/SKILL.md).

| Version | Date | Highlights |
|---------|------|------------|
| [0.4.0](0.4.0.md) | October 2026 | `swe-router` 0.2.0 picks a model from a six-question task rubric (74.7% saved for -3.22 points on v2, against 70.5% and -5.06 before); new cli/cli dataset (21 Go tasks) with Claude Opus, Sonnet and Haiku 5.5 run on it. |
| [0.3.0](0.3.0.md) | October 2026 | Claude Opus 5.5, Sonnet 5.5 and Haiku 5.5 on the omp / `/swe3` frontier (Haiku 5.5 at 72.69 for $0.14 a task); Kimi K3 on Bedrock; `strands` and `strands-harness` added as harnesses; omp can no longer run a different model than requested. |
| [0.2.0](0.2.0.md) | September 2026 | `codex` added as a fifth coding harness; MiniCPM5-2B on the omp / `/swe3` frontier at 42.59 for $0.40 a task; Qwen3.6-35B FP8 on one L40S, held off the frontier on cost basis. |
| [0.1.0](0.1.0.md) | September 2026 | First tagged release: the harness x model x dataset benchmark, 18 models on the omp / `/swe3` headline run, four datasets, three hosting paths. |

---

[< Back to the README](../../README.md)
