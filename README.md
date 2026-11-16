# Daily interview practice

One problem a day, logged honestly.

Accepted LeetCode submissions sync into [`solutions/`](solutions) automatically through [LeetSync](https://github.com/3ba2ii/LeetSync). Each one gets an `approach.md` in my own words: the pattern, the key insight, complexity, and what tripped me up. A small CLI, [`lc.py`](lc.py), schedules from-scratch re-solves with spaced repetition, so a problem counts as learned only once I can solve it again cold. Hints and peeks at solutions are logged too.

<!-- lc:stats:start -->
[![LeetCode stats](https://leetcard.jacoblin.cool/chippenkales?ext=heatmap)](https://leetcode.com/u/chippenkales/)

- **Streak:** not started yet · **Practice days:** 0
- **Problems logged:** 0 (0 Easy · 0 Medium · 0 Hard) · **Solved first try without hints:** n/a
- **Re-solves:** 0 · **Retained** (solved again cleanly): 0
- **Practical sessions:** Code design 0 · Bug squash 0 · Integration 0 · AI-assisted 0 · Mock interview 0

| Pattern | Roadmap progress |
|---|---|
| Arrays & Hashing | ░░░░░░░░░░ 0/7 |
| Two Pointers | ░░░░░░░░░░ 0/5 |
| Sliding Window | ░░░░░░░░░░ 0/5 |
| Prefix Sum | ░░░░░░░░░░ 0/2 |
| Stack | ░░░░░░░░░░ 0/6 |
| Binary Search | ░░░░░░░░░░ 0/6 |
| Linked List | ░░░░░░░░░░ 0/6 |
| Trees | ░░░░░░░░░░ 0/8 |
| Tries | ░░░░░░░░░░ 0/3 |
| Heap / Priority Queue | ░░░░░░░░░░ 0/5 |
| Intervals | ░░░░░░░░░░ 0/4 |
| Backtracking | ░░░░░░░░░░ 0/5 |
| Graphs | ░░░░░░░░░░ 0/7 |
| Union-Find, Dijkstra, MST | ░░░░░░░░░░ 0/5 |
| 1-D Dynamic Programming | ░░░░░░░░░░ 0/7 |
| 2-D Dynamic Programming | ░░░░░░░░░░ 0/4 |
| Greedy | ░░░░░░░░░░ 0/4 |
| Data Structure Design | ░░░░░░░░░░ 0/5 |

**Recent**

| Date | Problem | Level / track | Pattern | Minutes | Hints |
|---|---|---|---|---|---|
| | Nothing logged yet | | | | |
<!-- lc:stats:end -->

## How I practice

1. **Attempt cold.** About 25 minutes (40 for a Hard) before any help, and the approach and its complexity said out loud before any code.
2. **Hints come one rung at a time:** a nudge, then the pattern, then the key insight, then pseudocode. Every rung is counted. Seeing a full solution is logged as assisted and puts the problem back on a one-day re-solve.
3. **After an accept:** state the insight in one sentence, fill in `approach.md`, and log time, hints and confidence.
4. **Re-solve on a schedule:** 1, 3, 7, 14, 30, 60, then 120 days. A clean, confident re-solve moves a problem up the ladder; needing a hint moves it down.
5. **One practical session a week** in [`practical/`](practical): code design, debugging an unfamiliar codebase, building against API docs, an AI-assisted round, or a timed mock interview.

## Layout

| Path | What's there |
|---|---|
| `solutions/<id>-<slug>/` | The problem and my accepted code (from LeetSync), plus my `approach.md` |
| `practical/<date>-<track>-<name>/` | Code and a `debrief.md` from each practical session |
| `roadmap.csv` | 94 problems across 18 patterns, in the order I'm working through them |
| `log.csv` | Every attempt: time, hints, confidence, next re-solve date |
| `prompts/` | The coach, reviewer and interviewer prompts I use with Claude or ChatGPT |
| `CLAUDE.md` | Rules for AI coding agents working in this repo |
| `lc.py` | The CLI: Python standard library only, tested in CI |

## Using `lc.py`

```bash
python lc.py today              # re-solves due, unlogged solutions, next problems
python lc.py log two-sum -m 18 -H 0 -c 4 -n "store complement -> index while scanning"
python lc.py log two-sum -m 18 -H 0 -c 4 -e     # same, but open approach.md to write notes first
python lc.py log rate-limiter -t design -m 60 -c 3 -n "settle the API before the data structure"
python lc.py next -p graphs     # next unsolved problems in one pattern
python lc.py stats              # rebuild the stats above
python lc.py doctor --online    # check git identity, config, and the roadmap against LeetCode
```

`-m` is minutes, `-H` hint rungs used, `-c` confidence from 1 (lost) to 5 (could teach it), and `-a` means I saw a solution. Logging commits the notes, the log and this README, then pushes.
