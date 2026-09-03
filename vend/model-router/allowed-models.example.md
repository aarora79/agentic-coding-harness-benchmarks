# Allowed models

Copy this to `allowed-models.md` beside the skill, or to your repository root, and edit it. The skill reads it before it recommends anything: a model absent from this list is never recommended, whatever it scores.

Delete this file if your organisation has no such policy. The skill works without it and considers every model the assistant offers.

## Format

One model per bullet, in backticks. Anything after the backticked name is a note for humans — the skill reads the name and ignores the rest, so record why a model is on or off the list.

Names are matched through `model-aliases.json`, so any name your assistant shows will work: `claude-sonnet-5`, `us.anthropic.claude-sonnet-5` and `Claude Sonnet 5` all resolve to the same model.

## Allowed

- `claude-sonnet-5` — default for application work
- `claude-haiku-4-5` — approved for docs, tests and scripts
- `claude-opus-5` — approved; check with the platform team before a long run
- `qwen3.8-27b` — self-hosted on the shared cluster, ask #ml-platform for access

## Not allowed

This section is documentation for your developers. The skill does not read it — anything missing from **Allowed** is excluded regardless of whether it appears here.

- `deepseek-v3.2` — pending security review
- `kimi-k2.7-code` — no data-residency agreement
