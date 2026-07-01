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
