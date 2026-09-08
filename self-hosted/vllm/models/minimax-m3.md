# MiniMax-M3 - serving guidelines

> [!IMPORTANT]
> **Not yet served on this node.** Every other guide in this directory records a configuration that booted and ran a benchmark. This one is written ahead of the first bring-up, from the [official vLLM recipe](https://recipes.vllm.ai/MiniMaxAI/MiniMax-M3) plus what was verified against the vLLM build installed here. Rows marked **unverified** are the recipe's claims, not measurements. Correct them the first time the model actually serves, and delete this note once it has.

| | |
|---|---|
| **HF repo (BF16)** | `MiniMaxAI/MiniMax-M3` |
| **HF repo (FP8)** | `MiniMaxAI/MiniMax-M3-MXFP8` - **MXFP8**, microscaling FP8, not the block-FP8 used by M2.5 and GLM-5.3 |
| **Model card** | [huggingface.co/MiniMaxAI/MiniMax-M3](https://huggingface.co/MiniMaxAI/MiniMax-M3) |
| **Recipe** | [recipes.vllm.ai/MiniMaxAI/MiniMax-M3](https://recipes.vllm.ai/MiniMaxAI/MiniMax-M3) |
| **Type** | MoE, `minimax_m3` architecture, MSA sparse attention with an index cache |
| **Weights size** | unverified - measure on first download |
| **Minimum hardware** | 8x H200/H20 recommended by the recipe; compute capability >= 9.0 (Hopper or newer) |
| **Fits 4x L40S (184 GB)?** | No |
| **Tool-call parser** | `minimax_m3` |
| **Reasoning parser** | `minimax_m3` (a reasoning model; thinking is separated into its own block) |
| **Native context** | 1048576 (1M) by default; cap it with `--max-model-len` |

## What this build actually supports

The recipe says M3 "has not yet shipped in a stable vLLM release - use the dedicated Docker image". That is **out of date for the vLLM pinned here (0.28.0)**, which carries M3 support natively. Verified in the installed package, so no Docker image is needed:

| What | Where |
|---|---|
| Model config | `vllm/transformers_utils/configs/minimax_m3.py` |
| Reasoning parser | `vllm/reasoning/minimax_m3_reasoning_parser.py` |
| Tool-call parser name | `minimax_m3` registered under `entrypoints/openai/tool_parsers/` |
| Sparse-attention kernels | `minimax_m3_index_decode`, `minimax_m3_index_decode_score` |

Re-check this after a vLLM upgrade or on a different box before assuming it holds.

## Serve it

`--block-size 128` is **mandatory**: the MSA sparse attention and its index cache require it, and the default 16 will not work. `vllm-serve.sh` has no dedicated variable for it, so it rides in `EXTRA_ARGS`, exactly as GLM-5.3's `--kv-cache-dtype` and speculative config do.

On a p5en.48xlarge, source the node's environment first ([p5en-h200-cuda-fixes.md](../../../.claude/skills/vllm-setup/p5en-h200-cuda-fixes.md)) so the CUDA JIT fixes and `NCCL_NVLS_ENABLE=0` are in place. Without the NCCL setting the server dies at distributed init, before any weights load.

```bash
cd self-hosted/vllm/scripts

MODEL="MiniMaxAI/MiniMax-M3-MXFP8" \
SERVED_NAME="minimax-m3" \
TP=8 PORT=8000 MAX_MODEL_LEN=262144 GPU_MEM_UTIL=0.90 \
TOOL_PARSER="minimax_m3" REASONING_PARSER="minimax_m3" \
EXTRA_ARGS="--trust-remote-code --block-size 128" \
  ./vllm-serve.sh
```

`--enable-auto-tool-choice` is added by `vllm-serve.sh` whenever a tool parser is set, so it does not belong in `EXTRA_ARGS`.

`MAX_MODEL_LEN` is set to 262144 rather than the native 1M so the KV cache fits alongside the weights. The repo's harness gate wants at least 200K, so this clears it with room. Raise it only after confirming the reported `GPU KV cache size` still supports a workable concurrency.

## Confirm TP before trusting TP=8

The recipe recommends TP=8, and that is the starting point. But **MXFP8 is a block-quantized format**, so this node's two divisibility constraints may both apply, exactly as they do for M2.5 and Qwen3-Coder-480B (see [p5en-h200-cuda-fixes.md](../../../.claude/skills/vllm-setup/p5en-h200-cuda-fixes.md#why-tp-is-4-for-minimax-m25-and-qwen3-coder-480b-not-8)):

1. `num_key_value_heads % TP == 0`
2. `moe_intermediate_size / TP` divisible by the weight block size

M2.5 fails the second at TP=8 and must run at TP=4. Before the first serve, read `num_key_value_heads` and `moe_intermediate_size` from the repo's `config.json` and check both. A failure looks like `ValueError: The output_size of gate's and up's weight = N is not divisible by weight quantization block_n = 128` at engine init.

If M3 also lands on TP=4, two replicas fit on one 8x H200 node (GPUs 0-3 and 4-7 via `CUDA_VISIBLE_DEVICES`, different `PORT`), though the benchmark harness drives one endpoint at a time.

## Benchmark it

Add a registry row to [run-multi-model-benchmark.sh](../../../benchmarks/scripts/run-multi-model-benchmark.sh) in the documented column order (`served_name | HF repo | max_model_len | tool_parser | tp | fits | gpu_mem_util | reasoning_parser | extra_args | extra_env`):

```text
"minimax-m3|MiniMaxAI/MiniMax-M3-MXFP8|262144|minimax_m3|8|p5en.48xl|0.90|minimax_m3|--trust-remote-code --block-size 128|"
```

**Never edit that script while a benchmark is running.** Bash reads a script incrementally, so an in-place edit can make the live shell execute garbage. Wait for the batch to finish, or copy the script.

Then:

```bash
./scripts/run-multi-model-benchmark.sh minimax-m3 \
  --agent omp --skill swe3 \
  --dataset dataset/mcp-gateway-registry-v2.yaml \
  --judge-mode async --timeout-seconds 7200 --dollars-per-hour 27.72
```

## Runtime observed

Nothing yet. Record on first bring-up: weights size and download time, startup duration, `GPU KV cache size`, maximum concurrency at the served window, and the mean minutes per `/swe3` task. Those are what the next person needs, and what the cost-per-task derivation reads.

## Comparison with the other frontier models on this node

| Model | Quantization | TP | Served window | Status |
|-------|--------------|----|---------------|--------|
| Kimi-K2.7-Code | block FP8 | 8 | 131072 | measured |
| GLM-5.3 | block FP8 + FP8 KV cache | 8 | 300000 | measured |
| Qwen3-Coder-480B | block FP8 | 4 | 200000 | measured |
| MiniMax-M2.5 | block FP8 | 4 | 196608 | measured |
| **MiniMax-M3** | **MXFP8** | **8 (confirm)** | **262144 (proposed)** | **not yet served** |
