# Historical Superpowers change: 2026-06-26-signin-binding-ordered-rendering

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-26-signin-binding-ordered-rendering.md

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

## specs: 2026-06-26-signin-binding-ordered-rendering-design.md

> 说明：本文档聚焦 Web 登录页 `/auth/signin` 与 session expired modal 的登录项渲染规则收敛，只覆盖公开登录认证列表的消费方式、账号密码登录项的承载语义、兜底规则与前端状态机，不展开系统管理治理全文重写。

## 背景

当前仓库中的登录链路已经部分收敛到基于 binding 的统一认证流程，但登录页与过期登录弹窗仍保留一个关键不一致：

- 系统管理中的登录认证列表已经有明确的 `order` 排序语义，且内建 `bk_lite_builtin` 登录项也存在展示映射对象。
- 公开登录接口 `get_login_auth_bindings` 已经能返回有效可登录 binding 列表。
- 但前端 `SigninClient` 仍将账号密码登录表单固定在主区域，并在第三方列表中主动过滤 `bk_lite_builtin`。

这导致两个问题：

1. 登录页和过期登录弹窗并没有真正按“登录认证列表”的顺序渲染登录项。
2. 账号密码登录仍是前端特判入口，而不是登录认证排序体系中的一个正式可选项。

本次设计的目标不是把账号密码登录改造成强依赖 binding 的真实认证开关，而是让前端在正常态下严格按公开登录认证列表渲染登录项，同时保留“公开可登录项全空时仍可用”的最小兜底。

## 目标

1. 登录页与 session expired modal 共享同一套登录项排序与渲染规则。
2. 正常态下，前端只消费公开接口 `get_login_auth_bindings` 返回的可登录 binding 列表。
3. `bk_lite_builtin` 不再被前端常态过滤，而是作为“账号密码登录项”参与排序。
4. 默认选中排序第一项，不为账号密码登录保留前端置顶特权。
5. 若选中项为 `bk_lite_builtin`，内容区渲染账号密码表单。
6. 若选中项为第三方 binding，内容区渲染该登录方式的说明态与手动发起入口，不自动打开第三方认证页。
7. 若公开可登录 binding 列表为空，页面和 modal 统一退化为纯账号密码登录表单兜底。

## 非目标

- 不改变后端 `/login/` 的传统账号密码认证协议。
- 不把 `bk_lite_builtin` 改造成账号密码登录的真实启停开关。
- 不重做 OTP、密码过期重置、第三方回调事务模型的底层协议。
- 不在本次设计中重构系统管理登录认证页的视觉结构。
- 不改变系统管理里“内建登录项只读、不可删除、不可禁用”的既有治理方向。

## 当前实现事实

### 1. 登录认证排序事实

- `LoginAuthBinding` 模型默认按 `order, id` 排序。
- 系统管理登录认证列表页允许通过拖拽与手工编辑修改 `order`。
- 公开接口 `get_login_auth_bindings` 最终返回的是“有效可登录 binding 列表”，其顺序同样来自 `order, id`。

因此，后端已经具备“登录认证顺序”的唯一事实来源。

### 2. 公开可登录 binding 的当前判定

当前公开接口返回的不是全部 binding，而是实际可登录项，至少满足：

- `LoginAuthBinding.enabled = true`
- 关联 `IntegrationInstance.enabled = true`
- `IntegrationInstance.capability_status.login_auth = ready`

前端不需要再次在本地解释“启用/未启用”；是否有效，以公开接口返回结果为准。

### 3. 账号密码登录的当前事实

当前产品与代码事实仍然是：

- 后端 `/login/` 在未传 `binding_id` 时走传统账号密码链路。
- 该链路不依赖 `LoginAuthBinding` 或 `IntegrationInstance` 才能工作。
- `bk_lite_builtin` 目前是“平台账号密码登录”的展示映射对象，而非真实登录开关。

这意味着本次改造只能收敛“前端渲染规则”，不能反向宣称账号密码登录已成为强 binding 架构。

## 设计原则

### 1. 正常态坚持规则纯度

只要公开接口返回了非空的可登录 binding 列表，登录页和过期登录弹窗就必须完全按该列表渲染登录项：

- 不再过滤 `bk_lite_builtin`
- 不再将账号密码表单固定排除在排序体系之外
- 不再在前端插入额外的“账号密码默认项”

### 2. 异常态只做最小兜底

当前端获取到的公开可登录 binding 列表为空时，允许退化为纯账号密码表单。

该兜底态的目的仅是防止内建展示映射缺失或全部登录认证项失效时，登录页面完全无入口；它不是正常产品路径，也不参与排序语义。

### 3. 默认选中第一项

正常态下，前端不为账号密码登录保留默认优先级。首屏展示由排序第一项决定：

- 第一项是 `bk_lite_builtin`：首屏即账号密码表单
- 第一项是第三方 binding：首屏即该第三方登录方式的说明态

### 4. 第三方登录必须显式发起

即使默认选中项是第三方登录方式，页面也不能自动打开新窗口发起认证。用户必须显式点击“继续登录”后，前端才调用 `start_login_auth`。

这样可以避免首屏自动弹窗、浏览器拦截、以及 modal 打开即触发外部认证的反直觉行为。

## 顶层状态设计

本次设计将 page / modal 的登录壳拆成两个顶层渲染状态。

### 状态 A：公开可登录 binding 列表非空

满足条件：

- `get_login_auth_bindings` 返回非空数组

行为：

- 登录项列表按返回顺序渲染
- 默认选中第一项
- 内容区根据当前选中项类型切换
- page 与 modal 使用同一状态机

### 状态 B：公开可登录 binding 列表为空

满足条件：

- `get_login_auth_bindings` 返回空数组

行为：

- 不展示“登录项选择列表”
- 直接展示账号密码表单
- OTP、密码重置等后续步骤仍沿用原账号密码链路
- page 与 modal 使用同一兜底语义

## 正常态下的界面结构

正常态不再采用“账号密码表单固定在上方，第三方列表固定在下方”的语义，而是统一为：

- 顶部：页面标题区或 modal 标题区
- 中部：当前选中登录项的内容区
- 底部：登录项选择区

这里的关键是：

- 外层骨架可以继续复用 `SigninClient` 现有 page / modal 布局
- 但主内容区不再固定等同于账号密码表单
- 主内容区必须成为由“当前选中登录项”驱动的切换区

## 登录项选择区规则

### 1. 数据来源

登录项选择区只消费 `get_login_auth_bindings` 返回数据，不叠加其他可见入口来源：

- 不再使用旧 WeChat 特殊入口
- 不再使用旧 BK 特殊入口
- 不再本地补一条账号密码伪登录项

### 2. 排序规则

按接口返回顺序渲染，不做任何前端重排。

因为后端返回顺序已经承载：

- 系统管理登录认证列表中的 `order`
- 有效可登录项过滤后的最终顺序

### 3. 默认选中规则

首次加载完成后：

- 若当前没有用户显式选择记录，则默认选中数组第一项
- 后续在同一轮登录会话内，除非状态机重置，不主动切换用户已选中项

### 4. 锁定规则

以下状态下，登录项选择区必须整体锁定，不允许切换到其他登录方式：

- 已发起第三方登录，处于 `starting`
- 已打开第三方页面，处于 `waiting`
- 第三方认证成功，处于 `syncing-session`
- 账号密码登录进入 OTP 验证步骤
- 账号密码登录进入密码重置步骤

锁定规则的目的是保持单一登录流程上下文，避免并发认证请求和混乱状态恢复。

## 主内容区规则

### 1. 选中 `bk_lite_builtin`

当当前选中项的 `provider_key = bk_lite_builtin` 时：

- 渲染账号密码表单
- 提交后继续调用现有 `/login/` 接口
- 若后续进入 OTP 验证或密码重置，仍沿用 `SigninClient` 既有流程

也就是说，`bk_lite_builtin` 在正常态下只是“选中后显示账号密码登录主内容”的登录项，而不是一个前端额外分支。

### 2. 选中第三方 binding

当当前选中项不是 `bk_lite_builtin` 时：

- 渲染当前登录项的名称、图标、描述
- 渲染显式操作按钮，例如“继续登录”
- 用户点击按钮后才调用 `start_login_auth`

在未点击前，不发起任何外部跳转，也不自动进入等待态。

### 3. 第三方等待态

点击第三方登录按钮后：

- 主内容区切换到等待态 / 同步态展示
- 选中项保持高亮
- 其他登录项禁用
- 不允许在等待态期间切换其他登录方式

### 4. 第三方失败、取消、过期

轮询结果返回 `failed` / `cancelled` / `expired` 时：

- 主内容区回到当前已选登录项的默认内容
- 若当前选中项是第三方，则回到该第三方说明态
- 若用户随后改选 `bk_lite_builtin`，再显示账号密码表单

失败恢复时不强制跳回账号密码登录，也不强制切回第一项。

## session expired modal 规则

session expired modal 与登录页必须共享同一套登录项语义：

- 使用同一公开 binding 列表
- 使用同一默认选中规则
- 使用同一“正常态 / 空列表兜底态”判定
- 使用同一第三方等待态与错误恢复规则

modal 与 page 的差异只允许存在于展示尺寸与文案密度上，不允许存在于登录项来源和排序逻辑上。

这意味着：

- modal 不再维护独立第三方登录产品分支
- modal 也不再保留“只展示账号密码，第三方逻辑另算”的特例

## 公开列表为空时的兜底态

当 `get_login_auth_bindings` 返回空数组时：

- page：直接展示账号密码表单
- modal：直接展示账号密码表单
- 不展示登录项选择区
- 不展示“空列表但仍有可选登录方式”的伪状态

兜底态的交互目标非常单一：

- 用户仍可通过平台账号密码完成登录
- 页面不因为 binding 数据缺失而无入口

同时需要明确其限制：

- 兜底态不表达排序
- 兜底态不表达 `bk_lite_builtin` 一定存在于公开列表
- 兜底态不回退旧 WeChat / BK 特殊入口

## 与系统管理治理语义的关系

本次设计依赖但不重写以下既有治理前提：

1. `bk_lite_builtin` 仍是展示映射对象，不是账号密码登录的真实启停开关。
2. 初始化命令和环境数据仍应保证 `bk_lite_builtin` 默认存在。
3. 系统管理登录认证页中，内建登录项仍维持只读启用态、不可删除、不可禁用。

与该前提结合后的产品语义是：

- 正常环境中，`bk_lite_builtin` 应进入公开 binding 列表并参与排序渲染。
- 异常环境中，即使内建映射缺失，账号密码真实登录链路仍可能可用，因此前端允许进入空列表兜底态。

## 前端状态机建议

建议将 `SigninClient` 中的登录态明确拆分为两层：

### 1. 顶层加载态

- `loading-bindings`
- `bindings-ready`
- `bindings-empty`

### 2. 认证流程态

- `idle`
- `starting`
- `waiting`
- `syncing-session`
- `otp-verification`
- `reset-password`
- `failed`
- `cancelled`
- `expired`

其中：

- `bindings-ready` 下才存在“登录项选择 + 主内容区切换”
- `bindings-empty` 下直接走账号密码表单链路
- `otp-verification` / `reset-password` 期间必须锁定登录项切换区

## 错误处理

### 1. 拉取公开 binding 失败

若 `get_login_auth_bindings` 请求本身失败：

- 不应直接按“空列表”处理
- 应展示明确的加载失败提示
- 允许用户刷新重试

原因是“接口失败”和“公开列表为空”是两种完全不同的产品语义：

- 空列表：系统当前没有有效登录认证方式，应进入账号密码兜底态
- 接口失败：系统状态未知，不能假装已确认不存在 binding

### 2. 第三方登录发起失败

若 `start_login_auth` 失败：

- 保持当前选中项不变
- 主内容区返回当前选中项默认内容
- 展示轻量错误提示

### 3. 轮询终态失败

若轮询结果为 `failed` / `cancelled` / `expired`：

- 保持当前选中项
- 恢复可交互状态
- 向用户展示终态错误信息

## 测试与验收建议

### 1. 正常态

- 公开 binding 列表包含 `bk_lite_builtin` 且排第一时，首屏默认显示账号密码表单。
- 公开 binding 列表第一项为第三方时，首屏默认显示第三方说明态，而不是账号密码表单。
- 登录项列表渲染顺序与接口返回顺序一致，无前端重排。

### 2. 锁定态

- 第三方登录发起后，登录项选择区整体禁用。
- OTP 验证和密码重置步骤中，登录项选择区整体禁用。

### 3. 错误恢复

- 第三方登录失败后，恢复当前选中第三方项的默认说明态。
- 失败后用户可切换到 `bk_lite_builtin` 并继续账号密码登录。

### 4. 兜底态

- 当公开 binding 列表为空时，page 与 modal 都直接显示账号密码表单。
- 空列表兜底态中不渲染登录项选择区。

### 5. 非回归

- 账号密码登录原有 OTP / 密码过期重置流程保持可用。
- 第三方登录事务、轮询、session 同步链路保持可用。
- session expired modal 登录成功后仍通过既有回调关闭并刷新页面。

## 结论

本次改造不是把账号密码登录改造成强 binding 架构，而是把登录页与过期登录弹窗的前端呈现统一收敛到“公开登录认证列表驱动”的模型：

- 正常态按公开 binding 列表排序渲染，账号密码也在排序体系中。
- 异常态仅在公开可登录项全空时退化为纯账号密码表单兜底。

这套规则既保留了登录认证排序的单一事实来源，也避免了展示映射数据缺失时页面完全失去可登录入口。
