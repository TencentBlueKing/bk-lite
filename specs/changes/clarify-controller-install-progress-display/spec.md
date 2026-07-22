# Clarify Controller Install Progress Display

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/clarify-controller-install-progress-display/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

Controller installation progress currently mixes several different meanings into the same visible step. The UI can show `执行安装器` as completed while the installer detail summary says `0/6` and lists missing installer steps. Users cannot tell whether the platform connected to the target host, whether the install command ran, whether the target host could download the installer with curl, whether installer events reached the server, or whether the sidecar simply has not connected back yet.

The confusing case is especially important when the platform successfully logs in to the target host and dispatches the install command, but the target host fails while running curl/bootstrap/install or cannot reach Server/NATS/object storage. In that case no installer step events are returned to the server. The current display treats this mostly as missing detail data, but users need to understand it as a concrete installation break point.

## What Changes

- Present controller installation as user-facing phases: credential validation, install command dispatch, installer execution, and node connectivity.
- Separate command dispatch success from installer execution success.
- Promote "installer no report" to an explicit user-facing state when no installer step events reach the server after the command has been dispatched.
- Make success, running, and failure judgments precise and easy to understand.
- Show clear next actions for login failure, command failure, installer no-report, installer step failure, and connectivity timeout.
- Keep low-level diagnostics such as duplicated installer events available without making them the primary success display.
- Align backend installer summary semantics and frontend display semantics so progress counts and phase labels do not contradict each other.

## Capabilities

### Added Capabilities

- `controller-install-progress-display`: define controller install progress phases, state mapping, no-report handling, user-facing display rules, and acceptance scenarios.

## Impact

- **Server node_mgmt**: normalize controller install task result summaries and expose enough state for the frontend to distinguish command dispatch, installer reporting, installer failure, and connectivity.
- **Web node-manager**: update controller install progress table and log drawer to render the four-phase model, explicit no-report state, and phase-specific next actions.
- **i18n**: update Chinese and English copy for phase names, no-report diagnostics, failure reasons, and next actions.
- **Tests**: add backend summary tests and frontend utility/component tests for success, running, no-report, installer failure, and connectivity timeout cases.

## Implementation Decisions

## Context

Controller installation is a chained process:

```text
Server / executor
  -> SSH/WinRM login to target host
  -> dispatch bootstrap install command
  -> target host runs curl/bootstrap/installer
  -> installer emits BKINSTALL_EVENT step lines
  -> sidecar/controller connects back to server
```

The current UI shows a single `执行安装器` step for both the remote command and the target-side installer. This creates contradictions:

- `run` can be marked success because the remote command returned successfully.
- `installer_summary.state` can still be `no_installer_events` because no target-side installer events were captured.
- `connectivity_check` can still be running or timeout because sidecar has not connected back.

Users need the screen to answer three simple questions:

1. Did the platform reach the target host?
2. Did the target host report installer progress?
3. Did the installed sidecar/controller connect back?

## Goals / Non-Goals

**Goals:**

- Make controller install progress understandable without knowing internal step names.
- Distinguish command dispatch from installer execution.
- Treat no installer events as a first-class state, not as a generic missing-step note.
- Show a clear phase, reason, and next action for failures.
- Keep successful installs visually clean.
- Preserve diagnostic details for support users.

**Non-Goals:**

- Do not redesign the entire node-manager installation wizard.
- Do not change the controller installer protocol beyond the state data needed for clearer display.
- Do not require the target host to have extra tools beyond the existing installation path.
- Do not make duplicated installer events a primary user-facing warning on successful installs.

## User-Facing Phase Model

The UI should present four phases:

```text
1. 校验登录凭据
   Platform can authenticate to the target host.

2. 下发安装命令
   Platform has dispatched the bootstrap/install command to the target host.

3. 安装器执行
   Target-side installer is reporting step events to the server.

4. 等待节点回连
   Installed sidecar/controller connects back to the server.
```

This replaces the ambiguous meaning of `执行安装器` with two different phases:

- `下发安装命令`: remote command dispatch/execution layer.
- `安装器执行`: target-side installer event layer.

## State Mapping

Recommended normalized user states:

| User state | Meaning |
| --- | --- |
| `waiting` | Phase has not started. |
| `credential_failed` | Login/authentication failed before command dispatch. |
| `command_running` | Install command is being dispatched or executed remotely. |
| `command_failed` | Platform reached the target host, but command dispatch/execution failed. |
| `installer_waiting` | Command was dispatched and the system is waiting for installer events. |
| `installer_no_report` | No installer step events were returned after command dispatch. |
| `installer_running` | Installer events are being received and the installer is not terminal. |
| `installer_failed` | An installer step failed. |
| `connectivity_waiting` | Installer command path has completed enough to wait for sidecar/controller connectivity. |
| `connectivity_failed` | Sidecar/controller did not connect back before timeout. |
| `success` | Node connected back successfully. |
| `success_without_detail` | Node connected back successfully, but installer detail events were not captured. |

## Success, Running, and Failure Judgments

### Success

The main success condition is node connectivity confirmation. If installer detail steps were captured and complete, show:

```text
校验登录凭据    已完成
下发安装命令    已完成
安装器执行      已完成 6/6
等待节点回连    已完成

结果：安装成功
```

If node connectivity is confirmed but no installer detail events were captured, show success with a low-severity note:

```text
结果：安装成功
提示：节点已回连，但未采集到安装器详细步骤。
```

### Running

When installer events are present, show current installer progress:

```text
安装器执行    执行中 3/6
当前步骤：下载安装包
```

When the install command has been dispatched but no installer events have arrived yet, show:

```text
安装器执行    等待回报
提示：安装命令已在目标机器执行，正在等待安装器返回步骤。
```

If this no-event state lasts beyond the configured or inferred no-report threshold, upgrade the phase to:

```text
安装器执行    未收到回报
```

### Failure

Failures must identify the phase that failed:

| Failure phase | User message direction |
| --- | --- |
| 登录失败 | Check account, password/private key, port, SSH/WinRM connectivity. |
| 命令下发失败 | Check shell permissions, curl availability, remote command output, execution agent output. |
| 安装器无回报 | Check target host access to Server/NATS/object storage, curl download result, bootstrap output, and stream log collection. |
| 安装器步骤失败 | Show the failed installer step, failure reason, key context, and step-specific next action. |
| 节点回连失败 | Check `bk-sidecar.service`, journal logs, `sidecar.yml`, token, `server_url`, firewall, DNS, and route from target host to server. |

## Installer No-Report Handling

`installer_no_report` is the critical new state. It applies when:

- credential validation succeeded, and
- the install command reached the target host or returned from the executor path, and
- `installer_summary.state` is `no_installer_events`, and
- connectivity has not been confirmed.

Display text should avoid saying every installer step is "missing" by default. The primary message should be:

```text
平台已连接目标机器并下发安装命令，但未收到安装器返回的步骤。
可能原因：目标机器无法访问 Server/NATS/对象存储、curl 下载失败、安装命令执行失败，或远程输出未被采集。
```

If connectivity later succeeds, the final state becomes `success_without_detail`. If connectivity times out, the final failure becomes:

```text
安装失败：安装器无回报，节点未回连。
```

## Display Rules

- The main timeline should show the four user-facing phases.
- Installer internal steps should be nested under `安装器执行` only when installer events exist.
- When no installer events exist, show `安装器步骤：未收到`, not a long list of missing step names.
- Only show missing installer step names when at least one installer event exists and the event sequence is incomplete.
- Duplicated event counts should be available in diagnostics or a collapsed detail area, not as the primary success message.
- The progress count used by the table and the drawer should use the same expected step set.

## Data Flow

```text
ControllerTaskNode.result.steps
  -> backend read normalization
  -> installer_summary / installer_progress / optional display_state
  -> frontend normalization utility
  -> progress table status summary
  -> log drawer phase timeline and diagnostics
```

The backend may either expose an explicit display state or expose enough normalized summary fields for the frontend to derive it deterministically. The implementation should prefer one shared frontend utility for table and drawer derivation so they cannot disagree.

## Risks / Trade-offs

- **Legacy task results**: historical tasks may lack newer fields. The display derivation must gracefully fall back from existing `steps`, `overall_status`, `installer_summary`, and `installer_progress`.
- **Timing threshold**: no-report during the first few seconds can be normal. The first implementation can avoid hardcoding a new timer by using existing task phase and connectivity timeout, but the UI should still say "waiting for installer report" before declaring failure.
- **Progress count mismatch**: existing code has a six-step installer summary and a seven-step realtime progress sequence. The implementation must choose one user-facing expected count and keep table/drawer consistent.
- **Manual install**: manual installation can also lack server-side step visibility. Any changes should avoid making remote-only assumptions in shared utilities.

## Capability Deltas

### controller-install-progress-display

## ADDED Requirements

### Requirement: Controller install progress SHALL use user-facing phases
The node manager UI SHALL present controller installation progress using separate user-facing phases for credential validation, install command dispatch, installer execution, and node connectivity.

#### Scenario: Remote installation is shown as four phases
- **WHEN** a user views the controller installation log for a remote install task
- **THEN** the primary timeline SHALL include phases equivalent to `校验登录凭据`, `下发安装命令`, `安装器执行`, and `等待节点回连`
- **AND** the display SHALL NOT use one ambiguous phase to mean both command dispatch and target-side installer execution

#### Scenario: Command dispatch completion does not imply installer completion
- **WHEN** credential validation succeeds and the remote install command returns successfully
- **AND** no installer step events have been received
- **THEN** the command dispatch phase SHALL be allowed to show completed
- **AND** the installer execution phase SHALL NOT show completed

### Requirement: Controller install status SHALL distinguish success, running, and failure precisely
The system SHALL derive controller install display status from the installation phase and terminal outcome instead of only from the top-level task-node status.

#### Scenario: Complete successful installation
- **WHEN** credential validation succeeds
- **AND** install command dispatch succeeds
- **AND** installer detail steps are complete
- **AND** node connectivity is confirmed
- **THEN** the UI SHALL show installation success
- **AND** the installer execution phase SHALL show completed progress using the agreed expected step count
- **AND** the node connectivity phase SHALL show completed

#### Scenario: Node connects back without installer detail
- **WHEN** credential validation succeeds
- **AND** install command dispatch succeeds
- **AND** no installer step events were captured
- **AND** node connectivity is confirmed
- **THEN** the UI SHALL show installation success
- **AND** the UI SHALL show a low-severity note that the node connected back but installer detail steps were not captured
- **AND** the UI SHALL NOT show this case as installer execution failure

#### Scenario: Installer is actively reporting progress
- **WHEN** installer step events have been received
- **AND** the latest installer step is not terminal failure
- **AND** node connectivity is not yet confirmed
- **THEN** the UI SHALL show installation in progress
- **AND** the installer execution phase SHALL show the latest installer step label and progress count

#### Scenario: Installer step fails
- **WHEN** an installer step event has status error or timeout
- **THEN** the UI SHALL show installation failure at the installer execution phase
- **AND** the UI SHALL show the failed step, failure reason, key context when available, and a step-specific next action

#### Scenario: Connectivity times out after complete installer steps
- **WHEN** installer detail steps are complete
- **AND** node connectivity times out
- **THEN** the UI SHALL show installation failure at the node connectivity phase
- **AND** the UI SHALL guide the user to check sidecar service, journal logs, sidecar configuration, token, server URL, firewall, DNS, and target-to-server route

### Requirement: Installer no-report SHALL be explicit
The system SHALL treat absence of installer step events after command dispatch as a distinct state so users understand that the target host did not report installer progress.

#### Scenario: Command dispatched but installer has not reported yet
- **WHEN** credential validation succeeds
- **AND** install command dispatch has started or returned successfully
- **AND** no installer step events have been received
- **AND** node connectivity is not terminal
- **THEN** the UI SHALL show a state equivalent to `等待安装器回报` or `安装器无回报`
- **AND** the UI SHALL explain that the platform connected to the target host and dispatched the command but has not received installer steps

#### Scenario: No installer report with connectivity timeout
- **WHEN** credential validation succeeds
- **AND** install command dispatch succeeds or reaches the target host execution path
- **AND** no installer step events are received
- **AND** node connectivity times out
- **THEN** the UI SHALL show installation failure with a message equivalent to `安装器无回报，节点未回连`
- **AND** the next action SHALL tell the user to check target-host access to Server/NATS/object storage, curl download result, bootstrap command output, and remote output collection

#### Scenario: No installer events are not rendered as missing step list
- **WHEN** no installer step events have been received
- **THEN** the UI SHALL NOT primarily show a long list of every expected installer step as missing
- **AND** the UI SHALL instead show that installer steps were not received

#### Scenario: Partial installer events may show missing steps
- **WHEN** at least one installer step event has been received
- **AND** the installer event sequence is incomplete
- **THEN** the UI MAY show missing installer step names to help diagnose where reporting stopped

### Requirement: Diagnostic details SHALL not obscure the primary outcome
The installation display SHALL keep the main success/running/failure message focused on user action while preserving deeper diagnostics for troubleshooting.

#### Scenario: Duplicate installer events on a successful install
- **WHEN** duplicated installer events are detected
- **AND** installer detail steps are otherwise complete
- **AND** node connectivity is confirmed
- **THEN** the primary display SHALL show installation success
- **AND** duplicate event counts SHALL be hidden by default or placed in diagnostics rather than shown as a primary warning

#### Scenario: Failure includes phase-specific guidance
- **WHEN** installation fails at credential validation, command dispatch, installer execution, installer no-report, or node connectivity
- **THEN** the UI SHALL show a next action tailored to that phase
- **AND** the next action SHALL be visible without requiring the user to infer it from raw logs

### Requirement: Progress count semantics SHALL be consistent
Backend summaries and frontend displays SHALL use a consistent expected installer step set for user-facing progress.

#### Scenario: Table and drawer show the same installer progress count
- **WHEN** installer progress is shown in the progress table and log drawer for the same task node
- **THEN** both views SHALL use the same expected step count and completed count
- **AND** the views SHALL NOT disagree between six-step and seven-step user-facing progress semantics

## Work Checklist

## 1. Backend State and Summary Semantics

- [x] 1.1 Audit existing controller install result shapes for remote success, remote failure, no installer events, partial installer events, installer step failure, connectivity success, and connectivity timeout.
- [x] 1.2 Align installer expected-step semantics so backend summary and frontend progress use one user-facing count.
- [x] 1.3 Add or derive a stable display state for controller install progress, covering success, running, no-report, installer failure, command failure, and connectivity failure.
- [x] 1.4 Ensure `no_installer_events` plus connectivity timeout produces a clear no-report/connectivity failure reason.
- [x] 1.5 Preserve compatibility for historical task results that only contain legacy `steps`.
- [x] 1.6 Add backend tests for no-report running, no-report timeout, success without detail, installer step failure, complete success, and duplicated-event diagnostics.

## 2. Frontend State Derivation

- [x] 2.1 Add a shared frontend utility that derives the four user-facing phases from normalized controller install result data.
- [x] 2.2 Use the shared utility in both the install progress table and log drawer.
- [x] 2.3 Distinguish `下发安装命令` from `安装器执行` in display labels and state tags.
- [x] 2.4 Render `安装器无回报` / `等待安装器回报` as explicit states when no installer events are present after command dispatch.
- [x] 2.5 Show `success_without_detail` as success with a low-severity note instead of a failure.
- [x] 2.6 Keep duplicated-event counts in diagnostics instead of primary success UI.

## 3. User Copy and Guidance

- [x] 3.1 Add Chinese and English i18n strings for the four phases.
- [x] 3.2 Add Chinese and English i18n strings for installer waiting, installer no-report, success without detail, and no-report timeout.
- [x] 3.3 Add phase-specific next-action guidance for credential failure, command failure, installer no-report, installer step failure, and connectivity timeout.
- [x] 3.4 Replace default `0/6` missing-step display with `安装器步骤：未收到` when no installer events exist.
- [x] 3.5 Only show explicit missing installer step names when at least one installer event has been received.

## 4. UI Verification

- [x] 4.1 Add or update frontend tests for table status rendering across success, running, no-report, installer failure, and connectivity timeout.
- [x] 4.2 Add or update frontend tests for log drawer phase rendering and nested installer detail steps.
- [ ] 4.3 Manually verify the successful screenshot case shows clean success and hides duplicated-event diagnostics by default.
- [ ] 4.4 Manually verify the no-step screenshot case shows `安装器无回报` or `等待安装器回报` instead of a misleading completed installer step.
- [ ] 4.5 Run `cd web && pnpm lint && pnpm type-check` for frontend changes.
  - Targeted eslint for changed node-manager files passed. `NEXTAPI_INSTALL_APP=node-manager pnpm precommit && pnpm exec tsc -p tsconfig.lint.json --noEmit` passed.
  - Full `pnpm lint` is currently blocked by pre-existing cmdb/log/monitor/storybook lint errors unrelated to this change.
  - Full `pnpm type-check` is currently blocked by pre-existing `opspilot` message payload type errors unrelated to this change.

## 5. Server Verification

- [x] 5.1 Run targeted node_mgmt installer summary tests.
- [x] 5.2 Run `cd server && make test` or the narrowest reliable node_mgmt test command if full tests are blocked by environment dependencies.
