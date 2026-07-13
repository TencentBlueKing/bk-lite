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
