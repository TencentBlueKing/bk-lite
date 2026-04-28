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
