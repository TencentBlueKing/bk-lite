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
