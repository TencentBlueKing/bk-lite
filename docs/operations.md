# Operations —— 操作详档(命令 / 工作流 / Runbook）

> 从 [AGENTS.md](../AGENTS.md) 提取的明细。AGENTS.md 给「快速开始」,本文给「完整命令 + dev→test→build→release 流程 + 故障 Runbook」。

## 1. 完整命令清单

### Agent 基础工具（OpenSpec / projectmem / CodeGraph）
```bash
scripts/agent-tooling-bootstrap          # 安装/修复 openspec、pjm、codegraph,安装 projectmem hooks,必要时初始化 CodeGraph 索引
scripts/agent-tooling-bootstrap --check  # 只检查,缺工具时失败
scripts/agent-tooling-bootstrap --no-index # 跳过 CodeGraph 索引初始化
```

约定:
- `openspec` 与 `codegraph` 通过 npm 全局包安装:`@fission-ai/openspec`、`@colbymchenry/codegraph`。
- `pjm` 通过 `uv tool install projectmem` 安装;若 `uv` 不存在,脚本会尝试用 `python3 -m pip install --user uv` 补齐。
- Claude / Codex 的 projectmem 与 CodeGraph MCP 不直接引用个人机器绝对路径,统一走 `scripts/projectmem-mcp`、`scripts/codegraph-mcp`。
- Agent 发现团队成员机器缺这些工具时,应先运行 bootstrap,不要继续在半可用状态下执行 OpenSpec、projectmem 或 CodeGraph 流程。

### Server（`server/`，Django）
```bash
make install          # uv sync 安装依赖
make migrate          # makemigrations + migrate + 建缓存表
make dev              # Uvicorn 启动于 :8011（--reload）
make test             # pytest
make test-unit        # 仅 unit marker
make test-bdd         # 仅 bdd marker
make test-fast        # 跳过 slow
make test-app         # 指定 app 测试
make celery           # Celery worker
make celery-beat      # Beat 调度
make start-nats       # NATS 监听
make shell            # IPython shell_plus
make setup-dev-user   # 建 admin/password 超管
make server-init      # batch_init 初始化
make collect-static   # 收集静态文件
make init-buckets     # 初始化 MinIO bucket
```
单测运行:
```bash
cd server
uv run pytest apps/monitor/tests/test_x.py -v
uv run pytest apps/monitor/tests/test_x.py::TestClass::test_method -v
uv run pytest -m unit         # 按 marker
uv run pytest -m "not slow"
```

### Web（`web/`）
```bash
pnpm install   # 强制 pnpm（only-allow）
pnpm dev       # :3000（--turbo）
pnpm build     # 生产构建
pnpm lint      # ESLint
pnpm type-check
pnpm storybook # :6006
```

### Mobile（`mobile/`）
```bash
pnpm dev            # :3001
pnpm dev:tauri      # Tauri 桌面
pnpm build          # Web 产物
pnpm build:android  # Android release
pnpm build:aab      # AAB
```

### WebChat（`webchat/`）/ Stargazer / Algorithms
```bash
cd webchat && npm install && npm run dev|build|test
cd agents/stargazer && make install && make run   # Sanic :8083；make lint / make build
cd algorithms/<svc> && make install && make serving  # BentoML :3000；uv run pytest
```

## 2. 工作流（dev → test → build → release）

### Server
- dev `make dev` → `uvicorn ... --port 8011` 启动成功
- test `make test` → pytest 退出码 0
- build `docker build -t bklite/server -f support-files/release/Dockerfile .`（在 `server/`）
- release 容器执行 `support-files/release/startup.sh`(migrate/createcachetable/collectstatic/supervisord)
- 常见失败:`.env` 缺 DB/NATS/Redis;迁移冲突;依赖安装失败
- 回滚:`git revert` / `manage.py migrate <app> <target>` / 回退镜像 tag

### Web
- dev `pnpm dev`(:3000)/ test `pnpm lint && pnpm type-check` / build `pnpm build`(`next build --turbo`)/ release 镜像 `pnpm run start`
- 常见失败:非 pnpm 被拦;`NEXTAPI_URL` 配错;Node 版本不一致
- 回滚:`git revert` / `pnpm clean && pnpm install && pnpm build` / 回退镜像

### Mobile
- dev `pnpm dev` / `pnpm dev:tauri`;build `pnpm build:android` / `pnpm build:aab`;release 由 `scripts/android-build.mjs` + `src-tauri/tauri.conf.json` 生成
- 常见失败:缺 `keystore.properties`/keystore;Android SDK/NDK/Java 异常;3001 端口冲突

### WebChat
- release:`webchat/.github/workflows/build.yml` 的 publish job(main push);需 `NPM_TOKEN`/`NODE_AUTH_TOKEN`
- 常见失败:token 缺失/权限不足;Node matrix 18/20 不满足

### Stargazer
- dev `make run`(`sanic ... --port=8083`);test `make lint`(pre-commit);build `make build`
- 常见失败:Server/Worker Redis 配置不一致;`.env` 缺 NATS/Redis。**先起 Worker 再起 Server**

### K8s 采集器（`deploy/dist/bk-lite-kubernetes-collector/`）
- release:`kubectl apply -f bk-lite-metric-collector.yaml` / `bk-lite-log-collector.yaml`
- 验证:`kubectl get pods/ds/deploy -n bk-lite-collector` 健康
- 常见失败:`secret.env`/`ca.crt` 未注入或 NATS 参数错

## 3. Algorithms 设计约定（补充,真相源 [algorithms/DESIGN_GUIDE.md](../algorithms/DESIGN_GUIDE.md)）

- 每个算法服务遵循 classifier 模式 + `ModelRegistry` 装饰器注册。
- 训练配置由 `TrainingConfig` 驱动;MLflow 做实验追踪。
- 传统 ML(anomaly/timeseries/log/text):最终训练前 **合并 train+val**。
- 深度学习(image/object_detection):**train/val 分离**(YOLO 要求)。

## 4. 关键环境变量

| 变量 | 说明 |
|------|------|
| `DB_ENGINE` | postgresql(默认)/ mysql / sqlite / dameng / gaussdb / goldendb / oceanbase |
| `DB_NAME/USER/PASSWORD/HOST/PORT` | 数据库连接 |
| `INSTALL_APPS` | 逗号分隔的加载 app(空=全加载) |
| `NEXTAPI_URL` | 前端访问后端的 API 地址 |

模板:`server/envs/.env.example`、`server/support-files/env/*.example`、`web/.env.example`、`agents/stargazer/.env.example`、K8s `secret.*.template`。
> 新增 env 走 `os.getenv` 默认值,不改 `.env.example`(易冲突,见团队约定)。

## 5. Runbook（常见故障）

1. `git pull --ff-only` 失败 → 先解决分叉/未提交变更。
2. `make dev` 启动失败 → 核对 `.env` 的 DB/NATS/Redis。
3. `make test` 因迁移失败 → 先 `make migrate`,再查 `server/scripts/check_migrate/`。
4. `web pnpm install` 被拒 → 必须用 pnpm(`only-allow`)。
5. `web build` 内存不足 → 参考 `web/Dockerfile` 的 `NODE_OPTIONS`,降并发。
6. `mobile dev:tauri` 连不上后端 → 确认 `tauri.conf.json` `devUrl=3001` 且后端可达。
7. `mobile build:android` 签名报错 → 补 `src-tauri/gen/android/keystore.properties` 与 keystore。
8. `webchat publish` 失败 → 检查 `NPM_TOKEN`、npm 权限与版本冲突。
9. `stargazer` 无任务消费 → Redis/NATS 与 Server/Worker 一致,先起 Worker。
10. K8s 采集器无数据 → 检查 `secret.env` 的 `CLUSTER_NAME/NATS_*` 与 `ca.crt`。

## 6. 升级说明 / 集成中心 AD Provider `base_dn` 字段废弃 (2026-07)

- **变更摘要**：集成中心 AD provider 的 `base_dn` 字段已从 manifest、adapter、serializer 与 capability contract 中整体移除；`IntegrationInstance.config.base_dn` 与 `UserSyncSource.business_config.base_dn` 不再被接受。
- **运行时影响（breaking change）**：
  - 旧 API 客户端若仍随 `POST / PATCH` 携带 `config.base_dn` 或 `business_config.base_dn`,`validate_user_sync_contract` 的严格白名单校验会拒绝未知字段,返回 **HTTP 400** `Unsupported user_sync business config fields: base_dn`。
  - 正常前后端协调升级路径安全:新 manifest 驱动的表单已不再渲染 `base_dn` 字段,前端 POST 自然不会带该字段。
- **数据层面**:
  - **无 Django 数据迁移**。`base_dn` 是 `IntegrationInstance.config` / `UserSyncSource.business_config` 这两个 JSONField 里的一个 key,不是 DB 列;升级后存量 JSON 里残留的 `base_dn` 键是「无害的尸体」,**不会有任何代码路径再读它**。
  - 如运维出于节省存储 / 审计可读性考虑需要清理存量 JSON 里的 `base_dn`,由运维另起一次性 `manage.py shell` 任务维护,**不在本变更的契约范围内**。
- **升级动作**:
  - **前端**:升级到移除 `base_dn` 表单项的版本;确认 `web/src/app/system-manager/.../user-sync` 与 i18n 文案不再出现 `catalog/baseDn`。
  - **后端**:升级到 manifest / adapter / serializer / capability contract 一致移除 `base_dn` 读写路径的版本。
  - **第三方客户端**(脚本 / 老版 GUI):停发 `config.base_dn` 与 `business_config.base_dn`,否则请求会被 400 拒绝。
- **回滚**:见 spec §8;短期可借 `git revert` 回滚该 PR;存量 JSON 里残留 `base_dn` 不会因为回滚而「自动恢复成被读取状态」,DB 数据无需特殊处理。
- **关联文档**:`docs/superpowers/specs/2026-07-02-integration-center-ad-base-dn-relocation-spec.md`(spec v0.2)、`docs/superpowers/plans/2026-07-02-integration-center-ad-base-dn-removal-plan.md`(plan v1.2,决定不再做 silent-tolerance)。

> 质量门禁与代码红线见 [QUALITY_SCORE.md](../QUALITY_SCORE.md);回滚与韧性见 [RELIABILITY.md](../RELIABILITY.md)。
