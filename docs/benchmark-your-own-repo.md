# Benchmark your own repositories

The harness works against any GitHub repository. Name your own repos in a dataset YAML and the models, judge and cost math are the ones behind every published result here.

## Datasets

A dataset is a single YAML file: a metadata header plus a list of tasks, each pointing at a GitHub repo and a problem. Two datasets ship in [benchmarks/dataset/](../benchmarks/dataset/):

- [hello-world.yaml](../benchmarks/dataset/hello-world.yaml) -- a trivial sanity dataset (the [octocat/Hello-World](https://github.com/octocat/Hello-World) repo) for kicking the tires of a new model or endpoint.
- [mcp-gateway-registry.yaml](../benchmarks/dataset/mcp-gateway-registry.yaml) -- the reference dataset, whose tasks are drawn from real upstream issues in [agentic-community/mcp-gateway-registry](https://github.com/agentic-community/mcp-gateway-registry).

**Nothing in the harness is specific to a particular repository.** Adding your own benchmark dataset is just writing another YAML file in the same format -- point tasks at any public repo and pinned ref. The dataset format is documented in the [harness reference](../benchmarks/docs/harness-reference.md#the-dataset).

### What do I do with this?

The point of this repo is to help you **pick the right coding agent and model for your tasks** -- the pairing that lands the quality you need at the cost and latency you can live with, instead of defaulting to the most expensive option. There are two ways to get there:

1. **Use the frontier we already published.** The cost/quality results here (across harnesses, models, and hosting paths) are a strong, ready-made baseline -- read the [harness comparison](agentic-coding-swe-comparison-swe3.md) and per-harness docs and pick from the models on the frontier. No runs of your own required.
2. **Build your own frontier on your own code.** When you want numbers on **work that looks like yours** rather than our example repo, use the benchmarking harness in this repo: write a dataset YAML pointing at your repositories and run it -- the models, harnesses, judge, and cost math are identical to what produced the results above. This is the rest of this section.

**Then put it in front of developers.** [`swe-router`](../vend/swe-router/) reads whichever frontier you point it at -- ours or the one you just built -- and names the cheapest model clearing the bar for each task. Five files, no dependencies, works in any assistant that reads a skill. Point it at your own `models.json` and the recommendations are grounded in your code rather than our example repo.

### Benchmark your own code repositories

This is option 2 above -- building your own frontier on your own code. It is a few steps:

1. **Create a dataset file** under [benchmarks/dataset/](../benchmarks/dataset/), for example `my-team.yaml`. Copy [mcp-gateway-registry.yaml](../benchmarks/dataset/mcp-gateway-registry.yaml) as a template. Minimal shape:

   ```yaml
   schema_version: "1.0"
   name: my-team
   title: My team's benchmark
   description: Real tasks from our own repositories.
   default_ref: main                      # pin a tag/commit per task for reproducibility
   metrics: [input_tokens, output_tokens, num_turns]
   complexity_levels: [low, medium, high]
   tasks:
     - id: add-rate-limiting-to-gateway
       repo: https://github.com/your-org/your-repo
       ref: v2.3.0                         # pin so every run clones the same code
       complexity: medium
       tags: [python, api, feature]
       problem_statement: |
         Describe the task in enough detail for an agent to act on it without
         you present -- what to change, constraints, and what "done" means.
   ```

Each task points at a repo + pinned ref + a problem statement (from a real ticket or issue). Full field reference: [harness reference -> The dataset](../benchmarks/docs/harness-reference.md#the-dataset). Any repo the runner can `git clone` works (public, or private with credentials available to your shell).

2. **Run it** against whichever model/harness/path you want -- same commands as the example, just swap the dataset:

   ```
   /benchmark provider=bedrock model=claude-opus-5 dataset=dataset/my-team.yaml
   ```

or headless: `benchmarks/scripts/run-e2e-benchmark.sh --provider bedrock --model ... --dataset dataset/my-team.yaml`. Pick the harness with `--agent claude|pi|omp|kiro` and the skill with `--skill swe2|swe3` (`--agent kiro` drives Kiro's managed models and sets `--provider kiro` for you).

3. **Read your results.** Artifacts and scores land under `benchmarks/swe-benchmark-data/<model>/<harness>/<skill>/<your-dataset-repo>/<task>/`, and the same generators build your own cost/quality frontier (`gen_swe_comparison.py`, `plot_cost_quality.py`). Your runs are gitignored, so a customer's private code never lands in version control.

> **Tips for good tasks:** pin a `ref` so reruns are comparable; write the `problem_statement` like a well-scoped ticket; use `tags` to slice results by language/domain/change-type; and add optional `ground_truth` (reviewer-only, never shown to the agent) if you want the judge to check against a known-good approach.

[dataset/workshop-template.yaml](../benchmarks/dataset/workshop-template.yaml) is a two-task starting point with every field annotated. Copy it rather than editing it, fill in the placeholders, and validate before you run:

```bash
cd benchmarks
cp dataset/workshop-template.yaml dataset/my-team.yaml
uv run scripts/dataset_loader.py dataset/my-team.yaml
```

### Pin the release before the fix

This is the rule that decides whether a task measures anything, and it is the one most teams get wrong on their first dataset.

The harness clones the repository at the `ref` you pinned and asks the agent to do the work. Pin a ref that already contains the fix and the agent finds the change already made, so the task measures nothing and every model scores about the same on it. For each task, find the closed issue, find the release that shipped its fix, and pin the release **before** that one. The defect, or the missing feature, is then genuinely present in the tree the agent clones.

[dataset/mcp-gateway-registry-v2.yaml](../benchmarks/dataset/mcp-gateway-registry-v2.yaml) does this for all 21 of its tasks and records the release each fix shipped in as a `fixed_in` tag, which is worth copying as a habit.

## Private repositories, GitHub Enterprise Server, and internal CAs

Any repository the runner can `git clone` works. The harness shells out to `git` with the ambient environment and clones per task, so it uses whatever credentials your shell already has. Nothing in the harness stores or handles a token itself.

Two consequences. Credentials must be available **without prompting**, because a benchmark run is unattended and a `git` password prompt would hang it rather than fail it. And because the clone happens once per task, a credential problem discovered at run time fails once per task, hours into a batch.

### Check reachability before the run

```bash
cd benchmarks
uv run scripts/preflight_check.py --dataset dataset/my-team.yaml --check-repos
```

This resolves every task's repository and pinned ref, then confirms each answers, using `git ls-remote` so it transfers no objects and costs seconds. It reports a missing credential, a rejected token, an untrusted certificate, an unresolvable host and a tag that does not exist as separate diagnoses, each with the fix. [run-e2e-benchmark.sh](../benchmarks/scripts/run-e2e-benchmark.sh) runs it automatically before starting a run.

### Store a credential non-interactively

Any of these work. Pick whichever your organisation already uses.

```bash
# A personal access token with read access, recorded on first use
git config --global credential.helper store
git clone https://ghe.example.com/org/repo /tmp/once && rm -rf /tmp/once

# Or rewrite the URL to carry a token from the environment, so nothing is on disk
git config --global url."https://oauth2:${GHE_TOKEN}@ghe.example.com/".insteadOf \
    "https://ghe.example.com/"

# Or an SSH key or deploy key, with dataset repo URLs written as git@host:org/repo
```

A token needs read access only. The harness never pushes, commits, or opens a pull request: it edits a throwaway clone, captures the result as `patch.diff`, and deletes the clone.

### Trust an internal certificate authority

If your server or model gateway presents a certificate from an internal CA, point **two** things at the CA bundle. They fail separately and for the same reason, which is what makes this cost an hour to diagnose the first time:

```bash
export GIT_SSL_CAINFO=/etc/pki/tls/certs/internal-ca.pem   # git
export NODE_EXTRA_CA_CERTS=/etc/pki/tls/certs/internal-ca.pem   # the agent CLIs
```

The coding-agent CLIs are Node programs and do not read the system certificate store by default, so `git` can be working while the agent still cannot reach the gateway.

### Keep a gateway token out of the config file

`config/runner.yaml` holds the endpoint's `api_key`, and its `local` default is right for a self-hosted vLLM server, which ignores the value. A corporate model gateway needs a real token, and a real token should not sit in a file. Name the environment variable holding it instead:

```yaml
# config/runner.yaml
endpoint: https://gateway.example.com
api_key_env: GATEWAY_API_KEY
```

`api_key_env` wins over `api_key`, and a variable that is unset or empty fails at config load rather than hours later inside the agent. `--api-key-env GATEWAY_API_KEY` does the same from the command line. The value is never logged: the run records which variable it came from, not what was in it, and `--dry-run` prints the agent command with the key redacted.

Where the key ends up depends on the agent, which matters if you share the machine:

| Agent | Where the key goes | Visible to another local user? |
|---|---|---|
| `omp`, `pi` | A per-run `models.yml` / `models.json`, written `0600` | No |
| `claude` | Inline in the `--settings` JSON, a command-line argument | Yes, through the process table |

Claude Code needs a token source even against an endpoint that ignores it, and it takes that from the settings object passed on the command line. Any local user running `ps` can therefore read a real key on the `claude` path. If that matters, point `settings_file` at a `0600` JSON file holding the `env` block instead of relying on the inline default, or keep the benchmark runner on a machine you do not share.

> Your run artifacts are gitignored, so private code and its designs never land in version control. The judge also clones each repository read-only into a temporary directory to verify the artifacts against real source, so it needs the same read credential.


---

[< Back to the README](../README.md)
