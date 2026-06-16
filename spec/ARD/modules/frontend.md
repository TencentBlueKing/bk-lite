# 模块 ARD：前端（web / mobile）

## web —— Next.js 16【已实现/已存在】
- 路径 `web/src/app`，App Router。产品模块目录：`alarm`、`cmdb`、`job`、`log`、`monitor`、`mlops`、`node-manager`、`ops-analysis`、`ops-console`、`opspilot`、`system-manager`（11 个）；另有 `(core)`(认证/布局)、`api`(内部 route handlers，含 proxy/locales/markdown 等)、`no-permission`(无权限页)。
- **认证**：next-auth（JWT，maxAge 86400），`constants/authOptions.ts` + `lib/auth.ts`；Provider：Credentials（`/api/v1/core/api/login/`）、WeChat OAuth。
- **API 通信（两层）**：客户端 `utils/request.ts` axios baseURL=`/api/proxy`，由 **axios 请求拦截器注入 `Authorization: Bearer {token}`**（`utils/request.ts:56`）；route handler `(core)/api/proxy/[...path]/route.ts` 为**透明代理**（不再注入鉴权），转发到 `NEXTAPI_URL/api/v1`；支持 SSE；响应拦截 401→重登、460→强制登出。
- **i18n**：react-intl，`locales/{en,zh}.json`，`next.config.mjs:combineLocales()` 合并模块级语言包。
- **UI**：antd v5 + echarts + @antv/g6/x6（拓扑/图）。
- **构建**：多阶段 Dockerfile（builder→node:24-alpine），多模块 Docker 构建目标。

## mobile —— Next.js 15 + Tauri 2【已实现/已存在】
- 路径 `mobile/src/app`：`login`、`workbench`(+detail)、`conversation`（opspilot 会话）、`search`、`profile`。功能为 web 子集（聚焦 AI 会话 + 工作台）。
- **认证**：直接 token 存储（Tauri Store，`utils/secureStorage.ts`），非 next-auth。
- **API 通信**：Tauri Rust 命令 `api_proxy`/`api_stream_proxy` 绕过 CORS（`utils/tauriApiProxy.ts`），fallback fetch。
- **构建**：`output: 'export'` 静态导出 + Tauri；目标 Android（`build:android*`）、桌面（Windows）。
- UI：antd-mobile v5 + @ant-design/x（聊天）。

## 风险 / 待确认
- web 模块按 `NEXTAPI_INSTALL_APP` 启用，与后端 `INSTALL_APPS` 的对齐策略【待确认】。
- mobile 仅暴露会话+工作台，其余模块是否规划【待确认】。

## 证据来源
`web/src/{app,utils/request.ts,constants/authOptions.ts,lib/auth.ts,context/*,locales/*}`、`web/{Dockerfile,.env.example,next.config.mjs}`、`mobile/src/{app,utils/{tauriApiProxy,secureStorage}.ts,context/auth.tsx}`、`mobile/src-tauri/tauri.conf.json`、`mobile/next.config.ts`。
