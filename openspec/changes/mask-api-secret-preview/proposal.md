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
