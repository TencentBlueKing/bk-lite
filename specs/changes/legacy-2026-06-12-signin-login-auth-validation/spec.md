# Historical Superpowers change: 2026-06-12-signin-login-auth-validation

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-12-signin-login-auth-validation.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the current `/auth/signin` login-auth flow so the default signin page opens provider auth in a new tab, polls backend auth-request status, and completes NextAuth session sync after backend login succeeds.

**Architecture:** Keep `/auth/signin` as the single frontend entry and switch the default signin shell to the login-auth panel flow. Backend owns the auth transaction in a cache-backed `auth_request` service, exposes public start/status/callback endpoints in `apps.core.views.index_view`, and reuses the existing login-auth binding runtime to build provider URLs and complete platform login. Frontend keeps the existing password / OTP / reset-password flow inside the same shell rather than preserving a separate legacy visible mode branch.

**Tech Stack:** Next.js App Router, React 19, TypeScript, NextAuth credentials session sync, Django 4.2, Django cache, existing system_mgmt login-auth runtime service

---

## File Structure

### Backend

- Create: `server/apps/core/services/login_auth_request_service.py`
  - Own cache-backed `auth_request` lifecycle: create, read, update status, parse signed state, validate poll token, expire records.
- Modify: `server/apps/core/views/index_view.py`
  - Add public endpoints for `start_login_auth`, `get_login_auth_request_status`, and backend callback handling; reuse existing cookie writer and logging.
- Modify: `server/apps/core/urls.py`
  - Register the new public login-auth routes.
- Create: `server/templates/login_auth_callback.html`
  - Render a minimal completion page for the new-tab callback experience.
- Modify: `server/apps/core/tests/views/test_login_auth_bindings.py`
  - Extend existing public login-auth tests for the new endpoints and callback state transitions.

### Frontend

- Create: `web/src/app/(core)/auth/signin/login-auth/types.ts`
  - Centralize login-auth flow types for bindings, auth requests, poll status, and sync states.
- Create: `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
  - Own login-auth data flow: fetch bindings, start auth request, open new tab, poll status, trigger session sync.
- Create: `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
  - Render binding-driven provider items and waiting / syncing / failed / expired states in `/auth/signin` style.
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`
  - Switch the default signin shell to the login-auth flow, reuse `completeAuthentication()`, and expose a callback for session sync.
- Modify: `web/src/app/(core)/auth/signin/page.tsx`
  - Keep the server entry focused on authenticated redirect handling without introducing a separate `loginAuthMode` branch.

## Implementation Notes

- Reuse `django.core.cache` and follow the existing short-lived challenge pattern from `server/apps/system_mgmt/otp_challenge.py`.
- Reuse `build_login_auth_redirect()` and `login_with_binding()` rather than adding a second provider runtime path.
- Keep public login-auth endpoints in `apps.core.views.index_view.py` because existing public login endpoints already live there.
- Do not add new frontend test files. Validate frontend work with targeted lint + TypeScript checks and manual UI verification.
- Do not add git commit steps; this repo workflow leaves commits to the user.

### Task 1: Build the backend auth-request service

**Files:**
- Create: `server/apps/core/services/login_auth_request_service.py`
- Test: `server/apps/core/tests/views/test_login_auth_bindings.py`
- Reference: `server/apps/system_mgmt/otp_challenge.py`
- Reference: `server/apps/system_mgmt/services/login_auth_binding_service.py`

- [ ] **Step 1: Add cache-backed contract tests to the existing login-auth view test file**

Add new cases in `server/apps/core/tests/views/test_login_auth_bindings.py` for:

```python
def test_start_login_auth_returns_auth_request_and_poll_token():
    ...

def test_login_auth_status_requires_matching_poll_token():
    ...

def test_login_auth_status_returns_expired_when_cache_entry_missing():
    ...
```

Focus assertions on payload shape:
- `auth_request_id`
- `poll_token`
- `login_url`
- `expires_at`
- status endpoint rejects missing / wrong `poll_token`

- [ ] **Step 2: Run the focused backend test file to capture the baseline**

Run:

```bash
cd server && uv run pytest apps/core/tests/views/test_login_auth_bindings.py -v
```

Expected:
- existing tests pass
- new test skeletons fail because service / endpoints do not exist yet

- [ ] **Step 3: Create `login_auth_request_service.py` with cache helpers**

Implement a focused service module with:

```python
AUTH_REQUEST_PREFIX = "login_auth_request:"
AUTH_REQUEST_TTL = 300

def create_auth_request(binding_id: int, provider_key: str, callback_url: str) -> dict: ...
def get_auth_request(auth_request_id: str) -> dict | None: ...
def update_auth_request_status(auth_request_id: str, status: str, error_message: str = "", login_result: dict | None = None) -> dict | None: ...
def build_auth_request_state(auth_request_id: str, binding_id: int, callback_url: str) -> str: ...
def parse_auth_request_state(state: str) -> dict | None: ...
def validate_poll_token(auth_request: dict, poll_token: str) -> bool: ...
```

Implementation constraints:
- use `django.core.cache`
- use `uuid.uuid4()` for `auth_request_id` / `poll_token`
- store `created_at`, `expired_at`, `completed_at`
- keep `cancelled` only for provider-declared denial, not “tab closed”
- persist a sanitized platform `login_result` only for successful auth completion so the original page can reuse `completeAuthentication()`
- allow `login_result` to be either token-ready or OTP-challenge-ready (`require_otp`, `challenge_id`, optional `qr_code`)

- [ ] **Step 4: Reuse the existing binding runtime instead of inventing new provider logic**

Inside the new service, prepare data needed by views but do **not** duplicate provider calls:
- derive the provider-facing `redirect_uri` from the current request origin plus the backend callback route
- use `build_login_auth_redirect()` to get the provider URL
- keep `binding_id`, `auth_request_id`, and final business `callback_url` inside signed / encoded state
- do not modify `login_with_binding()`

- [ ] **Step 5: Re-run the focused backend test file**

Run:

```bash
cd server && uv run pytest apps/core/tests/views/test_login_auth_bindings.py -v
```

Expected:
- service-facing payload assertions now pass where views are already wired
- remaining failures should point only to missing public endpoints / callback handling

### Task 2: Add public backend endpoints and callback handling

**Files:**
- Modify: `server/apps/core/views/index_view.py`
- Modify: `server/apps/core/urls.py`
- Create: `server/templates/login_auth_callback.html`
- Modify: `server/apps/core/tests/views/test_login_auth_bindings.py`

- [ ] **Step 1: Extend the existing test file with endpoint and callback cases**

Add cases for:

```python
def test_start_login_auth_calls_runtime_and_returns_public_payload():
    ...

def test_login_auth_callback_marks_request_success_and_sets_cookie():
    ...

def test_login_auth_callback_marks_cancelled_on_access_denied():
    ...

def test_login_auth_callback_rejects_invalid_state():
    ...

def test_login_auth_status_returns_failed_payload():
    ...

def test_login_auth_status_returns_login_result_on_success():
    ...

def test_login_auth_status_returns_otp_challenge_payload_on_success():
    ...
```

Mock boundaries:
- patch auth-request service helpers
- patch `SystemMgmt().login_with_binding()` only if callback view still delegates through existing login path

- [ ] **Step 2: Add `start_login_auth` and status views in `index_view.py`**

Implement public handlers that:
- parse `binding_id` and `callback_url`
- validate `callback_url` as a relative in-site path
- fetch the public binding list or the target binding safely
- create `auth_request`
- build an absolute backend callback URL from the current request (this is provider `redirect_uri`, not final business `callback_url`)
- follow the existing public-login pattern with `@api_exempt` so the unauthenticated browser POST does not fail CSRF checks
- return `auth_request_id`, `poll_token`, `login_url`, `expires_at`

Status handler responsibilities:
- read `auth_request_id` from URL
- require `poll_token`
- return one of `pending / success / failed / expired / cancelled`
- return sanitized `login_result` only when status is `success`
- avoid exposing provider secrets or third-party profile data

- [ ] **Step 3: Add backend callback handling in `index_view.py`**

Implement a new public callback view that:
- reads provider callback params (`code`, `state`, `error`, `error_description`)
- parses signed state into `auth_request_id`, `binding_id`, `callback_url`
- maps provider-declared denial to `cancelled`
- on success, calls the existing binding login path and reuses `_set_auth_cookie_on_response()`
- updates `auth_request.status` and stores the sanitized platform login payload needed by the original page
- renders `login_auth_callback.html`

Keep logging aligned with existing login views and avoid printing raw tokens / code values.

If the binding login path returns `require_otp=True`, keep `auth_request.status="success"` and store the OTP challenge payload instead of forcing token issuance inside the callback.

- [ ] **Step 4: Register the new routes in `server/apps/core/urls.py`**

Add routes for:

```python
re_path(r"api/start_login_auth/", index_view.start_login_auth),
re_path(r"api/login_auth_requests/(?P<auth_request_id>[^/]+)/status", index_view.get_login_auth_request_status),
re_path(r"api/login_auth/callback/", index_view.login_auth_callback),
```

Match the existing public `api/...` route style in this file.

- [ ] **Step 5: Add the callback completion template**

Create `server/templates/login_auth_callback.html` with:
- success / failed / cancelled copy placeholders driven by context
- no sensitive data rendering
- a simple instruction like “认证已完成，可返回原页面继续”

Keep it minimal; this page is only a completion bridge for the new-tab flow.

- [ ] **Step 6: Run the backend login-auth test file again**

Run:

```bash
cd server && uv run pytest apps/core/tests/views/test_login_auth_bindings.py -v
```

Expected:
- all login-auth public view tests pass

### Task 3: Add frontend login-auth types, panel, and polling hook

**Files:**
- Create: `web/src/app/(core)/auth/signin/login-auth/types.ts`
- Create: `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
- Create: `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
- Modify: `web/src/app/(core)/auth/signin/page.tsx`
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`

- [ ] **Step 1: Create frontend types for the current login-auth flow**

In `types.ts`, add focused types:

```ts
export type LoginAuthRequestStatus = 'pending' | 'success' | 'failed' | 'expired' | 'cancelled';

export interface LoginAuthBindingItem {
  id: number;
  name: string;
  icon: string;
  description: string;
  provider_key: string;
}

export interface StartLoginAuthResponseData {
  auth_request_id: string;
  poll_token: string;
  login_url: string;
  expires_at: string;
}
```

- [ ] **Step 2: Build `useLoginAuthValidation.ts`**

The hook should own:
- fetching `get_login_auth_bindings`
- starting `start_login_auth`
- `window.open(login_url, "_blank")`
- storing `auth_request_id`, `poll_token`, `callbackUrl`
- polling `/api/proxy/core/api/login_auth_requests/{id}/status`
- stopping on `success / failed / expired / cancelled`
- handling `window.open()` failure without starting polling
- surfacing OTP challenge payloads back to `SigninClient`

Keep fetch code inside the hook because current signin flow already uses direct `fetch()` rather than a separate API layer.

- [ ] **Step 3: Build `LoginAuthValidationPanel.tsx`**

Render:
- built-in platform password card
- external login-auth cards
- waiting state
- syncing-session state
- failed / expired / cancelled state with retry action

UI rules:
- follow `/auth/signin` visual style
- use existing `--color-*` variables
- no backend-config-page layout patterns

- [ ] **Step 4: Keep `page.tsx` focused on the default signin shell entry**

Update the server page entry to preserve existing behavior:
- do not introduce a `loginAuthMode` branch
- keep current authenticated redirect logic unchanged
- pass through only the existing query data needed by the client

- [ ] **Step 5: Switch `SigninClient.tsx` to the login-auth shell**

Add a top-level branch so that:
- the default signin shell renders `LoginAuthValidationPanel`
- the existing username/password form remains inside the same shell
- old visible WeChat / BK entry rendering no longer acts as the primary frontend path

Do **not** rewrite current OTP / password reset flow; the login-auth shell should wrap it, not fork it.

- [ ] **Step 6: Run targeted frontend lint**

Run:

```bash
cd web && pnpm exec eslint src/app/\(core\)/auth/signin/page.tsx src/app/\(core\)/auth/signin/SigninClient.tsx src/app/\(core\)/auth/signin/login-auth/LoginAuthValidationPanel.tsx src/app/\(core\)/auth/signin/login-auth/useLoginAuthValidation.ts src/app/\(core\)/auth/signin/login-auth/types.ts
```

Expected:
- no new lint errors in touched files

### Task 4: Reuse `completeAuthentication()` for session sync after polling success

**Files:**
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Modify: `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
- Modify: `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
- Reference: `web/src/utils/authRedirect.ts`

- [ ] **Step 1: Extract a reusable “sync current backend login into NextAuth” callback from `SigninClient.tsx`**

Reuse the existing pieces already in `completeAuthentication()`:
- `saveAuthToken(...)`
- `signIn('credentials', { skipValidation: 'true', userData: ... })`
- `buildThirdLoginCallbackUrl(...)`

The login-auth success path should not invent a second session-sync mechanism.

- [ ] **Step 2: On poll `success`, branch between OTP challenge and token-ready login payload**

In the hook:
- move state from `waiting` to `syncing-session`
- read the protected `login_result` from the success status response
- if `require_otp` and `challenge_id` are present, hand the payload back to `SigninClient` and reuse the existing OTP flow
- otherwise validate that it contains the existing `completeAuthentication()` essentials (`id` or `username`, `token`, locale/timezone defaults)
- pass the token-ready payload to the reusable session-sync callback

If the backend callback marked success but the returned `login_result` is neither OTP-ready nor token-ready, or if session sync fails, transition to `failed` with a retry action.

- [ ] **Step 3: Make builtin password login inside the login-auth shell preserve `callbackUrl` semantics**

Ensure built-in password login still ends at:
- the login-auth shell `callbackUrl`
- existing `thirdLogin` token appending behavior when applicable

This avoids a split between external-auth success and password success.

- [ ] **Step 4: Reuse the existing OTP verification path when external auth requires OTP**

Wire the login-auth shell so that:
- polling success with `require_otp` switches `authStep` to `otp-verification`
- existing `OtpVerificationForm` still posts to `/api/proxy/core/api/verify_otp_login/`
- successful OTP verification falls back into the same `completeAuthentication()` path
- first-time OTP binding QR payload still renders through existing signin logic

- [ ] **Step 5: Run targeted TypeScript validation**

Run:

```bash
cd web && pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected:
- no new type errors from touched auth files
- if blocked by known repo baseline issues, record that the failure is pre-existing and unrelated

### Task 5: End-to-end verification for backend contract and frontend states

**Files:**
- Modify: `server/apps/core/tests/views/test_login_auth_bindings.py` (only if small assertion gaps remain)
- Modify: `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx` (only if light/dark or state copy issues remain)

- [ ] **Step 1: Re-run the backend login-auth tests**

Run:

```bash
cd server && uv run pytest apps/core/tests/views/test_login_auth_bindings.py -v
```

Expected:
- all login-auth public flow tests pass

- [ ] **Step 2: Re-run frontend lint and TypeScript checks together**

Run:

```bash
cd web && pnpm exec eslint src/app/\(core\)/auth/signin/page.tsx src/app/\(core\)/auth/signin/SigninClient.tsx src/app/\(core\)/auth/signin/login-auth/LoginAuthValidationPanel.tsx src/app/\(core\)/auth/signin/login-auth/useLoginAuthValidation.ts src/app/\(core\)/auth/signin/login-auth/types.ts
cd web && pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected:
- touched frontend auth files remain clean
- any remaining type failures are existing repo baseline issues, not introduced by this change

- [ ] **Step 3: Manually verify the required UI states**

Check in the browser:
- signin page login-auth list state
- click external auth opens a **new tab**
- original signin page stays in place and enters waiting state
- success path moves to syncing-session then redirects
- OTP-enabled success path moves from waiting into the existing OTP verification UI, then completes login after OTP verification
- failure / cancelled / expired states show retry affordance
- light and dark themes both remain readable and use existing theme tokens

- [ ] **Step 4: Verify cookie-scope assumption before rollout**

Confirm in the target environment:
- backend callback writes `bklite_token`
- success status response returns the sanitized platform login payload expected by `completeAuthentication()`
- original `/auth/signin` page can still rely on the callback-written `bklite_token` for subsequent authenticated requests after NextAuth sync

If this fails, stop rollout and resolve cookie domain / proxy alignment before continuing.
