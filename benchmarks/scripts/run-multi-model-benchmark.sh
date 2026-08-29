#!/usr/bin/env bash
set -uo pipefail

# ---------------------------------------------------------------------------
# run-multi-model-benchmark.sh -- run the end-to-end SWE benchmark (/swe2:
# design PLUS implementation) for one or more self-hosted vLLM models, back to
# back, unattended, on whatever machine you are on.
#
# For each model it: stops any other served model, serves this one from the
# model registry below, waits for readiness, starts the DuckDB metrics
# collector, runs run-e2e-benchmark.sh (which clears stale artifact folders with
# --yes, runs the /swe2 harness, and scores with the codex judge), archives the
# metrics snapshot, writes run-summary.{json,md}, and commits the run-summary to
# the current branch. It then moves to the next model.
#
# All paths are RELATIVE TO THE REPO ROOT (derived from this script's location),
# so it runs unchanged on any clone / any machine.
#
# The run takes hours, so the script SELF-DETACHES (setsid) on launch: a shell
# or session teardown cannot kill it mid-task. The parent returns immediately;
# tail the log it prints.
#
# Usage:
#   ./scripts/run-multi-model-benchmark.sh <model> [<model> ...] [options]
#
# Options (with defaults):
#   --dataset PATH        dataset YAML relative to benchmarks/ (mcp-gateway-registry)
#   --dollars-per-hour N  instance $/hr, recorded in the summary (0 = unset)
#   --agent NAME          coding agent that runs each task: claude (default), pi,
#                         omp, or kiro
#   --skill NAME          SWE skill: swe3 (default, single-agent) or swe2 (multi-agent)
#   --timeout-seconds N   per-task wall-clock timeout passed to run-e2e-benchmark.sh.
#                         Unset uses the harness default, which is tuned for the
#                         small g6e models; a frontier model on a 200K+ window is
#                         far slower per task and needs this raised (7200 = 2 h).
#   --no-detach           run in the foreground (do not self-detach)
#   --skip-judge          run the harness only; score later
#
# Models are REQUIRED. If none are given the script fails loudly and prints the
# full catalog (see below) with which models fit which machine.
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$BENCH_DIR")"
VLLM_DIR="$REPO_ROOT/self-hosted/vllm"
SCRATCH="$REPO_ROOT/.scratchpad"
mkdir -p "$SCRATCH"
LOG="$SCRATCH/multi-model-benchmark.log"

# --- Model registry ----------------------------------------------------------
# One row per known model:
#   served_name | HF repo | max_model_len | tool_parser | tp | fits (see key)
#              | gpu_mem_util | reasoning_parser | extra_args
# fits: "g6e.12xl" = runs on 4xL40S (this repo's default 184 GB node);
#       "p5en.48xl" = needs 8xH200 (or half of it at TP=4);
#       "g6e.48xl"  = needs 8xL40S (does not fit 4xL40S at a usable window).
#
# The last three fields are NOT cosmetic and must match the model's doc under
# self-hosted/vllm/models/ and the verified table in p5en-h200-cuda-fixes.md:
#   - gpu_mem_util: glm-5.2 at a 300K window and qwen3-coder-480b at 200K do not
#     fit their KV cache at 0.90 and abort at engine init.
#   - reasoning_parser: without it a thinking model's reasoning tokens leak into
#     the response text, which corrupts the artifacts the judge then scores.
#   - extra_args: --trust-remote-code is REQUIRED by kimi, glm-5.2, glm-5.3,
#     minimax and qwen3-coder-480b. vllm-serve.sh does NOT add it automatically
#     (an earlier version of this comment claimed it did); without it those five
#     fail to load. glm-5.3 carries more: vllm-serve.sh has no env var for the
#     KV-cache dtype or the speculative config, so its FP8 KV cache and 5-token
#     MTP drafting (both from the official vLLM recipe) ride in extra_args too.
#     Multi-word values are safe here: vllm-serve.sh splits them with `read -ra`
#     into an argv array, never eval.
#
# --trust-remote-code makes vLLM execute Python that ships inside the HF repo, in
# this process, at load time. It is accepted here only because those five
# architectures cannot load without it -- so treat the repo IDs above as part of
# the trust boundary: keep them pinned to the official vendor org, and do not add
# the flag to a row that does not genuinely need it or repoint a row at a fork.
REGISTRY=(
  "qwen3-coder-30b|Qwen/Qwen3-Coder-30B-A3B-Instruct|200000|qwen3_coder|4|g6e.12xl|0.90||"
  "qwen3.6-35b|Qwen/Qwen3.6-35B-A3B|200000|qwen3_coder|4|g6e.12xl|0.90||"
  "gemma-4-31b|google/gemma-4-31B-it|200000|gemma4|4|g6e.12xl|0.90||"
  "qwen3-32b|Qwen/Qwen3-32B|32768|hermes|4|g6e.12xl|0.90||"
  "qwen3-coder-next|Qwen/Qwen3-Coder-Next|16384|qwen3_coder|4|g6e.48xl|0.90||"
  "minimax-m2.5|MiniMaxAI/MiniMax-M2.5|196608|minimax_m2|4|p5en.48xl|0.92|minimax_m2|--trust-remote-code"
  "qwen3-coder-480b|Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8|200000|qwen3_coder|4|p5en.48xl|0.95||--trust-remote-code"
  "kimi-k2.7-code|moonshotai/Kimi-K2.7-Code|131072|kimi_k2|8|p5en.48xl|0.90|kimi_k2|--trust-remote-code"
  "glm-5.2|zai-org/GLM-5.2-FP8|300000|glm47|8|p5en.48xl|0.95|glm47|--trust-remote-code"
  "glm-5.3|zai-org/GLM-5.3|300000|glm47|8|p5en.48xl|0.95|glm47|--trust-remote-code --kv-cache-dtype fp8 --speculative-config.method mtp --speculative-config.num_speculative_tokens 5"
  "deepseek-v3.2|deepseek-ai/DeepSeek-V3.2|131072|deepseek_v32|8|p5en.48xl|0.90||"
  "devstral-2-123b|mistralai/Devstral-2-123B-Instruct-2512|262144|mistral|4|p5en.48xl|0.90||"
)

DATASET="dataset/mcp-gateway-registry.yaml"
DOLLARS_PER_HOUR="0"
AGENT="claude"
SKILL="swe3"
# Match runner.example.yaml's timeout_seconds (and runner_config.DEFAULT_TIMEOUT_SECONDS).
# Passed explicitly so the value in effect is visible in this script's log and does
# not silently change if someone edits their local, gitignored runner.yaml.
TIMEOUT_SECONDS="7200"
DETACH=1
SKIP_JUDGE=""
MODELS=()

info() { printf '\033[0;36m[info]\033[0m  %s\n' "$1"; }
die()  { printf '\033[0;31m[FAIL]\033[0m  %s\n' "$1" >&2; exit 1; }
say()  { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

_registry_row() {  # $1 served-name -> prints the row, or nothing
  local m
  for m in "${REGISTRY[@]}"; do [[ "${m%%|*}" == "$1" ]] && { echo "$m"; return 0; }; done
  return 1
}

print_catalog() {
  echo "Known models (served-name -- HF repo -- window -- fits):" >&2
  local m name repo win parser tp fits util rparser xargs
  for m in "${REGISTRY[@]}"; do
    IFS='|' read -r name repo win parser tp fits util rparser xargs <<< "$m"
    printf '  %-18s %-45s %8s  TP=%s  %s\n' "$name" "$repo" "$win" "$tp" "$fits" >&2
  done
  cat >&2 <<'EOF'

Fit key:
  g6e.12xl  -- runs on 4xL40S (184 GB), this repo's default node. Combine these
               freely in one invocation: qwen3-coder-30b qwen3.6-35b gemma-4-31b
               qwen3-32b. They are served one at a time (swapped), so any subset
               works on a single 4xL40S box.
  p5en.48xl -- needs 8xH200. minimax-m2.5, qwen3-coder-480b and devstral-2-123b use
               TP=4 (half the box); kimi-k2.7-code, glm-5.2, glm-5.3 and
               deepseek-v3.2 use TP=8 (whole box). All are served one at a time
               here, so group any p5en models together on an 8xH200 node. There is
               no 4xH200 instance type, so the TP=4 models still require a whole
               p5en. glm-5.2 and glm-5.3 are ~750 GB each and cannot be resident
               together, which is fine -- this script swaps them.
               glm-5.3 additionally needs vLLM >= 0.28.0 and transformers >= 5.15.
  g6e.48xl  -- qwen3-coder-next needs 8xL40S (384 GB) for a >=200K window; on a
               4xL40S it only fits ~16K and every agentic task fails on turn 1.

Guidance: pass only models that fit the machine you are on. This script serves
each model sequentially (one at a time), so you can list every model that fits
the node and it will benchmark them in turn.
EOF
}

# --- Parse args (models are positional; flags are --flag) --------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dataset)          DATASET="${2:?}"; shift 2 ;;
    --dollars-per-hour) DOLLARS_PER_HOUR="${2:?}"; shift 2 ;;
    --agent)            AGENT="${2:?}"; shift 2 ;;
    --skill)            SKILL="${2:?}"; shift 2 ;;
    --timeout-seconds)  TIMEOUT_SECONDS="${2:?}"; shift 2 ;;
    --no-detach)        DETACH=0; shift ;;
    --skip-judge)       SKIP_JUDGE="--skip-judge"; shift ;;
    -h|--help)          sed -n '4,37p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; print_catalog; exit 0 ;;
    -*)                 die "unknown flag: $1 (see --help)" ;;
    *)                  MODELS+=("$1"); shift ;;
  esac
done

# --- Validate the agent + skill ---------------------------------------------
case "$AGENT" in
  claude|pi|omp|kiro) ;;
  *) die "invalid --agent '$AGENT'. Must be one of: claude, pi, omp, kiro." ;;
esac
case "$SKILL" in
  swe2|swe3) ;;
  *) die "invalid --skill '$SKILL'. Must be one of: swe2, swe3." ;;
esac
# ${2:?} above only rejects an EMPTY value, so `--timeout-seconds --no-detach`
# would set the timeout to the literal string "--no-detach", silently swallow
# --no-detach, and hand garbage to run-e2e-benchmark.sh -- and this is the value
# that decides how long an unattended multi-hour run lets a hung task sit.
[[ "$TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] \
  || die "invalid --timeout-seconds '$TIMEOUT_SECONDS'. Must be a positive integer of seconds (e.g. 7200)."

# --- Fail loudly if no models, or an unknown model, was given ----------------
if [[ ${#MODELS[@]} -eq 0 ]]; then
  printf '\033[0;31m[FAIL]\033[0m  No models given. Pass one or more served-model-names.\n\n' >&2
  print_catalog
  exit 1
fi
for want in "${MODELS[@]}"; do
  _registry_row "$want" >/dev/null || {
    printf '\033[0;31m[FAIL]\033[0m  Unknown model: %s\n\n' "$want" >&2
    print_catalog
    exit 1
  }
done

# --- Self-detach so a session teardown cannot kill a multi-hour run ----------
if [[ "$DETACH" == "1" && -z "${MMB_DETACHED:-}" ]]; then
  MMB_DETACHED=1 setsid nohup "$0" --no-detach \
    ${SKIP_JUDGE:+--skip-judge} --dataset "$DATASET" --agent "$AGENT" --skill "$SKILL" \
    --timeout-seconds "$TIMEOUT_SECONDS" \
    --dollars-per-hour "$DOLLARS_PER_HOUR" "${MODELS[@]}" \
    >>"$SCRATCH/multi-model-benchmark.nohup.log" 2>&1 &
  echo "detached multi-model benchmark (pid $!)."
  echo "  models: ${MODELS[*]}"
  echo "  tail:   $LOG"
  exit 0
fi

SCOPE="$(basename "$DATASET" .yaml)"
# Harness folder level (claude -> claude-code, pi -> pi). Skill (swe2/swe3) is its
# own path level, so summarize/commit target <model>/<harness>/<skill>/<repo>.
HARNESS_SLUG="$(cd "$BENCH_DIR" && uv run python -c "import sys; sys.path.insert(0,'scripts'); from runner_config import HARNESS_SLUGS; print(HARNESS_SLUGS['$AGENT'])")"

# On an 8xH200 (p5en) DLAMI the FP8 models JIT-compile DeepGemm/FlashInfer kernels
# at engine init, and that link step fails on the stock environment: there is no
# /usr/local/cuda (nvcc lives in /opt/pytorch/cuda), ninja is only inside the vLLM
# venv, and FlashInfer's link command hardcodes -L$CUDA_HOME/lib64[/stubs], which
# the DLAMI does not ship. vllm-serve.sh inherits our environment, so export the
# fixes here rather than requiring the caller to remember them. Full rationale:
# .claude/skills/vllm-setup/p5en-h200-cuda-fixes.md (Fixes 1-3).
#
# No-op on any other node: keyed on 8 GPUs reporting as H200, and every step is
# idempotent, so a re-run costs nothing.
_apply_p5en_cuda_env() {
  local gpus h200
  gpus="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | wc -l)"
  h200="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | grep -c H200 || true)"
  if [[ "$gpus" -ne 8 || "$h200" -ne 8 ]]; then
    say "  (not an 8xH200 node: skipping the p5en CUDA fixes)"
    return 0
  fi

  # The venv and caches live on the big NVMe on this node -- the 29 GB root disk
  # cannot hold torch, the CUDA wheels and the weights.
  local nvme=/opt/dlami/nvme
  export VLLM_ENV="${VLLM_ENV:-$nvme/vllm-env}"
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$nvme/uv-cache}"
  export TMPDIR="${TMPDIR:-$nvme/tmp}"
  export CUDA_HOME="${CUDA_HOME:-/opt/pytorch/cuda}"
  export PATH="$VLLM_ENV/bin:$CUDA_HOME/bin:$PATH"                     # Fix 1: ninja + nvcc

  # Fixes 2 + 3. The link dir lives INSIDE $VLLM_ENV, not directly under $nvme:
  # /opt/dlami/nvme is mode 1777 (world-writable, like /tmp) and is wiped on every
  # instance stop, so a path created there does not pre-exist on a fresh boot --
  # another local user could create it first, or as a symlink to a directory they
  # own, and our ln -sf would then populate a directory they control. That
  # directory is prepended to LD_LIBRARY_PATH for every vLLM process, which turns
  # it into arbitrary shared-library injection into the serving process. $VLLM_ENV
  # is owned by us and not world-writable, so it closes that window.
  local linkdir="$VLLM_ENV/cuda-link"
  local venv_cu13="$VLLM_ENV/lib/python3.12/site-packages/nvidia/cu13/lib"
  mkdir -p "$linkdir"
  ln -sf "$venv_cu13/libcudart.so.13"           "$linkdir/libcudart.so"
  ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so.1 "$linkdir/libcuda.so"
  ln -sf "$venv_cu13/libnvrtc.so.13"            "$linkdir/libnvrtc.so"

  # Fix 3: create and populate the lib64[/stubs] that FlashInfer's -L expects.
  if mkdir -p "$CUDA_HOME/lib64/stubs" 2>/dev/null; then
    ln -sf "$venv_cu13/libcudart.so.13"           "$CUDA_HOME/lib64/libcudart.so"
    ln -sf "$venv_cu13/libnvrtc.so.13"            "$CUDA_HOME/lib64/libnvrtc.so"
    ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so.1 "$CUDA_HOME/lib64/libcuda.so"
    ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so.1 "$CUDA_HOME/lib64/stubs/libcuda.so"
  else
    say "  WARN could not write $CUDA_HOME/lib64 (needs sudo); FP8 JIT may fail with 'cannot find -lnvrtc'"
  fi

  export LIBRARY_PATH="$linkdir:$CUDA_HOME/lib64:$CUDA_HOME/lib64/stubs:$venv_cu13:/usr/lib/x86_64-linux-gnu:${LIBRARY_PATH:-}"
  export LD_LIBRARY_PATH="$linkdir:$CUDA_HOME/lib64:$venv_cu13:/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
  say "  p5en CUDA env applied (VLLM_ENV=$VLLM_ENV, CUDA_HOME=$CUDA_HOME)"
}

# A frontier FP8 model is 466 GB - 1 TB of weights. On a COLD HF cache the first
# boot is dominated by the download, not the load: at ~1 GB/s that alone is 8-17
# minutes, and slower without an HF token, before ~4 min of shard loading,
# torch.compile and CUDA-graph capture. The old 15-minute ceiling here meant every
# frontier model was declared "never ready" and skipped on its first run. Budget
# 3 hours, and log progress so a stall is distinguishable from a slow download.
wait_ready() {  # $1 served-name
  local name="$1" i served waited
  for i in $(seq 1 1080); do  # up to ~3 h at 10 s per attempt
    served="$(curl -s -m 5 http://127.0.0.1:8000/v1/models 2>/dev/null \
      | python3 -c 'import sys,json;print(",".join(m["id"] for m in json.load(sys.stdin).get("data",[])))' 2>/dev/null || true)"
    [[ ",$served," == *",$name,"* ]] && { say "  $name ready"; return 0; }
    # Every 5 min, report elapsed time and the cache size so a download in
    # progress is visibly distinct from a hung engine init.
    if (( i % 30 == 0 )); then
      waited=$(( i / 6 ))
      say "  still waiting for $name (${waited} min; HF cache $(du -sh "${HF_HOME:-/opt/dlami/nvme/hf-cache}" 2>/dev/null | cut -f1 || echo '?'))"
    fi
    sleep 10
  done
  return 1
}

stop_all_vllm() {
  ( cd "$VLLM_DIR/scripts" && ./vllm-serve.sh --stop >/dev/null 2>&1 || true )
  local pid
  for pid in $(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null); do
    kill -9 "$pid" 2>/dev/null || true
  done
  pkill -9 -f "VLLM::EngineCore" 2>/dev/null || true
  pkill -9 -f "vllm serve" 2>/dev/null || true
  # Wait until GPUs are fully released (up to 60s).
  local i
  for i in $(seq 1 12); do
    local count
    count="$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | wc -l)"
    [[ "$count" -eq 0 ]] && break
    sleep 5
  done
}

say "=== START multi-model benchmark: ${MODELS[*]} (dataset=$SCOPE) ==="
command -v uv >/dev/null 2>&1 || die "uv not on PATH"
_apply_p5en_cuda_env

for want in "${MODELS[@]}"; do
  IFS='|' read -r SLUG REPO MML PARSER TP FITS GPU_UTIL RPARSER XARGS <<< "$(_registry_row "$want")"
  GPU_UTIL="${GPU_UTIL:-0.90}"
  say "===== MODEL: $SLUG (fits: $FITS) ====="

  # Serve unless already serving this exact model.
  cur="$(curl -s -m 5 http://127.0.0.1:8000/v1/models 2>/dev/null | python3 -c 'import sys,json;print(",".join(m["id"] for m in json.load(sys.stdin).get("data",[])))' 2>/dev/null || true)"
  if [[ ",$cur," == *",$SLUG,"* ]]; then
    say "  already serving $SLUG"
  else
    say "  stopping current model + freeing GPUs"
    stop_all_vllm
    say "  serving $SLUG ($REPO, tp=$TP, mml=$MML, parser=$PARSER, util=$GPU_UTIL${RPARSER:+, reasoning=$RPARSER}${XARGS:+, extra='$XARGS'})"
    ( cd "$VLLM_DIR/scripts" && MODEL="$REPO" SERVED_NAME="$SLUG" TP="$TP" PORT=8000 \
        MAX_MODEL_LEN="$MML" GPU_MEM_UTIL="$GPU_UTIL" TOOL_PARSER="$PARSER" \
        REASONING_PARSER="$RPARSER" EXTRA_ARGS="$XARGS" \
        ./vllm-serve.sh >"$SCRATCH/serve-$SLUG.log" 2>&1 ) &
    sleep 20
  fi
  wait_ready "$SLUG" || { say "  SKIP $SLUG: server never became ready (see $SCRATCH/serve-$SLUG.log)"; continue; }

  WIN="$(curl -s -m 5 http://127.0.0.1:8000/v1/models | python3 -c 'import sys,json;d=json.load(sys.stdin).get("data",[]);print(next((m.get("max_model_len") for m in d if m.get("max_model_len")),0))' 2>/dev/null || echo 0)"
  say "  served window: $WIN"
  if [ "$WIN" -lt 64000 ]; then
    say "  SKIP $SLUG: window $WIN too small for agentic tasks (needs a larger-VRAM node -- see the model doc)"
    continue
  fi

  ( cd "$VLLM_DIR/scripts" && ./vllm-metrics.sh start >/dev/null 2>&1 || true )

  say "  running e2e benchmark for $SLUG (per-task timeout ${TIMEOUT_SECONDS}s) ..."
  ( cd "$BENCH_DIR" && ./scripts/run-e2e-benchmark.sh --agent "$AGENT" --skill "$SKILL" --provider vllm --model "$SLUG" \
      --timeout-seconds "$TIMEOUT_SECONDS" \
      --dataset "$DATASET" --yes $SKIP_JUDGE >"$SCRATCH/e2e-$SLUG.log" 2>&1 )
  say "  e2e done for $SLUG (exit $?)"

  ( cd "$VLLM_DIR/scripts" && ./vllm-metrics.sh stop >/dev/null 2>&1 || true )
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  [ -f "$VLLM_DIR/benchmark-output/vllm-metrics.duckdb" ] && \
    mv "$VLLM_DIR/benchmark-output/vllm-metrics.duckdb" \
       "$VLLM_DIR/benchmark-output/vllm-metrics_${SLUG}_${SCOPE}_${TS}.duckdb" 2>/dev/null || true

  TARGET="swe-benchmark-data/$SLUG/$HARNESS_SLUG/$SKILL/$SCOPE"
  say "  summarizing $SLUG ..."
  ( cd "$BENCH_DIR" && uv run python scripts/summarize_run.py \
      --folder "$TARGET" --run-date "$(date -u +%Y-%m-%d)" \
      >>"$SCRATCH/e2e-$SLUG.log" 2>&1 ) || say "  WARN summarize failed for $SLUG"

  # Commit the run-summary plus the now-tracked per-task metrics.json/eval.json
  # (the six large artifacts stay gitignored).
  #
  # AGENTS.md forbids committing to main, and this loop pushes unattended for
  # hours -- so on main it stops at the commit and leaves the work staged rather
  # than pushing. Results are never lost either way: the artifacts are on disk and
  # the next run does not touch a different model's folder.
  ( cd "$REPO_ROOT"
    BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    git add "benchmarks/$TARGET/run-summary.json" "benchmarks/$TARGET/run-summary.md" \
            "benchmarks/$TARGET"/*/metrics.json "benchmarks/$TARGET"/*/eval.json 2>/dev/null
    if git diff --cached --quiet; then
      exit 0
    fi
    git commit -q -m "$SLUG ($AGENT, $SKILL): benchmark run on $SCOPE (implementation + judge scores)"
    if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
      echo "on $BRANCH: committed locally, NOT pushing (open a PR instead)"
    else
      git pull --rebase -q 2>/dev/null; git push -q 2>/dev/null
    fi
  ) && say "  committed $SLUG run" || say "  WARN commit failed for $SLUG"

  # Remove any stray untracked root-level .md files a /swe2 task may have misplaced.
  ( cd "$REPO_ROOT" && for f in $(git ls-files --others --exclude-standard -- '*.md' | grep -vE '/'); do
       say "  removing stray root file: $f"; rm -f "$f"; done ) || true

  say "===== DONE: $SLUG ====="
done
say "=== ALL DONE: ${MODELS[*]} ==="
