# 模块 ARD：前端（web / mobile）

## web —— Next.js 16【已实现/已存在】
- 路径 `web/src/app`，App Router。产品模块目录：`alarm`、`cmdb`、`job`、`log`、`monitor`、`mlops`、`node-manager`、`ops-analysis`、`ops-console`、`opspilot`、`system-manager`（11 个）；另有 `(core)`(认证/布局)、`no-permission`(无权限页)。内部 route handlers 实际位于路由组 `(core)/api/` 下（`proxy`、`locales`、`markdown`、`menu`、`auth`、`json`、`versions`、`mlops` 等）；顶层 `app/api` 仅含 `wechat-popup-login`（微信弹窗登录回调）一个 handler【已实现】。
- **认证**：next-auth（JWT，maxAge 86400），`constants/authOptions.ts` + `lib/auth.ts`；Provider：Credentials（`/api/v1/core/api/login/`）、WeChat OAuth。
- **API 通信（两层）**：客户端 `utils/request.ts` axios baseURL=`/api/proxy`，由 **axios 请求拦截器注入 `Authorization: Bearer {token}`**（`utils/request.ts:56`）；route handler `(core)/api/proxy/[...path]/route.ts` 为**透明代理**（不再注入鉴权），转发到 `NEXTAPI_URL/api/v1`。
- **响应拦截分支**【已实现】（`utils/request.ts:74-89`）：`460`→`forceLogoutAndRedirect()` 强制登出并跳转；`401`→`emitSessionExpired({reason:'api-session-expired'})` 发出会话过期事件（非直接重登）；`400/403/500/其它`→统一 `message.error(messageText)` 弹错并抛 `HandledRequestError`（静默化已处理错误，避免上层重复弹窗）；无响应时：先放行非 axios 错误与超时（`code==='ECONNABORTED'`）按原始 error 透传（`utils/request.ts:93-95`），其余无响应的网络错误抛 `HandledRequestError('网络异常')`（`utils/request.ts:96`）。
- **透明代理行为**【已实现】（`(core)/api/proxy/[...path]/route.ts`）：经 `AbortController` 控制超时（`:5-8`、`:88-91`、`:119`）——所有请求先以 `SSE_TIMEOUT_MS=300s` 计时等待响应头（`:91`），收到响应后若为 SSE 则清除计时不再限时（`:113`），若为普通响应则改用 `DEFAULT_TIMEOUT_MS=60s` 计时其余传输（`:118-119`）；目标路径不以 `/` 结尾时自动补 `/`（`:66-69`）；注入 `X-Forwarded-Host`/`X-Forwarded-For`/`X-Forwarded-Proto`（`:84-86`）；检测到 `content-type: text/event-stream` 即判为 SSE，清除超时并设 `X-Accel-Buffering: no`（禁用 Nginx 缓冲，`:110-114`、`:49`）；异常时 `AbortError` 返回 504、其它返回 500（`:129-141`）。
- **i18n**：react-intl，`locales/{en,zh}.json`，`next.config.mjs:combineLocales()` 合并模块级语言包。
- **UI**：antd v5 + echarts + @antv/g6/x6（拓扑/图）。
- **本轮功能面扩展**【已实现/已存在】：`alarm` 新增告警丰富、告警处理、执行记录三组设置页；`system-manager` 新增内网白名单页；`ops-analysis` 新增大屏、报表与网络状态拓扑组件入口；`monitor` 集成页新增采集探测任务与资产视图路由组装。
- **构建**：多阶段 Dockerfile（builder→node:24-alpine），多模块 Docker 构建目标。

## mobile —— Next.js 15 + Tauri 2【已实现/已存在】
- 路径 `mobile/src/app`：`login`、`workbench`(+detail)、`conversation`（opspilot 会话）、`search`、`profile`。功能为 web 子集（聚焦 AI 会话 + 工作台）。
- **认证**：直接 token 存储（Tauri Store，`utils/secureStorage.ts`），非 next-auth。
- **API 通信**：Tauri Rust 命令 `api_proxy`/`api_stream_proxy` 绕过 CORS（`utils/tauriApiProxy.ts`），fallback fetch。本轮原生代理增加 URL host 白名单、敏感头脱敏、SSE 流取消注册表，默认仅放行 `localhost/127.0.0.1/::1`，生产需显式配置 `TAURI_ALLOWED_HOSTS`（`src-tauri/src/api_proxy.rs:11-82,123-175,259-346`）。
- **语音权限**：会话页改用 `getUserMedia` 统一处理 Web 与 Tauri/Android 麦克风权限，不再依赖单独 IPC 权限探测命令（`src/app/conversation/hooks/useSpeechRecognition.ts:92-109,179-188`）。
- **构建**：`output: 'export'` 静态导出 + Tauri；目标 Android（`build:android*`）、桌面（Windows）。
- UI：antd-mobile v5 + @ant-design/x（聊天）。

## 风险 / 待确认
- web 模块按 `NEXTAPI_INSTALL_APP` 启用已实际落地【已实现】：运行期由 `(core)/api/_utils/installApps.ts:23` 解析 `process.env.NEXTAPI_INSTALL_APP`（为空时回退到目录发现）；构建期由 `scripts/generate-workspace.js:10-11`、`scripts/generate-tsconfig.js:9-10` 据其生成 `pnpm-workspace.yaml` 与 `tsconfig.lint.json` 的 include 范围。其与后端 `INSTALL_APPS` 的对齐/同步策略【待确认】。
- mobile 仅暴露会话+工作台，其余模块是否规划【待确认】。

## 证据来源
`web/src/{app,utils/request.ts,constants/authOptions.ts,lib/auth.ts,context/*,locales/*}`、`web/src/app/api/wechat-popup-login/route.ts`、`web/src/app/(core)/api/{proxy/[...path]/route.ts,_utils/installApps.ts,locales,markdown,menu,auth,json,versions,mlops}`、`web/src/app/alarm/{constants/menu.json,api/settings.ts,(pages)/settings/*}`、`web/src/app/system-manager/{api/settings/index.ts,(pages)/settings/network-whitelist/page.tsx}`、`web/src/app/ops-analysis/{api/{screen.ts,report.ts,networkStatusTopology.ts},(pages)/view/{screen,report}}`、`web/src/app/monitor/{api/integration.ts,(pages)/integration/asset/viewRoute.ts}`、`web/scripts/{generate-workspace.js,generate-tsconfig.js}`、`web/{Dockerfile,.env.example,next.config.mjs}`、`mobile/src/{app,utils/{tauriApiProxy,secureStorage}.ts,context/auth.tsx}`、`mobile/src/app/conversation/hooks/useSpeechRecognition.ts`、`mobile/src-tauri/{src/api_proxy.rs,tauri.conf.json}`、`mobile/next.config.ts`。
