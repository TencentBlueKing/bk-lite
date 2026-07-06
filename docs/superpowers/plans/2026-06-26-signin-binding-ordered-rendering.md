# Signin Binding Ordered Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/auth/signin` and the session-expired modal render login methods strictly from the public login-auth binding list, including `bk_lite_builtin`, while preserving the existing username/password fallback only when the public list is truly empty.

**Architecture:** Keep the backend public binding endpoint and current `/login/` password protocol intact. Frontend work stays inside the existing signin shell: add a small pure state helper for ordered-binding semantics, refactor the login-auth hook to expose top-level binding load states plus current selection, and let `SigninClient` switch its main content region between builtin form, third-party description state, waiting state, and empty-list fallback with the same logic in page and modal modes.

**Tech Stack:** Next.js App Router, React 19, TypeScript, Ant Design, existing NextAuth credentials session sync, Django 4.2 test suite for login-auth backend contract verification

## Execution Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If design intent, compatibility scope, login semantics, or implementation direction becomes unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to this signin rendering adjustment; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- The implementation must stay on one shared signin shell and one public binding-driven login item model for both page and modal.
- Prefer no temporary compatibility layer unless explicitly required.
- If callback behavior, provider contract semantics, or session synchronization expectations become unclear, stop and align with the user before continuing.
- Execute this plan in `executing-plans` style: follow the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.

## Global Constraints

- Login page and session expired modal must share the same login-item source, ordering, selection, lock, and fallback semantics.
- In the normal path, frontend must consume only `/api/proxy/core/api/get_login_auth_bindings/` and must not inject extra visible login entries.
- `bk_lite_builtin` must remain in the returned list and participate in ordering; frontend must stop filtering it out.
- The default selected item is the first returned binding; username/password has no frontend pin-to-top privilege.
- Selecting `bk_lite_builtin` renders the existing username/password form and keeps the current `/api/proxy/core/api/login/` flow.
- Selecting a third-party binding renders an explanation state plus an explicit “continue login” action; frontend must not auto-open external auth on initial selection.
- If the public binding list is empty, page and modal both degrade to a plain username/password form without a selector.
- If binding fetch fails, frontend must not treat that as an empty list; it must show an explicit load failure state with retry.
- Selector switching must stay locked during `starting`, `waiting`, `syncing-session`, OTP verification, and password reset states.
- Do not restore old WeChat/BK special entry code paths or redesign the system-manager login-auth page.

---

## File Structure

### Existing files to modify

- `web/src/app/(core)/auth/signin/SigninClient.tsx`
  - Convert the current “form first, external providers below” shell into a selected-binding-driven content region used by both page and modal modes.
- `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
  - Stop filtering builtin bindings, introduce top-level binding load states, track explicit binding selection, expose retry/select/start APIs, and preserve the active selection across terminal recovery.
- `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
  - Narrow this component into the ordered selector UI with disabled-state handling rather than a “start external auth immediately” grid.
- `web/src/app/(core)/auth/signin/login-auth/types.ts`
  - Add explicit top-level binding load-state and selection-related types used by the helper, hook, and UI.
- `server/apps/system_mgmt/tests/test_builtin_platform_login_auth.py`
  - Lock in the backend public binding contract that this frontend behavior depends on: builtin inclusion plus `order, id` public ordering.

### New files to create

- `web/src/app/(core)/auth/signin/login-auth/orderedBindingState.ts`
  - Pure helper functions for deriving selected binding, fallback mode, and selector lock rules from bindings + flow state.
- `web/src/app/(core)/auth/signin/login-auth/LoginAuthBindingContent.tsx`
  - Focused content renderer for builtin form host state, third-party explanation state, waiting/syncing state, and fetch-error retry state.
- `web/scripts/signin-binding-ordered-rendering-test.ts`
  - Lightweight script-style regression checks for the pure ordered-binding helper functions.

### Reference files to read during implementation

- `docs/superpowers/specs/2026-06-26-signin-binding-ordered-rendering-design.md`
- `web/src/context/auth.tsx`
- `web/src/utils/sessionExpiry.ts`
- `server/apps/system_mgmt/services/login_auth_binding_service.py`
- `server/apps/core/views/index_view.py`

---

### Task 1: Lock In The Public Binding Ordering Contract

**Files:**
- Modify: `server/apps/system_mgmt/tests/test_builtin_platform_login_auth.py`
- Reference: `server/apps/system_mgmt/services/login_auth_binding_service.py`

**Interfaces:**
- Consumes: `get_login_auth_bindings() -> dict`
- Produces: backend test coverage proving public bindings include builtin entries and preserve `order, id` ordering for frontend consumers

- [ ] **Step 1: Add a failing backend test for ordered public bindings**

Add a focused case near the existing `get_login_auth_bindings` tests:

```python
@pytest.mark.django_db
def test_get_login_auth_bindings_returns_enabled_ready_items_in_order():
    builtin_instance, builtin_binding = create_builtin_platform_login_auth()
    builtin_binding.order = 20
    builtin_binding.save(update_fields=["order"])

    ready_instance = IntegrationInstance.objects.create(
        name="Feishu Ready",
        provider_key="feishu",
        enabled=True,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        config={},
    )
    ready_binding = LoginAuthBinding.objects.create(
        name="Feishu Login",
        integration_instance=ready_instance,
        enabled=True,
        order=10,
        icon="feishu",
        description="Feishu SSO",
        external_field="open_id",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        default_group_name="",
    )

    response = get_login_auth_bindings()

    assert response["result"] is True
    assert [item["id"] for item in response["data"]] == [ready_binding.id, builtin_binding.id]
    assert [item["provider_key"] for item in response["data"]] == ["feishu", "bk_lite_builtin"]
```

- [ ] **Step 2: Run the focused backend public-binding tests**

Run:

```bash
cd server && uv run pytest apps/system_mgmt/tests/test_builtin_platform_login_auth.py -k "get_login_auth_bindings" -v
```

Expected:
- the new ordering case fails only if the public contract is weaker than the spec assumes
- existing builtin payload coverage stays green

- [ ] **Step 3: Tighten backend public ordering only if the new test reveals a gap**

If the test fails, make the minimal fix in `server/apps/system_mgmt/services/login_auth_binding_service.py` so the public list still comes from enabled + ready bindings ordered by `order, id`:

```python
queryset = (
    LoginAuthBinding.objects
    .select_related("integration_instance")
    .filter(enabled=True, integration_instance__enabled=True)
    .order_by("order", "id")
)
```

Do not add new filtering semantics beyond what the current design already states.

- [ ] **Step 4: Re-run the backend public-binding tests**

Run:

```bash
cd server && uv run pytest apps/system_mgmt/tests/test_builtin_platform_login_auth.py -k "get_login_auth_bindings" -v
```

Expected:
- PASS with explicit proof that builtin items are public and ordering is stable

---

### Task 2: Add Pure Ordered-Binding State Helpers And Regression Checks

**Files:**
- Create: `web/src/app/(core)/auth/signin/login-auth/orderedBindingState.ts`
- Create: `web/scripts/signin-binding-ordered-rendering-test.ts`
- Modify: `web/src/app/(core)/auth/signin/login-auth/types.ts`

**Interfaces:**
- Consumes: `LoginAuthBindingItem[]`, `LoginAuthBindingsLoadState`, `LoginAuthValidationViewState`, builtin provider key string
- Produces:
  - `resolveInitialBindingId(bindings: LoginAuthBindingItem[]): number | null`
  - `resolveSelectedBinding(bindings: LoginAuthBindingItem[], selectedBindingId: number | null): LoginAuthBindingItem | null`
  - `resolveBindingsLoadState(bindings: LoginAuthBindingItem[], requestFailed: boolean): LoginAuthBindingsLoadState`
  - `isBindingSelectionLocked(args: { authStep: 'login' | 'reset-password' | 'otp-verification'; viewState: LoginAuthValidationViewState }): boolean`
  - `isBuiltinBinding(binding?: LoginAuthBindingItem | null): boolean`

- [ ] **Step 1: Write failing script tests for selection, fallback, and lock semantics**

Create `web/scripts/signin-binding-ordered-rendering-test.ts`:

```ts
import assert from "node:assert/strict";
import {
  isBindingSelectionLocked,
  isBuiltinBinding,
  resolveBindingsLoadState,
  resolveInitialBindingId,
  resolveSelectedBinding,
} from "../src/app/(core)/auth/signin/login-auth/orderedBindingState";

const bindings = [
  { id: 11, name: "Feishu", icon: "feishu", description: "Feishu SSO", provider_key: "feishu" },
  { id: 12, name: "Platform Login", icon: "user", description: "Username and password", provider_key: "bk_lite_builtin" },
];

assert.equal(resolveInitialBindingId(bindings), 11);
assert.equal(resolveSelectedBinding(bindings, null)?.id, 11);
assert.equal(resolveSelectedBinding(bindings, 12)?.provider_key, "bk_lite_builtin");
assert.equal(resolveBindingsLoadState(bindings, false), "bindings-ready");
assert.equal(resolveBindingsLoadState([], false), "bindings-empty");
assert.equal(resolveBindingsLoadState([], true), "bindings-error");
assert.equal(isBuiltinBinding(bindings[1]), true);
assert.equal(
  isBindingSelectionLocked({ authStep: "otp-verification", viewState: "idle" }),
  true,
);
assert.equal(
  isBindingSelectionLocked({ authStep: "login", viewState: "waiting" }),
  true,
);
assert.equal(
  isBindingSelectionLocked({ authStep: "login", viewState: "idle" }),
  false,
);

console.log("signin binding ordered rendering tests passed");
```

- [ ] **Step 2: Run the script test to confirm the helper module is still missing**

Run:

```bash
cd web && pnpm exec tsx scripts/signin-binding-ordered-rendering-test.ts
```

Expected:
- FAIL with module-not-found or missing-export errors for `orderedBindingState`

- [ ] **Step 3: Implement the helper and shared types**

Add the minimal shared state model in `types.ts`:

```ts
export type LoginAuthBindingsLoadState =
  | "loading-bindings"
  | "bindings-ready"
  | "bindings-empty"
  | "bindings-error";
```

Create `orderedBindingState.ts`:

```ts
import type {
  LoginAuthBindingItem,
  LoginAuthBindingsLoadState,
  LoginAuthValidationViewState,
} from "./types";

const BUILTIN_PROVIDER_KEY = "bk_lite_builtin";

export function resolveInitialBindingId(bindings: LoginAuthBindingItem[]): number | null {
  return bindings[0]?.id ?? null;
}

export function resolveSelectedBinding(
  bindings: LoginAuthBindingItem[],
  selectedBindingId: number | null,
): LoginAuthBindingItem | null {
  return bindings.find((binding) => binding.id === selectedBindingId) ?? bindings[0] ?? null;
}

export function resolveBindingsLoadState(
  bindings: LoginAuthBindingItem[],
  requestFailed: boolean,
): LoginAuthBindingsLoadState {
  if (requestFailed) return "bindings-error";
  return bindings.length > 0 ? "bindings-ready" : "bindings-empty";
}

export function isBuiltinBinding(binding?: LoginAuthBindingItem | null) {
  return binding?.provider_key === BUILTIN_PROVIDER_KEY;
}

export function isBindingSelectionLocked(args: {
  authStep: "login" | "reset-password" | "otp-verification";
  viewState: LoginAuthValidationViewState;
}) {
  return (
    args.authStep !== "login"
    || args.viewState === "starting"
    || args.viewState === "waiting"
    || args.viewState === "syncing-session"
  );
}
```

- [ ] **Step 4: Re-run the ordered-binding script tests**

Run:

```bash
cd web && pnpm exec tsx scripts/signin-binding-ordered-rendering-test.ts
```

Expected:
- PASS with `signin binding ordered rendering tests passed`

---

### Task 3: Refactor The Login-Auth Hook Around Binding Load State And Explicit Selection

**Files:**
- Modify: `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
- Modify: `web/src/app/(core)/auth/signin/login-auth/types.ts`
- Reference: `web/src/app/(core)/auth/signin/login-auth/orderedBindingState.ts`

**Interfaces:**
- Consumes:
  - `resolveBindingsLoadState(bindings, requestFailed)`
  - `resolveInitialBindingId(bindings)`
  - `resolveSelectedBinding(bindings, selectedBindingId)`
- Produces:
  - `bindingsLoadState: LoginAuthBindingsLoadState`
  - `selectedBinding: LoginAuthBindingItem | null`
  - `selectedBindingId: number | null`
  - `selectBinding(bindingId: number): void`
  - `reloadBindings(): Promise<void>`
  - `startSelectedBindingLogin(): Promise<void>`

- [ ] **Step 1: Extend the script test with hook-facing selection recovery expectations**

Append coverage in `web/scripts/signin-binding-ordered-rendering-test.ts` for the helper behavior the hook will rely on:

```ts
assert.equal(resolveSelectedBinding(bindings, 999)?.id, 11);

const builtinOnly = [bindings[1]];
assert.equal(resolveInitialBindingId(builtinOnly), 12);
assert.equal(resolveBindingsLoadState(builtinOnly, false), "bindings-ready");
```

- [ ] **Step 2: Re-run the script to preserve a failing-first edit cycle if any new helper behavior is missing**

Run:

```bash
cd web && pnpm exec tsx scripts/signin-binding-ordered-rendering-test.ts
```

Expected:
- PASS if the helper already covers the added expectations
- otherwise FAIL on the newly added assertions before hook refactor begins

- [ ] **Step 3: Rework `useLoginAuthValidation.ts` to expose selection instead of immediate provider launch**

Refactor the hook so fetch success stores the returned list as-is and derives top-level load state without filtering builtin items:

```ts
const [bindingsLoadState, setBindingsLoadState] =
  useState<LoginAuthBindingsLoadState>("loading-bindings");
const [selectedBindingId, setSelectedBindingId] = useState<number | null>(null);

const selectedBinding = resolveSelectedBinding(bindings, selectedBindingId);

if (!cancelled) {
  const nextBindings = responseData.data as LoginAuthBindingItem[];
  const nextLoadState = resolveBindingsLoadState(nextBindings, false);
  setBindings(nextBindings);
  setBindingsLoadState(nextLoadState);
  setSelectedBindingId((current) => {
    if (current && nextBindings.some((binding) => binding.id === current)) {
      return current;
    }
    return resolveInitialBindingId(nextBindings);
  });
}
```

On fetch failure, keep bindings empty but mark the explicit failure state instead of pretending the list is empty:

```ts
setBindings([]);
setBindingsLoadState("bindings-error");
setErrorMessage("Failed to load login methods. Please refresh and try again.");
```

Expose an explicit selector API and a selected-binding launcher:

```ts
const selectBinding = (bindingId: number) => {
  if (viewState === "starting" || viewState === "waiting" || viewState === "syncing-session") {
    return;
  }
  setSelectedBindingId(bindingId);
  setErrorMessage("");
};

const startSelectedBindingLogin = async () => {
  if (!selectedBinding) return;
  await startLoginAuth(selectedBinding);
};
```

On terminal third-party failure/cancel/expiry, preserve the chosen binding instead of clearing back to null:

```ts
const resetSelectionState = (
  nextState: Extract<LoginAuthValidationViewState, "failed" | "cancelled" | "expired">,
  nextErrorMessage: string,
) => {
  stopPolling();
  setActiveRequest(null);
  setViewState(nextState);
  setErrorMessage(nextErrorMessage);
};
```

- [ ] **Step 4: Run targeted lint for the hook and shared login-auth files**

Run:

```bash
cd web && pnpm exec eslint src/app/\(core\)/auth/signin/login-auth/useLoginAuthValidation.ts src/app/\(core\)/auth/signin/login-auth/types.ts src/app/\(core\)/auth/signin/login-auth/orderedBindingState.ts
```

Expected:
- PASS

---

### Task 4: Reshape The Signin Shell Around The Selected Binding

**Files:**
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Modify: `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
- Create: `web/src/app/(core)/auth/signin/login-auth/LoginAuthBindingContent.tsx`
- Reference: `web/src/context/auth.tsx`

**Interfaces:**
- Consumes:
  - `bindingsLoadState`
  - `selectedBinding`
  - `selectedBindingId`
  - `selectBinding(bindingId: number)`
  - `startSelectedBindingLogin()`
  - `reloadBindings()`
  - `isBindingSelectionLocked({ authStep, viewState })`
  - `isBuiltinBinding(selectedBinding)`
- Produces:
  - shared page/modal rendering semantics for `bindings-ready`, `bindings-empty`, and `bindings-error`
  - selector-driven switching between builtin form and third-party content

- [ ] **Step 1: Add a focused content component for third-party, waiting, and fetch-error states**

Create `LoginAuthBindingContent.tsx` with an explicit prop contract:

```tsx
interface LoginAuthBindingContentProps {
  mode: "page" | "modal";
  bindingLoadState: LoginAuthBindingsLoadState;
  selectedBinding: LoginAuthBindingItem | null;
  viewState: LoginAuthValidationViewState;
  activeBindingName: string;
  errorMessage: string;
  onRetryBindings: () => void;
  onContinueThirdParty: () => void;
}
```

Render behavior:

```tsx
if (bindingLoadState === "bindings-error") {
  return <RetryCard message={errorMessage} onRetry={onRetryBindings} />;
}

if (!selectedBinding) {
  return null;
}

if (viewState === "starting" || viewState === "waiting" || viewState === "syncing-session") {
  return <WaitingState activeBindingName={activeBindingName} viewState={viewState} />;
}

return (
  <ThirdPartyIntroCard
    name={selectedBinding.name}
    description={selectedBinding.description}
    icon={selectedBinding.icon}
    onContinue={onContinueThirdParty}
  />
);
```

- [ ] **Step 2: Update `LoginAuthValidationPanel.tsx` so clicking selects rather than immediately launching**

Refactor its props to separate selection from third-party start:

```tsx
interface LoginAuthValidationPanelProps {
  bindings: LoginAuthBindingItem[];
  selectedBindingId: number | null;
  isSelectionLocked: boolean;
  onSelectBinding: (bindingId: number) => void;
}
```

Button behavior should be:

```tsx
<button
  type="button"
  onClick={() => onSelectBinding(binding.id)}
  disabled={isSelectionLocked}
  aria-pressed={binding.id === selectedBindingId}
>
```

Do not auto-launch third-party auth from selector click anymore.

- [ ] **Step 3: Rebuild `SigninClient.tsx` main content switching around load state + selected binding**

Inside `SigninClient.tsx`, derive selector lock and builtin-vs-third-party rendering once:

```tsx
const bindingSelectionLocked = isBindingSelectionLocked({
  authStep,
  viewState: loginAuthValidation.viewState,
});
const selectedBinding = loginAuthValidation.selectedBinding;
const showBindingsSelector =
  authStep === "login" && loginAuthValidation.bindingsLoadState === "bindings-ready";
const showBuiltinLoginForm =
  authStep === "login"
  && (
    loginAuthValidation.bindingsLoadState === "bindings-empty"
    || (
      loginAuthValidation.bindingsLoadState === "bindings-ready"
      && isBuiltinBinding(selectedBinding)
    )
  );
```

Render rules in the main content region:

```tsx
{showBuiltinLoginForm && renderLoginForm()}

{authStep === "login" && !showBuiltinLoginForm && (
  <LoginAuthBindingContent
    mode={mode}
    bindingLoadState={loginAuthValidation.bindingsLoadState}
    selectedBinding={selectedBinding}
    viewState={loginAuthValidation.viewState}
    activeBindingName={loginAuthValidation.activeBindingName}
    errorMessage={loginAuthValidation.errorMessage}
    onRetryBindings={() => void loginAuthValidation.reloadBindings()}
    onContinueThirdParty={() => void loginAuthValidation.startSelectedBindingLogin()}
  />
)}

{showBindingsSelector && (
  <LoginAuthValidationPanel
    bindings={loginAuthValidation.bindings}
    selectedBindingId={loginAuthValidation.selectedBindingId}
    isSelectionLocked={bindingSelectionLocked}
    onSelectBinding={loginAuthValidation.selectBinding}
  />
)}
```

Keep the existing OTP / password-reset forms intact and let them lock the selector by state rather than branching into a separate login-mode system.

- [ ] **Step 4: Keep third-party terminal recovery on the selected item instead of jumping to password login**

In `SigninClient.tsx`, only surface `failed` / `cancelled` / `expired` as inline errors when the selected third-party item is still active, and do not rewrite the selection back to builtin:

```tsx
const validationInlineError =
  authStep === "login"
  && ["failed", "cancelled", "expired"].includes(loginAuthValidation.viewState)
    ? loginAuthValidation.errorMessage
    : "";
```

This keeps the content region on the chosen provider’s intro state after a failed external attempt.

- [ ] **Step 5: Run targeted frontend validation for the signin shell**

Run:

```bash
cd web && pnpm exec eslint src/app/\(core\)/auth/signin/SigninClient.tsx src/app/\(core\)/auth/signin/login-auth/LoginAuthValidationPanel.tsx src/app/\(core\)/auth/signin/login-auth/LoginAuthBindingContent.tsx
```

Expected:
- PASS

- [ ] **Step 6: Run the broader web type-check gate**

Run:

```bash
cd web && pnpm type-check
```

Expected:
- PASS

---

### Task 5: Verify Shared Page/Modal Behavior End-To-End

**Files:**
- Reference: `web/src/context/auth.tsx`
- Reference: `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Reference: `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`

**Interfaces:**
- Consumes: completed Tasks 1-4
- Produces: manual verification evidence that page and modal now share one ordered-binding model

- [ ] **Step 1: Manually verify ordered rendering on `/auth/signin`**

Check these cases in a browser against a backend with at least one builtin binding and one third-party binding:

```text
1. Third-party binding ordered first -> first screen shows third-party intro state, no auto-open.
2. Builtin binding ordered first -> first screen shows username/password form.
3. Selector order matches the public API response order exactly.
```

- [ ] **Step 2: Manually verify the session-expired modal uses the same selector semantics**

Trigger the modal from an authenticated page and confirm:

```text
1. The same binding order appears as on /auth/signin.
2. Selecting builtin shows the same password form path.
3. Selecting third-party shows the same intro/waiting/error recovery path.
```

- [ ] **Step 3: Manually verify lock and fallback cases**

Check:

```text
1. Starting/waiting/syncing state disables selector switching.
2. OTP verification disables selector switching.
3. Password reset disables selector switching.
4. Empty public list shows only the username/password form and no selector.
5. Binding fetch failure shows an explicit retry state instead of silently falling back to empty-list mode.
```

---

## Self-Review

- Spec coverage:
  - Ordered public binding source and builtin participation: Tasks 1, 3, 4
  - Page/modal shared semantics: Tasks 4, 5
  - Third-party explicit start only: Task 4
  - Empty-list fallback vs fetch-error distinction: Tasks 2, 4, 5
  - OTP/reset/starting/waiting/syncing lock rules: Tasks 2, 4, 5
- Placeholder scan:
  - No `TODO`, `TBD`, or “similar to” references remain.
- Type consistency:
  - Shared names are fixed as `LoginAuthBindingsLoadState`, `selectedBindingId`, `selectedBinding`, `selectBinding`, and `startSelectedBindingLogin`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-26-signin-binding-ordered-rendering.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
