# Mobile H5 密码登录联调设计

## 目标与边界

本轮用于内部联调，先完成 Mobile H5 的密码登录闭环。H5 复用 Web 已有的 NextAuth 服务保存浏览器会话，不在 localStorage 或 sessionStorage 中持久化后端 JWT。

本轮只修改 Mobile 及其部署配置，不改变现有 Web 登录流程、NextAuth Provider 行为或 Server API 契约。

同 Origin 下 Web 与 H5 使用同一枚 NextAuth Session Cookie，因此属于共享登录态：Web 已登录时 H5 可恢复同一会话，任一端 `signOut` 也会使另一端退出。这是复用方案的既有语义；如产品要求两端会话隔离，必须使用独立 Origin/Cookie 命名空间或独立 BFF，不能仅靠 Mobile 页面实现。

本轮采用的是过渡型会话方案：NextAuth 负责浏览器会话恢复，H5 从运行时 Session 取得后端 JWT，并以 Bearer Token 调用现有 Django API。它不是完整 BFF，因为后端 JWT 仍会进入 H5 的 JavaScript 内存。

长期目标是将浏览器认证统一收口到 Django 或独立认证服务，由 Web/H5 使用 HttpOnly Cookie 会话或完整 BFF；Tauri 使用独立认证适配和系统安全存储。本轮不改造后端认证中间件，也不承诺 Tauri 的生产会话能力。

本轮包含：

- 账号密码登录、登录失败反馈和重复提交防护。
- 通过 NextAuth 恢复 H5 会话，并通过后端受保护接口确认 JWT 仍然有效。
- 受保护页面的未登录拦截和会话过期处理。
- 后端 token 撤销与 NextAuth 会话清理。
- 识别 OTP 和临时密码分支，明确提示用户暂时到 Web 完成验证。

本轮不包含 OTP 输入、首次二维码绑定和临时密码修改页面。这些是正式交付前必须补齐的认证闭环。

## 部署前提

- Mobile H5 与 Web 使用同一公开 Origin。
- 同域 `/api/auth/*` 转发到 Web Next.js，`/api/proxy/*` 继续按项目现有方式访问 Django。
- NextAuth 会话 Cookie 的 Path 覆盖 `/mobile/h5/`，并使用项目生产环境要求的 `HttpOnly`、`Secure` 和 `SameSite` 配置。
- Mobile 只使用 `next-auth/react` 的客户端能力，不在静态导出项目中实现 NextAuth 服务端路由。
- Mobile 只调用现有 CredentialsProvider 的账号、密码和域登录分支，不使用 Web 内部的 `skipValidation + userData` 会话同步入口。

## 认证流程

1. H5 登录页调用 `signIn('credentials', { username, password, domain, redirect: false })`。
2. `signIn` 向当前 Origin 的 `/api/auth/*` 发起 CSRF 和 Credentials 回调请求，由部署路由转发到 Web Next.js。
3. Web 现有 CredentialsProvider 在 Next 服务端调用 Django `/core/api/login/` 验证账号、密码和域；本轮不修改该 Provider。
4. 普通账号登录成功后，NextAuth 将用户信息和后端 JWT 写入加密的 HttpOnly 会话 Cookie。
5. H5 启动或刷新时通过 `getSession()` 恢复 NextAuth Session，将其中的后端 JWT 只保存在运行时内存。
6. H5 携带该 JWT 请求 `/core/api/login_info/`；成功后设置当前用户，401 或未认证业务响应则清理 NextAuth Session 并进入未登录态。
7. 后续业务请求沿用 `/api/proxy/*`，由统一请求层添加 `Authorization: Bearer <token>`。

NextAuth Session 存在只表示其自身 Cookie 完整且未过期，不代表其中的后端 JWT 一定仍然有效。后端受保护接口的认证结果才是最终依据。

## 未实现分支

- Django 返回 OTP challenge 时，现有 Web Provider 创建的 Session 不包含后端 token；H5 将其识别为未完成验证，清理 NextAuth Session，并提示暂时使用 Web。
- Django 返回 `temporary_pwd: true` 时，该标记会进入现有 NextAuth Session；H5 在使用 token 前拦截并清理 Session，引导用户到 Web 修改密码。
- 未实现分支必须结束 loading、允许返回或重试，不得进入假登录状态。
- 未实现分支的错误信息不得包含密码、JWT、`challenge_id` 或后端异常详情。

## 登出流程

1. H5 调用 Web 的 `/api/auth/federated-logout`。
2. Web 现有路由从 NextAuth Session 中读取后端 JWT，并调用 Django `/core/api/logout/` 请求撤销 token；本轮不改变其“后端异常也可能返回成功”的既有语义。
3. 无论联合登出请求是否成功，H5 都调用 `signOut({ redirect: false })` 删除 NextAuth 会话 Cookie，清理用户信息和团队上下文，最后返回登录页。

Mobile 只能把联合登出路由的 2xx 解释为“请求已接受”，不能据此宣称后端 token 已确认撤销。

## 状态与责任

`AuthContext` 维护 `checking`、`anonymous` 和 `authenticated` 三类全局认证状态。NextAuth 负责恢复浏览器会话，后端受保护接口负责确认真实认证状态。

登录表单自行管理提交中、凭据错误和未支持分支。启动校验的网络错误作为可重试错误展示，不冒充为会话过期。

页面组件不感知 Cookie、JWT 或运行形态差异，只通过认证适配层使用 `getSession`、`login` 和 `logout`。本轮仅实现 H5 适配，Tauri 保留接口边界。

## 安全约束

- H5 不得将后端 JWT 写入 localStorage、sessionStorage、IndexedDB 或普通 Cookie。
- 浏览器侧用户展示缓存必须移除 `token` 等认证凭据，不能把 JWT 藏在 `user_info` 等普通缓存对象中。
- H5 不得调用 Web 的 `skipValidation + userData` 内部同步分支。
- 回调地址只允许站内相对路径，避免开放重定向。
- 401、用户不存在和 token 撤销必须同步清理 NextAuth Session，避免页面显示已登录但后端已拒绝请求。
- 本轮不宣称实现完整 BFF；正式发布前应重新确认是改为完整 BFF，还是由 Django 统一提供浏览器 Cookie 会话。

## 验收场景

- 普通账号可登录，刷新后恢复登录，localStorage 和 sessionStorage 中均无 JWT。
- 登录凭据只通过现有 NextAuth Credentials 回调提交给 Django，H5 不预先直连登录接口，也不传 `skipValidation` 或 `userData`。
- 错误密码不会建立 NextAuth Session，表单可继续提交。
- NextAuth Session 恢复后，H5 使用 Bearer Token 调用 `login_info` 成功并设置当前用户。
- 后端 JWT 被撤销或过期时，即使 NextAuth Cookie 尚未过期，H5 也会在受保护接口返回未认证后退出登录。
- 登出会请求撤销后端 token、删除 NextAuth Cookie，并清理用户与团队上下文；本轮不承诺从现有 Web 路由获得可靠的撤销确认。
- OTP 和临时密码账号不会进入 Mobile 已认证状态；临时 NextAuth Session 会被清理，页面不会持续 loading。
- `/api/auth/*` 未正确转发时显示可诊断的登录服务不可用错误，不退化为本地 JWT 存储。
- 中英文文案、窄屏、键盘弹出和加载/错误状态符合 `mobile/DESIGN.md`。
