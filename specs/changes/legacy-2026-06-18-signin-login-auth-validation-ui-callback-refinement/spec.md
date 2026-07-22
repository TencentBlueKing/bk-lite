# Historical Superpowers change: 2026-06-18-signin-login-auth-validation-ui-callback-refinement

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-18-signin-login-auth-validation-ui-callback-refinement.md

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

## specs: 2026-06-18-signin-login-auth-validation-ui-callback-refinement-design.md

> 说明：本文档保留设计阶段的过程记录。当前仓库实现已经在此基础上继续演进，凡与现状不一致之处，以当前代码实现为准。

## 背景

现有 `/auth/signin?loginAuthMode=validation` 已具备如下能力：

- 原登录页保留在当前标签页
- 用户可选择外部登录认证方式
- 页面通过 `window.open(...)` 打开第三方认证页
- 后端通过 `auth_request` 缓存对象记录认证请求状态
- 原登录页通过轮询 `/login_auth_requests/{auth_request_id}/status` 感知成功 / 失败 / 取消 / 过期
- 第三方认证完成后，后端 callback 会更新状态并写入认证 cookie

当前存在两个收敛问题：

1. validation 模式下，点击外部登录方式后，原登录页中间区域的等待态展示与现有登录页结构不够一致，且在不同屏幕高度下纵向压迫感明显。
2. 第三方认证完成后的结果停留页当前由后端模板 `login_auth_callback.html` 承载，职责边界不清晰。

本设计只收敛上述两个问题，不重做整套认证架构。

## 目标

1. 保持 `/auth/signin` 当前整体页面骨架不变。
2. validation 模式下，点击外部登录方式后，中间账号密码区域切换为等待态，而不是额外叠加一张独立卡片。
3. 等待态期间锁定当前外部登录方式，避免多条并发认证请求导致状态混乱。
4. 第三方认证结果页迁移到前端承载，后端 callback 仅负责协议处理与重定向。
5. 第三方认证结果页当前阶段不做自动关闭，保持由用户手动关闭并返回原登录页。
6. callback 结果页保留现有页面内容表达，不在本阶段重做视觉或文案。

## 非目标

- 不改造为整页 OAuth 跳转模型。
- 不引入 `postMessage`、自动关闭新标签页、桥接页脚本执行等能力。
- 不支持等待态下切换到另一种外部认证方式。
- 不改动现有 `auth_request` 缓存机制与轮询主链路。
- 不重写 callback 结果页的品牌样式、多语言内容或交互细节。

## 当前链路事实

### 原登录页行为

- `SigninClient.tsx` 在 `validationMode=true` 时启用 `useLoginAuthValidation`
- `useLoginAuthValidation` 加载外部登录绑定列表
- 用户点击某个 binding 后，前端调用 `/api/proxy/core/api/start_login_auth/`
- 后端返回：
  - `auth_request_id`
  - `poll_token`
  - `login_url`
  - `expires_at`
- 前端执行 `window.open(login_url, "_blank")`
- 原页面开始轮询认证状态

### 后端 callback 行为

- 第三方回调打到 `/api/v1/core/api/login_auth/callback/`
- 后端读取 `state`，定位 `auth_request_id` 与 `binding_id`
- 后端调用 `login_with_binding(...)`
- 成功后：
  - 更新 `auth_request.status = success`
  - 保存 `login_result`
  - 写入 `bklite_token`
- 失败 / 取消 / 过期时：
  - 更新对应状态
- 当前 callback 最终通过后端模板页停留展示结果

### 关键约束

当前后端不存在“取消旧 auth_request”的机制。

因此，如果原登录页在等待态下继续允许用户点击另一种外部登录方式，将产生多条并行认证请求；后续任一请求完成都可能写入认证 cookie，而原登录页仅轮询最后一次发起的请求，存在状态理解混乱风险。

## 设计结论

### 1. 原登录页整体骨架保持不变

validation 模式下继续沿用当前 `/auth/signin` 页面结构：

- 外层标题区保持不变
  - `Sign In`
  - 副标题
- 底部外部登录方式列表保留当前位置与现有内容表达
- 中间主操作区作为“内容态切换区”

不将等待态额外包裹成新卡片，也不新增第二个主视觉容器。

### 2. 中间主操作区采用内容态切换

#### 默认选择态

中间区域展示：

- 用户名输入框
- 密码输入框
- 登录按钮

底部外部登录方式列表可点击。

#### 等待外部认证态

点击某个外部登录方式后，中间区域替换为等待态内容。

展示内容：

- loading / waiting 状态图标
- 标题：等待第三方认证
- 辅助文案：当前方式：`{binding.name}`
- 说明文案：已打开新页面，请在第三方平台完成认证，成功后将自动返回此页

不展示：

- 用户名输入框
- 密码输入框
- 登录按钮
- 额外包裹卡片
- 重新打开按钮
- 返回按钮

#### 同步中

当轮询结果返回 success，且原登录页正在执行后续前端会话同步时，中间区域继续保留状态型内容，不恢复为表单态。

展示内容可复用等待态容器，只更新主标题与说明文案：

- 标题：正在完成登录
- 说明：认证已成功，正在同步登录状态，请稍候

#### 失败 / 取消 / 过期

当轮询结果返回 `failed` / `cancelled` / `expired` 时，页面回到默认选择态：

- 中间区域恢复用户名 / 密码输入区
- 顶部或表单区展示一条轻量错误提示
- 底部外部登录方式列表恢复可点击

不保留长期停留的失败状态面板，避免页面同时竞争多个状态中心。

### 3. 底部外部登录方式列表规则

#### 默认选择态

- 列表可点击
- 可发起任意外部登录方式

#### 等待外部认证态

- 列表保留位置不变
- 当前已发起的方式高亮
- 其他方式禁用，不允许切换
- 禁用采用真实不可点击态，不保留 hover 后点击再拦截的交互形式

#### 同步中

- 与等待态一致
- 保持当前方式高亮
- 列表继续禁用

#### 失败 / 取消 / 过期

- 列表恢复可点击
- 原登录页错误提示统一复用 validation 链路已有的错误状态来源，不额外引入多套本地文案判断策略

### 4. callback 结果页迁移到前端承载

当前 `login_auth_callback.html` 的问题不在于页面内容本身，而在于用户可见结果页由后端模板承载，职责边界不够清晰。

本阶段调整为：

1. 后端 callback 继续作为第三方平台的回调入口
2. 后端 callback 继续负责：
   - 解析 `state/code`
   - 校验请求合法性
   - 调用 `login_with_binding`
   - 更新 `auth_request`
   - 写认证 cookie
3. 后端 callback 不再直接渲染后端模板结果页
4. 后端 callback 根据成功 / 失败 / 取消 / 过期结果，重定向到前端专用结果页
5. 前端结果页继续展示当前已有内容表达

后端与前端之间需要使用明确、稳定的结果参数传递 callback 状态，不在实现阶段依赖前端自行推断。
本阶段至少稳定传递：

- 结果状态：`success` / `failed` / `cancelled` / `expired`
- 结果说明文案或错误描述（如有）

### 5. callback 结果页当前阶段不做自动关闭

当前阶段保持：

- 用户手动关闭第三方认证结果页
- 用户返回原登录页

不引入：

- `window.close()`
- `window.opener.postMessage(...)`
- 自动桥接原页
- 自动关闭失败兜底逻辑

这样可以先收敛职责边界，而不扩展窗口控制复杂度。

### 6. 为什么不直接重定向回普通登录页

当前 validation 模式采用的是“原页面保留 + 新开页认证”模型。

因此如果第三方 callback 完成后，后端直接重定向到普通 `/auth/signin`：

- 被重定向的是新开认证页本身
- 不会替换原始登录页实例
- 用户只会在新开页中再次看到登录页

所以本阶段不重定向到普通登录页，而是重定向到前端专用结果页。

## 页面状态机

### 原登录页状态

- `selecting`
  - 展示账号密码输入区
  - 外部登录方式列表可点击

- `waiting`
  - 展示等待态
  - 列表锁定
  - 当前方式高亮

- `syncing-session`
  - 展示同步中状态
  - 列表锁定

- `failed/cancelled/expired`
  - 恢复到 `selecting`
  - 展示轻量错误提示

### callback 结果页状态

- `success`
- `failed`
- `cancelled`
- `expired`

当前阶段均保持现有页面内容表达，只调整承载位置为前端页面。

## 影响范围

### 前端

- `web/src/app/(core)/auth/signin/SigninClient.tsx`
  - 调整 validation 模式下中间内容区状态切换逻辑
  - 在等待态 / 同步中锁定底部外部登录方式列表

- `web/src/app/(core)/auth/signin/login-auth/LoginAuthValidationPanel.tsx`
  - 从“独立卡片面板”收敛为“中间主操作区状态内容”
  - 与页面原表单区保持同层级切换

- 新增前端 callback 结果页
  - 承载当前 callback 结果展示内容

### 后端

- `server/apps/core/views/index_view.py`
  - 保留 callback 协议处理逻辑
  - 将最终响应从渲染模板页切换为重定向前端结果页

### 不涉及

- 不改 `auth_request` service 数据结构
- 不改 `login_with_binding(...)` 认证逻辑
- 不改 NextAuth session 同步模型
- 不改普通 `/auth/signin` 非 validation 模式

## 风险与约束

1. 等待态锁定列表是基于当前后端不支持取消旧请求的现实约束，不是纯视觉偏好。
2. callback 结果页迁移到前端后，后端仍需保证成功 / 失败 / 取消 / 过期状态可稳定映射到前端结果页参数。
3. 当前阶段不做自动关闭，因此用户仍需手动关闭新开认证页；这是有意控制范围的设计决定。
4. 若未来希望等待态下支持切换外部认证方式，需要先补齐“取消旧 auth_request”或“仅承认最后一次请求”的后端约束，再讨论交互放开。

## 验收标准

1. 访问 `/auth/signin?loginAuthMode=validation` 时，页面外层标题与底部登录方式列表位置保持现有布局。
2. 点击某个外部登录方式后，中间账号密码区域切换为等待态，且不出现额外独立卡片。
3. 等待态和同步中状态下，底部外部登录方式列表不可切换，当前方式高亮。
4. 外部认证失败 / 取消 / 过期后，页面恢复为默认表单态，并重新允许选择外部登录方式。
5. 第三方 callback 完成后，后端不再渲染后端模板结果页，而是重定向到前端专用结果页。
6. 前端专用结果页保持当前页面内容表达，不要求自动关闭页面。
