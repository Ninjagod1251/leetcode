# Integration (60 minutes)

Practice for rounds like Stripe's Integration: write working code against API docs you've never seen.

---

Write documentation for a small fictional HTTP API (payments, shipping or inventory), plus a single-file Python mock server that implements it using only the standard library. Include bearer-token auth, cursor pagination, idempotency keys on POST, a rate limit that returns 429 with Retry-After, and webhooks signed with HMAC-SHA256.

Then give me the task in parts, one at a time:
1. Fetch every record across pages and compute a summary.
2. Create records safely, so retries never create duplicates.
3. Handle 429s and transient 5xx errors with backoff.
4. Verify and process a webhook payload.

I'll work from the docs only. Answer my questions briefly, the way a teammate who knows the API would, and don't write code for me. At the end, debrief me: did I read the docs before coding, handle errors and edge cases, test against the server, and keep the code clean? Score 1 to 4 on problem solving, code quality, verification and communication.
