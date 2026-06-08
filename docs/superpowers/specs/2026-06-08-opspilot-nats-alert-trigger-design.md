# OpsPilot NATS Alert Trigger Design

## Context

OpsPilot Studio already supports multiple workflow entry nodes such as `celery`, `restful`, `openai`, `enterprise_wechat`, `web_chat`, and related trigger types. In the current repository:

- `server/apps/system_mgmt/nats_api.py::send_msg_with_channel` already dispatches by channel type.
- `server/apps/system_mgmt/utils/channel_utils.py::send_nats_message` already forwards a NATS request based on channel `namespace` and `method_name`.
- OpsPilot workflow execution records `entry_type` and uses `flow_input` as the shared context for downstream nodes.
- Memory nodes currently resolve personal memory from `flow_input.user_id`, while team memory is still tied to the memory space configuration.

The new requirement is to let Alert Center trigger an OpsPilot workflow through a NATS channel and carry alert-specific session context forward for later nodes, especially personal memory, organization memory, notification, and permission-sensitive tools.

The updated upstream contract is:

1. Alert Center does **not** call a dedicated OpsPilot NATS API directly. It calls `system_mgmt.send_msg_with_channel`.
2. When the selected channel is a NATS channel, `content` is designed as:
   ```json
   {
     "message": "",
     "team": [],
     "user_ids": []
   }
   ```
3. The NATS channel config adds two routing keys: `bot_id` and `node_id`.

## Goals

- Keep Alert Center integrated through the existing `send_msg_with_channel` entry.
- Reuse the existing NATS channel abstraction instead of adding a second alert-only dispatch path.
- Add an OpsPilot-native `nats` trigger node and execution type.
- Standardize the alert payload into workflow context so downstream nodes can reuse it without parsing raw NATS kwargs repeatedly.
- Make alert recipients become the session stakeholders for downstream personal-memory and notification flows.
- Make alert team information become the organization context for downstream organization-memory and permission flows.
- Keep the design backward-compatible for non-NATS channels and non-alert workflows.

## Non-Goals

- Alert Center-side auto-inference of organization.
- Complex stakeholder prioritization rules beyond preserving order and selecting the first entry as the primary stakeholder.
- A second payload shape for NATS alerts.
- General-purpose multi-organization memory writes in one execution.

## Approaches

### Recommended: Channel-side enrichment and OpsPilot-side normalization

Alert Center always calls `send_msg_with_channel`. For NATS channels, `send_msg_with_channel` validates `content`, and `send_nats_message` injects `bot_id` and `node_id` from channel config before making the NATS request. OpsPilot exposes a dedicated NATS-consumer method that receives the enriched kwargs and normalizes them into workflow `flow_input`.

Why this is preferred:

- Alert Center only needs to know the stable `content` contract.
- OpsPilot routing stays in System Management channel config, where `namespace`, `method_name`, `bot_id`, and `node_id` already belong.
- The workflow engine receives a fully standardized context and downstream nodes stay simple.

### Alternative: Alert Center assembles the full OpsPilot request itself

Alert Center would provide `bot_id`, `node_id`, and all execution fields directly in the NATS payload.

Why this is weaker:

- Routing knowledge leaks into Alert Center.
- Channel config becomes partially redundant.
- Changes to workflow routing would require Alert Center changes instead of only channel reconfiguration.

### Alternative: Minimal relay with no context normalization

System Management forwards the raw `content` plus config keys, and each downstream OpsPilot node decides how to parse `team` and `user_ids`.

Why this is not recommended:

- Node behavior becomes inconsistent.
- Personal memory, organization memory, and notification nodes would duplicate parsing logic.
- Future changes to payload shape would require touching many nodes.

## Trigger Contract

### Alert Center -> System Management

Alert Center calls:

```python
send_msg_with_channel(channel_id, title, content, receivers, attachments=None)
```

For NATS channels:

- `title` is ignored by the NATS branch.
- `receivers` is kept only for interface compatibility and is not the source of truth.
- `content` is the source of truth and must be a dict with:
  - `message: str`
  - `team: list[int]`
  - `user_ids: list[str]`

Validation rules in the NATS branch:

- `message` must be a non-empty string after trimming.
- `team` must be a list; invalid items are dropped after integer normalization.
- `user_ids` must be a list; invalid or empty items are dropped after string normalization.
- Invalid payload returns `{"result": False, "message": "..."}`
- Non-NATS channel behavior remains unchanged.

### System Management NATS Channel Config

The NATS channel config keeps:

- `namespace`
- `method_name`
- `timeout`

And adds:

- `bot_id`
- `node_id`

`send_nats_message` enriches the outgoing kwargs as:

```json
{
  "message": "...",
  "team": [2],
  "user_ids": ["alice", "bob"],
  "bot_id": 12,
  "node_id": "nats-entry-1"
}
```

`bot_id` and `node_id` are owned by channel config rather than Alert Center payload so routing can be changed without changing Alert Center code.

## OpsPilot NATS Trigger Design

OpsPilot adds a dedicated NATS consumer in `server/apps/opspilot/nats_api.py`, referenced by the NATS channel `namespace` and `method_name`.

The consumer is responsible for:

1. Validating `bot_id`, `node_id`, `message`, `team`, and `user_ids`
2. Loading the target `Bot` and `BotWorkFlow`
3. Ensuring the target node exists and is of type `nats`
4. Creating a workflow engine with `entry_type="nats"`
5. Building normalized `input_data`
6. Executing the workflow

OpsPilot also adds:

- `WorkFlowExecuteType.NATS`
- Node registry support for `nats`
- Frontend Studio support for the `nats` trigger node as a first-class entry node

The `nats` node behaves like other trigger nodes in execution flow: it is only the workflow entry and does not perform business logic by itself.

## Normalized Workflow Context

The NATS payload must be normalized once at workflow entry and then stored into `flow_input`.

Recommended normalized shape:

```json
{
  "last_message": "告警内容摘要",
  "message": "告警内容摘要",
  "entry_type": "nats",
  "trigger_type": "nats",
  "bot_id": 12,
  "node_id": "nats-entry-1",
  "user_id": "alice",
  "session_stakeholders": ["alice", "bob"],
  "primary_stakeholder_user_id": "alice",
  "current_organization_id": 2,
  "current_organization_ids": [2],
  "authorized_team_ids": [2],
  "trigger_payload": {
    "message": "告警内容摘要",
    "team": [2],
    "user_ids": ["alice", "bob"]
  },
  "is_third_party": true
}
```

Normalization rules:

- `user_id` = the first valid `user_ids` element, or empty string if none exists.
- `session_stakeholders` = normalized `user_ids` in original order.
- `primary_stakeholder_user_id` = first stakeholder.
- `current_organization_ids` = normalized `team`.
- `authorized_team_ids` = same as `current_organization_ids` for downstream permission checks.
- `current_organization_id` = first team entry.

The first team entry is treated as the current organization because the current memory engine and most permission-sensitive downstream operations need one active organization context. The full array is still preserved for future expansion.

## Downstream Node Semantics

### Personal memory

For NATS-triggered executions, personal-memory resolution should prefer:

1. `flow_input.primary_stakeholder_user_id`
2. `flow_input.user_id`
3. Existing fallback behavior

This keeps alert recipients as the session stakeholders and makes later personal-memory reads and writes target the notified person instead of an unrelated system account.

### Organization memory

For NATS-triggered executions, organization-memory resolution should prefer:

1. `flow_input.current_organization_id`
2. Existing fallback behavior based on memory space configuration

This lets Alert Center-provided team information drive the organization memory target for the current run while keeping old workflows compatible.

### Notification and email nodes

Downstream notification behavior should reuse normalized stakeholders instead of forcing users to re-enter recipients for alert-driven flows.

Recommended first-step support:

- Add recipient-resolution logic that can read `session_stakeholders`
- Keep static recipient configuration for existing workflows
- For alert-driven workflows, allow explicit use of normalized stakeholders as the recipient source

This should be implemented as reuse of normalized context, not as a second alert-only notification path.

### Permission-sensitive tools

Tools or nodes that need organization scope should use:

- `current_organization_id` as the active organization
- `authorized_team_ids` as the permissible scope

If the organization context is missing when a node requires it, the execution should fail explicitly with a clear error message.

## Error Handling

### System Management layer

- If NATS channel config misses `namespace`, `method_name`, `bot_id`, or `node_id`, reject the send request.
- If `content` is not a dict or misses required fields, reject the send request.
- Do not silently merge `receivers` into `user_ids`.

### OpsPilot NATS consumer

- If `bot_id` or `node_id` is invalid, reject the trigger.
- If the node is not a `nats` entry node, reject the trigger.
- If `team` is empty, organization memory and organization-scoped tools must fail explicitly when invoked.
- If `user_ids` is empty, personal memory and stakeholder-based notification must fail explicitly when invoked.

### Observability

Execution logs and records should include summaries of:

- `execution_id`
- `entry_type=nats`
- `bot_id`
- `node_id`
- stakeholder count
- active organization id

Sensitive content should not be expanded into logs beyond safe summaries.

## Frontend Studio Impact

Studio should expose a new trigger node type `nats` alongside current trigger nodes.

The node configuration should stay minimal because routing is owned by the System Management channel config:

- no token or webhook fields
- no direct namespace/method entry in Studio
- standard input/output parameter display consistent with other entry nodes

This keeps workflow design focused on execution flow while channel routing stays in the channel system.

## Backward Compatibility

- Existing `send_msg_with_channel` calls for email, webhook, bot channels, and custom webhook remain unchanged.
- Existing NATS channels that do not target OpsPilot can continue using the existing `namespace` and `method_name` behavior, but they must now provide valid payloads for the methods they call.
- Existing OpsPilot workflows without a `nats` node remain unchanged.
- Existing memory workflows keep their current fallback behavior when the new NATS context is absent.

## Rollout Sequence

1. Extend NATS channel config with `bot_id` and `node_id`
2. Tighten `send_msg_with_channel` NATS payload validation
3. Make `send_nats_message` enrich payload from config
4. Add OpsPilot NATS consumer method
5. Add `nats` workflow entry type and node registration
6. Normalize NATS payload into `flow_input`
7. Update memory and notification recipient resolution to consume normalized context
8. Add Studio `nats` node and display support

## Final Recommendation

Use **System Management as the stable integration boundary** and **OpsPilot as the context normalization boundary**.

That means:

- Alert Center only knows `send_msg_with_channel`
- NATS routing stays in channel config through `namespace`, `method_name`, `bot_id`, and `node_id`
- OpsPilot receives one enriched payload shape and turns it into stable workflow context
- Downstream memory, notification, and permission logic all reuse the same normalized fields

This keeps the change minimal in integration surface, explicit in routing, and extensible for later alert-specific workflow capabilities.
