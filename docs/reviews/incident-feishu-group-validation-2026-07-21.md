# Incident 飞书协作群验证报告

> 计划日期：2026-07-21
>
> 实际执行日期：2026-07-23
>
> 分支：`codex/incident-feishu-im-group`
>
> 被测实现提交：`6753af0e9`（包含规格边界、测试结构和 `WEB_BASE_URL` 失败关闭收口）

## 1. 最终结论

**Block**

本轮取得了 Incident 前端合同测试、功能改动文件 ESLint、后端 247 项完整回归、覆盖率和迁移门禁的新鲜通过证据；但真实飞书租户 12 场景仍未完成，Web 全量 lint/type-check 也被仓库依赖与既有基线错误阻断。缺少测试租户、测试应用和凭据时，不能把真实闭环写成 Pass，也不能发布该功能。

解除阻断至少需要：

1. 恢复与 `web/pnpm-lock.yaml` 一致的 Node 24 依赖，重跑 `pnpm lint`、`pnpm type-check`；
2. 用户提供专用飞书测试租户/应用，或由用户按 Runbook 在其控制的测试环境输入凭据并执行 12 场景；
3. 提交脱敏后的 BK-Lite 页面、飞书实际结果、BK-Lite request ID、飞书 request ID 和清理记录。

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
| 后端最终候选完整门禁 | worktree `.venv/bin/pytest`，显式 SQLite/MinIO/SECRET_KEY/Celery 环境，覆盖第 7 节完整文件集 | 0 | **Pass：247 passed in 36.38s**。 |
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

最终候选已使用 worktree 现有 `.venv` 取得 247 项后端回归、两组 coverage 与迁移门禁的新鲜 Pass；上述历史数字仍仅用于解释任务过程，不替代本轮结果。

## 4. 十二个真实飞书场景

本轮没有专用飞书测试租户、测试应用、2 名已映射 operator、1 名已映射 collaborator、1 名未映射 collaborator，也没有由用户在系统管理 UI 输入的凭据。因此下表全部为 **Not Run**，没有伪造 request ID、chat ID、截图或清理结果。

| # | 场景 | 结果 | BK-Lite 页面证据 | 飞书实际证据 | Request ID | 备注 |
|---:|---|---|---|---|---|---|
| 1 | 用户同步与预览 | Not Run | 无 | 无 | 无 | 缺测试租户/应用/用户 |
| 2 | 单次建群 | Not Run | 无 | 无 | 无 | 缺测试通道与凭据 |
| 3 | 部分映射 | Not Run | 无 | 无 | 无 | 缺 mapped/unmapped 测试用户 |
| 4 | Incident 摘要 | Not Run | 无 | 无 | 无 | 未创建测试群 |
| 5 | 重复提交/任务重投 | Not Run | 无 | 无 | 无 | 未创建 binding/Outbox |
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
- 结果：后端 247 项、两组 coverage、迁移漂移和 SQL 生成均已通过，不再作为发布阻断。

### VAL-IM-002：Web 依赖状态不完整且沙箱无法下载

- 严重度：Blocker（完整 Web 门禁证据缺失）
- 证据：pnpm 非 TTY 依赖重建中止；CI 重试访问 `registry.npmmirror.com` 返回 `EPERM`。
- 影响：计划形式的 `pnpm lint`/`pnpm type-check` 无法在本 worktree 正常启动。
- 解除：按 lockfile 预装依赖，并确保 Node 24 与 pnpm 使用一致。

### VAL-IM-003：仓库 Web 全量 lint/type-check 基线失败

- 严重度：Baseline
- 证据：全量 ESLint 47 errors/3 warnings；直接 tsc 返回 5 类错误，包括缺失 `react-activation` 和 React 18/19 类型冲突。
- 影响：全量 Web 门禁不能为 Pass；focused Incident 合同和 lint 独立通过。
- 处理：由仓库维护者确认并修复基线，或提供已批准的基线豁免清单；本任务未修改无关文件。

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
  apps/system_mgmt/tests/test_im_notification_viewset.py \
  apps/alerts/tests/test_incident_im_models_service.py \
  apps/alerts/tests/test_incident_im_members_service.py \
  apps/alerts/tests/test_incident_im_group_*_views.py apps/alerts/tests/test_incident_im_group_create_service.py \
  apps/alerts/tests/test_incident_im_delivery_*_service.py \
  apps/alerts/tests/test_incident_im_reconcile_service.py apps/alerts/tests/test_incident_im_lifecycle_service.py \
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

cd ../web
PATH=/path/to/node-v24/bin:$PATH pnpm exec tsx scripts/incident-im-group-ui-test.ts
PATH=/path/to/node-v24/bin:$PATH pnpm lint
PATH=/path/to/node-v24/bin:$PATH pnpm type-check
```

随后按 [真实验证 Runbook](../validation/incident-feishu-group-runbook.md) 完成 12 场景，将每行 Not Run 替换为真实结果和脱敏证据。只有自动化门禁与 12 场景全部 Pass、无阻断缺陷且清理完成后，最终结论才可改为 `Pass`。
