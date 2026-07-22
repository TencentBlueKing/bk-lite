# Historical Superpowers change: 2026-06-11-signin-login-auth-validation

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-11-signin-login-auth-validation-design.md

> 说明：本文档保留设计阶段的过程记录。当前仓库实现已经在此基础上继续演进，凡与现状不一致之处，以当前代码实现为准。

## 背景

当前系统已经具备两类基础能力：

- 后端可返回已启用的登录认证列表：`GET /api/v1/core/api/get_login_auth_bindings/`
- 后端可基于登录认证绑定生成外部认证地址，并在拿到 `auth_code` 后完成平台登录

但当前 `/auth/signin` 仍以“平台账号密码登录 + 既有第三方入口”为主，尚未具备一条**通用的、可扩展的登录认证编排链路**。
本次不直接替换默认登录页，而是在不影响现有登录流的前提下，先实现一套“登录认证验证模式”，用于验证：

1. 登录页展示统一的登录认证列表
2. 点击某个登录认证方式后，由后端发起认证事务
3. 外部认证在新标签页完成
4. 原登录页保持原地等待，不刷新
5. 外部认证完成后由后端更新认证结果
6. 原登录页通过轮询获取结果并完成前端会话同步

## 目标

1. 继续复用 `/auth/signin` 路由，不新增长期独立登录页路由。
2. 通过 query 参数切换到“登录认证验证模式”，默认登录页保持现状不变。
3. 在验证模式中完整跑通：
   - 登录认证列表展示
   - 点击登录认证方式后获取认证地址
   - 以前端打开**新标签页**的方式进入第三方认证
   - 原登录页进入等待认证完成状态
   - 第三方认证回调后端
   - 原登录页通过轮询拿到认证结果
   - 成功后建立前端会话并跳转业务页
4. 在验证模式中，将“平台账号密码登录”作为前端内置登录认证方式展示。
5. 前端视觉风格对齐项目现有 `/auth/signin`，不做后台配置页风格迁移。

## 非目标

- 本阶段**不直接替换**默认 `/auth/signin` 登录流程。
- 本阶段**不要求**系统管理中的登录认证列表立刻落一条真实的“平台账号密码登录”数据库记录。
- 不重做现有用户名密码登录、OTP、重置密码、微信既有登录链路。
- 不在本阶段统一改造微信为同一套认证事务模型。
- 不引入 WebSocket / SSE；状态同步优先使用轮询。

## 现状梳理

### 前端

- `web/src/app/(core)/auth/signin/page.tsx`
- `web/src/app/(core)/auth/signin/SigninClient.tsx`

当前 `SigninClient` 已具备：

- 平台账号密码登录表单
- 阶段切换（登录 / OTP / 重置密码）
- `completeAuthentication()`：把后端登录结果接入现有 NextAuth 会话

### 后端

- `server/apps/core/views/index_view.py`
- `server/apps/system_mgmt/services/login_auth_binding_service.py`
- `server/apps/system_mgmt/viewset/login_auth_binding_viewset.py`

当前后端已具备：

1. 返回启用中的登录认证列表
2. 生成指定登录认证的外部授权地址
3. 使用 `binding_id + auth_code` 完成平台登录
4. 登录成功时写入 `bklite_token` cookie

## 推荐方案

采用**同一路由双模式 + 后端认证事务驱动**方案：

- 默认访问 `/auth/signin`：继续走现有登录页逻辑
- 访问 `/auth/signin?loginAuthMode=validation`：进入登录认证验证模式
- 点击外部登录认证方式后，不在当前页跳走，而是：
  1. 由后端创建认证事务
  2. 前端打开新标签页进入第三方认证
  3. 原登录页进入等待态并轮询认证结果
  4. 后端 callback 完成后更新认证事务状态
  5. 原登录页拿到成功结果后再同步前端会话

该方案的核心价值：

1. **交互符合目标**：原登录页不刷新，能够保持等待态
2. **兼容面更大**：不仅适用于标准 OAuth/OIDC，也为扫码确认、异步确认类登录预留了模型
3. **后端主导编排**：第三方回调、用户匹配、平台登录态建立统一由后端负责

## 方案对比

### 方案 A：新标签页认证 + 后端 callback + 原页轮询（推荐）

- 优点：
  - 符合当前确认的产品交互
  - 后端掌握认证事务，兼容更多 provider 差异
  - 原页可保持稳定等待态
- 缺点：
  - 需要新增认证事务模型与状态查询接口

### 方案 B：当前页整页跳转 + 前端 callback 页承接 `code`

- 优点：
  - 改动更少
  - 更接近当前微信普通链路
- 缺点：
  - 当前页会离开，无法满足“原页等待”的目标
  - 对异步确认类登录兼容性较弱

### 方案 C：popup 小窗口认证 + `postMessage` 通知原页

- 优点：
  - 也能保留原页
  - 与仓库现有微信 popup 方案一致
- 缺点：
  - 产品当前要求是**新标签页**而不是 popup
  - 浏览器拦截与窗口管理复杂度更高

## 详细设计

### 1. 模式切换

`/auth/signin` 新增专用 query 参数：

- `loginAuthMode=validation`：进入登录认证验证模式
- 无该参数：保持当前默认登录模式

验证模式下的前端阶段建议使用本地状态管理，不再依赖 callback query 参数推进主流程。

### 2. 验证模式页面结构

验证模式下，`SigninClient` 渲染新的“登录认证容器”，包含两部分：

#### 2.1 平台内置登录认证卡片

前端固定渲染一条“平台账号密码登录”卡片：

- 名称：平台账号密码登录
- 图标：复用项目内现有平台风格图标
- 描述：平台内建账号体系

点击后切换回当前已有的用户名密码登录表单。

#### 2.2 外部登录认证列表

从 `GET /api/v1/core/api/get_login_auth_bindings/` 获取其它已启用登录认证方式，按返回顺序渲染卡片列表。

每个卡片至少展示：

- 名称
- 图标
- 描述

卡片风格对齐当前 `/auth/signin` 的登录模块，而不是后台管理列表风格。

### 3. 认证事务模型

后端需要引入一条可查询的认证事务 `auth_request`，用于承接整个登录认证过程。

建议最小字段：

- `id`
- `binding_id`
- `provider_key`
- `status`
- `callback_url`
- `state`
- `poll_token`
- `error_message`
- `created_at`
- `expired_at`
- `completed_at`

建议状态枚举：

- `pending`
- `success`
- `failed`
- `expired`
- `cancelled`

第一阶段不强制规定必须落库为数据库模型，但后端必须有一条**可被 callback 更新、可被前端查询**的认证事务记录。

### 4. 发起认证

当用户点击某个外部登录认证卡片时：

1. 前端调用新的公开接口：`POST /api/v1/core/api/start_login_auth/`
2. 请求体至少包含：
   - `binding_id`
   - `callback_url`（登录完成后平台内最终要跳转的地址，默认 `/`）
3. 后端负责：
   - 创建 `auth_request`
   - 生成 `auth_request_id`
   - 生成 provider 所需的 `state`，并确保可关联到该 `auth_request`
   - 生成第三方回调到 BK-Lite 后端的绝对 `redirect_uri`
   - 调用现有登录认证绑定能力生成 `login_url`
4. 后端成功响应：
   - `auth_request_id`
   - `poll_token`
   - `login_url`
   - `expires_at`

建议成功响应：

```json
{
  "result": true,
  "data": {
    "auth_request_id": "xxx",
    "poll_token": "yyy",
    "login_url": "https://...",
    "expires_at": "2026-06-11T12:00:00Z"
  },
  "message": ""
}
```

### 5. 新标签页认证

前端拿到 `login_url` 后：

1. 使用 `window.open(login_url, "_blank")` 打开新标签页
2. 当前 `/auth/signin` 页面不离开
3. 当前页进入 `waiting` 状态
4. 保存 `auth_request_id`
5. 保存 `poll_token`
6. 启动状态轮询

如果新标签页打开失败（被浏览器拦截），当前页应给出明确错误提示，并允许用户重试。

### 6. 第三方回调后端

用户在新标签页完成第三方认证后，第三方应将浏览器重定向到 BK-Lite 后端 callback URL。

后端 callback 负责：

1. 校验 `state`
2. 解析并定位对应 `auth_request`
3. 使用 provider 返回的 `code` / `ticket` / 等价凭证完成真实认证
4. 获取第三方用户信息
5. 匹配或创建平台用户
6. 生成平台 token 并写入 `bklite_token` cookie
7. 更新 `auth_request.status`
   - 成功：`success`
   - 失败：`failed`
   - 第三方明确返回拒绝 / access_denied：`cancelled`
   - 超时：`expired`
8. 返回一个简单的完成页面，告知用户“认证已完成，可返回原页面”

这一步不要求 callback 再把用户浏览器带回 `/auth/signin`；主流程由原页面轮询推进。

这里需要明确一点：**关闭新标签页本身不可被后端可靠感知**，因此不将“用户手动关闭认证页”直接映射为 `cancelled`。第一阶段中：

- `cancelled` 仅表示第三方明确返回取消 / 拒绝
- 用户关闭新标签页但未完成认证，原页继续轮询直到超时，最终进入 `expired`

### 7. 认证状态轮询

原登录页在 `waiting` 状态下轮询新的公开接口：

- `GET /api/v1/core/api/login_auth_requests/{auth_request_id}/status`

请求必须同时携带 `poll_token`，例如通过请求头或 query 参数传入。
`poll_token` 由发起认证接口返回，用于证明当前轮询方拥有该认证事务的查询权；后端不能仅凭 `auth_request_id` 就返回状态。

建议返回结构：

```json
{
  "result": true,
  "data": {
    "status": "pending",
    "message": "",
    "expires_at": "2026-06-11T12:00:00Z"
  }
}
```

可返回的 `status`：

- `pending`
- `success`
- `failed`
- `expired`
- `cancelled`

前端只消费状态结果与通用错误消息，不依赖第三方平台专有字段。

### 8. 前端会话同步

当原登录页轮询到 `success` 后，不能只结束等待，还需要同步当前 Web 的前端登录态。

推荐流程：

1. 当前页进入 `syncing-session` 状态
2. 调用 `/api/proxy/core/api/get_bk_settings/` 获取当前已登录用户
3. 如果拿到有效用户信息，则复用现有 `completeAuthentication()` 或等价逻辑：
   - `saveAuthToken(...)`
   - `signIn('credentials', skipValidation=true, userData=...)`
4. 建立 NextAuth session
5. 成功后跳转到 `callback_url`

如果后端认证事务已经成功，但前端会话同步失败，则进入失败态并给出可重试提示。

该流程成立的前提是：**第三方 callback 页写入的 `bklite_token` cookie 对原 `/auth/signin` 页是可见的**。
也就是说，后端 callback 所在域与前端通过 `/api/proxy/core/api/get_bk_settings/` 读取登录态所依赖的 cookie 作用域必须与当前仓库现有登录流保持一致。若部署形态不能满足这一点，则本方案不能直接落地，必须先统一 cookie 域策略。

### 9. 前端状态机

验证模式至少覆盖以下状态：

1. `list`：展示平台内置登录方式与外部登录认证列表
2. `builtin-password`：展示平台账号密码表单
3. `waiting`：已打开新标签页，等待第三方认证完成
4. `syncing-session`：后端认证成功，前端正在同步 NextAuth 会话
5. `success`：登录完成，准备跳转
6. `failed`：认证失败
7. `expired`：认证超时
8. `cancelled`：第三方明确返回用户取消或拒绝授权

其中 `waiting` 与 `syncing-session` 必须分开，避免用户误解当前进度。

### 10. 样式与交互约束

实现时遵循以下约束：

1. **优先参考当前 `/auth/signin` 风格**
   - 大卡片容器
   - 明确标题和说明文案
   - 一致的按钮、圆角、阴影、间距
2. 不使用系统管理页的配置型布局风格
3. 等待态需要明确告知：
   - 已打开新标签页
   - 请在新标签页完成认证
   - 完成后此页会自动继续
4. 失败态需要支持：
   - 返回列表
   - 重新发起认证

## 数据与接口约束

### 公开接口补齐

当前公开登录页已具备：

- `GET /api/v1/core/api/get_login_auth_bindings/`

本方案要求新增两个公开接口：

1. `POST /api/v1/core/api/start_login_auth/`
2. `GET /api/v1/core/api/login_auth_requests/{auth_request_id}/status`

现有 `system_mgmt/login_auth_binding/<id>/login_url/` 受后台权限保护，不能直接给未登录用户页面使用，因此必须由公开登录入口补齐对外能力。

### 两个关键概念

- `callback_url`：登录成功后平台内最终业务跳转地址，例如 `/`、`/console`
- `redirect_uri`：第三方认证完成后回调到 BK-Lite 后端 callback 的地址，由后端基于当前请求域名生成绝对 URL，不由前端自行拼接

## 风险与控制

### 风险

1. 新旧登录模式共存，若分支边界不清晰，可能影响默认登录页
2. `auth_request` 状态管理不完整，可能导致原页长期卡在等待态
3. 后端 callback 成功但前端 session 同步失败，可能造成“后端已登录、前端未完成”的中间态
4. `callback_url` 若不校验，存在 open redirect 风险
5. 若 `poll_token` 设计不当，可能导致跨用户读取认证状态

### 控制措施

1. 用显式 query 参数隔离新旧模式
2. `auth_request` 必须有过期时间与失败兜底状态
3. 成功后统一复用现有前端会话建立逻辑
4. `callback_url` 仅允许站内相对路径或受控同源地址
5. 状态查询必须同时校验 `auth_request_id + poll_token`

## 验收标准

1. 不带验证参数访问 `/auth/signin` 时，现有登录页行为不变
2. 带验证参数访问 `/auth/signin` 时，可进入登录认证验证模式
3. 验证模式中可看到：
   - 平台账号密码登录内置卡片
   - 后端返回的其它登录认证卡片
4. 点击外部登录认证卡片后：
   - 可获取 `auth_request_id + login_url`
   - 浏览器打开新标签页进入第三方认证
   - 原登录页进入等待态且不刷新
5. 第三方认证完成后：
   - 后端 callback 更新认证事务状态
   - 原登录页可通过轮询拿到成功或失败结果
   - 第三方明确拒绝授权时可进入 `cancelled`
6. 成功时：
   - 后端写入平台登录 cookie
   - 原登录页可成功同步 NextAuth 会话
   - 最终跳转到 `callback_url`
7. 失败或超时时：
   - 原登录页退出等待态
   - 给出清晰错误反馈
   - 支持重新发起认证

## 预期结果

完成后，BK-Lite 将在 `/auth/signin` 上具备一套更通用的登录认证验证模式：

- 原登录页保留原地等待体验
- 外部认证在新标签页进行
- 后端统一承接第三方 callback 和平台登录态建立
- 原登录页通过认证事务状态推进 UI

这套模型比单纯“前端 callback 页拿 `code`”更适合后续兼容更多登录方式，也为未来统一登录认证编排留出了清晰边界。
