# Bug squash (45 to 60 minutes)

Practice for debugging rounds like Stripe's Bug Squash: find and fix bugs in a codebase you didn't write.

---

Set up a debugging round for me using one of these options.

**Option A, real open source (closest to the real thing).** Pick a bug that was fixed in a popular Python or Java project, such as requests, click, httpx, rich or Jackson. Give me the repository, the commit just before the fix, and a bug report written like a GitHub issue: symptoms and a reproduction only, nothing about the cause. Don't reveal the fix commit until I say I'm done. Then compare my fix with the real one.

**Option B, generated.** Write a small multi-file Python project (300 to 500 lines, something like an invoicing or ledger service) with 3 or 4 realistic bugs, for example money stored as floats, an off-by-one in pagination, time-zone handling, a mutable default argument, state shared between requests, or a serialization mismatch. Include a test suite where some tests fail and a README saying what the service should do. Give me only the files. Don't say where the bugs are or how many there are until I'm done.

Either way, debrief me afterwards: did I reproduce before changing code, read before guessing, form and test hypotheses, make the smallest safe fix, and add a regression test? Score 1 to 4 on problem solving, code quality, verification and communication.
