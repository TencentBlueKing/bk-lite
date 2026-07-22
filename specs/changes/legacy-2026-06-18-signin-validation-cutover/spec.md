# Historical Superpowers change: 2026-06-18-signin-validation-cutover

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-18-signin-validation-cutover.md

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

## specs: 2026-06-18-signin-validation-cutover-design.md

> 说明：本文档保留设计阶段的过程记录。当前仓库实现已经在此基础上继续演进，凡与现状不一致之处，以当前代码实现为准。

## 背景

当前仓库中的登录体系仍然处于并存状态：

- 默认登录页 `/auth/signin` 仍包含传统账号密码登录与前端特判的第三方登录入口
- `validation` 模式已经具备基于 binding 的统一第三方登录主链路
- 会话过期后的 Modal 登录仍然依赖旧登录入口与旧分支
- 系统管理前端中仍保留旧的 `auth-sources` 认证源菜单入口

从产品方向看，未来登录体系应统一到 validation 模型中：

- 账号密码登录作为固定表单保留
- 第三方登录入口只来自 binding 列表
- 默认登录页与 Modal 登录共用同一套前端状态机
- 后续再逐步把具体 provider 的底层链路收口到统一的后端事务模型

当前阶段不是直接上线切换，而是在本地按阶段完成改造；真正上线以“前端已切换且 binding 能力补齐”为前提。

## 目标

### 总目标

将现有登录体系切换到 validation 方向，分阶段完成：

1. 第一阶段先完成前端入口收口
2. 第二阶段再完成部分 provider 的后端链路收口

### 第一阶段目标

1. 默认登录页切换为统一的 validation 风格壳
2. Modal 过期登录切换为同一套 validation 风格壳
3. 登录页顶部固定保留账号密码表单
4. 第三方登录入口仅展示 binding 列表项
5. 移除前端中所有 WeChat / BK 特殊登录入口展示
6. 移除前端 `system-manager/user/auth-sources` 认证源菜单入口

### 第二阶段目标

1. 将微信登录收口到统一的 provider / binding 链路
2. 保证微信可作为标准 binding provider 跑通完整流程
3. 第二阶段不兼容或复刻之前的微信特殊登录流程，而是直接与现有 binding 登录流程保持一致
4. BK 暂不纳入本阶段收口范围

## 非目标

### 第一阶段非目标

- 不要求微信或 BK 在第一阶段立刻完成后端链路统一
- 不要求第一阶段具备可直接上线的完整 provider 集合
- 不改造账号密码、OTP、重置密码的既有核心后端协议
- 不把账号密码登录改造成 binding 列表项

### 第二阶段非目标

- 不处理 BK 登录的 provider 收口
- 不在本阶段重做所有第三方 provider 的统一适配

## 现状事实

### 登录页

`web/src/app/(core)/auth/signin/SigninClient.tsx` 当前同时承载：

- 用户名密码登录
- OTP 验证
- 密码重置
- validation 第三方绑定登录
- WeChat 特判入口
- BK 特判入口
- Modal 专属微信分支

这导致登录主流程仍然存在多条前端入口路径。

### Modal 过期登录

`web/src/context/auth.tsx` 中的过期登录弹窗当前复用 `SigninClient`，但：

- 未直接切到 validation 模式
- 仍依赖旧第三方入口展示
- 成功回调与等待逻辑没有完全统一到 validation 思维模型

### Session Expiry 拦截

`web/src/utils/sessionExpiry.ts` 当前对部分公开登录接口做了豁免，但尚未完整覆盖 validation 模式需要的公开接口集合。
如果不调整，Modal 处于会话过期状态时，请求 validation 公开接口可能被前端拦截器提前拒绝。

### 第三方入口来源

目前前端还存在两类第三方入口来源：

1. binding 列表入口
2. WeChat / BK 特殊入口

目标方向是只保留第 1 类。

## 设计结论

## 第一阶段：前端入口收口

### 1. 统一登录壳

默认登录页和 Modal 过期登录统一收敛到同一套前端登录壳，结构固定为：

- 上方：账号密码表单
- 下方：第三方 binding 列表

这套登录壳由 `SigninClient` 统一承载，不再允许 page 与 modal 分别维护不同的第三方入口体系。

这里的控制语义需要明确：

- 默认访问 `/auth/signin` 时，直接进入这套统一登录壳
- 旧的“非 validation 可见模式”不再作为默认主路径存在
- 不再保留 `loginAuthMode` 作为登录方式选择开关
- `/auth/signin` 只保留这一套统一登录壳，不再根据 query 参数在旧登录模式与 validation 模式之间切换

### 2. 账号密码表单位置固定

第一阶段不将账号密码登录并入 binding 列表，而是继续作为固定主表单保留在上方。

原因：

- 与当前用户认知一致
- 对 OTP / 重置密码的衔接最小
- 能先完成前端入口收口，而不同时引入“内建 provider 化”的额外改造

### 3. 第三方入口只来自 binding

第一阶段中，页面上可见的第三方登录入口只允许来自 binding 列表。

具体要求：

- 不再渲染旧的 WeChat 按钮
- 不再渲染旧的 BlueKing 按钮
- 不再保留 Modal 中的微信专属切换页作为可见入口
- 只保留 `get_login_auth_bindings` 返回的列表项作为第三方登录展示来源

这意味着：

- 如果某个 provider 尚未进入 binding，则在第一阶段前端中不展示
- BK 在第一阶段前端中可以直接消失

当当前环境中没有任何可用 binding 时：

- 页面仍保留账号密码表单
- 账号密码登录仍是完整可用的主路径，不受第三方空态影响
- 第三方区域统一展示只读空态
- 不回退旧 WeChat / BK 特殊入口
- page 与 modal 使用同一种空态语义，避免出现两套不同兜底策略

这属于开发实施分阶段允许的状态，不代表立即上线。

### 4. Modal 登录直接复用同一壳

过期会话弹窗中的登录界面不再单独保留旧第三方分支，而是直接复用 page 登录页的统一结构：

- 账号密码表单仍可使用
- binding 列表仍可使用
- OTP / 重置密码仍由 `SigninClient` 原有步骤承接
- 登录成功后仍通过 `onAuthenticated` 回调关闭弹窗并刷新页面

Modal 只是统一登录壳的一种展示模式，不再是独立登录产品。

### 5. 统一前端状态机

第一阶段内，第三方登录统一收敛到一套前端状态机，不再让不同入口各自维护不同等待语义。

最小状态集合：

- `idle`
- `starting`
- `waiting`
- `syncing-session`
- `failed`
- `cancelled`
- `expired`

行为要求：

- 点击某个 binding 后进入 `starting` / `waiting`
- 等待态期间禁用 binding 列表切换
- 成功后进入 `syncing-session`
- 失败、取消、过期后恢复到表单 + 可选 binding 列表

### 6. 旧前端入口退场

第一阶段需要将以下旧入口从主链路中移除：

- `showThirdPartyLogin` 驱动的旧 WeChat / BK 登录按钮区域
- `modalThirdPartyView === 'wechat'` 驱动的 Modal 微信专属界面
- 任何直接面向用户暴露的旧第三方入口渲染分支

允许代码短期残留，但不能继续作为前端主链路的可见入口。

### 7. Session Expiry 兼容调整

第一阶段必须补齐 validation 公开接口在过期态下的可访问性。

至少需要保证以下接口不会被前端过期拦截器误拦：

- `get_login_auth_bindings`
- `start_login_auth`
- `login_auth_requests/{id}/status`

否则 Modal 登录在会话失效后无法走统一 validation 壳。

### 8. 移除系统管理旧认证源菜单

第一阶段还应同步移除前端 `system-manager/user/auth-sources` 认证源菜单入口。

目的不是删除所有后端能力，而是先让前端信息架构与“登录入口收口”方向保持一致，避免旧体系继续在导航层暴露。

这里的范围仅限前端菜单层，不要求同阶段处理其后端接口或数据结构清理。

## 第二阶段：微信 provider 收口

### 1. 收口范围

第二阶段只收微信，不处理 BK。

目标是让微信成为标准 binding provider，走统一的 validation 主链路，而不是继续依赖前端特殊页面或 popup bridge。

### 2. 目标链路

微信应最终走统一流程：

1. 出现在 binding 列表中
2. 前端点击后调用 `start_login_auth`
3. 打开认证承载页
4. 第三方回调后端
5. 原页面或 Modal 轮询状态
6. 成功后统一同步前端会话

这里的设计语义是：

- 微信按标准 binding provider 接入
- 前端与后端都复用现有 validation / binding 主链路
- 不为微信保留“扫码页 / popup bridge / 特殊回传协议”的兼容型新实现
- 第二阶段的目标是替换旧微信特殊流程，而不是把旧流程包装后继续沿用

这里还需要明确责任边界：

- 第二阶段不只是前端“按 binding 方式消费微信”
- 还必须补齐让微信能够作为标准 binding provider 出现在 `get_login_auth_bindings` 返回结果中的实现条件
- 如果现有 provider 配置、启用条件或公开返回逻辑不足以让微信进入 binding 列表，这部分补齐工作属于第二阶段实现范围，而不是外部前置条件

### 3. 需要退出主链路的旧微信实现

第二阶段完成后，以下内容不应再作为微信主登录流程依赖：

- `WechatQrLoginPanel`
- `wechat-popup/bridge`
- 基于 popup message 的微信专属成功回传
- 微信登录专属前端页面切换分支

也就是说，第二阶段实现微信 provider 时，应直接对齐当前 binding 登录流程，而不是新增一套“看起来统一、实际仍沿用旧微信特殊机制”的过渡实现。

### 4. BK 处理策略

BK 在第二阶段继续不动：

- 可暂时保留现有实现
- 但由于第一阶段前端入口已隐藏，BK 可以处于“实现仍在、入口不暴露”的状态
- 后续如需收口，可单独作为下一次改造任务处理

## 组件与职责边界

### `SigninClient`

第一阶段后应继续作为唯一登录主壳，负责：

- 账号密码登录
- OTP 验证
- 密码重置
- binding 列表展示
- 第三方登录等待态 / 同步态
- page / modal 两种展示模式

不再负责：

- 直接面向用户展示 WeChat / BK 特殊入口
- 承担 modal 专属第三方登录产品分支

### `useLoginAuthValidation`

继续作为 binding 第三方流程控制器，负责：

- 加载 binding 列表
- 发起第三方认证
- 轮询认证状态
- 驱动等待态与同步态

第一阶段内重点是让它成为 page / modal 共用的统一状态来源。

### `AuthProvider`

继续负责会话过期后的弹窗承载与成功回调收口，但不再维护自己的独立第三方登录分支。

### `sessionExpiry`

只负责“过期态请求拦截”这一横切逻辑，不应阻断统一登录壳自身所依赖的公开认证接口。

## 风险与控制

### 风险 1：第一阶段切前端后，某些 provider 暂时不可用

这是预期内结果。
由于当前是本地阶段性改造，不要求第一阶段单独具备上线能力。

控制方式：

- 明确第一阶段只负责前端收口
- 真正上线前以 binding 能力补齐为前提

### 风险 2：Modal validation 请求被过期拦截器阻断

控制方式：

- 将 validation 所需公开接口加入过期态白名单
- 在实现阶段用最小验证覆盖 Modal 登录发起链路

### 风险 3：旧入口虽然隐藏，但逻辑分支仍干扰主链路

控制方式：

- 第一阶段即要求旧入口退出主渲染路径
- 即使代码暂时残留，也不能继续被 `SigninClient` 主流程触发

### 风险 4：第二阶段微信收口与第一阶段统一壳耦合过深

控制方式：

- 第一阶段只稳定壳和状态机
- 第二阶段只替换 provider 实现，不重新设计 page / modal UI 壳

## 验收标准

### 第一阶段验收标准

1. 默认登录页展示为：
   - 固定账号密码表单
   - 仅 binding 第三方列表
2. 页面中不再出现 WeChat / BK 特殊登录按钮入口
3. Modal 过期登录展示为与默认登录页一致的统一壳
4. Modal 中不再出现微信专属页面切换或旧第三方入口
5. 账号密码、OTP、重置密码在 page / modal 中均仍可承接
6. validation 公开接口在过期态下可被正常调用
7. 前端 `system-manager/user/auth-sources` 菜单入口被移除

### 第二阶段验收标准

1. 微信可作为标准 binding provider 出现在列表中
2. 微信通过统一 validation / binding 链路跑通登录
3. 前端主流程不再依赖微信 popup bridge 或专属页面
4. 微信实现不复刻旧微信特殊登录流程，而是直接复用现有 binding 登录模型
5. page 与 modal 均只消费统一 binding provider 流程
6. BK 仍未收口不影响本阶段完成

## 预期结果

完成两阶段后，登录体系会形成更清晰的过渡路径：

- 第一阶段先统一前端入口与交互壳
- 第二阶段再将微信纳入统一 provider 链路
- BK 留待后续独立处理

这样可以先把页面结构、状态机、Modal 入口和系统管理前端信息架构收口，再逐步替换底层 provider 实现，避免一次性同时重构 UI 与认证协议。
