# The workflow diagram, in ASCII

The same diagram the [README](../README.md) shows as an image, for terminals and for anywhere the PNG will not render. There is also a [slide-ready HTML version](slides/swe-router-workflow.html).

Change one and change the others: the HTML is the source, the PNG is a screenshot of it, and this is a hand-composed replica.

```
MEASURE ONCE, SPEND LESS ON EVERY TASK
Everyone knows the top model is overkill for most tasks.
This makes the cheaper choice the automatic one.

+- PLATFORM TEAM: a cron job, weekly, unattended ------------+  +- EVERY DEVELOPER: every task ----+
| 1 . MEASURE                     SHIPS AS THE               |  | 2 . ROUTE                        |
| self-hosted . managed service   swe-router SKILL           |  | Claude Code . Codex . pi . ...   |
| . vendor API                                               |  |                                  |
|                                 +------------------------+ |  | +------------------------------+ |
| +----------------------------+  | models.json            | |  | | A task begins                | |
| | Available models           |  |   score + cost, per    | |  | |   swe-router is installed in | |
| |   whatever security        |  |   difficulty bucket    | |  | |   the harness - it engages   | |
| |   approved                 |  |                        | |  | |   on its own, nobody invokes | |
| +----------------------------+  |   allowed-models.txt   | |  | |   it                         | |
|                                 |   the approved list,   | |  | +------------------------------+ |
| +----------------------------+  |   now the filter       | |  |                |                 |
| | Your dataset               |  |                        | |  |   +------------+------------+    |
| |   tasks from your repo     |  |   rubric.md + route.py | |  |   v                         v    |
| +----------------------------+  |   six questions, then  | |  |   +------------+  +------------+ |
|               |                 |   the decision as code | |  |   | How hard?  |  | How bad if | |
|               v                 |                        | |  |   | 4 questions|  |   wrong?   | |
| +----------------------------+  |   One curl to install. | |  |   | -> a bucket|  | 2 questions| |
| | Run the benchmark          |  |   Every developer      | |  |   |            |  | -> a bar   | |
| |   every model x every      |  |   reads the same       | |  |   +------------+  +------------+ |
| |   task, judged; each task  |  |   numbers on the same  | |  |   +------------+------------+    |
| |   gets a difficulty bucket |  |   day.                 | |  |                v                 |
| +----------------------------+  +------------------------+ |  | +==============================+ |
|               |                                            |  | | CHEAPEST MODEL OVER THE BAR  | |
|               v                                            |  | | IN THAT BUCKET               | |
| +============================+                             |  | |   ranked over what this      | |
| | YOUR FRONTIER              |                             |  | |   developer can actually     | |
| |   not a vendor claim, not  |                             |  | |   select                     | |
| |   a public set that leaked |                             |  | +==============================+ |
| |   into training data       |                             |  |                                  |
| +============================+                             |  |                                  |
+------------------------------------------------------------+  +----------------------------------+

====================================================================================================
PLATFORM TEAM GETS   Up to 88% less per task, against running the top model on every task
                     - measured on your own repo, not claimed.

DEVELOPERS GET       No decision. The right model arrives with the task; nobody weighs
                     quality against the bill, twenty times a day.
```

---

[< Back to the README](../README.md)
