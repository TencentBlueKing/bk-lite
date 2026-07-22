# Mask Api Secret Preview

Status: done

## Migration Context

- Legacy source: `openspec/changes/mask-api-secret-preview/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

The current API secret feature exposes the full secret in list responses and frontend tables, which makes repeated viewing and copying possible after creation. This weakens the intended role of the secret as a service credential and creates unnecessary exposure in both API and UI flows.

Now is the right time to tighten this behavior because the system already has a dedicated API secret management page and a clear create flow, so the feature can be adjusted without changing the underlying authentication model or database schema.

## What Changes

- Change API secret list and detail responses to return a preview field instead of the full secret.
- Keep full secret disclosure only in the create response so the frontend can present it once immediately after creation.
- Update the system-manager settings/key page to display preview values only and remove the list copy action.
- Add a one-time success modal after create with warning text and an explicit confirmation checkbox before closing.
- Preserve the current uniqueness rule of one API secret per user, domain, and team.
- Preserve the existing `generate_api_secret` endpoint behavior and keep it out of the new frontend flow.

## Capabilities

### New Capabilities
- `api-secret-management`: Manage API secrets with preview-only read operations and one-time full-secret reveal during creation.

### Modified Capabilities

## Impact

- Backend API contract changes in `server/apps/base/user_api_secret_mgmt/views.py` and `serializers.py`.
- Frontend behavior changes in `web/src/app/system-manager/(pages)/settings/key/page.tsx` and `web/src/app/system-manager/api/settings/index.ts`.
- Locale updates in `web/public/locales/zh.json` and `web/public/locales/en.json`.
- Test updates in existing backend serializer and integration test files.
- No database migration, authentication model redesign, or new dependency introduction.

## Implementation Decisions

## Context

BK-Lite currently manages API secrets through `server/apps/base/user_api_secret_mgmt` and exposes them in the system-manager settings page. The current implementation uses a single serializer with `fields = "__all__"`, so both list and retrieve operations return the full stored `api_secret`, and the frontend table renders and copies that full value directly.

This change spans backend response shaping, frontend settings-page behavior, i18n text, and tests, but it does not change the underlying authentication model. Existing API secret creation, uniqueness rules, and downstream token validation in middleware and business logic remain in place. The main constraint is to reduce post-creation secret exposure without introducing schema changes or breaking the create flow that legitimately needs the full generated secret once.

## Goals / Non-Goals

**Goals:**
- Prevent read operations from exposing the full persisted API secret after creation.
- Preserve a one-time full-secret reveal in the create response so the user can save it immediately.
- Align the settings page UX with one-time-secret semantics by removing list copy behavior and adding an explicit confirmation modal after create.
- Keep the implementation incremental and compatible with the current model and uniqueness constraints.

**Non-Goals:**
- Redesign API token authentication or middleware behavior.
- Change database schema or convert stored API secrets to encrypted or hashed storage.
- Introduce secret rotation, multiple secrets per user/team, or replacement workflows.
- Rework the unused `generate_api_secret` endpoint.

## Decisions

### 1. Split read and create response contracts
List and retrieve responses will expose a new `api_secret_preview` field and omit the full `api_secret`. Create responses will continue returning the full `api_secret`. This is preferred over overloading `api_secret` with different meanings across endpoints because it keeps preview semantics explicit and avoids frontend confusion.

**Alternative considered:** Reuse `api_secret` for preview values in GET responses. Rejected because the same field would represent full and partial values depending on endpoint, which increases the risk of incorrect reuse.

### 2. Keep `retrieve` but apply the same masking policy as `list`
The frontend does not currently call `retrieve`, but DRF exposes it via `ModelViewSet`. Keeping the route while returning preview-only data avoids compatibility surprises and closes a straightforward bypass path.

**Alternative considered:** Disable `retrieve` entirely. Rejected because it is a stronger API behavior change than needed for this feature.

### 3. Enforce one-time reveal in the frontend flow, not with new persistence rules
The frontend settings page will consume the full secret only from the successful create response, show it in a modal with warning text, require checkbox confirmation before the primary close action, and then refresh into preview-only state.

**Alternative considered:** Add a separate backend flag or extra persistence state to track whether the secret has been acknowledged. Rejected as over-design for the current requirement.

### 4. Remove full-secret copy from the list page
Once list responses are preview-only, keeping a copy action would either copy the preview or suggest that a full secret remains available. Removing the list copy action makes the UX consistent with the new contract.

## Risks / Trade-offs

- **[Risk] Existing non-frontend consumers may expect `api_secret` in GET responses** → Mitigation: keep the change limited to the user API secret management endpoints, add/update backend tests, and make the new field name explicit (`api_secret_preview`).
- **[Risk] Users may close the success modal without actually saving the secret** → Mitigation: require an explicit checkbox confirmation before the primary action and warn clearly that the secret cannot be viewed again after closing.
- **[Risk] The secret remains plaintext in storage** → Mitigation: document that this change reduces response/UI exposure only and does not attempt at-rest secrecy.
- **[Risk] `retrieve` could become an overlooked bypass if left unchanged** → Mitigation: apply the same serializer policy to both `list` and `retrieve`.

## Migration Plan

1. Update backend tests to define the new contract for list, retrieve, and create.
2. Implement serializer and view changes in `user_api_secret_mgmt`.
3. Update the system-manager settings API typings and page behavior.
4. Add locale strings for the one-time success modal.
5. Run targeted backend tests and frontend type-check.

Rollback is straightforward: revert the serializer/view/page changes to restore the previous full-secret list behavior.

## Open Questions

- None for this scoped change. The remaining implementation choices have already been decided: preview field name, no list copy action, preserve duplicate-create behavior, preserve `retrieve` route with masking, and leave `generate_api_secret` unchanged.

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-27
```

## Capability Deltas

### api-secret-management

## ADDED Requirements

### Requirement: API secret read operations return preview-only values
The system SHALL return preview-only values for persisted API secrets in read operations. Read operations MUST NOT expose the full stored API secret after creation is complete.

#### Scenario: List API secrets
- **WHEN** a client requests the API secret list endpoint for the current user and team
- **THEN** each item includes `api_secret_preview` containing the first four characters of the stored secret
- **THEN** the response does not include the full `api_secret` value

#### Scenario: Retrieve a single API secret
- **WHEN** a client requests the API secret detail endpoint for an existing API secret
- **THEN** the response includes `api_secret_preview` containing the first four characters of the stored secret
- **THEN** the response does not include the full `api_secret` value

### Requirement: API secret creation reveals the full secret once
The system SHALL return the full generated API secret only in the successful create response so the client can present it immediately to the user.

#### Scenario: Create API secret successfully
- **WHEN** a client creates an API secret for a user and team that do not already have one
- **THEN** the response includes the full generated `api_secret`
- **THEN** the response remains associated with the created user, domain, and team

#### Scenario: Reject duplicate API secret creation
- **WHEN** a client attempts to create an API secret for a user and team that already have one
- **THEN** the system rejects the request with the existing duplicate-create behavior
- **THEN** the existing API secret remains unchanged

### Requirement: API secret management UI enforces one-time reveal behavior
The system-manager API secret page SHALL present preview-only values in the list view and SHALL present the full secret only in the immediate create-success flow.

#### Scenario: View API secret list in settings page
- **WHEN** a user opens the settings API secret page after at least one secret exists
- **THEN** the list displays `api_secret_preview` instead of the full secret
- **THEN** the list does not provide an action to copy the full secret

#### Scenario: Handle successful secret creation in settings page
- **WHEN** a user successfully creates a new API secret from the settings page
- **THEN** the page opens a success modal that displays the full secret returned by the create response
- **THEN** the modal warns that the secret cannot be viewed again after closing
- **THEN** the modal requires explicit user confirmation before it can be closed through the primary action

#### Scenario: Return to preview-only state after confirmation
- **WHEN** the user confirms they have saved the secret in the create-success modal
- **THEN** the modal closes
- **THEN** the page refreshes the API secret list
- **THEN** the refreshed page shows only `api_secret_preview`

## Work Checklist

## 1. Backend contract changes

- [x] 1.1 Update existing backend serializer tests to define preview-only list and retrieve responses plus full create responses
- [x] 1.2 Split API secret serializers so read operations return `api_secret_preview` and create responses return full `api_secret`
- [x] 1.3 Update the user API secret viewset so `list` and `retrieve` use the preview serializer while `create` returns the full-secret serializer
- [x] 1.4 Run targeted backend API secret tests and fix any contract regressions

## 2. Frontend API secret page updates

- [x] 2.1 Update the system-manager settings API types so list responses use `api_secret_preview` and create responses use full `api_secret`
- [x] 2.2 Update the settings/key page table to render preview-only values and remove the list copy action
- [x] 2.3 Add the one-time create-success modal with warning text, checkbox confirmation, and post-close list refresh

## 3. Content and verification

- [x] 3.1 Add or update locale strings for the create-success modal and one-time warning text
- [x] 3.2 Run frontend type-check and fix any typing issues introduced by the API contract change
- [x] 3.3 Review changed backend and frontend files to confirm the final behavior matches the approved design
