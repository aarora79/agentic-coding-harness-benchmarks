# Does the swe-router pay for itself?

> Across the 21 tasks the router selected **4 different models**: **qwen3.8-27b** 13x, **claude-opus-5** 2x, **claude-opus-4-8** 1x, **glm-5.3** 1x. On 4 further task(s) nothing cleared the floor, so the skill's answer was to stay on `claude-opus-5`.
>
> Against running `claude-opus-5` on everything, that cost **46.4% less** ($134.64 against $251.04) for a quality change of **-4.7%** (78.94 against 82.83 mean task score, -3.89 points).
>
> The saving is total-over-total, which is what lands on a bill. The mean of the per-task percentages is 61.9%, higher because it weights a cheap task the same as an expensive one.

Replays the `swe-router` skill over all 21 tasks of `mcp-gateway-registry-v2`, then looks up what the model it picked ACTUALLY scored and cost on that task, against running `claude-opus-5` on everything.

- **Sampling.** Leave-one-out: each task routes from tier means recomputed with that task excluded, so no pick knows the run it is scored against.
- **Floor.** Judged per task by omp + us.anthropic.claude-opus-5 running the skill's step 1 against the cloned repo -- the real judgment the skill asks for, not a policy constant. See `swe-router-judged-inputs.md`.
- **Tier.** Classified per task by the same judged run, NOT read from the dataset. Each row carries the dataset's own `complexity` label beside it so disagreement is visible.
- **Candidates.** 16 model(s) the developer could select: claude-haiku-4-5, claude-opus-4-5, claude-opus-4-6-v1, claude-opus-4-7, claude-opus-4-8, claude-opus-5, claude-sonnet-5, deepseek-v3.2, devstral-2-123b, gemma-4-31b, glm-5.3, kimi-k2.7-code, minimax-m2.5, qwen3-coder-30b, qwen3.6-35b, qwen3.8-27b. The organisational allow-list was ignored (`--no-allow-list`).
- **Cost basis.** Metered provider bills for Bedrock models; hardware-derived ($/token from the throughput sweep x tokens the server processed) for self-hosted ones. Mixing the two on one axis is directional -- see `docs/cost-per-task-methodology.md`.
- **Scoring.** `task_score` from the repo-grounded `openai.gpt-5.6-sol` judge. One run per task, so a per-task gap under ~3 points is noise.
- **Runs.** omp harness, /swe3, measured 2026-09-01.

A ⚠ marks a task where the model the router picked landed below the floor it was chosen to clear. That is the router getting it wrong, and the totals count it.

## Judged floors and tiers

| Task | Tier | Floor | Router pick | Predicted | Actual | claude-opus-5 | Δ score | Cost | Baseline cost | Saving |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| default-create-in-idp-checkbox-unchecked | low | 80 | qwen3.8-27b | 80.70 | 81.8 | 90.6 | -8.8 | $0.54 | $5.53 | +90% |
| build-docker-images-from-uv-lock | medium | 75 | qwen3.8-27b | 81.32 | 65.6 ⚠ | 83.2 | -17.6 | $0.50 | $12.00 | +96% |
| honor-cloud-provider-override-in-ui | low | 70 | qwen3.8-27b | 80.05 | 84.4 | 88.4 | -4.0 | $0.58 | $4.81 | +88% |
| fix-reserved-groups-var-in-service-account-script | low | 80 | qwen3.8-27b | 82.15 | 76.0 ⚠ | 87.6 | -11.6 | $0.26 | $5.35 | +95% |
| cli-custom-egress-oauth-provider-flags | low | 80 | claude-opus-4-8 | 80.35 | 84.0 | 91.2 | -7.2 | $3.63 | $8.57 | +58% |
| derive-repo-url-from-skill-md | medium | 75 | qwen3.8-27b | 78.80 | 78.2 | 78.2 | +0.0 | $0.71 | $11.29 | +94% |
| consistent-csrf-across-toggle-endpoints | high | 80 | _stay on claude-opus-5_ | -- | 86.4 | 86.4 | +0.0 | $10.94 | $10.94 | +0% |
| configurable-ui-title | medium | 75 | qwen3.8-27b | 77.72 | 83.6 | 83.2 | +0.4 | $0.84 | $10.35 | +92% |
| configurable-mcp-proxy-upstream-timeout | medium | 70 | qwen3.8-27b | 77.76 | 83.4 | 79.2 | +4.2 | $0.74 | $10.12 | +93% |
| nginx-location-trailing-slash-route-hijack | medium | 80 | glm-5.3 | 81.60 | 82.6 | 80.4 | +2.2 | $5.02 | $9.22 | +46% |
| registration-admission-control-gate | high | 80 | _stay on claude-opus-5_ | -- | 81.8 | 81.8 | +0.0 | $13.29 | $13.29 | +0% |
| server-side-oauth-token-storage | high | 75 | qwen3.8-27b | 77.27 | 54.0 ⚠ | 81.2 | -27.2 | $2.54 | $24.32 | +90% |
| lifecycle-workflow-webhooks | high | 80 | claude-opus-5 | 80.25 | 77.8 ⚠ | 77.8 | +0.0 | $31.96 | $31.96 | -0% |
| per-caller-per-target-rate-limits-and-quarantine | high | 80 | _stay on claude-opus-5_ | -- | 81.0 | 81.0 | +0.0 | $31.69 | $31.69 | +0% |
| idp-authenticated-embedding-endpoint | high | 80 | claude-opus-5 | 80.45 | 77.0 ⚠ | 77.0 | +0.0 | $18.10 | $18.10 | -0% |
| index-demo-videos-in-one-page | low | 70 | qwen3.8-27b | 80.92 | 83.0 | 87.0 | -4.0 | $0.36 | $6.60 | +94% |
| hide-register-button-on-virtual-and-skills-tabs | trivial | 70 | qwen3.8-27b | 81.05 | 82.8 | 86.4 | -3.6 | $0.44 | $3.98 | +89% |
| pass-ssrf-allowlist-env-to-registry-container | trivial | 75 | qwen3.8-27b | 79.20 | 90.2 | 89.6 | +0.6 | $0.61 | $6.35 | +90% |
| macos-setup-python-version-precheck | low | 70 | qwen3.8-27b | 80.92 | 74.0 | 80.2 | -6.2 | $0.45 | $4.08 | +89% |
| portable-env-secret-generation-in-build-script | low | 80 | qwen3.8-27b | 80.92 | 77.0 ⚠ | 75.8 | +1.2 | $0.46 | $11.52 | +96% |
| logout-id-token-hint-out-of-browser-url | high | 80 | _stay on claude-opus-5_ | -- | 73.2 ⚠ | 73.2 | +0.0 | $10.97 | $10.97 | +0% |

**Totals over 21 tasks** (15 switched away from claude-opus-5)

| | Router | Baseline | Difference |
|---|---:|---:|---:|
| Total cost | $134.64 | $251.04 | **-$116.40 (46.4%)** |
| Mean score (21 tasks scored in both arms) | 78.94 | 82.83 | **-3.89** |
| Tasks under floor | 7 | 4 | +3 |
| Tasks failed outright | 0 | 0 | +0 |

Models the router used: claude-opus-4-8, claude-opus-5, glm-5.3, qwen3.8-27b.
