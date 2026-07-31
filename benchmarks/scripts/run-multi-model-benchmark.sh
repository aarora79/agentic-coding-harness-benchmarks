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
# metrics snapshot, writes RUN-SUMMARY.{json,md}, and commits the RUN-SUMMARY to
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
#   --agent NAME          coding agent that runs each task: claude (default) or pi
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
# fits: "g6e.12xl" = runs on 4xL40S (this repo's default 184 GB node);
#       "p5en.48xl" = needs 8xH200 (or half of it at TP=4);
#       "g6e.48xl"  = needs 8xL40S (does not fit 4xL40S at a usable window).
# Extra serve flags (trust-remote-code, max_num_seqs) come from the model doc;
# vllm-serve.sh applies trust-remote-code automatically where required.
REGISTRY=(
  "qwen3-coder-30b|Qwen/Qwen3-Coder-30B-A3B-Instruct|200000|qwen3_coder|4|g6e.12xl"
  "qwen3.6-35b|Qwen/Qwen3.6-35B-A3B|200000|qwen3_coder|4|g6e.12xl"
  "gemma-4-31b|google/gemma-4-31B-it|200000|gemma4|4|g6e.12xl"
  "qwen3-32b|Qwen/Qwen3-32B|32768|hermes|4|g6e.12xl"
  "qwen3-coder-next|Qwen/Qwen3-Coder-Next|16384|qwen3_coder|4|g6e.48xl"
  "minimax-m2.5|MiniMaxAI/MiniMax-M2.5|196608|minimax_m2|4|p5en.48xl"
  "qwen3-coder-480b|Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8|200000|qwen3_coder|4|p5en.48xl"
  "kimi-k2.7-code|moonshotai/Kimi-K2.7-Code|131072|kimi_k2|8|p5en.48xl"
  "glm-5.2|zai-org/GLM-5.2-FP8|300000|glm47|8|p5en.48xl"
  "devstral-2-123b|mistralai/Devstral-2-123B-Instruct-2512|262144|mistral|8|p5en.48xl"
)

DATASET="dataset/mcp-gateway-registry.yaml"
DOLLARS_PER_HOUR="0"
AGENT="claude"
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
  local m name repo win parser tp fits
  for m in "${REGISTRY[@]}"; do
    IFS='|' read -r name repo win parser tp fits <<< "$m"
    printf '  %-18s %-45s %8s  %s\n' "$name" "$repo" "$win" "$fits" >&2
  done
  cat >&2 <<'EOF'

Fit key:
  g6e.12xl  -- runs on 4xL40S (184 GB), this repo's default node. Combine these
               freely in one invocation: qwen3-coder-30b qwen3.6-35b gemma-4-31b
               qwen3-32b. They are served one at a time (swapped), so any subset
               works on a single 4xL40S box.
  p5en.48xl -- needs 8xH200. minimax-m2.5 and qwen3-coder-480b use TP=4 (half the
               box); kimi-k2.7-code and glm-5.2 use TP=8 (whole box). All are
               served one at a time here, so group any p5en models together on
               an 8xH200 node.
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
    --no-detach)        DETACH=0; shift ;;
    --skip-judge)       SKIP_JUDGE="--skip-judge"; shift ;;
    -h|--help)          sed -n '4,37p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; print_catalog; exit 0 ;;
    -*)                 die "unknown flag: $1 (see --help)" ;;
    *)                  MODELS+=("$1"); shift ;;
  esac
done

# --- Validate the agent -----------------------------------------------------
case "$AGENT" in
  claude|pi) ;;
  *) die "invalid --agent '$AGENT'. Must be one of: claude, pi." ;;
esac

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
    ${SKIP_JUDGE:+--skip-judge} --dataset "$DATASET" --agent "$AGENT" \
    --dollars-per-hour "$DOLLARS_PER_HOUR" "${MODELS[@]}" \
    >>"$SCRATCH/multi-model-benchmark.nohup.log" 2>&1 &
  echo "detached multi-model benchmark (pid $!)."
  echo "  models: ${MODELS[*]}"
  echo "  tail:   $LOG"
  exit 0
fi

SCOPE="$(basename "$DATASET" .yaml)"

wait_ready() {  # $1 served-name
  local name="$1" i served
  for i in $(seq 1 90); do  # up to ~15 min (large FP8 downloads/boots)
    served="$(curl -s -m 5 http://127.0.0.1:8000/v1/models 2>/dev/null \
      | python3 -c 'import sys,json;print(",".join(m["id"] for m in json.load(sys.stdin).get("data",[])))' 2>/dev/null || true)"
    [[ ",$served," == *",$name,"* ]] && { say "  $name ready"; return 0; }
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

for want in "${MODELS[@]}"; do
  IFS='|' read -r SLUG REPO MML PARSER TP FITS <<< "$(_registry_row "$want")"
  say "===== MODEL: $SLUG (fits: $FITS) ====="

  # Serve unless already serving this exact model.
  cur="$(curl -s -m 5 http://127.0.0.1:8000/v1/models 2>/dev/null | python3 -c 'import sys,json;print(",".join(m["id"] for m in json.load(sys.stdin).get("data",[])))' 2>/dev/null || true)"
  if [[ ",$cur," == *",$SLUG,"* ]]; then
    say "  already serving $SLUG"
  else
    say "  stopping current model + freeing GPUs"
    stop_all_vllm
    say "  serving $SLUG ($REPO, tp=$TP, mml=$MML, parser=$PARSER)"
    ( cd "$VLLM_DIR/scripts" && MODEL="$REPO" SERVED_NAME="$SLUG" TP="$TP" PORT=8000 \
        MAX_MODEL_LEN="$MML" GPU_MEM_UTIL=0.90 TOOL_PARSER="$PARSER" \
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

  say "  running e2e benchmark for $SLUG ..."
  ( cd "$BENCH_DIR" && ./scripts/run-e2e-benchmark.sh --agent "$AGENT" --provider vllm --model "$SLUG" \
      --dataset "$DATASET" --yes $SKIP_JUDGE >"$SCRATCH/e2e-$SLUG.log" 2>&1 )
  say "  e2e done for $SLUG (exit $?)"

  ( cd "$VLLM_DIR/scripts" && ./vllm-metrics.sh stop >/dev/null 2>&1 || true )
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  [ -f "$VLLM_DIR/benchmark-output/vllm-metrics.duckdb" ] && \
    mv "$VLLM_DIR/benchmark-output/vllm-metrics.duckdb" \
       "$VLLM_DIR/benchmark-output/vllm-metrics_${SLUG}_${SCOPE}_${TS}.duckdb" 2>/dev/null || true

  say "  summarizing $SLUG ..."
  ( cd "$BENCH_DIR" && uv run python scripts/summarize_run.py \
      --folder "swe-benchmark-data/$SLUG/$SCOPE" --run-date "$(date -u +%Y-%m-%d)" \
      >>"$SCRATCH/e2e-$SLUG.log" 2>&1 ) || say "  WARN summarize failed for $SLUG"

  # Commit the RUN-SUMMARY (only the scrubbed rollup is tracked; task folders are gitignored).
  ( cd "$REPO_ROOT"
    git add "benchmarks/swe-benchmark-data/$SLUG/$SCOPE/RUN-SUMMARY.json" \
            "benchmarks/swe-benchmark-data/$SLUG/$SCOPE/RUN-SUMMARY.md" 2>/dev/null
    git diff --cached --quiet || git commit -q -m "$SLUG: /swe2 benchmark run on $SCOPE (implementation + judge scores)"
    git pull --rebase -q 2>/dev/null; git push -q 2>/dev/null
  ) && say "  committed+pushed $SLUG RUN-SUMMARY" || say "  WARN commit failed for $SLUG"

  # Remove any stray untracked root-level .md files a /swe2 task may have misplaced.
  ( cd "$REPO_ROOT" && for f in $(git ls-files --others --exclude-standard -- '*.md' | grep -vE '/'); do
       say "  removing stray root file: $f"; rm -f "$f"; done ) || true

  say "===== DONE: $SLUG ====="
done
say "=== ALL DONE: ${MODELS[*]} ==="
