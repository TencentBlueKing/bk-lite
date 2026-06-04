# Host Remote Ansible Callback Design

**Goal:** Make Host Remote collection in Stargazer use an Ansible callback-driven flow so the chain can run through cleanly without treating ansible-executor as a synchronous RPC that returns the final host metrics result.

**Scope:** This design only covers the Host Remote collection path. It intentionally does not generalize callback handling for other monitor types yet, and it does not add durable task recovery across Stargazer restarts.

## Current Problem

Host Remote currently calls `ansible.adhoc.<node_id>` and waits inline for a final execution result. That does not match the current ansible-executor contract:

1. `ansible.adhoc.*` accepts the task and returns `accepted + task_id`.
2. The actual execution runs asynchronously in the executor worker.
3. If a callback is provided, the executor pushes the final result back later.

This mismatch creates two problems:

1. Stargazer expects final stdout in the initial reply even though the executor is queue-based.
2. Long-running host commands keep the collection flow coupled to a request/reply path that is already showing instability and timeout sensitivity.

## Recommended Approach

Implement a **Host Remote–specific callback loop**:

1. Stargazer submits Ansible adhoc with a dedicated callback subject.
2. ansible-executor executes asynchronously.
3. ansible-executor calls back into Stargazer with the final execution payload.
4. Stargazer callback code extracts stdout, converts it to host metrics, and publishes metrics to NATS.

This keeps the change small, aligns with the executor’s existing model, and avoids building a generic callback framework too early.

## Alternatives Considered

### Option 1: Poll `ansible.task.query`

After receiving `accepted + task_id`, Stargazer could poll `ansible.task.query.<node_id>` until completion.

**Pros**
- Smaller conceptual change than a callback receiver.
- No new Stargazer NATS handler required.

**Cons**
- Still not aligned with the executor’s preferred callback model.
- Adds repeated query traffic and more retry/timeout logic in Stargazer.
- Feels like an adapter layer rather than a clean design.

### Option 2: Build a generic callback framework now

Create a durable callback/task-center abstraction for all future async collectors.

**Pros**
- Best long-term shape.
- Reusable across monitor types.

**Cons**
- Too large for the immediate goal.
- Adds persistence, generic routing, and lifecycle design before Host Remote is proven.

### Option 3: Host Remote–specific callback loop (**recommended**)

Build only the callback path needed for Host Remote and keep the rest of the system unchanged.

**Why this is recommended**
- Smallest design that matches the executor’s real behavior.
- Lets Host Remote run through first.
- Keeps room for later generalization after the callback path is proven in production.

## Architecture

### 1. Host Remote submission path

When Stargazer receives a Host Remote request, it should:

1. Build the adhoc payload as it does today.
2. Add a callback config pointing to a new Stargazer NATS subject dedicated to Host Remote callback handling.
3. Include only the minimum callback context needed to finish the flow:
   - `task_id`
   - `host`
   - `os_type`
   - `instance_id`
   - `metrics_modules`
   - any existing routing fields needed for final metric publishing
4. Treat the initial ansible reply as **task acceptance**, not final execution output.

The submission path should log:

- callback subject
- selected runtime `node_id`
- ansible `task_id`
- target host
- module list
- executor acceptance result

### 2. Stargazer callback receiver

Stargazer should expose a **new dedicated NATS handler** for Host Remote callback results.

This handler is only for Host Remote in this phase. It should:

1. Validate that the payload is a Host Remote callback payload.
2. Read the final Ansible execution result.
3. Extract stdout from the contacted host result.
4. Reuse Host Remote’s existing post-processing path:
   - parse JSON stdout
   - transform to Prometheus metrics
   - publish metrics to the existing destination
5. If execution failed, generate the existing error metrics and publish those instead.

The callback handler should log:

- callback received
- task id
- host
- execution success/failure
- stdout extraction status
- post-processing success/failure
- final publish success/failure

### 3. Reuse instead of rebuilding host parsing

The change should avoid duplicating Host Remote parsing logic.

The existing `HostCollector` behavior should be split conceptually into two phases:

1. **submit or execute host command**
2. **parse stdout and build Prometheus output**

The callback path should reuse the second phase directly. The goal is to keep one authoritative implementation for:

- stdout extraction
- JSON parsing
- Prometheus conversion
- error metric generation

## Data Flow

### Request side

1. Telegraf hits Stargazer `/host/metrics`
2. Stargazer submits adhoc request with callback
3. ansible-executor replies immediately with `accepted + task_id`
4. Stargazer ends the submission phase successfully

### Completion side

1. ansible-executor finishes execution
2. ansible-executor requests Stargazer callback subject
3. Stargazer callback handler receives final result
4. Stargazer converts stdout to host metrics
5. Stargazer publishes metrics to NATS

## Error Handling

This phase keeps error handling intentionally minimal.

### In scope

- If the initial adhoc submit fails, log and emit Host Remote error metrics.
- If callback arrives with failed execution, generate and publish Host Remote error metrics.
- If callback result cannot be parsed, generate and publish Host Remote error metrics.
- If publish-to-NATS fails, log the failure clearly.

### Out of scope for this phase

- Durable recovery if Stargazer restarts before callback arrives
- Generic callback routing for other collectors
- Full deduplication of repeated callbacks
- Generic async task orchestration across monitor types

## Logging Requirements

The implementation should add explicit logs at these points:

1. **Submitting Ansible task**
   - node id
   - host
   - task id
   - callback subject

2. **Ansible accepted**
   - accepted flag
   - queued status
   - task id

3. **Callback received**
   - callback subject
   - task id
   - host
   - success/failure

4. **Metrics published**
   - publish target
   - data size or error type
   - task id

These logs are part of the design, not optional debugging extras.

## Testing Strategy

This phase should use focused regression coverage only.

### Required tests

1. **Submission path test**
   - Host Remote submission includes callback config
   - callback subject is the new Host Remote callback subject
   - selected runtime node id is passed correctly

2. **Callback handler success test**
   - callback payload containing successful Ansible stdout
   - stdout is post-processed into Host Remote metrics
   - publish path is called

3. **Callback handler failure test**
   - failed Ansible result or malformed stdout
   - Host Remote error metrics are generated and published

### Not required in this phase

- cross-process restart recovery
- callback replay/dedup framework
- generic callback support for non-host collectors

## Implementation Boundaries

### Included now

- Host Remote submission switched to callback mode
- new Stargazer NATS callback handler for Host Remote only
- refactoring Host Remote code so stdout post-processing can be reused
- detailed logs through the full callback path
- targeted regression tests

### Explicitly deferred

- generic Stargazer async callback framework
- persistence for pending callback state
- full callback idempotency layer
- converting other monitor types to callback mode

## Success Criteria

This design is successful when all of the following are true:

1. Host Remote no longer expects final stdout from the initial `ansible.adhoc` request.
2. Host Remote results are completed through an Ansible callback into Stargazer.
3. The selected runtime node id is still the executor routing key.
4. Successful callbacks publish real host metrics.
5. Failed callbacks publish Host Remote error metrics.
6. The full flow is traceable from logs without manual guesswork.
