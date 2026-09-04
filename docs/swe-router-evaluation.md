# Does routing pay for itself?

Running `swe-router` against its own evidence: what it picked across 21 tasks, what those picks scored and cost, and the three caveats that decide how far to trust the result.

The results above rank models on a whole dataset. A developer picks one per task, which is a different question -- and the usual answer is "run the best model for everything", which these numbers say is expensive. The **[`/swe-router`](../.claude/skills/swe-router/SKILL.md)** skill answers it per task: read the repository and the change, decide a quality floor from the consequence of getting it wrong and a complexity tier, then take the cheapest measured model that clears the floor at that tier. It recommends and stops. The developer makes the switch.

We ran it against its own evidence. All 16 models have run all 21 v2 tasks, so for whatever the skill picks we can look up what that model scored and cost on that task instead of estimating it.

| | Router | `claude-opus-5` on everything |
|---|---:|---:|
| Total cost, 21 tasks | **$134.64** | $251.04 |
| Mean task score | 78.94 | 82.83 |

**46.4% cheaper for 4.7% less quality**, using four models: `qwen3.8-27b` on 13 tasks, `claude-opus-5` on 2, `claude-opus-4-8` and `glm-5.3` on 1 each. On 4 further tasks nothing cleared the floor and the skill's answer was to stay put.

Three caveats decide how much to trust that, and all three come from the judgment step rather than the arithmetic:

- **The judgment is not stable.** Run three times per task with an identical prompt, the floor came out unanimous on only **14 of 21** tasks and the tier on 18 of 21.
- **The tier classifier is right about 76% of the time**, matching the dataset's own complexity label on 16 of 21 -- and every miss rated the task *harder* than it was.
- **Some floors are unreachable.** The skill never checks that a model exists which can clear the floor it just set. At the floors this run produced, nothing measured scores 80 on the hard tier, so `claude-opus-5` itself falls short on 4 tasks.

Read the full working: **[what the model judged each task to need](swe-router-judged-inputs.md)** (floor, tier and reasoning per task, with the spread across repeats) and **[the routing result joined to the measured runs](swe-router-evaluation-judged.md)** (per-task picks, costs and score deltas). A script writes both -- see [Reproducing the routing evaluation](../benchmarks/README.md#reproducing-the-routing-evaluation).

One thing is still a person's job: `swe-router` recommends, and the developer switches. [docs/vision.md](vision.md) describes the step past that, a harness that changes model on its own.

---

[< Back to the README](../README.md)
