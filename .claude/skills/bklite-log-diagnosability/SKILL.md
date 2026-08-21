---
name: bklite-log-diagnosability
description: Audit, design, or repair BK-Lite Server and Stargazer logging for incident diagnosability. Use when failures are hard to locate, critical logs are missing, logs are noisy/duplicated/misleading, exceptions are swallowed or lose tracebacks, Django/Celery/NATS/ARQ/Stargazer events cannot be correlated, log levels or context are inconsistent, sensitive/raw payloads are logged, or the user asks to improve logging signal-to-noise. Produce evidence-cited findings by default; implement only when the user asks for changes. Do not use merely to install an observability backend or add generic telemetry.
---

# BK-Lite Log Diagnosability

Make production failures explainable from logs without increasing steady-state noise. Optimize for incident questions and mean time to repair, not log count.

## Operating rules

- Read `AGENTS.md`, `docs/backend-coding-guide.md`, `SECURITY.md`, and `RELIABILITY.md` before judging or editing logging behavior.
- Treat detector output as candidates. Read the complete control flow before reporting a finding.
- Audit critical workflows end to end, especially Server → Celery/NATS → Stargazer → plugin/executor → callback → Server persistence.
- Prefer one terminal failure log at the layer that owns the outcome. Avoid log-then-raise duplication at every stack layer.
- Preserve original exception causality and traceback. Do not replace exceptions with empty results unless the path is explicitly best-effort and the degraded outcome is observable.
- Do not add start/success INFO logs to every function. Emit lifecycle summaries at operational boundaries; keep decisions and per-item detail at DEBUG.
- Do not introduce OpenTelemetry, structlog, a new log backend, or a schema migration unless the user explicitly asks.
- Never log secrets, credentials, cookies, authorization headers, full request bodies, raw command output, or unbounded plugin results.
- Follow TDD and the repository's module gates for any behavior change.

## Select the mode

Infer the narrowest mode from the request:

| Mode | Use for | Default mutation |
|---|---|---|
| `audit` | Missing signal, noisy logs, incident-readiness review | Read-only |
| `design` | Define a logging contract or critical-flow coverage | Documentation/proposal only |
| `fix` | Implement approved or explicitly requested remediation | Code and tests |
| `verify` | Re-check an earlier audit or logging change | Read-only except requested report updates |

If the user asks only to inspect, diagnose, audit, or review, do not edit source files or create a report file unless requested. Return the report in the response.

## Phase 1: Orient around failure paths

1. Read the project guidance listed above.
2. Read [references/log-contract.md](references/log-contract.md).
3. Read [references/critical-flows.md](references/critical-flows.md) when Server/Stargazer, NATS, Celery, ARQ, collection, callback, or remote execution is in scope.
4. Inspect the active logging configuration and logger wrappers before evaluating call sites:
   - `server/config/components/log.py`
   - `server/apps/core/logger.py`
   - `agents/stargazer/start_worker.py`
   - `agents/stargazer/Makefile` and `agents/stargazer/support-files/supervisor/*.conf`
   - other development, production, and worker launchers plus `basicConfig`, `dictConfig`, handlers, filters, and adapters discovered with `rg`
5. Resolve the requested scope. Default to `server/` and `agents/stargazer/`; exclude tests, migrations, generated files, and third-party vendored code unless they are directly relevant.
6. Identify one or more critical flows and write a compact flow map containing:
   - boundary/stage;
   - success outcome;
   - failure modes;
   - owner of the terminal outcome;
   - correlation identifiers available at that stage.

For dynamic plugin families, trace at least one credential-bearing representative
and one high-volume representative. Stop after the shared orchestration and data
contract are proven; list plugin families not inspected instead of implying full
coverage.

Do not form findings from isolated logging calls before completing the flow map.

## Phase 2: Build a candidate inventory

Run the bundled AST scanner from the repository root. Start with counts so a
large legacy inventory does not consume the audit context:

```bash
python3 <skill-root>/scripts/inventory_logging.py server agents/stargazer --format json --summary-only
```

After choosing a critical flow, expand only its files:

```bash
python3 <skill-root>/scripts/inventory_logging.py <critical-flow-files> --format markdown
```

Use `--format json` for machine-readable output and `--include-tests` only when tests themselves are in scope. The scanner detects mechanical smells such as formatted message templates, swallowed exceptions, missing traceback context, repeated error emission, INFO in loops, decorative logs, raw payload logging, and sensitive-name exposure.

Supplement it with targeted searches. Prefer `rg`; examples:

```bash
rg -n 'logger\.(info|warning|error|exception)' <scope>
rg -n 'except|raise|return \[\]|return \{\}|return None' <critical-flow-files>
rg -n 'task_id|collect_task_id|execution_id|debug_id|request_id|trace_id|subject' <critical-flow-files>
```

For every candidate, read the enclosing function and its callers/callees far enough to answer:

- Does the event change the operational outcome?
- Would an on-call engineer know the failed stage and next action?
- Is the failure logged exactly once with traceback at an owning boundary?
- Can the Server event be correlated with the Stargazer event?
- Could the message expose or serialize sensitive/unbounded data?
- Is the log emitted once per operation, once per retry, or once per item?

## Phase 3: Classify evidence

Classify only evidence-backed findings:

- `missing-signal`: a terminal/degraded failure is invisible or lacks actionable context.
- `misleading-signal`: a failure is converted to success/empty data, the level contradicts the outcome, or a message claims completion too early.
- `duplicate-signal`: the same exception is logged at multiple layers or as multiple ERROR lines.
- `noise`: high-volume, decorative, per-item, raw-result, or routine decision logs obscure incident signals.
- `correlation-gap`: identifiers are generated but not propagated or emitted across boundaries.
- `sensitive-or-unbounded`: secrets, credential-bearing objects, full payloads/results, commands, or responses may reach logs.
- `configuration-gap`: handler/filter/format/propagation behavior drops, duplicates, fragments, or prevents querying logs.

Use this severity rubric:

- **P0**: confirmed credential/secret exposure, or missing evidence on an irreversible/high-risk execution path that can cause data loss or target-host harm.
- **P1**: common terminal failure is invisible/misreported; traceback or correlation is lost across a critical boundary; duplicate ERRORs materially distort incident triage.
- **P2**: substantial INFO noise, inconsistent levels, unstable templates, or incomplete context slows diagnosis but does not hide the outcome.
- **P3**: localized cosmetic or low-frequency cleanup with little incident impact.

Do not report a formatted message, broad exception, INFO call, or missing field solely because it matches a heuristic. State the concrete incident consequence.
For a sensitive-value candidate, verify that the value itself—not only an ID or
presence flag—is emitted and that the call is reachable under a supported
development or production launcher. If level filtering or runtime reachability
is unknown, label it a P0 candidate and name the runtime evidence still needed.

## Phase 4: Deliver the audit

Lead with the critical-flow judgment. Use this structure:

```markdown
## 结论
<Can an on-call engineer locate and explain the failure from current logs?>

## 关键链路覆盖
| Stage | Success signal | Failure signal | Correlation | Judgment |

## Findings
| ID | Priority | Category | Evidence | Incident impact | Minimal recommendation |

## 噪声预算
| Source | Frequency | Current level/volume | Recommended policy |

## 看起来可疑但合理
<Candidates reviewed and intentionally not flagged, with reasons.>

## 修复顺序
<Small batches ordered by incident value and risk.>
```

Every finding must cite `path:line`, distinguish confirmed fact from inference, and name the operational question that current logs cannot answer. Keep the report focused: 5 strong findings are better than 50 regex matches.

## Phase 5: Implement only when requested

Work one critical flow or one coherent rule family at a time.

1. Write failing behavior tests first. Assert log level, stable event/message, required identifiers, traceback ownership, and absence of sensitive/raw data. Do not assert timestamps or full rendered lines.
2. Apply the minimum source change. Avoid repository-wide logging rewrites and formatting churn.
3. Use the compatibility pattern in [references/log-contract.md](references/log-contract.md); respect the formatter actually deployed.
4. Preserve exception semantics. If an error remains recoverable, log one WARNING summary; if it becomes terminal, log one ERROR with traceback at the owner.
5. Aggregate loop/progress output. Move per-item diagnostics to DEBUG or remove them.
6. Remove decorative separators, emoji-only markers, hand-built traceback strings, and multi-line ERROR explanations when one structured terminal event suffices.
7. Propagate existing domain identifiers before inventing a new global correlation mechanism.
8. Run targeted tests, then the relevant gates:
   - Server: `cd server && make test`
   - Stargazer: targeted `uv run pytest ...` when tests exist, then `cd agents/stargazer && make lint`
9. Re-run the inventory scanner. Compare semantics and critical-flow coverage, not merely candidate counts.

Never auto-fix all f-strings, all broad catches, or all INFO logs. Mechanical mass changes can remove useful context or alter exception behavior.

## Verification bar

A remediation is complete only when a representative failure test proves:

- the terminal outcome is not silently converted to success;
- exactly one owning ERROR contains the traceback, or one WARNING describes an intentional degraded result;
- Server and Stargazer records share usable identifiers;
- batch/high-frequency paths emit bounded summaries;
- sensitive/raw inputs are absent;
- existing return values, retries, callbacks, and error contracts remain correct.

Report remaining gaps and any paths that require runtime evidence. Static review cannot prove production log shipping, retention, or query behavior.
