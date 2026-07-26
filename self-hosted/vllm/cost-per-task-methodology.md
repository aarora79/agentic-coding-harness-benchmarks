# Cost per task: methodology, the two lenses, and what agentic coding does to it

How the throughput skill turns a fixed instance price into a **cost per token** and **cost per task** for a self-hosted (vLLM) model, why there are two ways to express it, and what the agentic-coding workload shape means for user experience and for scaling. Companion to [serving-optimization-notes.md](serving-optimization-notes.md); produced by [clients/build_performance_summary.py](clients/build_performance_summary.py) and surfaced by [clients/build_performance_dashboard.py](clients/build_performance_dashboard.py) and [clients/cost_for_task.py](clients/cost_for_task.py).

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

The dashboard exposes `N`, `M`, and `w` as adjustable inputs so you can price any task shape. [clients/cost_for_task.py](clients/cost_for_task.py) does the same from the CLI for any task run **outside** the harness — because per-token cost is a property of the model + hardware + load, not of the tasks the sweep happened to run.

### The trade-off between the lenses

- **Blended** is assumption-free and workload-honest, but it prices input and output identically — which looks unfamiliar next to a commercial API invoice.
- **Split** looks like an API bill, but its output-heavy pricing (`cost_out = 4x cost_in` at `w=0.25`) **understates the true cost of an input-heavy workload**. Agentic coding is exactly that (see below), so the split lens's headline "cost per output token" can be misleading — a task that is 98% input tokens is cheap under split's logic but is really consuming the machine's prefill capacity. Report both; **trust blended for this workload.**

## What agentic coding does to all of this

Agentic coding (Claude Code driving `/swe2`) has an extreme request shape: **very large, read-heavy prompts and small outputs.** Measured on qwen3.6-35b across 5 real runs: **~1.51M input : ~30K output tokens per task — roughly 50:1 input:output.** The model reads the repo, tool-calls, reasons over big files, and emits a comparatively tiny design/patch.

That shape has three consequences:

1. **The server is prefill-bound, not decode-bound.** The GPU spends ~99% of its time processing prompt tokens; generation is a rounding error on the compute. Measured prefill:decode ran **130:1 to 280:1**. See [serving-optimization-notes.md](serving-optimization-notes.md) for the full investigation (it is a workload property, not a mistuning).

2. **User experience = time-to-first-token dominated, and it is severe.** Because each request must prefill ~100K+ tokens before the first output token appears, **TTFT is the felt latency**. Measured on the realistic multi-repo sweep it was **~138 to 248 seconds** (2-4 minutes) across concurrency 2-20 — the user waits minutes for the first token, then generation itself is fast. Per-output-token latency (TPOT) stays modest; the wait is almost entirely prefill. "More concurrent users" does not degrade gracefully — each additional heavy prompt lengthens everyone's wait for a prefill slot. **This, not cost, is the real product constraint for agentic coding on a single self-hosted instance.**

   Full realistic curve (qwen3.6-35b, multi-repo, 25 repos, 10-min windows per level):

   | c | gen t/s | prompt t/s | blended $/1M | task $ (blended) | KV% peak | TTFT |
   |--:|--:|--:|--:|--:|--:|--:|
   | 2 | 44.5 | 5936 | 0.49 | 0.75 | 62.6 | 248 s |
   | 5 | 19.6 | 5568 | 0.52 | 0.80 | 47.9 | 241 s |
   | 7 | 21.1 | 6466 | 0.45 | 0.69 | 38.2 | 234 s |
   | 10 | 24.4 | 6602 | 0.44 | 0.68 | 36.3 | 211 s |
   | 15 | 24.8 | 6734 | 0.43 | 0.66 | 39.5 | 196 s |
   | 20 | 49.3 | 8195 | 0.35 | 0.54 | 50.7 | 138 s |

   Note how **generation tok/s is erratic and low (20-49) while prompt tok/s is stable and high (5.9-8.2K), KV never saturates (50-63% peak), and there are zero preemptions** — the blended cost (which counts both token types) is the only smooth, interpretable column. Cheapest blended task cost ~$0.54 at c=20.

3. **Generation tokens/sec is the wrong headline.** It *falls* with concurrency here (the prefix cache stops masking the prefill cost across diverse repos), which makes a healthy, fully-utilized server look broken. The machine is doing more useful work as concurrency rises — it is just prefill work. **Blended cost per processed token stays stable (~5-8K processed tok/s across the whole sweep)** because it counts the work actually done. That is why blended is the honest headline for cost.

## Why the answer to "make it faster/cheaper" is horizontal scaling

Given a fixed workload shape (input-heavy) and fixed serving defaults (already correct — chunked prefill on, batch budget auto), a single instance has a **prefill throughput ceiling** set by its GPU FLOPs. You cannot tune your way past it per model:

- Vertical knobs (`max_num_batched_tokens`, window size, `max_num_seqs`) redistribute the same fixed FLOPs; they do not add prefill capacity. Lowering the context window does not help because the bottleneck is prefill compute, not KV memory.
- The workload is embarrassingly parallel: N developers on N repos are N independent sessions with no shared state. There is nothing to synchronize.

So the scaling story is **horizontal**: to serve more concurrent agentic users at acceptable TTFT, add more replicas (more instances behind a load balancer), not a bigger single box. The **blended cost per token is roughly flat across replicas** — each instance has the same $/hr and the same prefill ceiling — so cost scales linearly with load and the per-task cost you measure on one instance is the per-task cost at fleet scale. That is the property that makes the blended number a useful planning figure: **measure once on one instance, multiply by replicas for capacity.**

## Summary

- Cost is derived from `instance $/hr / measured tokens/sec` — real, not a quoted price.
- **Blended** (per processed token, input == output) is the honest primary lens; **split** (`w`-weighted, API-shaped) is a familiar-but-misleading secondary lens for input-heavy work.
- Agentic coding is input-heavy (~50:1) -> prefill-bound -> TTFT-dominated UX that degrades under concurrency, and generation tok/s is a misleading metric.
- You cannot tune the ceiling away per model; the lever is **horizontal scaling**, and blended per-task cost is flat across replicas, so it is the right figure to plan capacity with.
