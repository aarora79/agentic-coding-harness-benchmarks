# Allowed models

The models on the measured cost/quality frontier: nothing else scores at least as well for at most the cost, across the whole 21-task benchmark.

Edit this list for your organisation. The skill treats it as a hard constraint — a model absent from it is never recommended, whatever it scores. Delete the file and every model is permitted. `allowed-models.example.md` shows the format and what the sections mean.

## Allowed

- `claude-opus-5` — 82.83, $11.95/task, Bedrock. Highest scoring model measured.
- `glm-5.3` — 81.27, $8.09/task, self-hosted. Within 1.6 points of the top at a third less.
- `qwen3.8-27b` — 78.48, $1.47/task, self-hosted. Best value on the list; drops to 71.45 on high-complexity work and did not finish one of the five hard tasks.
- `gemma-4-31b` — 59.74, $0.87/task, self-hosted.
- `qwen3.6-35b` — 59.24, $0.26/task, self-hosted. Cheapest model measured.

## Read this before adopting the list as written

**Four of the five are self-hosted.** A developer on a hosted API can reach exactly one entry, `claude-opus-5` at $11.95 per task. The skill would then recommend it for everything, including a docs page.

**Frontier membership comes from whole-dataset means and is not the ranking that decides a task.** `claude-sonnet-5` is missing from this list because `qwen3.8-27b` beats it on both axes *on average* — 78.48 against 76.97, at a third of the cost. On high-complexity work that reverses: sonnet scores 73.68 and finished all five hard tasks, qwen3.8-27b scores 71.45 and failed one. Excluding sonnet costs a hosted-API developer the model the measurements actually favour for hard work.

So a frontier-only list is a defensible starting point and a poor finished one. Add the models your developers can reach:

```
- `claude-sonnet-5` — 76.97, $4.67/task, Bedrock. Beats qwen3.8-27b on high-complexity work.
- `claude-haiku-4-5` — 56.18, $0.76/task, Bedrock. Cheapest hosted option.
```

## Not allowed

Documentation for your developers. The skill does not read this section — anything missing from **Allowed** is excluded whether it appears here or not.

- Every other model in `models.json` is excluded by omission, including `claude-sonnet-5`, `claude-haiku-4-5` and the four other Opus versions.
