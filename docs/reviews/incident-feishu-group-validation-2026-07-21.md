# Incident 飞书协作群验证报告

> 计划日期：2026-07-21
>
> 实际执行日期：2026-07-23（2026-07-24、2026-07-29 在同一 worktree 复跑自动化门禁，见 §3.2、§3.3）
>
> 分支：`codex/incident-feishu-im-group`
>
> 2026-07-29 被测实现提交：`540ccd2f8`

## 1. 最终结论

**Block**

2026-07-29 已把 readiness、51/101 人单批链、三类 ACK 窗口、delivery lease fencing、权限边界、0024/0025 迁移和结构化可观测性纳入最终候选门禁。扩大后的后端统一回归首次运行暴露 5 条旧测试合同/事务隔离失败；修复测试合同和终审发现后，同一 20 文件集合无排除重跑为 357 项全部通过，迁移、Incident 前端合同和功能改动文件 ESLint 也均取得新鲜通过证据，详见 §3.3。真实飞书租户 12 场景仍未执行，且仓库 Web 全量 lint/type-check 存在与本需求无关的既有基线失败。缺少测试租户、测试应用和凭据时，不能把真实闭环写成 Pass，也不能发布该功能。

解除阻断需要：

1. 用户提供专用飞书测试租户/应用，或由用户按 Runbook 在其控制的测试环境输入凭据并执行 12 场景；
2. 提交脱敏后的 BK-Lite 页面、飞书实际结果、BK-Lite request ID、飞书 request ID 和清理记录；
3. Web 全量门禁转绿需仓库维护者修复既有基线（缺失依赖声明等），不属于本需求范围。

## 2. 环境摘要

| 项目 | 实际值 |
|---|---|
| OS | Darwin 24.6.0 arm64 |
| Worktree | `.worktrees/incident-feishu-im-group` |
| Python 运行器 | uv 0.8.16 |
| Web 指定运行时 | Node.js v24.15.0 |
| Shell 默认 Node | v14.16.0，不满足当前 pnpm 要求；所有有效 Node 门禁显式使用 Node 24 |
| 后端测试数据库计划 | SQLite `:memory:`，`INSTALL_APPS=system_mgmt,alerts` |
| Celery 测试配置 | `ENABLE_CELERY=true` |
| 飞书测试租户/应用 | 未提供 |
| 飞书凭据 | 未提供；未写入文件或命令 |

## 3. 本轮新鲜自动化证据

以下结果只描述 2026-07-23 本轮实际执行；未执行的命令不计为通过。

| 门禁 | 命令摘要 | 退出码 | 结果与原始摘要 |
|---|---|---:|---|
| 后端 10 文件完整门禁（沙箱） | `uv run pytest ...10 files... -q`，显式 SQLite/MinIO/SECRET_KEY/Celery 环境 | 2 | **未收集测试**。原文：`failed to open file ~/.cache/uv/sdists-v9/.git: Operation not permitted`。 |
| 后端权限重跑 | 同上，申请既有 `uv run pytest` 受控权限 | 无进程退出码 | **Not Run**。审批系统因当前 Codex usage limit 拒绝启动，并明确禁止绕过；没有测试结果。 |
| 后端最终候选完整门禁 | worktree `.venv/bin/pytest`，显式 SQLite/MinIO/SECRET_KEY/Celery 环境，覆盖第 7 节完整文件集及配置/成员重试新增合同 | 0 | **Pass：262 passed in 38.18s**。 |
| Coverage：成员解析 | `test_incident_im_members_service.py`，`--cov=...members --cov-fail-under=75` | 0 | **Pass：11 passed，95%**。 |
| Coverage：Delivery/Outbox | `test_incident_im_delivery_*_service.py test_outbox.py`，两个核心模块，门槛 75% | 0 | **Pass：71 passed；delivery 93%、outbox 98%、合计 94%**。 |
| `makemigrations --check --dry-run` | worktree `.venv/bin/python`，显式 SQLite、`INSTALL_APPS=system_mgmt,alerts` | 0 | **Pass：No changes detected**。 |
| `sqlmigrate alerts 0022/0023` | 检查普通唯一约束和 `last_reconcile_attempt_at` | 0 | **Pass**：`0022` 生成 `UNIQUE (incident_id, active_slot)`；`0023` 生成 nullable `last_reconcile_attempt_at`。 |
| Web 计划合同命令首次尝试 | Node 24，`pnpm exec tsx scripts/incident-im-group-ui-test.ts` | 1 | pnpm 在非 TTY 中要求重建 `node_modules`：`ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`。 |
| Web 依赖重建尝试 | `CI=true` 后重试 | 130（人工终止） | pnpm 尝试下载 1583 个包，访问 `registry.npmmirror.com` 持续 `EPERM`；未把依赖失败记为测试失败或通过。 |
| Incident UI 合同 | Node 24，使用主 checkout 现有同项目依赖直接加载 tsx loader，执行同一脚本 | 0 | **Pass**。脚本无输出，包含本功能 changed-file TypeScript diagnostics、状态、API、交互和 i18n 合同。执行后已移除临时依赖链接，未改主 checkout 依赖或 lock。 |
| Focused ESLint | Node 24，显式列出本功能 13 个 TS/TSX 文件 | 0 | **Pass with one ignored-file warning**。业务源文件无 error；`scripts/incident-im-group-ui-test.ts` 被仓库 ESLint 默认忽略。 |
| Web 全量 ESLint | Node 24，`eslint . --ext .js,.jsx,.ts,.tsx` | 1 | **Baseline Fail**：47 errors、3 warnings，均不在本功能 13 个改动文件。代表性错误：CMDB unused var、monitor/ops-analysis indent、opspilot unused import、既有 Storybook `no-renderer-packages`。 |
| `pnpm type-check` 计划命令 | Node 24，`pnpm type-check` | 1 | pnpm 依赖状态检查再次要求重建 `node_modules`，原文同 `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`；未进入 tsc。 |
| 直接全量 tsc 诊断 | Node 24，现有依赖，`tsc -p tsconfig.lint.json --noEmit` | 2 | **Baseline Fail**：缺少 `react-activation`；`matchRule.tsx` 的 `MatchRuleValue` 不兼容；`locale.tsx` 出现 React 18/19 `ReactNode` 冲突。Incident 合同脚本的 changed-file diagnostics 已单独通过。 |
| Diff whitespace | `git diff --check`（写文档前） | 0 | Pass；提交前将再次执行。 |

### 3.1 与此前任务级证据的区别

以下内容来自本分支 `.superpowers/sdd/progress.md` 的既有任务记录，**不是本轮重跑结果**，不能替代 Task 11 完整门禁：

- Task 7：Task 1–7 regression 202 passed，核心覆盖率 93.89%；
- Task 8：六文件 regression 155 passed，Black/isort/Flake8 clean；
- Task 9：前端 behavior/type contract 与 ESLint clean；
- Task 10：前端 UI behavior/type contract 与 ESLint clean。

最终候选已使用 worktree 现有 `.venv` 取得 262 项后端回归、两组 coverage 与迁移门禁的新鲜 Pass；上述历史数字仍仅用于解释任务过程，不替代本轮结果。

### 3.2 复跑：2026-07-24（Claude Code，本机非沙箱）

本轮在本机（同一 worktree、HEAD `7608ed326`、Node v24.15.0、pnpm 11.5.2）新鲜重跑全部自动化门禁，目的：解除 VAL-IM-002 的依赖阻断假设并复核上轮结论。

| 门禁 | 命令摘要 | 退出码 | 结果 |
|---|---|---:|---|
| 后端完整回归 | worktree `.venv/bin/pytest`，同 §7 环境与文件集（含配置/成员重试合同） | 0 | **Pass：262 passed in 37.21s**。 |
| Coverage：成员解析 | `members/models` 测试 + `--cov=service/incident_im` | 0 | **Pass：members.py 98%**。 |
| Coverage：Delivery | delivery/outbox 测试 + 同上 | 0 | **Pass：delivery.py 93%**（与上轮 93%/94% 一致）。 |
| `makemigrations --check --dry-run` | 同 §7 环境 | 0 | **Pass：No changes detected**。 |
| `sqlmigrate alerts 0022/0023` | 同 §7 环境 | 0 | **Pass**，SQL 正常生成。 |
| Web 依赖安装 | `CI=true pnpm install --frozen-lockfile` | 0 | **Pass**：lock 一致可装；VAL-IM-002 解除，证明上轮失败是沙箱 `EPERM` 而非依赖问题。 |
| Incident UI 合同 | `node_modules/.bin/tsx scripts/incident-im-group-ui-test.ts`（本 worktree 自己的依赖，非借用主 checkout） | 0 | **Pass**：94 条断言全过（脚本以断言失败即非零退出，无输出为通过）。 |
| Focused ESLint | 本功能 10 个 TS/TSX 源文件 + API/types/入口 | 0 | **Pass：0 errors**。 |
| Web 全量 ESLint | `eslint . --ext .js,.jsx,.ts,.tsx` | 1 | **Baseline Fail：47 errors、3 warnings**，与上轮完全一致；分布：`src/stories` 31、cmdb/monitor/ops-analysis/opspilot 各若干，**无一在本功能文件**。 |
| 全量 tsc | `tsc -p tsconfig.lint.json --noEmit` | 2 | **Baseline Fail**，本功能文件零错误；基线错误详见 VAL-IM-003。 |

复跑副产物：pytest 生成的 `server/:memory:` 临时文件已移至 `/tmp`，工作区保持干净。

**结论变化**：VAL-IM-002（Web 依赖阻断）Resolved；发布阻断仅剩 VAL-IM-004（真实飞书 12 场景）。VAL-IM-003 维持 Baseline 豁免。

### 3.3 复跑：2026-07-29（最终加固候选）

本轮最终在 worktree HEAD `540ccd2f8`、Node v24.15.0、pnpm 11.5.2 上执行。所有后端命令显式设置测试 `SECRET_KEY`、SQLite `:memory:`、`INSTALL_APPS=system_mgmt,alerts` 和 `ENABLE_CELERY=true`。当前进程环境及仓库安全配置入口均未发现真实飞书测试凭据；检查未读取用户主目录敏感文件，也未输出任何环境变量值。

| 门禁 | 退出码 | 新鲜结果 |
|---|---:|---|
| 后端最终 20 文件统一回归 | 0 | **Pass：357 passed in 47.82s**。终审新增生命周期提交后事件与回滚合同；同一集合无排除重跑全部通过。 |
| Coverage：成员解析 | 0 | **Pass：18 passed；members.py 95%**。 |
| Coverage：Delivery/Outbox | 0 | **Pass：109 passed；delivery.py 94%、outbox.py 98%、合计 95%**，无 deselect。 |
| Coverage：可观测性 | 0 | **Pass：69 passed；observability.py 100%**。 |
| `makemigrations --check --dry-run` | 0 | **Pass：No changes detected**。 |
| `sqlmigrate alerts 0022–0025` | 0 | **Pass**：生成跨库 active slot 普通唯一约束、nullable reconcile 游标、3 个 `varchar(150)` 审计字段、nullable delivery lease 和 36 字符 fencing token。 |
| Web 依赖状态 | 0 | **Pass**：worktree 自有 `tsx`、`eslint`、`tsc` 均可执行，无需借用主 checkout 依赖。 |
| Incident UI 合同 | 0 | **Pass**：105 条断言通过，覆盖统一更多操作组件的复用、受控关闭和原生 MenuItem 键盘/禁用语义。沙箱内 pnpm 依赖重检受环境阻断后，直接使用 worktree 已安装的 `tsx` 运行同一脚本通过。 |
| Focused ESLint | 0 | **Pass**：本功能 12 个 TS/TSX 业务文件 0 errors。 |
| Web 全量 ESLint | 1 | **Baseline Fail：47 errors、3 warnings**，与 2026-07-24 一致；本功能文件 0 errors。 |
| 直接全量 tsc | 2 | **Baseline Fail**：缺 `react-activation`、DND、`vitest` 依赖声明及既有类型冲突；本功能文件无错误。 |

自动化最终结论为 **Pass with baseline waiver**：本功能后端、覆盖率、迁移、UI 合同及 focused ESLint 全部通过；仓库全量 Web 基线继续按 VAL-IM-003 豁免。真实租户 VAL-IM-004 仍是独立发布阻断，因此整体验证结论保持 **Block**。

#### 3.3.1 本轮纳入门禁的修复项

- 管理权限：前端动作矩阵与后端写接口统一要求当前 operator 且具备 `Incidents-Edit`，成员重试按钮具备 loading/disabled 防重；
- 用户与审计边界：群主用户名按实际映射用户模型限制为 100 字符，认证操作人审计字段支持 150 字符；
- readiness：不再以“获取 token 成功”代表可用；必须验证应用权限、机器人启用状态和运行时 capability 状态，不可用通道从 options 排除；
- 可靠投递：add-members 每个 Outbox 最多一次、每批最多 50 人，51/101 人通过链式 Outbox 串行推进；delivery lease token 阻止旧 worker 越权外呼或覆盖新终态；
- ACK 丢失：自动化覆盖 create、summary 和 add-members 三类重投窗口，关闭、暂停、解绑和过期 worker 不能越过最新状态；create/summary 使用稳定 UUID，add-members 没有飞书原生幂等键，外部成功但首个本地成员事实提交前硬崩溃仍可能重复外呼，其“已在群”真实返回及 Provider 分类必须在租户场景 5 验证，不能仅凭自动化宣称完整幂等；
- 可观测性：Provider 外呼耗时/结果/错误码/request ID、业务结果计数、对账状态与 Outbox backlog 均进入脱敏结构化日志；日志失败不阻断业务；
- 终审边界：飞书响应 request ID 在日志正文和结构化字段中统一转义 CR/LF/tab/backslash 并限长；手工暂停/恢复仅在事务提交后记录成功事件，回滚不留虚假成功事实；
- 前端组件治理：Incident 群卡片与协作时间线共同复用 `MoreActionsDropdown`；菜单项使用 Ant 原生 `MenuItem` 交互、权限禁用和键盘语义，动作触发时显式关闭浮层；
- 数据库迁移：0022–0025 覆盖跨 PostgreSQL/MySQL/SQLite 的 active slot 唯一约束、调度游标、审计字段长度和 delivery lease。

## 4. 十二个真实飞书场景

本轮没有专用飞书测试租户、测试应用、2 名已映射 operator、1 名已映射 collaborator、1 名未映射 collaborator，也没有由用户在系统管理 UI 输入的凭据。因此下表全部为 **Not Run**，没有伪造 request ID、chat ID、截图或清理结果。

| # | 场景 | 结果 | BK-Lite 页面证据 | 飞书实际证据 | Request ID | 备注 |
|---:|---|---|---|---|---|---|
| 1 | 用户同步与预览 | Not Run | 无 | 无 | 无 | 缺测试租户/应用/用户 |
| 2 | 单次建群 | Not Run | 无 | 无 | 无 | 缺测试通道与凭据 |
| 3 | 部分映射 | Not Run | 无 | 无 | 无 | 缺 mapped/unmapped 测试用户 |
| 4 | Incident 摘要 | Not Run | 无 | 无 | 无 | 未创建测试群 |
| 5 | 重复提交及 create/summary/add-members 三种 ACK 丢失重投 | Not Run | 无 | 无 | 无 | 未创建 binding/Outbox |
| 6 | 补齐映射自动入群 | Not Run | 无 | 无 | 无 | 缺可修改测试映射 |
| 7 | 新增协作人自动入群 | Not Run | 无 | 无 | 无 | 缺测试群与额外测试用户 |
| 8 | 移除人员不退群 | Not Run | 无 | 无 | 无 | 缺测试群 |
| 9 | Incident 关闭/重开 | Not Run | 无 | 无 | 无 | 缺测试群 |
| 10 | 手工暂停/恢复 | Not Run | 无 | 无 | 无 | 缺测试群 |
| 11 | 权限/非法用户/网络失败重试 | Not Run | 无 | 无 | 无 | 缺非 operator、测试故障注入环境 |
| 12 | 解绑保留群并允许新绑定 | Not Run | 无 | 无 | 无 | 缺测试群与 binding |

## 5. 发现的问题与阻断

### VAL-IM-001：uv 启动受限（已由 worktree `.venv` 完成等价门禁）

- 严重度：Resolved environment issue
- 证据：uv 读取 `~/.cache/uv/sdists-v9/.git` 返回 `Operation not permitted`；随后使用仓库 worktree 已存在、未下载依赖的 `.venv` 执行相同 pytest、coverage 和 Django migration 门禁。
- 结果：后端 262 项、两组 coverage、迁移漂移和 SQL 生成均已通过，不再作为发布阻断。

### VAL-IM-002：Web 依赖状态不完整且沙箱无法下载

- 严重度：Resolved（2026-07-24）
- 证据：2026-07-24 本机 `CI=true pnpm install --frozen-lockfile` 退出码 0，lock 一致；证实 2026-07-23 的 `EPERM` 是 Codex 沙箱网络限制，非仓库依赖问题。
- 备注：pnpm 对 `pnpm exec` 的依赖状态检查会把 ignored-builds 提示视为失败，本机执行 tsx 时直接使用 `node_modules/.bin/tsx`，语义等价。

### VAL-IM-003：仓库 Web 全量 lint/type-check 基线失败

- 严重度：Baseline（维护者已决定：只记录豁免，不在本需求内修复无关文件）
- 证据（2026-07-24 复核）：全量 ESLint 47 errors/3 warnings，分布 `src/stories`（31）、cmdb、monitor、ops-analysis、opspilot，无一落在本功能 16 个改动文件；全量 tsc 错误全部为基线：
  - `react-activation`、`@dnd-kit/core`、`@dnd-kit/sortable`、`@dnd-kit/utilities`、`vitest` 被源码 import 但**未在 `web/package.json` 声明**（`pnpm install --frozen-lockfile` 后仍缺失，坐实为仓库基线缺陷而非安装问题），涉及 `incidents/page.tsx`、`layout.tsx`、`correlationRules/operateModal.tsx`、`alarm/context/common.tsx`、`sectionMarkdown.test.ts`；
  - `settings/matchRule.tsx` 的 `MatchRuleValue` 与 `ValueType` 不兼容；
  - `src/context/locale.tsx` 的 React 18/19 `ReactNode` 类型冲突。
- 影响：全量 Web 门禁不能为 Pass；本功能 focused 合同、ESLint、tsc 诊断均独立通过。
- 处理：由仓库维护者另行修复基线（补依赖声明/类型收敛）；本任务未修改无关文件。

### VAL-IM-004：真实飞书闭环未执行

- 严重度：Blocker
- 证据：12 场景全部 Not Run。
- 影响：无法证明真实权限、群成员、消息幂等、暂停/解绑和飞书 request ID 行为。
- 解除：用户按 Runbook 准备专用测试租户并执行全部场景。

## 6. 测试对象与清理结果

| 对象 | 本轮创建 | 清理结果 |
|---|---:|---|
| 飞书应用/凭据 | 否 | 无需清理 |
| 飞书测试群 | 否 | 无需清理 |
| BK-Lite IntegrationInstance/Channel | 否 | 无需清理 |
| Incident/binding/member/Outbox | 否 | 无需清理 |
| 临时 Web 依赖链接 | 是 | 已移除；主 checkout `node_modules` 与 lock 未修改 |
| pnpm 未完成重建目录 | 是 | 已恢复为 worktree 的忽略目录，不进入 Git |
| pytest `server/:memory:` 临时文件（2026-07-24） | 是 | 已移至 `/tmp`，不进入 Git |
| worktree `web/node_modules`（2026-07-24 按 lock 安装） | 是 | Git 忽略目录，不进入提交 |

本轮没有残留外部测试对象。由于真实场景未执行，“无需清理”不等于真实租户清理已验证。

## 7. 待执行命令

在具备正常 uv 和 Node 24 依赖的环境执行：

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test \
MINIO_USE_HTTPS=false SECRET_KEY=task11-validation ENABLE_CELERY=true \
INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: \
uv run pytest -o addopts='' --nomigrations \
  apps/system_mgmt/tests/test_feishu_im_group_provider_pure.py \
  apps/system_mgmt/tests/test_im_group_service.py \
  apps/system_mgmt/tests/test_runtime_service.py \
  apps/system_mgmt/tests/test_im_notification_viewset.py \
  apps/alerts/tests/test_incident_im_models_service.py \
  apps/alerts/tests/test_incident_im_members_service.py \
  apps/alerts/tests/test_incident_im_group_*_views.py apps/alerts/tests/test_incident_im_group_create_service.py \
  apps/alerts/tests/test_incident_im_delivery_*_service.py \
  apps/alerts/tests/test_incident_im_add_members_outbox_batches.py \
  apps/alerts/tests/test_incident_im_reconcile_service.py apps/alerts/tests/test_incident_im_lifecycle_service.py \
  apps/alerts/tests/test_incident_im_observability.py \
  apps/alerts/tests/test_outbox.py \
  apps/alerts/tests/test_incident_operator.py -q

MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test \
MINIO_USE_HTTPS=false SECRET_KEY=task11-validation ENABLE_CELERY=true \
INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: \
uv run python manage.py makemigrations --check --dry-run

MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test \
MINIO_USE_HTTPS=false SECRET_KEY=task11-validation ENABLE_CELERY=true \
INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: \
uv run python manage.py sqlmigrate alerts 0022

MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test \
MINIO_USE_HTTPS=false SECRET_KEY=task11-validation ENABLE_CELERY=true \
INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: \
uv run python manage.py sqlmigrate alerts 0023

MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test \
MINIO_USE_HTTPS=false SECRET_KEY=task11-validation ENABLE_CELERY=true \
INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: \
uv run python manage.py sqlmigrate alerts 0024

MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test \
MINIO_USE_HTTPS=false SECRET_KEY=task11-validation ENABLE_CELERY=true \
INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: \
uv run python manage.py sqlmigrate alerts 0025

cd ../web
PATH=/path/to/node-v24/bin:$PATH pnpm exec tsx scripts/incident-im-group-ui-test.ts
PATH=/path/to/node-v24/bin:$PATH pnpm lint
PATH=/path/to/node-v24/bin:$PATH pnpm type-check
```

随后按 [真实验证 Runbook](../validation/incident-feishu-group-runbook.md) 完成 12 场景，将每行 Not Run 替换为真实结果和脱敏证据。只有自动化门禁与 12 场景全部 Pass、无阻断缺陷且清理完成后，最终结论才可改为 `Pass`。
