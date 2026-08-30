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
#                         omp (oh-my-pi), or kiro
#   --skill NAME          SWE skill: swe3 (default, single-agent) or swe2 (multi-agent)
#   --no-detach           run in the foreground (do not self-detach)
#   --judge-mode MODE     when to score: inline (default, judge after each model,
#                         GPU idle while it runs), async (judge in the background
#                         while the NEXT model generates -- the judge is a Bedrock
#                         call and uses no GPU, so the two overlap for free), or
#                         skip (harness only; score later)
#   --skip-judge          deprecated alias for --judge-mode skip
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
#   served_name | HF repo | max_model_len | tool_parser | tp | fits | extra_env
# fits: "g6e.12xl" = runs on 4xL40S (this repo's default 184 GB node);
#       "p5en.48xl" = needs 8xH200 (or half of it at TP=4);
#       "g6e.48xl"  = needs 8xL40S (does not fit 4xL40S at a usable window).
# extra_env: optional, space-separated KEY=VALUE pairs exported into the
# vllm-serve.sh environment for model-specific knobs the other columns cannot
# express (ROPE_SCALING, MAX_NUM_SEQS, EXTRA_ARGS). The field is word-split, so
# each VALUE must contain no spaces (use the --flag=value form) and no glob
# characters (* ? [), which the split would expand against the working dir.
# Never put a secret here (HF_TOKEN and friends): serve output is teed to a log
# under .scratchpad/. Export those in the environment instead.
# Other serve flags (trust-remote-code) come from the model doc; vllm-serve.sh
# applies trust-remote-code automatically where required.
REGISTRY=(
  "qwen3-coder-30b|Qwen/Qwen3-Coder-30B-A3B-Instruct|200000|qwen3_coder|4|g6e.12xl|"
  "qwen3.6-35b|Qwen/Qwen3.6-35B-A3B|200000|qwen3_coder|4|g6e.12xl|"
  "gemma-4-31b|google/gemma-4-31B-it|200000|gemma4|4|g6e.12xl|"
  # Qwen3.8-27B is served here as BF16 at TP=4 (~56 GB over 4 GPUs), not the FP8
  # single-GPU config in its model doc -- BF16 matches how every other model on
  # this node is benchmarked. MAX_NUM_SEQS caps decode sequences to the hybrid
  # model's Mamba state-cache pool, and the patched chat template accepts the
  # reasoning_effort value agents send (the stock one 500s on it).
  "qwen3.8-27b|Qwen/Qwen3.8-27B|200000|qwen3_coder|4|g6e.12xl|MAX_NUM_SEQS=32 EXTRA_ARGS=--chat-template=$VLLM_DIR/config/qwen3.8-27b-chat-template.jinja"
  # Qwen3-32B is 32768-native, below the 64000 agentic floor enforced below, so
  # it needs YaRN (factor 4 -> 131072) to be benchmarkable at all.
  "qwen3-32b|Qwen/Qwen3-32B|131072|hermes|4|g6e.12xl|ROPE_SCALING={\"rope_type\":\"yarn\",\"factor\":4.0,\"original_max_position_embeddings\":32768}"
  "qwen3-coder-next|Qwen/Qwen3-Coder-Next|16384|qwen3_coder|4|g6e.48xl|MAX_NUM_SEQS=128"
  "minimax-m2.5|MiniMaxAI/MiniMax-M2.5|196608|minimax_m2|4|p5en.48xl|"
  "qwen3-coder-480b|Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8|200000|qwen3_coder|4|p5en.48xl|"
  "kimi-k2.7-code|moonshotai/Kimi-K2.7-Code|131072|kimi_k2|8|p5en.48xl|"
  "glm-5.2|zai-org/GLM-5.2-FP8|300000|glm47|8|p5en.48xl|"
  "devstral-2-123b|mistralai/Devstral-2-123B-Instruct-2512|262144|mistral|8|p5en.48xl|"
)

DATASET="dataset/mcp-gateway-registry.yaml"
DOLLARS_PER_HOUR="0"
AGENT="claude"
SKILL="swe3"
DETACH=1
JUDGE_MODE="inline"
MODELS=()

# Background judge jobs launched by --judge-mode async, as "pid:model-slug".
JUDGE_PIDS=()
# How many judge jobs may run at once. Keep this at 1: codex_judge.py's
# _ensure_checkout is check-then-act with no locking, and every model in a batch
# judges the SAME dataset, so two concurrent judges resolve to the same
# /tmp/swe-judge-repos checkout and can clone over (or rmtree) each other. One
# in-flight job is enough to hide judging behind the next model's generation,
# which takes hours. Raising this REQUIRES a lock in codex_judge.py first.
JUDGE_MAX_PARALLEL=1

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
  local m name repo win parser tp fits extra_env
  for m in "${REGISTRY[@]}"; do
    IFS='|' read -r name repo win parser tp fits extra_env <<< "$m"
    printf '  %-18s %-45s %8s  %s\n' "$name" "$repo" "$win" "$fits" >&2
  done
  cat >&2 <<'EOF'

Fit key:
  g6e.12xl  -- runs on 4xL40S (184 GB), this repo's default node. Combine these
               freely in one invocation: qwen3-coder-30b qwen3.6-35b gemma-4-31b
               qwen3.8-27b qwen3-32b. They are served one at a time (swapped), so
               any subset works on a single 4xL40S box.
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
    --skill)            SKILL="${2:?}"; shift 2 ;;
    --no-detach)        DETACH=0; shift ;;
    --judge-mode)       JUDGE_MODE="${2:?}"; shift 2 ;;
    --skip-judge)       JUDGE_MODE="skip"; shift ;;
    -h|--help)          sed -n '4,42p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; print_catalog; exit 0 ;;
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
case "$JUDGE_MODE" in
  inline|async|skip) ;;
  *) die "invalid --judge-mode '$JUDGE_MODE'. Must be one of: inline, async, skip." ;;
esac

# In async mode the e2e script is told to skip the judge, which also skips ITS
# codex pre-flight -- so a missing or misconfigured codex would surface hours
# later, inside a background job, in a scratchpad log. Prove the judge here
# instead. Working AWS credentials are NOT sufficient: an unconfigured codex
# ignores them and 401s against api.openai.com (see
# benchmarks/docs/agent-cli-bedrock-setup.md).
if [[ "$JUDGE_MODE" == "async" ]]; then
  command -v codex >/dev/null 2>&1 \
    || die "codex CLI not found on PATH, but --judge-mode async needs it to score each model. Install codex, or use --judge-mode skip."
  timeout 120 codex exec --sandbox read-only --skip-git-repo-check "Reply with exactly: JUDGE OK" >/dev/null 2>&1 \
    || die "codex is installed but a test call failed. It must be wired to Amazon Bedrock before a long run (see benchmarks/docs/agent-cli-bedrock-setup.md). Re-run with --judge-mode skip to score later."
fi

# The e2e script judges inline unless told not to. async does its own judging in
# the background, so the inline pass must be suppressed there too.
E2E_SKIP_JUDGE=""
[[ "$JUDGE_MODE" != "inline" ]] && E2E_SKIP_JUDGE="--skip-judge"

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
    --judge-mode "$JUDGE_MODE" --dataset "$DATASET" --agent "$AGENT" --skill "$SKILL" \
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

# --- Judging, summarizing and committing one model ---------------------------
# Split out so --judge-mode async can run the whole tail (judge -> summarize ->
# commit) in the background while the next model generates. The commit MUST stay
# inside that unit: committing before the judge finishes writes a run-summary.json
# with num_scored 0, which is what every downstream report and chart reads.

_commit_run() {  # $1 model-slug, $2 target dir relative to benchmarks/
  local slug="$1" target="$2"
  # flock because a background judge job can overlap with the main loop's own git
  # usage (the stray-file cleanup below), and with a future higher parallelism.
  # Note the async path commits while the NEXT model is generating into this same
  # working tree. That is safe for what the harness writes (its six large
  # artifacts are gitignored, and each model owns its own folder), but a
  # pull --rebase here does touch tracked files, so keep the lock and keep the
  # committed set narrow.
  ( flock 9
    cd "$REPO_ROOT" || exit 1
    git add "benchmarks/$target/run-summary.json" "benchmarks/$target/run-summary.md" \
            "benchmarks/$target"/*/metrics.json "benchmarks/$target"/*/eval.json 2>/dev/null
    git diff --cached --quiet || git commit -q -m "$slug ($AGENT, $SKILL): benchmark run on $SCOPE (implementation + judge scores)"
    git pull --rebase -q 2>/dev/null; git push -q 2>/dev/null
  ) 9>"$SCRATCH/.git.lock"
}

summarize_and_commit() {  # $1 model-slug, $2 target -- inline/skip path
  local slug="$1" target="$2"
  say "  summarizing $slug ..."
  ( cd "$BENCH_DIR" && uv run python scripts/summarize_run.py \
      --folder "$target" --run-date "$(date -u +%Y-%m-%d)" \
      >>"$SCRATCH/e2e-$slug.log" 2>&1 ) || say "  WARN summarize failed for $slug"
  _commit_run "$slug" "$target" && say "  committed+pushed $slug run" \
    || say "  WARN commit failed for $slug"
}

judge_and_commit() {  # $1 model-slug, $2 target -- async path, runs backgrounded
  local slug="$1" target="$2"
  # Distinct exit codes so the end-of-run report names the stage that failed.
  ( cd "$BENCH_DIR/scripts" && uv run python codex_judge.py --recursive --no-overwrite \
      --folder "../$target" ) || return 1
  ( cd "$BENCH_DIR" && uv run python scripts/summarize_run.py \
      --folder "$target" --run-date "$(date -u +%Y-%m-%d)" ) || return 2
  _commit_run "$slug" "$target" || return 3
  return 0
}

_judges_running() {  # -> count of live background judge jobs
  local entry running=0
  [ "${#JUDGE_PIDS[@]}" -eq 0 ] && { echo 0; return 0; }
  for entry in "${JUDGE_PIDS[@]}"; do
    kill -0 "${entry%%:*}" 2>/dev/null && running=$((running + 1))
  done
  echo "$running"
}

_wait_for_judge_slot() {
  # Counts tracked PIDs rather than `jobs -rp`, which would also match the
  # backgrounded vllm-serve subshell and deadlock while a model is serving.
  while [ "$(_judges_running)" -ge "$JUDGE_MAX_PARALLEL" ]; do
    say "  waiting for a judge slot (${JUDGE_MAX_PARALLEL} in flight) ..."
    sleep 30
  done
}

_kill_judges() {
  local entry
  [ "${#JUDGE_PIDS[@]}" -eq 0 ] && return 0
  for entry in "${JUDGE_PIDS[@]}"; do kill "${entry%%:*}" 2>/dev/null || true; done
}

# A half-judged model with no summary is worse than an unjudged one, because
# codex_judge.py --no-overwrite makes the resume non-obvious. Stop cleanly and
# say so rather than orphaning jobs against a torn-down environment.
trap '_kill_judges; say "interrupted -- background judging stopped"; exit 130' INT TERM

say "=== START multi-model benchmark: ${MODELS[*]} (dataset=$SCOPE) ==="
command -v uv >/dev/null 2>&1 || die "uv not on PATH"

for want in "${MODELS[@]}"; do
  IFS='|' read -r SLUG REPO MML PARSER TP FITS EXTRA_ENV <<< "$(_registry_row "$want")"
  say "===== MODEL: $SLUG (fits: $FITS) ====="

  # Serve unless already serving this exact model.
  cur="$(curl -s -m 5 http://127.0.0.1:8000/v1/models 2>/dev/null | python3 -c 'import sys,json;print(",".join(m["id"] for m in json.load(sys.stdin).get("data",[])))' 2>/dev/null || true)"
  if [[ ",$cur," == *",$SLUG,"* ]]; then
    say "  already serving $SLUG"
  else
    say "  stopping current model + freeing GPUs"
    stop_all_vllm
    say "  serving $SLUG ($REPO, tp=$TP, mml=$MML, parser=$PARSER)"
    # shellcheck disable=SC2086 -- EXTRA_ENV is deliberately word-split into
    # separate KEY=VALUE arguments for env; its values contain no spaces.
    ( cd "$VLLM_DIR/scripts" && env MODEL="$REPO" SERVED_NAME="$SLUG" TP="$TP" PORT=8000 \
        MAX_MODEL_LEN="$MML" GPU_MEM_UTIL=0.90 TOOL_PARSER="$PARSER" $EXTRA_ENV \
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
  # shellcheck disable=SC2086 -- E2E_SKIP_JUDGE is a single flag or empty.
  ( cd "$BENCH_DIR" && ./scripts/run-e2e-benchmark.sh --agent "$AGENT" --skill "$SKILL" --provider vllm --model "$SLUG" \
      --dataset "$DATASET" --yes $E2E_SKIP_JUDGE >"$SCRATCH/e2e-$SLUG.log" 2>&1 )
  say "  e2e done for $SLUG (exit $?)"

  ( cd "$VLLM_DIR/scripts" && ./vllm-metrics.sh stop >/dev/null 2>&1 || true )
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  [ -f "$VLLM_DIR/benchmark-output/vllm-metrics.duckdb" ] && \
    mv "$VLLM_DIR/benchmark-output/vllm-metrics.duckdb" \
       "$VLLM_DIR/benchmark-output/vllm-metrics_${SLUG}_${SCOPE}_${TS}.duckdb" 2>/dev/null || true

  TARGET="swe-benchmark-data/$SLUG/$HARNESS_SLUG/$SKILL/$SCOPE"
  # Commit covers the run-summary plus the now-tracked per-task
  # metrics.json/eval.json (the six large artifacts stay gitignored).
  if [[ "$JUDGE_MODE" == "async" ]]; then
    # The judge is a Bedrock call per task and touches no GPU, so it overlaps
    # with the next model's generation instead of leaving the GPUs idle.
    _wait_for_judge_slot
    judge_and_commit "$SLUG" "$TARGET" >>"$SCRATCH/judge-$SLUG.log" 2>&1 &
    JUDGE_PIDS+=("$!:$SLUG")
    say "  judging $SLUG in the background (pid $!); the next model starts now"
  else
    summarize_and_commit "$SLUG" "$TARGET"
  fi

  # Remove any stray untracked root-level .md files a /swe2 task may have misplaced.
  ( cd "$REPO_ROOT" && for f in $(git ls-files --others --exclude-standard -- '*.md' | grep -vE '/'); do
       say "  removing stray root file: $f"; rm -f "$f"; done ) || true

  say "===== DONE: $SLUG ====="
done

# Every background judge must finish before the run reports completion --
# otherwise the log says ALL DONE while scoring is still in flight, and a failed
# job is never surfaced at all.
if [ "${#JUDGE_PIDS[@]}" -gt 0 ]; then
  say "waiting for ${#JUDGE_PIDS[@]} background judge job(s) ..."
  JUDGE_FAILED=()
  for entry in "${JUDGE_PIDS[@]}"; do
    pid="${entry%%:*}"; slug="${entry#*:}"
    if wait "$pid"; then
      say "  judged+committed $slug"
    else
      rc=$?
      case "$rc" in
        1) stage="judge" ;;
        2) stage="summarize" ;;
        3) stage="commit" ;;
        *) stage="unknown (exit $rc)" ;;
      esac
      JUDGE_FAILED+=("$slug ($stage)")
      say "  WARN $stage FAILED for $slug -- see $SCRATCH/judge-$slug.log"
    fi
  done
  if [ "${#JUDGE_FAILED[@]}" -gt 0 ]; then
    say "=== ALL DONE: ${MODELS[*]} -- but judging FAILED for: ${JUDGE_FAILED[*]} ==="
    exit 1
  fi
fi
say "=== ALL DONE: ${MODELS[*]} ==="
