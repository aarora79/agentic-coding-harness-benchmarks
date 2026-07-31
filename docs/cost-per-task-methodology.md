# Cost per task: methodology, the two lenses, and what agentic coding does to it

How the throughput skill turns a fixed instance price into a **cost per token** and **cost per task** for a self-hosted (vLLM) model, why there are two ways to express it, and what the agentic-coding workload shape means for user experience and for scaling. Companion to [serving-optimization-notes.md](serving-optimization-notes.md); produced by [clients/build_performance_summary.py](../self-hosted/vllm/clients/build_performance_summary.py) and surfaced by [clients/build_performance_dashboard.py](../self-hosted/vllm/clients/build_performance_dashboard.py) and [clients/cost_for_task.py](../self-hosted/vllm/clients/cost_for_task.py).

## The starting point: a fixed-cost machine, not a per-token bill

A self-hosted model has **no per-token price**. You rent a GPU instance by the hour (e.g. `g6e.12xlarge` at $10.49/hr on-demand) and it processes whatever tokens it can. So the only honest cost is derived, not quoted:

```
dollars_per_second = dollars_per_hour / 3600
```

Everything below attributes that fixed $/second to tokens. The number is real and defensible — it is what the hardware actually costs to run — unlike the fictional token-priced `total_cost_usd` the quality harness records for self-hosted models.

## The two lenses (why there are two)

On a fixed-cost machine the $/hr is **not itemized per token**, so "cost per token" depends on how you attribute the GPU-second. We report both; they answer different questions.

### Lens A — blended / measured (no assumption)

Every processed token — prompt or generation — costs the same slice of GPU time:

```
blended_cost_per_token = dollars_per_second / (prompt_tokens_per_second + generation_tokens_per_second)
```

Both throughputs are measured server-side from vLLM counters over the concurrency window. Input and output cost the **same** per token. This makes no pricing assumption — it just divides the bill by the work done. **This is the primary lens** (see "Why blended is the honest headline" below).

### Lens B — lab-style split (one convention `w`)

The commercial-API shape, where input tokens are billed cheaper than output. We introduce one convention: an input token counts as `w` of an output token when splitting GPU time (default `w = 0.25`).

```
cost_per_output_token = dollars_per_second / (generation_tps + w * prompt_tps)
cost_per_input_token  = w * cost_per_output_token
```

`w` is a **chosen convention, not a measurement** — it exists only to produce the familiar input-cheaper-than-output shape for comparison with hosted APIs. It is a secondary view.

### Cost per task (either lens)

A "task" is defined by its token counts `N` input : `M` output, taken from real agentic runs (`metrics.json` of the model's `/swe2` sessions):

```
task_cost = cost_per_input_token * N + cost_per_output_token * M      # Lens B
task_cost = blended_cost_per_token * (N + M)                          # Lens A (per-token equal)
```

The dashboard exposes `N`, `M`, and `w` as adjustable inputs so you can price any task shape. [clients/cost_for_task.py](../self-hosted/vllm/clients/cost_for_task.py) does the same from the CLI for any task run **outside** the harness — because per-token cost is a property of the model + hardware + load, not of the tasks the sweep happened to run.

### The trade-off between the lenses

- **Blended** is assumption-free and workload-honest, but it prices input and output identically — which looks unfamiliar next to a commercial API invoice.
- **Split** looks like an API bill, but its output-heavy pricing (`cost_out = 4x cost_in` at `w=0.25`) **understates the true cost of an input-heavy workload**. Agentic coding is exactly that (see below), so the split lens's headline "cost per output token" can be misleading — a task that is 98% input tokens is cheap under split's logic but is really consuming the machine's prefill capacity. Report both; **trust blended for this workload.**

## Prompt caching, and why self-hosted vs API costs are not measured the same way

Comparing a self-hosted model's `$/task` against a hosted API model's (e.g. Claude on Bedrock) is the most error-prone part of this analysis, because **the two paths account for cached tokens completely differently.** This is not a modeling choice — it is what each backend reports back to the client.

- **Anthropic API / Bedrock** implements explicit prompt caching and returns `cache_read_input_tokens` / `cache_creation_input_tokens` in every response's `usage`. Claude Code records those, so on a Bedrock run the reused context lands in `cache_read_tokens` (billed at ~10% of the input rate) and the fresh, full-price `input_tokens` is tiny. Example from an Opus-4.8 `/swe2` task: **`input_tokens: 15`, `cache_read_tokens: 315,567`** — 99.99% of the prompt served from cache. Opus's per-task cost is therefore dominated by *output* tokens (verbose, priced high), not input.
- **vLLM's OpenAI-compatible endpoint does not populate those Anthropic-specific cache fields** in the `usage` it returns. So Claude Code records **`cache_read_tokens: 0`** and books the entire (re-fed, growing) conversation as fresh `input_tokens`. Example from a GLM-5.2 task: **`input_tokens: 2,528,799`, `cache_read_tokens: 0`.**

**This does NOT mean the self-hosted model failed to cache.** vLLM's `--enable-prefix-caching` (on by default here) caches the KV of repeated prefixes server-side and reuses them across the growing agentic conversation — it simply is not surfaced back to the client. So Claude Code cannot attribute it, and the client-side `input_tokens` overstates the work the GPU actually did.

**The good news: the caching IS measured server-side, and we can recover an estimate.** vLLM exposes `vllm:prompt_tokens_cached_total` and `vllm:prefix_cache_hits_total` / `vllm:prefix_cache_queries_total` in its Prometheus metrics, and the benchmark archives a DuckDB snapshot of those for every run (`self-hosted/vllm/benchmark-output/vllm-metrics_<model>_<scope>_<timestamp>.duckdb`). Over the actual `/swe2` quality runs on `mcp-gateway-registry`, the server-side prompt-cache hit rate — the self-hosted analogue of Anthropic's `cache_read_tokens` fraction — was:

| Model (self-hosted) | Node | `prompt_tokens_cached` / `prompt_tokens` |
|---|---|--:|
| qwen3-coder-30b | g6e.12xlarge | **84.5%** (40.6M / 48.0M) |
| qwen3.6-35b | g6e.12xlarge | **71.3%** (54.8M / 76.9M) |
| gemma-4-31b | g6e.12xlarge | **69.1%** (22.4M / 32.5M) |
| deepseek-v3.2, glm-5.2, kimi-k2.7-code, minimax-m2.5, qwen3-coder-480b | p5en.48xlarge | **not captured** (see below) |

So on the models we have data for, roughly **70-85% of the prompt tokens Claude Code counted as fresh input were actually served from vLLM's prefix cache** — exactly the tokens Anthropic would have reported (and discounted) as `cache_read`. To estimate an API-style billable-input for a self-hosted run: `billable_input ~= input_tokens x (1 - hit_rate)`; to compute the hit rate for a run, read the archived snapshot (the `throughput` module in `self-hosted/vllm/clients` has the SQL, or query `vllm:prompt_tokens_cached_total` minus/over `vllm:prompt_tokens_total` deltas).

**We only have this for the g6e.12xlarge models.** The five p5en.48xlarge models (DeepSeek-V3.2, GLM-5.2, Kimi-K2.7-Code, MiniMax-M2.5, Qwen3-Coder-480B) were benchmarked on a separate 8×H200 node; only their scrubbed `RUN-SUMMARY.json` and `performance-summary.json` were committed back, not the DuckDB metric snapshots (gitignored, and they stayed on that node). The committed `performance-summary.json` records `kv_cache_usage` but not the prefix-cache hit counters, so their cache rates are recoverable only if that node still holds the raw DuckDBs. Given the same `--enable-prefix-caching` default and the same single-repo agentic workload, expect them in a similar 60-90% band, but we have not measured it — treat those p5en per-task input counts as un-cache-credited upper bounds.

**Why the hardware-derived cost is still fair despite the 0 in the client.** The blended `$/token` already bakes the caching in: it comes from *measured throughput* (tokens/sec the server actually sustained), and that throughput was achieved *with* prefix caching active (the throughput sweeps ran at 52-90% hit rates). So a self-hosted `$/task` is not penalized for the un-credited `input_tokens` — the cheap per-token rate reflects a GPU that was mostly reusing cached prefills. The client-side token *count* is inflated; the *cost* is not.

**Bottom line for cross-path comparison.** When a hosted-API model (small billable input, cached) lands near a self-hosted model (huge counted input, cheap per token) on `$/task`, treat it as an **order-of-magnitude** result, not an exact tie — the two token counts are measured on different bases. State the provenance (metered API bill vs hardware-derived) alongside the number, as the README leaderboard does.

## What agentic coding does to all of this

Agentic coding (Claude Code driving `/swe2`) has an extreme request shape: **very large, read-heavy prompts and small outputs.** Measured on qwen3.6-35b across 5 real runs: **~1.51M input : ~30K output tokens per task — roughly 50:1 input:output.** The model reads the repo, tool-calls, reasons over big files, and emits a comparatively tiny design/patch.

That shape has three consequences:

1. **The server is prefill-heavy: it spends far more compute on reading prompts than on generating.** Prompt throughput (~9-13K tok/s) dwarfs generation (~90-145 tok/s). But "prefill-heavy" is not the same as "saturated" — on a healthy server the prefill still completes in a few seconds (measured **prefill ~2-4s mean** across the sweep), because the prompt is processed in large batched chunks, not token-by-token.

2. **User experience = time-to-first-token, and on a healthy server it is fine and degrades gracefully.** Because each request must prefill ~100K+ tokens before the first output token, **TTFT is the felt latency**. Measured (median) it is **~1-2s uncontended and rises to ~5-8s at concurrency 20** — good, and it degrades gracefully, not off a cliff. TTFT = **queue wait + prefill**; the decomposition shows prefill is a flat ~2-4s and queue wait stays near zero until higher concurrency (p50 0s up to c=7, ~2s by c=20). Report **TTFT as p50/p90**, never the mean: the mean is distorted by a few cold-cache outliers and by how many requests complete in the window, which can make it move in the wrong direction.

   Full curve (qwen3.6-35b, multi-repo, 25 repos, 10-min windows per level, healthy server):

   | c | gen t/s | prompt t/s | TTFT p50 | TTFT p90 | queue p50 | prefill mean | blended $/1M | task $ |
   |--:|--:|--:|--:|--:|--:|--:|--:|--:|
   | 1 | 145 | 12202 | 2s | 20s | 0s | 4s | 0.24 | 0.36 |
   | 2 | 114 | 13252 | 1s | 20s | 0s | 3s | 0.22 | 0.34 |
   | 5 | 87 | 9441 | 2s | 20s | 0s | 3s | 0.31 | 0.47 |
   | 7 | 111 | 10168 | 5s | 20s | 0s | 3s | 0.28 | 0.44 |
   | 10 | 103 | 10326 | 5s | 40s | 1s | 3s | 0.28 | 0.43 |
   | 15 | 109 | 10667 | 8s | 80s | 2s | 3s | 0.27 | 0.42 |
   | 20 | 134 | 11705 | 5s | 40s | 2s | 2s | 0.25 | 0.38 |

   > **Watch the server state when you measure.** An earlier run of this same sweep reported TTFT p50 pegged at the histogram ceiling (>640s) with queue-wait means of ~135-240s. That was **not** the model's true behavior — the server was in a backed-up state (a stale scheduler backlog from prior experimentation): it completed ~7x fewer requests per window (23 vs 171 at c=10) because they sat queued. A clean re-run gave the healthy 1-8s numbers above. The lesson: the c=1 baseline and the queue-vs-prefill split exist precisely to catch this — if the c=1 TTFT is not a small number, or queue-wait dominates prefill at low concurrency, the server is not in a clean state and the run should be discarded.

3. **Report cost on the blended (per processed token) lens.** Generation tok/s alone is a poor headline for an input-heavy workload; blended cost counts prompt + generation, i.e. the work the machine actually does. Blended cost stayed in a tight **$0.22-0.31/1M** band across the whole sweep, cheapest at low concurrency, which is the stable, comparable figure.

## Scaling: vertical first (the instance has real headroom), then horizontal

On a **healthy** server this workload is not at a hard ceiling — TTFT p50 is only 5-8s at c=20, KV cache never saturates, and there are no preemptions. So there is genuine vertical headroom: this instance can take more concurrency before latency becomes a problem, and the serving defaults (chunked prefill on, batch budget auto) already use it well. Push concurrency up until p90 TTFT or KV pressure crosses your latency budget — that is the per-instance operating point (the dashboard's recommended-concurrency banner picks the cheapest-blended point; temper it with the p90 TTFT you can tolerate).

Beyond that per-instance limit, scale **horizontally**: the workload is embarrassingly parallel (N developers on N repos are N independent sessions, nothing to synchronize), so add replicas behind a load balancer. The **blended cost per token is roughly flat across replicas** — each instance has the same $/hr and the same throughput profile — so cost scales linearly with load and the per-task cost measured on one instance is the per-task cost at fleet scale: **measure once, multiply by replicas for capacity.**

## Summary

- Cost is derived from `instance $/hr / measured tokens/sec` — real, not a quoted price.
- **Blended** (per processed token, input == output) is the honest primary lens; **split** (`w`-weighted, API-shaped) is a familiar-but-misleading secondary lens for input-heavy work.
- Agentic coding is input-heavy (~50:1), so the server is prefill-heavy — but on a healthy instance TTFT is a few seconds and degrades gracefully; **report TTFT as p50/p90 (not mean) and decompose queue vs prefill**, and always include a c=1 baseline to catch a backed-up server.
- Blended per-task cost (~$0.34-0.47 here) is flat across replicas: use vertical headroom on one instance up to your latency budget, then scale horizontally, and plan capacity from the measured per-task cost.
