## 1. Queue payload sanitization

- [x] 1.1 Extract or define the ansible-executor sensitive-field policy used for queue-facing payload sanitization
- [x] 1.2 Sanitize work queue payloads in `agents/ansible-executor/service/nats_service.py` before publishing `QueuedTask`
- [x] 1.3 Replace raw task bodies in worker-task DLQ records with sanitized task summaries
- [x] 1.4 Apply the same sanitization policy to callback retry queue payloads and callback-retry DLQ records

## 2. Bounded command output

- [x] 2.1 Refactor `agents/ansible-executor/service/ansible_runner.py::run_command` to enforce a maximum retained output size during subprocess execution
- [x] 2.2 Add truncation metadata to bounded command output so downstream callers can detect partial results
- [x] 2.3 Update `agents/ansible-executor/service/nats_service.py` result assembly so persisted task results and callback payloads reuse the bounded output representation

## 3. Regression coverage

- [x] 3.1 Add ansible-executor tests proving queue, retry, and DLQ persistence paths do not retain plaintext sensitive credentials
- [x] 3.2 Add ansible-executor tests proving oversized command output is truncated and marked before persistence and callback
- [x] 3.3 Run the targeted ansible-executor test suite covering the new sanitization and bounded-output behavior
