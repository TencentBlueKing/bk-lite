# 模块 ARD：前端（web / mobile）

> Migrated from `spec/ARD/modules/frontend.md` as legacy capability evidence.

## web —— Next.js 16【已实现/已存在】
- 路径 `web/src/app`，App Router。产品模块目录：`alarm`、`cmdb`、`job`、`log`、`monitor`、`mlops`、`node-manager`、`ops-analysis`、`ops-console`、`opspilot`、`system-manager`（11 个）；另有 `(core)`(认证/布局)、`no-permission`(无权限页)。内部 route handlers 实际位于路由组 `(core)/api/` 下（`proxy`、`locales`、`markdown`、`menu`、`auth`、`json`、`versions`、`mlops` 等）；顶层 `app/api` 仅含 `wechat-popup-login`（微信弹窗登录回调）一个 handler【已实现】。
- **认证**：next-auth（JWT，maxAge 86400），`constants/authOptions.ts` + `lib/auth.ts`；Provider：Credentials（`/api/v1/core/api/login/`）、WeChat OAuth。
- **API 通信（两层）**：客户端 `utils/request.ts` axios baseURL=`/api/proxy`，由 **axios 请求拦截器注入 `Authorization: Bearer {token}`**（`utils/request.ts:56`）；route handler `(core)/api/proxy/[...path]/route.ts` 为**透明代理**（不再注入鉴权），转发到 `NEXTAPI_URL/api/v1`。
- **响应拦截分支**【已实现】（`utils/request.ts:74-89`）：`460`→`forceLogoutAndRedirect()` 强制登出并跳转；`401`→`emitSessionExpired({reason:'api-session-expired'})` 发出会话过期事件（非直接重登）；`400/403/500/其它`→统一 `message.error(messageText)` 弹错并抛 `HandledRequestError`（静默化已处理错误，避免上层重复弹窗）；无响应时：先放行非 axios 错误与超时（`code==='ECONNABORTED'`）按原始 error 透传（`utils/request.ts:93-95`），其余无响应的网络错误抛 `HandledRequestError('网络异常')`（`utils/request.ts:96`）。
- **透明代理行为**【已实现】（`(core)/api/proxy/[...path]/route.ts`）：经 `AbortController` 控制超时（`:5-8`、`:88-91`、`:119`）——所有请求先以 `SSE_TIMEOUT_MS=300s` 计时等待响应头（`:91`），收到响应后若为 SSE 则清除计时不再限时（`:113`），若为普通响应则改用 `DEFAULT_TIMEOUT_MS=60s` 计时其余传输（`:118-119`）；目标路径不以 `/` 结尾时自动补 `/`（`:66-69`）；注入 `X-Forwarded-Host`/`X-Forwarded-For`/`X-Forwarded-Proto`（`:84-86`）；检测到 `content-type: text/event-stream` 即判为 SSE，清除超时并设 `X-Accel-Buffering: no`（禁用 Nginx 缓冲，`:110-114`、`:49`）；异常时 `AbortError` 返回 504、其它返回 500（`:129-141`）。
- **i18n**：react-intl，`locales/{en,zh}.json`；模块级语言包在显式构建资源准备阶段汇总。
- **UI**：antd v5 + echarts + @antv/g6/x6（拓扑/图）。
- **本轮功能面扩展**【已实现/已存在】：`alarm` 新增告警丰富、告警处理、执行记录三组设置页；`system-manager` 新增内网白名单页；`ops-analysis` 新增大屏、报表与网络状态拓扑组件入口；`monitor` 集成页新增采集探测任务与资产视图路由组装。
- **构建与资源准备契约**：生产构建经显式入口串行完成企业扩展路由、语言包与菜单汇总、公共资源复制后再启动 Next.js 构建；任一准备步骤失败即中止，不再由框架配置加载时隐式触发副作用。生产类型检查使用面向交付代码的独立配置，排除脚本、端到端用例、故事与单元测试等非交付范围。

> 证据来源：web/scripts/build.mjs:68-119、web/scripts/prepare-build-assets.mjs:8-13、web/next.config.mjs:22-24、web/tsconfig.build.json:1-21　|　同步基线：d2769559　|　【已实现】

- **构建与验证环境契约**：容器构建与运行时统一使用 Node 24、pnpm 11.20，并以锁文件冻结依赖；开发和默认生产构建启用 Turbopack。企业扩展存在时，构建追踪与 Turbopack 的根目录提升至仓库根以覆盖其依赖边界。端到端冒烟验证先完成生产构建，再以本地生产服务校验应用外壳可访问、返回非服务端错误并具备可见页面主体。

> 证据来源：web/package.json:5-15、web/package.json:114-116、web/Dockerfile:1-2、web/Dockerfile:22-23、web/Dockerfile:37-41、web/next.config.mjs:25-34、web/playwright.config.ts:15-25、web/e2e/app-shell.spec.ts:3-9　|　同步基线：d2769559　|　【已实现】

- **按应用裁剪工作区**：`NEXTAPI_INSTALL_APP` 仅在显式执行“生成工作区”流程时用于生成工作区包范围并完成冻结依赖安装；常规构建不自动改变工作区范围。运行期菜单及可安装应用发现仍可读取该配置，二者与后端安装清单的一致性由部署流程保障。

> 证据来源：web/package.json:13-15、web/scripts/generate-workspace.js:69-78、web/src/app/(core)/api/_utils/installApps.ts:23　|　同步基线：d2769559　|　【已实现】

- **共享更多操作菜单**：跨模块的更多操作入口在呈现前按所需权限包装；危险操作必须通过二次确认后才执行。用于表格行、卡片等可点击容器时，可启用事件阻断，使展开菜单及选择操作不触发父容器的点击行为。

> 证据来源：web/src/components/more-actions-dropdown/index.tsx:51-65、web/src/components/more-actions-dropdown/index.tsx:68-112　|　同步基线：d2769559　|　【已实现】

## mobile —— Next.js 15 + Tauri 2【已实现/已存在】
- 路径 `mobile/src/app`：`login`、`workbench`(+detail)、`conversation`（opspilot 会话）、`search`、`profile`。功能为 web 子集（聚焦 AI 会话 + 工作台）。
- **认证**：直接 token 存储（Tauri Store，`utils/secureStorage.ts`），非 next-auth。
- **API 通信**：Tauri Rust 命令 `api_proxy`/`api_stream_proxy` 绕过 CORS（`utils/tauriApiProxy.ts`），fallback fetch。本轮原生代理增加 URL host 白名单、敏感头脱敏、SSE 流取消注册表，默认仅放行 `localhost/127.0.0.1/::1`，生产需显式配置 `TAURI_ALLOWED_HOSTS`（`src-tauri/src/api_proxy.rs:11-82,123-175,259-346`）。
- **语音权限**：会话页改用 `getUserMedia` 统一处理 Web 与 Tauri/Android 麦克风权限，不再依赖单独 IPC 权限探测命令（`src/app/conversation/hooks/useSpeechRecognition.ts:92-109,179-188`）。
- **构建**：`output: 'export'` 静态导出 + Tauri；目标 Android（`build:android*`）、桌面（Windows）。
- UI：antd-mobile v5 + @ant-design/x（聊天）。

## webchat —— npm monorepo【已实现/已存在】
- 目录 `webchat/` 为 npm monorepo，包含 `packages/webchat-core`、`packages/webchat-ui`、`packages/webchat-demo`。
- core 提供会话持久化、SSE/自定义 header fetch 与状态机能力（`webchat-core/src/sessionManager.ts:6`、`sse.ts:6`、`stateMachine.ts:6`）。
- ui 提供 React Chat 组件与 AG-UI 事件桥接（`webchat-ui/src/Chat.tsx:43`、`agui.ts:47`），支持 Vite library/UMD 构建。
- demo 为 Next 入口（`webchat-demo/app/page.tsx:9`）。

## 风险 / 待确认
- web 模块按 `NEXTAPI_INSTALL_APP` 启用已实际落地【已实现】：运行期解析该配置（为空时回退到目录发现）；工作区裁剪须通过显式生成流程执行，普通构建不会自动改变工作区范围。其与后端 `INSTALL_APPS` 的对齐/同步策略【待确认】。

> 证据来源：web/src/app/(core)/api/_utils/installApps.ts:23、web/scripts/generate-workspace.js:69-78、web/package.json:13-15　|　同步基线：d2769559　|　【已实现】
- mobile 仅暴露会话+工作台，其余模块是否规划【待确认】。

## 2026-07-01 Code-ARD 校准
- `[frontend#20260701-030]` 补录 webchat monorepo、Core/UI/Demo、会话持久化、SSE、自定义 header fetch、状态机、AG-UI 事件桥接、UMD 构建和 Next demo 入口。

## 证据来源
`web/src/{app,utils/request.ts,constants/authOptions.ts,lib/auth.ts,context/*,locales/*}`、`web/src/app/api/wechat-popup-login/route.ts`、`web/src/app/(core)/api/{proxy/[...path]/route.ts,_utils/installApps.ts,locales,markdown,menu,auth,json,versions,mlops}`、`web/src/app/alarm/{constants/menu.json,api/settings.ts,(pages)/settings/*}`、`web/src/app/system-manager/{api/settings/index.ts,(pages)/settings/network-whitelist/page.tsx}`、`web/src/app/ops-analysis/{api/{screen.ts,report.ts,networkStatusTopology.ts},(pages)/view/{screen,report}}`、`web/src/app/monitor/{api/integration.ts,(pages)/integration/asset/viewRoute.ts}`、`web/scripts/{generate-workspace.js,generate-tsconfig.js}`、`web/{Dockerfile,.env.example,next.config.mjs}`、`mobile/src/{app,utils/{tauriApiProxy,secureStorage}.ts,context/auth.tsx}`、`mobile/src/app/conversation/hooks/useSpeechRecognition.ts`、`mobile/src-tauri/{src/api_proxy.rs,tauri.conf.json}`、`mobile/next.config.ts`、`webchat/{package.json:2,7,packages/webchat-core/package.json:2,packages/webchat-core/src/{sessionManager.ts:6,sse.ts:6,stateMachine.ts:6},packages/webchat-ui/package.json:2,packages/webchat-ui/src/{Chat.tsx:43,agui.ts:47},packages/webchat-demo/package.json:2,packages/webchat-demo/app/page.tsx:9}`。
