# Practical sessions

Algorithms are one round of a loop. Most loops also test engineering more directly: designing a small component (Atlassian's Code Design), debugging code you didn't write (Stripe's Bug Squash), building against unfamiliar API docs (Stripe's Integration) and, more and more, working with an AI assistant. One session a week from [`prompts/`](../prompts) keeps those sharp.

Each session gets a folder, `<date>-<track>-<name>/`, holding the code I wrote and a `debrief.md` that `lc.py` creates:

```bash
python lc.py log rate-limiter -t design -m 60 -c 3 -n "settle the API before picking the data structure"
```

Tracks: `design`, `debug`, `integration`, `ai`, `mock`.
