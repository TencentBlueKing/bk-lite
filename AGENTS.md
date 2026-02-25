# AGENTS.md

> BK-Lite 工程 Agent 执行手册（基于仓库现状反向生成）

## 概览

### 技术栈（已确认）
- 后端：Python 3.12 + Django 4.2 + Uvicorn + Celery（`server/pyproject.toml`、`server/Makefile`）
- Web：Next.js 16 + React 19 + TypeScript + Ant Design（`web/package.json`）
- Mobile：Next.js 15 + Tauri 2 + TypeScript（`mobile/package.json`、`mobile/README.md`）
- WebChat：npm monorepo（core/ui/demo）+ Next.js 14 demo + Vite（`webchat/package.json`、`webchat/packages/*/package.json`）
- Stargazer：Python 3.12 + Sanic（`agents/stargazer/pyproject.toml`、`agents/stargazer/Makefile`）

### 仓库目录（按开发优先级）
- `server/`：Django 主后端
- `web/`：主 Web 控制台
- `mobile/`：移动端（Tauri）
- `webchat/`：独立 WebChat 库与 demo
- `agents/stargazer/`：采集代理服务
- `deploy/dist/bk-lite-kubernetes-collector/`：K8s 采集器 YAML 与 secret 模板

### 默认工作目录与选择规则
- 未特别说明时，默认在仓库根目录执行只读命令。
- 改动某模块时先 `cd` 到该模块目录再执行命令，避免跨模块依赖污染。
- 只修改目标模块，禁止“顺手”全仓格式化。

## 快速开始

### Server（`server/`）
- 入口：`make install` → `make migrate` → `make dev`
- 验证：访问 `http://localhost:8001`；进程命令应为 `uvicorn ... --port 8001`
- 常见失败入口：数据库/NATS/Redis 未配置，见 `server/envs/.env.example`
- 回滚：停止进程，回退本次变更并重新执行 `make migrate`

### Web（`web/`）
- 入口：`pnpm install` → `pnpm dev`
- 验证：访问 `http://localhost:3000`
- 常见失败入口：`pnpm` 被 `only-allow` 拦截（必须用 pnpm）、`.env.local` 未配置
- 回滚：`git restore --source=HEAD -- web`（仅回滚 web 目录变更）并重新安装依赖

### Mobile（`mobile/`）
- 入口：`pnpm install` → `pnpm dev`（Web 预览）或 `pnpm dev:tauri`（原生能力）
- 验证：Web 端口 `3001`；Tauri 窗口可正常发请求
- 常见失败入口：Tauri/Android 环境不完整、开发端口冲突
- 回滚：停止 dev 进程，回退移动端改动后重启 `pnpm dev`

### WebChat（`webchat/`）
- 入口：`npm install` → `npm run build` → `npm run dev`
- 验证：demo 可启动；core/ui 产物在各自 `dist/`
- 常见失败入口：Node 版本不满足（`>=18`）或 npm 依赖冲突
- 回滚：`npm run clean` 后回退变更并重新构建

### Stargazer（`agents/stargazer/`）
- 入口：`make install` → `make run`
- 验证：服务监听 `8083`
- 常见失败入口：`.env` 中 Redis/NATS 配置不一致
- 回滚：停止服务，回退改动后重启

## 环境与配置

### 版本与包管理
- Python：`3.12`（`server/.python-version`、`agents/stargazer/.python-version`）
- Node：`24`（`web/.nvmrc`）
- 包管理器：
- 后端/代理：`uv`
- 主 Web/Mobile：`pnpm`
- WebChat：`npm`（`webchat/.npmrc` 含 `legacy-peer-deps=true`）

### 环境变量分层
- Server 基础：`server/envs/.env.example`
- Server 模块：`server/support-files/env/.env.cmdb.example`、`.env.opspilot.example`、`.env.system_mgmt.example`
- Web：`web/.env.example`
- K8s 采集器：`deploy/dist/bk-lite-kubernetes-collector/secret.env.template`

### Secrets 策略（强制）
- 仅使用 `*.example` / `*.template` 作为模板，不提交真实密钥。
- NATS、DB、JWT、第三方凭证必须通过部署环境注入。
- 严禁把 token/password 写入代码、日志或提交记录。

## 工作流（dev -> test -> build -> release）

### Server 工作流
- Dev 入口：`cd server && make dev`
- Test 入口：`cd server && make test`（等价 `uv run pytest`）
- Build 入口：`docker build -t bklite/server -f server/support-files/release/Dockerfile server`
- Release 入口：容器启动执行 `server/support-files/release/startup.sh`
- 验证标准：
- dev：`8001` 可访问
- test：`pytest` 退出码 `0`
- build：镜像构建成功
- release：容器内 `migrate/createcachetable/collectstatic` 完成，`supervisord` 拉起
- 常见失败入口：数据库迁移失败、依赖未安装、环境变量缺失
- 回滚方式：回退代码到上一提交并重建镜像；数据库变更需执行反向迁移（若有）

### Web 工作流
- Dev 入口：`cd web && pnpm dev`
- Test 入口：`cd web && pnpm lint && pnpm type-check`
- Build 入口：`cd web && pnpm build`
- Release 入口：`web/Dockerfile`（`pnpm run start`）
- 验证标准：
- dev：`3000` 页面可访问
- test：lint/type-check 通过
- build：`.next` 构建完成
- release：容器 `start` 正常
- 常见失败入口：`NEXTAPI_URL` 配置错误、Node 版本不匹配、pnpm workspace 生成异常
- 回滚方式：回退变更并删除 `.next` 后重建

### Mobile 工作流
- Dev 入口：`cd mobile && pnpm dev` 或 `pnpm dev:tauri`
- Test 入口：`cd mobile && pnpm lint && pnpm type-check`
- Build 入口：`cd mobile && pnpm build` / `pnpm build:android`
- Release 入口：Android 产物由 `scripts/android-build.mjs` 生成
- 验证标准：
- dev：`3001` 正常
- test：lint/type-check 通过
- build：Next/Tauri 构建成功
- release：APK/AAB 生成到 README 指定路径
- 常见失败入口：签名文件缺失、Android NDK/SDK 配置问题、端口占用
- 回滚方式：停止构建，恢复上个可用 tag 并重新打包

### WebChat 工作流
- Dev 入口：`cd webchat && npm run dev`
- Test 入口：`cd webchat && npm run test`（当前仅输出 "No tests configured yet"）
- Build 入口：`cd webchat && npm run build`
- Release 入口：`webchat/.github/workflows/build.yml`（main 分支发布 npm）
- 验证标准：
- dev：demo 启动成功
- test：命令可执行（当前无真实测试）
- build：core/ui/demo 全部构建成功
- release：workflow 的 publish job 执行且 `NPM_TOKEN` 可用
- 常见失败入口：npm 权限、`NPM_TOKEN` 缺失、包版本冲突
- 回滚方式：撤回 npm 版本（按 npm 流程）并回退代码提交

### Stargazer 工作流
- Dev 入口：`cd agents/stargazer && make run`
- Test 入口：`cd agents/stargazer && make lint`
- Build 入口：`cd agents/stargazer && make build`
- Release 入口：Docker 镜像 `bklite/stargazer`
- 验证标准：
- dev：`8083` 监听
- test：pre-commit hooks 全通过
- build：镜像可构建
- release：容器可启动且健康检查正常
- 常见失败入口：Redis/NATS 配置错误、依赖未同步
- 回滚方式：回退镜像 tag 或上个稳定提交

## 质量门禁

### 提交前最小门禁（必须执行）
- 涉及 `web/`：`cd web && pnpm lint && pnpm type-check`
- 涉及 `mobile/`：`cd mobile && pnpm lint && pnpm type-check`
- 涉及 `server/`：`cd server && uv run pytest`
- 涉及 `agents/stargazer/`：`cd agents/stargazer && make lint`

### 自动门禁（已存在）
- Git hooks：`.husky/pre-commit` 会对 `web/` 和 `mobile/` 变更自动执行 lint + type-check。
- Python pre-commit：`server/.pre-commit-config.yaml` 包含 `black`、`isort`、`flake8` 与迁移检查脚本。

### CI/CD 现状
- 仓库根目录未发现通用 GitHub Actions workflow。
- 已发现模块级 CI：`webchat/.github/workflows/build.yml`。
- TODO: 根仓库统一 CI 入口确认；确认位置：组织级 CI 平台配置或仓库设置页面。

## Runbook（常见故障）

1. `git fetch/pull` 失败（代理/网络）：检查 `git config --get-regexp '.*proxy'`，必要时清理代理后重试。
2. `server make dev` 启动但接口 500：先核对 `server/envs/.env.example` 的 DB/NATS/Redis。
3. `server pytest` 失败于迁移：执行 `make migrate`，再看 `server/scripts/check_migrate/` 提示。
4. `web pnpm install` 被拒绝：确认使用 `pnpm`，不要用 npm/yarn（有 `only-allow pnpm`）。
5. `web pnpm build` 内存不足：按 `web/Dockerfile` 思路调整 `NODE_OPTIONS`。
6. `mobile dev:tauri` 无法连后端：检查 Tauri 代理配置与服务端地址。
7. `mobile build:android` 签名报错：补齐 `src-tauri/gen/android/keystore.properties` 与 keystore 文件。
8. `webchat publish` 失败：确认 `NPM_TOKEN`、包版本号与 npm 权限。
9. `stargazer` 启动后无任务消费：确认 Worker 与 Server 的 Redis 配置一致。
10. K8s 采集器部署后无数据：检查 `secret.env` 的 `NATS_*` 与 `ca.crt` 是否正确注入。

## Agent 执行规则

- 最小改动：只改任务相关文件，禁止无关重构。
- 禁止格式化污染：只格式化受影响文件，不跑全仓格式化。
- 变更后必验证：至少执行对应模块的最小门禁命令。
- 先证据后结论：命令、端口、脚本、变量都必须能在仓库定位。
- 不做向后兼容设计：发现失效入口直接修正文档，不保留旧路径说明。
- TODO 策略：任何无法确认的信息写成 `TODO:`，并附“确认位置（文件路径/关键词）”。

## 已识别 TODO（待仓库补齐）

- TODO: `web/Makefile` 引用的 `web/support-files/release/*/Dockerfile` 在仓库中不存在；确认位置：`web/Makefile` 与实际前端发布目录。
- TODO: 根仓库统一 CI 工作流未找到；确认位置：`.github/workflows/` 或外部 CI 系统。
- TODO: `docs/overview/*`、`docs/changelog/release.md`、`docs/db/README.md` 当前为空；确认位置：`docs/` 目录对应文档维护流程。
