# AGENTS.md

> BK-Lite 工程 Agent 执行手册（基于仓库事实，面向可执行流程）

## 概览

### 技术栈（证据化）
- 后端（`server/`）：Python 3.12 + Django 4.2 + Uvicorn + Celery（`server/pyproject.toml`、`server/Makefile`）
- Web（`web/`）：Next.js 16 + React 19 + TypeScript + Ant Design（`web/package.json`）
- Mobile（`mobile/`）：Next.js 15 + Tauri 2 + TypeScript（`mobile/package.json`、`mobile/src-tauri/tauri.conf.json`）
- WebChat（`webchat/`）：npm monorepo（core/ui/demo），demo 为 Next.js 14（`webchat/package.json`、`webchat/packages/*/package.json`）
- Stargazer（`agents/stargazer/`）：Python 3.12 + Sanic（`agents/stargazer/pyproject.toml`、`agents/stargazer/Makefile`）
- Algorithms（`algorithms/`）：Python 多算法服务（BentoML 形态，`uv` 管理依赖，子服务按 `make serving` / `uv run pytest` 运行）（`algorithms/AGENTS.md`、`algorithms/classify_*_server/`）

### 仓库目录（默认优先级）
- `server/`：Django 主后端
- `web/`：主控制台前端
- `mobile/`：移动端（Next.js + Tauri）
- `webchat/`：聊天组件库与 demo
- `agents/stargazer/`：云资源采集代理
- `algorithms/`：算法服务集合（异常检测/时序/日志/文本/图像/目标检测）
- `deploy/dist/bk-lite-kubernetes-collector/`：K8s 采集器部署模板

### 默认工作目录与选择规则
- 默认在仓库根目录执行只读命令。
- 进入目标模块目录再执行开发命令，避免跨模块污染。
- 只改与任务相关文件，禁止顺手改动和全仓格式化。

## 快速开始

### Server
- 开发：`cd server && make install && make migrate && make dev`
- 测试：`cd server && make test`
- 构建：`docker build -t bklite/server -f server/support-files/release/Dockerfile server`

### Web
- 开发：`cd web && pnpm install && pnpm dev`
- 测试：`cd web && pnpm lint && pnpm type-check`
- 构建：`cd web && pnpm build`

### Mobile
- 开发（浏览器）：`cd mobile && pnpm install && pnpm dev`
- 开发（Tauri）：`cd mobile && pnpm dev:tauri`
- 测试：`cd mobile && pnpm lint && pnpm type-check`
- 构建：`cd mobile && pnpm build` 或 `pnpm build:android`

### WebChat
- 开发：`cd webchat && npm install && npm run dev`
- 测试：`cd webchat && npm run test`（当前仅输出 `No tests configured yet`）
- 构建：`cd webchat && npm run build`

### Stargazer
- 开发：`cd agents/stargazer && make install && make run`
- 测试：`cd agents/stargazer && make lint`
- 构建：`cd agents/stargazer && make build`

### Algorithms
- 开发：`cd algorithms/<service> && make install && make serving`
- 测试：`cd algorithms/<service> && uv run pytest`
- 构建：`cd algorithms/<service> && docker build -t bklite/<service> -f support-files/release/Dockerfile .`

## 环境与配置

### 版本与依赖管理
- Python：`3.12`（`server/.python-version`、`agents/stargazer/.python-version`）
- Node：Web 为 `24`（`web/.nvmrc`），WebChat 要求 `>=18`（`webchat/package.json`）
- Python 依赖：`uv`（`server/Makefile`、`agents/stargazer/Makefile`）
- Web/Mobile 依赖：`pnpm`（`web/package.json` 的 `preinstall` 强制 only-allow pnpm）
- WebChat 依赖：`npm`（`webchat/package.json`）

### 环境变量与模板
- Server 基础模板：`server/envs/.env.example`
- Server 模块模板：`server/support-files/env/.env.cmdb.example`、`.env.opspilot.example`、`.env.system_mgmt.example`
- Web 模板：`web/.env.example`
- Stargazer 模板：`agents/stargazer/.env.example`
- Algorithms 模板：`algorithms/classify_*_server/.env.example`
- K8s 采集器模板：`deploy/dist/bk-lite-kubernetes-collector/secret.env.template`、`secret.yaml.template`

### Secrets 与配置策略（强制）
- 仅使用 `*.example`/`*.template` 提供样例，不提交真实密钥。
- `.env`、`*.keystore`、`keystore.properties` 属于敏感文件，不得入库（见根 `.gitignore` 与 `mobile/.gitignore`）。
- 所有账号密钥（DB/NATS/JWT/NPM_TOKEN）通过部署环境注入，不写入代码和日志。

## 工作流（dev -> test -> build -> release）

### 1) Server（`server/`）
- 入口：
  - dev：`make dev`
  - test：`make test`
  - build：`docker build -t bklite/server -f support-files/release/Dockerfile .`（在 `server/` 目录）
  - release：容器启动执行 `support-files/release/startup.sh`
- 验证标准：
  - dev：`uvicorn ... --port 8001` 启动成功
  - test：`pytest` 退出码为 0
  - build：镜像构建完成
  - release：启动脚本完成 `migrate/createcachetable/collectstatic` 并拉起 `supervisord`
- 常见失败入口：
  - `.env` 缺失 DB/NATS/Redis
  - 迁移冲突（`manage.py makemigrations/migrate`）
  - 镜像构建时 Python 依赖安装失败
- 回滚方式：
  - 代码回滚：`git revert <commit>`
  - 数据库回滚：执行对应 Django 迁移回退（`python manage.py migrate <app> <target_migration>`）
  - 运行回退：回滚到上一个可用镜像 tag 重新部署

### 2) Web（`web/`）
- 入口：
  - dev：`pnpm dev`
  - test：`pnpm lint && pnpm type-check`
  - build：`pnpm build`
  - release：`Dockerfile` 使用 `pnpm run start`
- 验证标准：
  - dev：`http://localhost:3000` 可访问
  - test：lint/type-check 全通过
  - build：`next build --turbo` 成功
  - release：容器内 `pnpm run start` 正常启动
- 常见失败入口：
  - 非 pnpm 安装被 `only-allow` 拦截
  - `.env.local` 或 `NEXTAPI_URL` 配置错误
  - Node 版本与构建环境不一致
- 回滚方式：
  - 回退代码：`git revert <commit>`
  - 清理产物后重建：`pnpm clean && pnpm install && pnpm build`
  - 镜像回退到上一个可用 tag

### 3) Mobile（`mobile/`）
- 入口：
  - dev：`pnpm dev` / `pnpm dev:tauri`
  - test：`pnpm lint && pnpm type-check`
  - build：`pnpm build` / `pnpm build:android` / `pnpm build:aab`
  - release：Android 产物由 `scripts/android-build.mjs` + `src-tauri/tauri.conf.json` 流程生成
- 验证标准：
  - dev：`http://localhost:3001` 可访问
  - dev:tauri：Tauri 窗口可启动并请求后端
  - test：lint/type-check 通过
  - build：APK/AAB 输出到 README 指定目录
- 常见失败入口：
  - 未配置 `keystore.properties` 或 keystore
  - Android SDK/NDK/Java 环境异常
  - 3001 端口冲突
- 回滚方式：
  - 回退代码：`git revert <commit>`
  - 删除构建产物后重打包：`pnpm clean && pnpm build:android-debug`
  - 继续发布时使用上一个可用 APK/AAB

### 4) WebChat（`webchat/`）
- 入口：
  - dev：`npm run dev`
  - test：`npm run test`
  - build：`npm run build`
  - release：`webchat/.github/workflows/build.yml` 的 `publish` job（main 分支 push）
- 验证标准：
  - dev：demo 可访问
  - test：命令执行成功（当前无真实测试）
  - build：core/ui/demo 均构建成功
  - release：workflow publish 步骤执行，`NODE_AUTH_TOKEN` 注入成功
- 常见失败入口：
  - `NPM_TOKEN` 缺失或 npm 权限不足
  - Node 版本不满足（matrix 18/20）
- 回滚方式：
  - 回退代码：`git revert <commit>`
  - npm 包回滚：按 npm 版本策略撤回/升补版本

### 5) Stargazer（`agents/stargazer/`）
- 入口：
  - dev：`make run`
  - test：`make lint`（`pre-commit run --all-files`）
  - build：`make build`
  - release：Docker 产物 `bklite/stargazer`
- 验证标准：
  - dev：`sanic ... --port=8083` 启动成功
  - test：pre-commit 执行成功
  - build：镜像构建完成
  - release：容器启动并可连通 Redis/NATS
- 常见失败入口：
  - Server/Worker Redis 配置不一致（README 明确要求）
  - `.env` 未配置 NATS/Redis
- 回滚方式：
  - 回退代码：`git revert <commit>`
  - 回滚镜像 tag
  - 重新加载上一个稳定 `.env` 配置

### 6) K8s 采集器（`deploy/dist/bk-lite-kubernetes-collector/`）
- 入口：
  - dev/build：无本地编译入口，按清单部署
  - release：`kubectl apply -f bk-lite-metric-collector.yaml` 与 `bk-lite-log-collector.yaml`
- 验证标准：
  - `kubectl get pods/ds/deploy -n bk-lite-collector` 全部健康
- 常见失败入口：
  - `secret.env`/`ca.crt` 未注入或 NATS 参数错误
- 回滚方式：
  - `kubectl delete -f ...` 回退本次部署

## 质量门禁

### 本地门禁（提交前）
- 影响 `server/`：`cd server && make test`
- 影响 `web/`：`cd web && pnpm lint && pnpm type-check`
- 影响 `mobile/`：`cd mobile && pnpm lint && pnpm type-check`
- 影响 `agents/stargazer/`：`cd agents/stargazer && make lint`
- 影响 `webchat/`：`cd webchat && npm run build && npm run test`
- 影响 `algorithms/classify_*_server/`：`cd algorithms/<service> && uv run pytest`

### 自动门禁（仓库已有）
- Git Hook：`.husky/pre-commit` 对 `web/`、`mobile/` 的 staged 变更自动执行 lint/type-check。
- Python pre-commit：`server/.pre-commit-config.yaml` 包含 `black`、`isort`、`flake8`、`check_migrate`、`check_requirements`。
- CI：仅确认到 `webchat/.github/workflows/build.yml`（build + publish）；根仓库无通用 workflow。

## Runbook（常见故障）

1. `git pull --ff-only` 失败：先解决本地分支分叉或未提交变更，再同步。
2. `server make dev` 启动失败：核对 `server/envs/.env.example` 的 DB/NATS/Redis 配置。
3. `server make test` 因迁移失败：先执行 `make migrate`，再排查 `server/scripts/check_migrate/check_migrate.py`。
4. `web pnpm install` 被拒绝：必须使用 pnpm（`preinstall: only-allow pnpm`）。
5. `web build` 内存不足：按 `web/Dockerfile` 使用 `NODE_OPTIONS`，并在本地减少并发任务。
6. `mobile dev:tauri` 无法访问后端：确认 `src-tauri/tauri.conf.json` 的 `devUrl=3001` 且后端可达。
7. `mobile build:android` 签名报错：补齐 `src-tauri/gen/android/keystore.properties` 与 keystore 文件。
8. `webchat publish` 失败：检查 `NPM_TOKEN`、npm 包权限与版本冲突。
9. `stargazer` 无任务消费：确认 Redis/NATS 与 Server/Worker 一致，先起 Worker 再起 Server。
10. K8s 采集器无数据：检查 `secret.env` 的 `CLUSTER_NAME/NATS_*` 与 `ca.crt`。

## Agent 执行规则

- 最小 diff：仅修改需求相关文件和代码块。
- 避免格式化污染：只格式化触及文件，不执行全仓格式化。
- 变更后必验证：至少执行对应模块最小门禁命令。
- 先读再写：先提取证据再形成结论，不凭经验补步骤。
- 不做向后兼容设计：发现旧入口与现状冲突时，直接更新到当前真实入口。
- TODO 策略：无法确认的信息必须写 `TODO:`，并附“确认位置（具体路径+关键词）”。

## TODO（待确认项）

- TODO: 根仓库统一 CI/CD 流程未发现。确认位置：仓库根 `.github/workflows/`、组织级 CI 平台配置。
- TODO: `Readme.md` 引用的 `docs/CONTRIBUTING.md` 与 `deploy/docker-compose/Readme.md` 在仓库中未找到。确认位置：`docs/` 与 `deploy/` 目录维护规范。
- TODO: `docs/overview/source_compile.md`、`docs/overview/installation.md`、`docs/changelog/release.md`、`docs/db/README.md` 当前为空。确认位置：文档负责模块与发布流程。
- TODO: Web 多模块镜像入口在 `web/Makefile` 中指向 `web/support-files/release/*/Dockerfile`，该目录当前不存在。确认位置：`web/Makefile` 对应发布脚本来源。
