# Historical Superpowers change: 2026-07-21-mobile-h5-password-auth-implementation

Status: done

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-21-mobile-h5-password-auth-implementation.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Mobile H5 通过现有 Web NextAuth 完成可恢复的密码登录，并由 Django Bearer 校验提供最终认证结果，不改变 Web 登录和 Server 接口。

**Architecture:** Mobile H5 调用现有 Web CredentialsProvider 的账号密码分支，NextAuth 恢复 Session 后，Mobile 仅在内存保存其中的 JWT并由统一请求层添加 Bearer；Tauri 继续使用现有存储适配。本轮是 token-mediating 过渡方案，不宣称完整 BFF。

**Tech Stack:** Next.js 16/15、NextAuth 4.24、React、TypeScript、Django API、Nginx、Node test runner。

## Global Constraints

- H5 不向 localStorage、sessionStorage、IndexedDB 或普通 Cookie 写入后端 JWT。
- 不修改 Web CredentialsProvider、Web 登录调用点或 Server 登录/注销接口。
- 同 Origin 下 Web/H5 共享 NextAuth 登录态；会话隔离不属于本轮范围。
- OTP 和临时密码账号本轮不在 Mobile 完成验证，但不得建立会话。
- Tauri 认证行为不得因 H5 改造而失效。

---

### Task 1: 保护现有 Web 与 Server 行为

**Files:**
- Verify only: `web/`
- Verify only: `server/`

- [x] 恢复本轮产生的全部 Web 和 Server 改动。
- [x] 确认 `git diff --exit-code -- web server` 通过。
- [x] Mobile 仅调用现有 CredentialsProvider 的账号密码分支。

### Task 2: Mobile H5 会话适配

**Files:**
- Create: `mobile/src/auth/h5Auth.ts`
- Create: `mobile/scripts/mobile-h5-auth-test.mjs`
- Modify: `mobile/src/context/auth.tsx`
- Modify: `mobile/src/types/auth.ts`
- Modify: `mobile/src/app/login/page.tsx`
- Modify: `mobile/src/api/request.ts`
- Modify: `mobile/src/utils/secureStorage.ts`
- Modify: `mobile/package.json`
- Modify: `mobile/pnpm-lock.yaml`

- [x] 写失败测试，覆盖 H5 登录成功取 Session token、现有 CredentialsSignin、OTP/临时密码拦截、会话恢复、登出始终清理 NextAuth，以及运行时 token 禁止回退 localStorage。
- [x] 运行 `pnpm test:h5-auth`，确认测试因 H5 适配尚不存在而失败。
- [x] 引入 `next-auth@4.24.13`，实现无 React 依赖的 H5 认证流程函数。
- [x] AuthContext 按 H5/Tauri 分流：H5 使用 NextAuth，Tauri 保持现有后端登录和安全存储流程。
- [x] 登录页改为消费统一登录结果，正确展示凭据错误、OTP 和临时密码提示。
- [x] 请求层使用显式运行时 token；H5 初始化前后均不得回退旧 localStorage token，浏览器用户缓存必须移除 JWT，401 触发认证适配清理。
- [x] 运行目标测试、lint 和 type-check。

### Task 3: 同源路由与部署验证

**Files:**
- Modify: `mobile/next.config.ts`
- Modify: `mobile/nginx.h5.conf`
- Modify: `mobile/scripts/mobile-h5-deploy-config-test.mjs`
- Modify: `mobile/scripts/mobile-h5-image-test.mjs`

- [x] 先扩展部署测试，要求开发环境和 H5 Nginx 将 `/api/auth/*` 转发到 Web。
- [x] 运行 `pnpm test:h5-deploy`，确认新增断言失败。
- [x] 增加开发 rewrite 和生产 Nginx 代理，保留 Host、Cookie 与转发协议。
- [x] 扩展最终镜像 mock，真实验证 `/api/auth/session` 和 `Set-Cookie` 透传。
- [x] 运行部署测试与最终镜像测试。

### Task 4: 完整验证与人工联调

**Files:**
- Verify only; fix failures in the owning files above.

- [x] 确认 Web 和 Server 为零 diff，不运行由本轮撤销代码产生的目标测试。
- [x] 运行 Mobile 的 H5 认证测试、部署测试、lint、type-check 和 H5 build。
- [x] 启动 Web、Mobile 与可控 Django 模拟服务，验证登录、刷新恢复、受保护 API、401 和登出。
- [x] 通过行为测试和请求链路确认浏览器持久化缓存无 JWT、NextAuth Cookie 可恢复、现有联合登出链路可调用；Mobile 不把路由 2xx 误报为后端撤销确认。
- [x] 审查 `git diff` 与 `git status`，确认只包含设计、计划和认证相关改动，不提交。
