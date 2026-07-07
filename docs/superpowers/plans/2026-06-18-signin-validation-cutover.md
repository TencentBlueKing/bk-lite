# Signin Validation Cutover Implementation Plan

> **For agentic workers:** REQUIRED EXECUTION STYLE: Use `superpowers:executing-plans` to implement this plan in a single mainline sequence. Follow the task order in this document, use lightweight validation between tasks, and perform full verification/review only after all planned tasks are complete. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the signin experience over to the current validation-oriented shell so the default signin page and session-expired modal only expose the fixed password form plus binding-driven third-party providers, with WeChat already converged onto the same binding flow.

**Architecture:** `SigninClient` is the single login shell for both page and modal modes, old WeChat/BK visible entry rendering is removed, and session-expiry interception is adjusted so public login-auth APIs remain usable after expiry. WeChat behaves as a standard binding provider on the existing `start_login_auth -> callback -> poll status -> session sync` contract, without preserving the legacy popup bridge flow as the main signin path.

**Tech Stack:** Next.js App Router, React 19, TypeScript, NextAuth credentials session sync, Django 4.2 public login-auth endpoints

## Execution Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If design intent, compatibility scope, login semantics, or implementation direction becomes unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to this signin cutover; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- The implementation is already converged on one login shell and one binding-driven provider flow.
- Prefer no temporary compatibility layer unless explicitly required.
- If callback behavior, provider contract semantics, or session synchronization expectations become unclear, stop and align with the user before continuing.
- Execute this plan in `executing-plans` style: follow the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.

**Delivery scope note:** The current code state already reflects the cutover result: visible legacy frontend entries are removed from the main signin path, and the active login flow is binding-driven.

---

## File Structure

### Existing files to modify

- `web/src/app/(core)/auth/signin/page.tsx`
  Keep the current login shell as the effective default signin mode and clean up redirect branching that only exists for legacy visible entry modes.
- `web/src/app/(core)/auth/signin/SigninClient.tsx`
  Collapse page/modal login rendering into one shell, keep the fixed password form, remove visible legacy third-party entry branches, and preserve OTP/reset-password handoff.
- `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
  Keep binding-driven provider flow as the sole visible third-party source and own the shared page/modal third-party state machine.
- `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
  Remain the third-party binding list renderer and loading/selection surface under the fixed password form.
- `web/src/app/(core)/auth/signin/login-auth/types.ts`
  Extend or tighten types for the unified page/modal shell and binding-driven provider/result contracts.
- `web/src/context/auth.tsx`
  Switch the session-expired modal to the same signin shell and remove reliance on visible legacy entry toggles.
- `web/src/utils/sessionExpiry.ts`
  Allow validation public APIs during expired-session relogin.
- `web/src/utils/authRedirect.ts`
  Adjust only if the remaining popup/redirect helpers need pruning or if WeChat convergence changes callback construction.
- `web/src/app/system-manager/constants/menu.json`
  Remove the `auth-sources` frontend menu entry.
- `web/src/app/system-manager/locales/zh.json`
  Clean up menu text only if the removed menu leaves dead label usage in nearby navigation code.
- `web/src/app/system-manager/locales/en.json`
  Same as above for English.
- `server/apps/core/views/index_view.py`
  Keep WeChat on the same public login-auth callback/start/status flow if backend glue needs adjustment.
- `server/apps/core/tests/views/test_login_auth_bindings.py`
  Add or adjust contract tests if provider convergence changes public login-auth behavior.

### Existing files likely to stay outside the main login path

- `web/src/app/(core)/auth/signin/WechatQrLoginPanel.tsx`
  No longer participates in the main signin flow.
- `web/src/app/(core)/auth/wechat-popup/bridge/page.tsx`
  No longer participates in the main WeChat signin flow.
- `web/src/app/api/wechat-popup-login/route.ts`
  No longer participates in the main signin flow if the legacy bridge remains unused.

### Reference files to read during implementation

- `docs/superpowers/specs/2026-06-18-signin-validation-cutover-design.md`
- `web/src/constants/authOptions.ts`
- `web/src/utils/crossDomainAuth.ts`
- `web/src/app/(core)/auth/signin/PopupAuthBridge.tsx`
- `web/src/app/system-manager/(pages)/user/auth-sources/page.tsx`
- `server/apps/core/services/login_auth_request_service.py`

---

### Task 1: Make the current shell the effective signin entry

**Files:**
- Modify: `web/src/app/(core)/auth/signin/page.tsx`
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Reference: `docs/superpowers/specs/2026-06-18-signin-validation-cutover-design.md`

- [ ] **Step 1: Update the page entry contract to treat the current shell as the active signin mode**

Requirements:
- stop treating legacy visible signin mode as the primary branch
- default `/auth/signin` must enter the unified shell directly
- remove `loginAuthMode` as a signin-mode switch
- `/auth/signin` must no longer branch between legacy visible mode and validation mode based on query parameters
- preserve existing authenticated redirect/session bridge behavior only where it is still needed by the unified shell itself
- `PopupAuthBridge` may remain only if it is still required by the unified main login chain; do not preserve extra page-entry branching just to keep old BK/WeChat visible-entry behavior alive

- [ ] **Step 2: Restructure `SigninClient.tsx` so the fixed password form remains the top-level login surface**

Requirements:
- keep username/password form visible in the login step for both `page` and `modal`
- keep OTP and reset-password steps behaviorally unchanged
- remove the assumption that validation mode replaces the form with a separate login selector view

- [ ] **Step 3: Run a targeted TypeScript/lint sanity check on the touched signin entry files**

Run:

```bash
cd web
pnpm exec eslint src/app/\(core\)/auth/signin/page.tsx src/app/\(core\)/auth/signin/SigninClient.tsx
```

Expected:
- no new lint errors in the touched files

### Task 2: Remove visible legacy third-party login entries from the main frontend path

**Files:**
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Modify: `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
- Modify: `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
- Reference: `web/src/app/(core)/auth/signin/WechatQrLoginPanel.tsx`

- [ ] **Step 1: Remove visible WeChat/BK button rendering from the page signin flow**

Requirements:
- the main signin page must no longer render legacy WeChat/BK button groups
- `showThirdPartyLogin` must stop acting as a visible entry toggle for the main page shell
- third-party login choices must come only from binding data rendered by `LoginAuthValidationPanel`

- [ ] **Step 2: Remove visible legacy WeChat/BK entry rendering from the modal signin flow**

Requirements:
- modal signin must no longer switch into `modalThirdPartyView === 'wechat'`
- modal signin must no longer expose old third-party buttons as user-visible entry points
- both page and modal should now share the same provider-entry surface semantics

- [ ] **Step 3: Tighten the validation panel/hook contract so the binding list is the only third-party source**

Requirements:
- keep loading/empty/selection states coherent for both page and modal use
- do not add synthetic WeChat/BK list items
- if no binding exists, the UI must show the same read-only empty/unavailable state in both page and modal rather than falling back to old visible entries
- the no-binding state must not block or alter the normal username/password submission path

- [ ] **Step 4: Make the shared frontend third-party state machine explicit in the hook and shell**

Requirements:
- the shared state source must cover `idle`, `starting`, `waiting`, `syncing-session`, `failed`, `cancelled`, and `expired`
- page and modal must consume the same state semantics rather than maintaining separate local interpretations
- while in `waiting` or `syncing-session`, provider switching must be disabled
- failure, cancellation, and expiry must return the UI to the fixed form plus selectable binding list state

- [ ] **Step 5: Run a focused signin UI sanity check**

Run:

```bash
cd web
pnpm exec eslint src/app/\(core\)/auth/signin/SigninClient.tsx src/app/\(core\)/auth/signin/login-auth/LoginAuthValidationPanel.tsx src/app/\(core\)/auth/signin/login-auth/useLoginAuthValidation.ts src/app/\(core\)/auth/signin/login-auth/types.ts
```

Expected:
- no new lint errors in the touched auth UI files

### Task 3: Switch the session-expired modal to the same unified validation shell

**Files:**
- Modify: `web/src/context/auth.tsx`
- Modify: `web/src/utils/sessionExpiry.ts`
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`

- [ ] **Step 1: Update `AuthProvider` so the expired-session modal uses the same unified signin shell**

Requirements:
- pass the correct props so modal relogin does not depend on legacy visible entry rendering
- preserve `onAuthenticated={handleReloginSuccess}` behavior
- keep the modal-specific wrapper styling, but not a separate login product flow

- [ ] **Step 2: Add the validation public login-auth APIs to the expired-session allowlist**

At minimum ensure the expired-session request gate does not block:
- `/api/proxy/core/api/get_login_auth_bindings/`
- `/api/proxy/core/api/start_login_auth/`
- `/api/proxy/core/api/login_auth_requests/.../status`

- [ ] **Step 3: Perform a lightweight modal-flow validation**

Check manually in the browser:
- expired-session modal can still show the password form
- binding list can load under expired-session conditions
- starting a binding login request is not rejected immediately by the session-expiry guard
- status polling requests for an active auth request are not rejected immediately by the session-expiry guard

Only fix directly related breakage discovered here; defer full verification to the final task.

### Task 4: Remove the frontend `auth-sources` menu entry

**Files:**
- Modify: `web/src/app/system-manager/constants/menu.json`
- Potentially modify: `web/src/app/system-manager/locales/zh.json`
- Potentially modify: `web/src/app/system-manager/locales/en.json`
- Reference: `web/src/app/system-manager/(pages)/user/auth-sources/page.tsx`

- [ ] **Step 1: Remove `auth-sources` from the user-management frontend menu structure**

Requirements:
- remove the `auth_sources` item from both `zh` and `en` menu trees
- keep sibling menu ordering stable
- do not delete the page implementation in this phase unless the menu removal reveals an immediate routing problem that must be resolved

- [ ] **Step 2: Clean up only directly related navigation text if needed**

Requirements:
- avoid broad locale cleanup
- only touch locale entries if dead references around the removed menu create obvious type/build issues

- [ ] **Step 3: Run a lightweight navigation sanity check**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/constants/menu.json
```

Expected:
- if JSON linting is not configured through eslint, skip without replacing it with heavyweight validation
- otherwise no new issues

### Task 5: Normalize WeChat on the standard binding flow

**Files:**
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Modify: `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
- Modify: `web/src/app/(core)/auth/signin/login-auth/types.ts`
- Potentially modify: `server/apps/core/views/index_view.py`
- Potentially modify: `server/apps/core/tests/views/test_login_auth_bindings.py`
- Reference: `web/src/app/(core)/auth/wechat-popup/bridge/page.tsx`
- Reference: `web/src/app/api/wechat-popup-login/route.ts`

- [ ] **Step 1: Remove WeChat special-flow assumptions from the signin frontend contract**

Requirements:
- the main signin flow must no longer depend on `WechatQrLoginPanel`
- the main signin flow must no longer require `wechat-popup/bridge`
- no new compatibility wrapper that merely hides the old WeChat special flow behind a new facade

- [ ] **Step 2: Ensure WeChat is consumed as a normal binding provider**

Requirements:
- WeChat enters through the same binding list as other providers
- it must follow the existing `start_login_auth -> new tab -> callback -> status polling -> session sync` flow
- if current provider/config/public-return conditions are insufficient for WeChat to appear in `get_login_auth_bindings`, that enablement work is part of this task scope
- if backend login-auth callback/start/status payloads need small adjustments for WeChat to behave like a standard binding provider, make only those directly related changes

- [ ] **Step 3: Exit the legacy WeChat main-path bridge logic**

Requirements:
- legacy bridge files may remain in the repo temporarily, but the main signin flow must no longer rely on them
- do not replace the old flow with another WeChat-specific pseudo-binding flow

- [ ] **Step 4: Run focused login-auth contract validation if backend glue changed**

Run:

```bash
cd server
uv run pytest apps/core/tests/views/test_login_auth_bindings.py -v
```

Expected:
- the public login-auth contract still passes after WeChat alignment

If no backend files changed in this task, record that and skip this command.

### Task 6: Final verification and review

**Files:**
- Review: `docs/superpowers/specs/2026-06-18-signin-validation-cutover-design.md`
- Test: touched signin/frontend files
- Test: `server/apps/core/tests/views/test_login_auth_bindings.py` if backend changed in Task 5

- [ ] **Step 1: Run the focused frontend validation suite for touched auth files**

Run:

```bash
cd web
pnpm exec eslint src/app/\(core\)/auth/signin/page.tsx src/app/\(core\)/auth/signin/SigninClient.tsx src/app/\(core\)/auth/signin/login-auth/LoginAuthValidationPanel.tsx src/app/\(core\)/auth/signin/login-auth/useLoginAuthValidation.ts src/app/\(core\)/auth/signin/login-auth/types.ts src/context/auth.tsx src/utils/sessionExpiry.ts
pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected:
- touched auth files remain clean
- if there is an unrelated baseline type issue, record it clearly instead of treating it as introduced by this plan

- [ ] **Step 2: Run the targeted backend login-auth test file if Task 5 touched backend code**

Run:

```bash
cd server
uv run pytest apps/core/tests/views/test_login_auth_bindings.py -v
```

Expected:
- PASS

If Task 5 was frontend-only, explicitly note that backend verification was not needed.

- [ ] **Step 3: Manually verify the end-state behaviors**

Checklist:
- default `/auth/signin` shows fixed password form plus only binding-driven third-party entries
- visible WeChat/BK legacy entries are gone
- expired-session modal shows the same shell semantics as the page
- modal relogin can load binding entries while expired-session gating is active
- modal relogin can poll auth-request status while expired-session gating is active
- OTP and reset-password still hand off correctly from password login
- `system-manager/user/auth-sources` is no longer exposed in the frontend menu
- WeChat uses the same binding flow rather than any special popup/bridge flow

- [ ] **Step 4: Review implementation against the spec before handoff**

Checklist:
- the signin cutover stayed focused on the frontend shell
- no broad compatibility layer was introduced just to keep old visible entries alive
- page and modal share one signin shell model
- page and modal share one third-party state machine model
- third-party entries come only from bindings
- WeChat convergence aligns with the existing binding flow semantics
- BK remains out of scope for provider convergence
