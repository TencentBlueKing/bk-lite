# Signin Login Auth Validation UI Callback Refinement Implementation Plan

> **For agentic workers:** REQUIRED EXECUTION STYLE: Use `superpowers:executing-plans` to implement this plan in a single mainline sequence. Follow the task order in this document, use lightweight validation between tasks, and perform full verification/review only after all planned tasks are complete. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the current `/auth/signin` login-auth flow so the login form area switches into a locked waiting state during external auth, and move the callback result page from a backend template to a frontend-owned page while keeping the current visible content.

**Architecture:** Keep the existing auth-request start/poll/callback mechanism and NextAuth session sync flow. Frontend changes stay inside the signin module and add a dedicated result page route, while backend callback handling in `apps.core.views.index_view` stops rendering `login_auth_callback.html` and instead redirects to the frontend result page with explicit status/message parameters.

**Tech Stack:** Next.js App Router, React 19, TypeScript, NextAuth credentials session sync, Django 4.2, Django cache, pytest

## Execution Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If design intent, callback parameter shape, result-page routing, or implementation direction becomes unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to this refinement; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- Prefer no temporary compatibility layer unless explicitly required.
- Execute this plan in `executing-plans` style: follow the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.

**Delivery scope note:** This plan only covers the signin UI waiting-state refinement and callback result-page ownership shift. It does not redesign the auth-request lifecycle, add auto-close/postMessage behavior, or allow switching providers while a request is pending.

---

## File Structure

### Existing files to modify

- `server/apps/core/views/index_view.py`
  Replace backend template rendering in `login_auth_callback()` with redirects to a frontend result route, while preserving callback protocol handling, status updates, and cookie writing.
- `server/apps/core/tests/views/test_login_auth_bindings.py`
  Update callback view assertions from rendered HTML content to redirect contract assertions, and add coverage for explicit callback-result parameters.
- `web/src/app/(core)/auth/signin/SigninClient.tsx`
  Change the current signin rendering so the middle form area switches between form / waiting / syncing states and locks provider switching while a request is active.
- `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
  Refactor from a standalone card-style panel into inline state content that fits the existing signin layout and supports disabled provider items.
- `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
  Expose the active request / waiting state needed to lock provider selection and keep error-source behavior consistent after failed/cancelled/expired outcomes.
- `web/src/app/(core)/auth/signin/login-auth/types.ts`
  Extend current login-auth types for frontend callback result status and provider-item disabled-state needs if required.

### New files to create

- `web/src/app/(core)/auth/signin/login-auth-result/page.tsx`
  Frontend-owned result page that reproduces the current callback page content for success / failed / cancelled / expired outcomes and instructs the user to close the page manually.

### Existing files likely to become unused

- `server/templates/login_auth_callback.html`
  Stop referencing this backend template once callback handling redirects to the frontend result page. Decide during implementation whether to delete it immediately or leave it temporarily unreferenced; if unclear, align with the user before deleting.

### Reference files to read during implementation

- `docs/superpowers/specs/2026-06-18-signin-login-auth-validation-ui-callback-refinement-design.md`
- `docs/superpowers/plans/2026-06-12-signin-login-auth-validation.md`
- `web/src/app/(core)/auth/signin/page.tsx`
- `web/src/constants/authOptions.ts`
- `server/apps/core/services/login_auth_request_service.py`

---

### Task 1: Redirect Backend Callback To A Frontend Result Route

**Files:**
- Modify: `server/apps/core/views/index_view.py`
- Modify: `server/apps/core/tests/views/test_login_auth_bindings.py`
- Reference: `server/templates/login_auth_callback.html`

- [ ] **Step 1: Add focused backend callback assertions for redirect payload shape**

Update `server/apps/core/tests/views/test_login_auth_bindings.py` so callback tests assert:

- success callback returns a redirect instead of rendered HTML
- cancelled / failed / expired / invalid-state branches redirect to the frontend result route with explicit status
- query parameters include at least:
  - `status`
  - `message`

- [ ] **Step 2: Run the focused backend callback tests to capture the current baseline**

Run:

```bash
cd server && uv run pytest apps/core/tests/views/test_login_auth_bindings.py -k "login_auth_callback" -v
```

Expected:
- current callback tests fail where they still expect rendered HTML content or HTTP 200 render responses

- [ ] **Step 3: Add a small helper in `index_view.py` to build the frontend result-page URL**

Implement a focused helper that:

- targets a dedicated frontend route such as `/auth/signin/login-auth-result`
- accepts `status` and `message`
- URL-encodes parameters safely
- keeps all redirects in-site relative

- [ ] **Step 4: Replace `_render_login_auth_callback_page(...)` usage in callback branches**

Adjust `login_auth_callback()` so:

- invalid state redirects to result route with `status=failed`
- cache-miss / expired request redirects with `status=expired`
- provider cancellation redirects with `status=cancelled`
- provider / runtime failure redirects with `status=failed`
- replayed terminal states redirect using the already-known terminal status
- success redirects with `status=success`

Keep existing behavior for:

- `update_auth_request_status(...)`
- `login_with_binding(...)`
- writing `bklite_token` on successful auth completion

- [ ] **Step 5: Keep callback result parameters explicit and stable**

When redirecting to the frontend result page, ensure the backend always passes:

- `status`
- `message`

Do not rely on the frontend to infer message text from status alone during this refinement.

- [ ] **Step 6: Re-run the focused backend callback tests**

Run:

```bash
cd server && uv run pytest apps/core/tests/views/test_login_auth_bindings.py -k "login_auth_callback" -v
```

Expected:
- callback-specific tests PASS with redirect assertions

---

### Task 2: Add The Frontend-Owned Callback Result Page

**Files:**
- Create: `web/src/app/(core)/auth/signin/login-auth-result/page.tsx`
- Modify: `web/src/app/(core)/auth/signin/login-auth/types.ts`
- Reference: `server/templates/login_auth_callback.html`

- [ ] **Step 1: Define the result-page input contract in frontend types if needed**

If the current signin types do not already cover callback result display, add a small type for:

- `status: 'success' | 'failed' | 'cancelled' | 'expired'`
- `message: string`

Keep this local to signin login-auth types; do not create a broad shared auth model for this small refinement.

- [ ] **Step 2: Create the frontend result page route**

Create `web/src/app/(core)/auth/signin/login-auth-result/page.tsx` that:

- reads `status` and `message` from `searchParams`
- renders the same visible content structure currently used by `server/templates/login_auth_callback.html`
- keeps the current manual-close behavior
- does not add auto-close, opener messaging, or extra actions

- [ ] **Step 3: Preserve current visible content semantics**

Match the existing callback page behavior:

- success shows `认证完成`
- cancelled shows `认证已取消`
- expired shows `认证已过期`
- all other statuses show `认证失败`
- body text comes from the passed `message`

The goal here is ownership shift, not content redesign.

- [ ] **Step 4: Add minimal fallback handling for bad parameters**

If `status` is missing or invalid, normalize to a safe failure display state rather than crashing or showing blank content.

- [ ] **Step 5: Run a targeted frontend lint check for the new page and touched types**

Run:

```bash
cd web && pnpm exec eslint src/app/\(core\)/auth/signin/login-auth-result/page.tsx src/app/\(core\)/auth/signin/login-auth/types.ts
```

Expected:
- PASS

---

### Task 3: Refine Waiting State In The Signin Page

**Files:**
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Modify: `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
- Modify: `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
- Modify: `web/src/app/(core)/auth/signin/login-auth/types.ts`

- [ ] **Step 1: Add the minimal hook state needed to distinguish selecting / waiting / syncing / terminal recovery**

Review `useLoginAuthValidation.ts` and expose only the state already implied by the existing flow, including:

- current `viewState`
- `activeBindingName`
- whether a request is actively pending
- the existing error source used for failed / cancelled / expired recovery

Do not invent a second parallel state model if the existing hook already owns the truth.

- [ ] **Step 2: Update `SigninClient.tsx` to treat the middle form area as a state-switching content zone**

Change signin rendering so:

- default selecting state shows the username/password form
- waiting state replaces that form area with inline waiting content
- syncing-session keeps the same region in status mode
- failed / cancelled / expired recover back to the form plus lightweight error display

Keep:

- page title area unchanged
- bottom provider list in the same general location

- [ ] **Step 3: Refactor `LoginAuthValidationPanel.tsx` away from the separate card layout**

Adjust the panel so it renders:

- provider-choice content compatible with the existing signin layout
- inline waiting / syncing content without introducing a second boxed card
- disabled provider items when the current view state is waiting or syncing

This component should stop competing visually with the main signin form container.

- [ ] **Step 4: Lock provider switching during waiting and syncing**

Implement provider locking rules exactly as designed:

- current provider remains visually active
- other provider items are truly disabled and not clickable
- no fake-disabled hover + click interception pattern

Do not allow starting a second external auth request while one is pending.

- [ ] **Step 5: Keep failure recovery tied to the existing validation error source**

When the signin flow returns from `failed` / `cancelled` / `expired`:

- restore the form area
- surface the existing hook-managed error message
- avoid mixing a second set of hardcoded local UI messages inside `SigninClient.tsx`

- [ ] **Step 6: Run targeted frontend lint on the signin refinement files**

Run:

```bash
cd web && pnpm exec eslint src/app/\(core\)/auth/signin/SigninClient.tsx src/app/\(core\)/auth/signin/login-auth/LoginAuthValidationPanel.tsx src/app/\(core\)/auth/signin/login-auth/useLoginAuthValidation.ts src/app/\(core\)/auth/signin/login-auth/types.ts
```

Expected:
- PASS

---

### Task 4: Final Verification And Cleanup Decision

**Files:**
- Review: `server/apps/core/views/index_view.py`
- Review: `server/apps/core/tests/views/test_login_auth_bindings.py`
- Review: `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Review: `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
- Review: `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
- Review: `web/src/app/(core)/auth/signin/login-auth-result/page.tsx`
- Review: `server/templates/login_auth_callback.html`

- [ ] **Step 1: Run the focused backend login-auth view test file**

Run:

```bash
cd server && uv run pytest apps/core/tests/views/test_login_auth_bindings.py -v
```

Expected:
- PASS

- [ ] **Step 2: Run the targeted frontend lint suite for all touched signin files**

Run:

```bash
cd web && pnpm exec eslint src/app/\(core\)/auth/signin/SigninClient.tsx src/app/\(core\)/auth/signin/login-auth/LoginAuthValidationPanel.tsx src/app/\(core\)/auth/signin/login-auth/useLoginAuthValidation.ts src/app/\(core\)/auth/signin/login-auth/types.ts src/app/\(core\)/auth/signin/login-auth-result/page.tsx
```

Expected:
- PASS

- [ ] **Step 3: Run a focused manual validation of the end-to-end UI behavior**

Verify manually in `/auth/signin`:

- initial page still shows title + form + provider list
- clicking an external provider opens a new page
- original page form area switches into waiting content
- provider list is locked while waiting
- failed / cancelled / expired flows restore the form and error message
- successful callback lands on the frontend result page and preserves current visible content

- [ ] **Step 4: Decide whether to delete the now-unused backend template**

If `server/templates/login_auth_callback.html` is no longer referenced anywhere after implementation:

- either delete it in the same change
- or stop and align with the user if there is any uncertainty about retaining it temporarily

- [ ] **Step 5: Perform a final lightweight code review against the spec**

Check that implementation matches:

- no extra card introduced for waiting state
- provider switching is locked during pending auth
- callback result page is frontend-owned
- no auto-close or postMessage behavior was introduced
