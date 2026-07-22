---
name: implement
description: Use only when the user explicitly invokes implement or asks to execute a durable change spec or ticket set; ordinary clear edits use the repository fast path.
---

Implement the work described by the user in the spec or tickets.

Use `$tdd` where possible, at pre-agreed seams.

Run typechecking and focused tests regularly. Follow the repository's verification matrix; use the full suite when the change's risk or documented contract requires it.

Once the implementation is ready but still uncommitted, use `$code-review` to review the complete working-tree diff. Address every accepted finding before closeout.

Immediately before claiming completion, rerun the task-appropriate checks that prove the requested behaviour and inspect their output. Evidence from an earlier session or commit is stale.

Update every affected capability contract in the same change. If the work came from a local change spec or tickets, update their status and completion evidence without moving or archiving them.

Follow the repository's branch and closeout rules to commit and push the verified work. Do not create a release or tag unless the user explicitly asks.
