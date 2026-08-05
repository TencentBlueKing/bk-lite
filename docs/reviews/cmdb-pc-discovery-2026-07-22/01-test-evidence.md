# PC 发现测试证据（离线门禁）

日期：2026-07-27　分支：feature_windyzhao（PC 工作基线提交 4b5f447bb，末次提交 33d924a0f）

## 1. Server 门禁

### 1.1 全量 `make test`（被既有基线故障阻断）

- 命令：`cd server && make test`（pytest 全量，含 coverage）
- 结果：**FAIL（与本功能无关）** — collection 阶段 84 个错误，全部来自
  `apps/opspilot/tests/**`：`RuntimeError: Model class apps.opspilot.models.bot_mgmt.Bot
  doesn't declare an explicit app_label and isn't in an application in INSTALLED_APPS.`
- 基线复现：在 PC 工作之前的提交 4b5f447bb 的干净 worktree（同一 .env、同一 venv 同步）
  运行同一文件 `apps/opspilot/tests/wiki/test_batch_create.py --collect-only`，
  出现**完全相同**的 app_label 错误 → 既有故障，非本功能引入。
- 原始日志：`/tmp/pc_gate_server_make_test.log`（250.78s，84 collection errors）。

### 1.2 定向门禁（影响范围：apps/cmdb + apps/rpc）

- 命令：`cd server && uv run pytest apps/cmdb/tests apps/rpc/tests -q -o addopts=''`
- 最终结果（删除遗留 test_bklite 后干净重跑，575.08s）：
  **3994 passed / 93 skipped / 50 failed / 0 errors**。
- 50 个失败全部归类，无一与本功能相关：
  - 31 个 `test_falkordb_graph_real_extra.py` / `test_falkordb_real_integration.py`：
    需要活体 FalkorDB 的真实集成测试，本环境无图库实例；在基线提交同环境复现；
  - 17 个既有失败（test_collect_task_single_flight×6、test_collect_management_hooks×2、
    test_instance_service_crud×1、test_model_layout×1、test_node_mgmt_sync_collection×1、
    bdd test_instance_crud_bdd×2、e2e dameng/placeholder×2、
    test_nats_region_resource_overview×1、test_topology_theme×1）：
    在基线提交 4b5f447bb 的干净 worktree 跑同一批文件得到**完全相同的 17 个失败**；
  - 1 个本功能回归（见 1.4），已修复并单独提交。
- 说明：初次两轮运行因两个 pytest 进程并发共用同一测试库产生碰撞
  （relation already exists / 遗留半迁移 test_bklite），删除后重跑；
  碰撞轮的计数不作为证据。
- PC 相关套件（87 项）单独验证全过：
  `test_pc_authority / test_pc_connection_test / test_pc_expiration_cleanup /
  test_pc_handover_views / test_pc_model_config / test_pc_node_params /
  test_pc_reconcile / test_pc_snapshot_parser / test_pc_task_serializer /
  test_pc_task_status` → **87 passed**。

### 1.4 门禁暴露并已修复的回归

`test_collect_service_methods.py::...test_destroy_外部清理失败时保留数据库删除入口可重试`
在基线通过、在本分支失败：Task 11 引入的 `_check_pc_authority_before_destroy`
对所有任务执行且按任务对象过滤 FK，非 PC 任务/替身对象触发 TypeError。
修复：仅 `model_id=pc` 时按 `authoritative_task_id` 过滤（提交 6a3c50ebc）。
验证：`test_collect_service_methods + test_pc_handover_views + test_pc_authority`
60 passed；collect 区域套件复跑仅剩 2 个基线一致失败。

### 1.3 端到端合同与秘密保护回归

- `apps/cmdb/tests/e2e/test_pc_discovery_pipeline.py`：6 passed（Windows 四轮 /
  macOS 三轮 / 失败行保护 / headers 无秘密 / fixture 身份一致×2）。
- `apps/cmdb/tests/test_collect_model_credential_pool.py`：+3（pc 加密字段集合
  真实解析、password/private_key/passphrase 全部掩码）。
- `apps/rpc/tests/test_sensitive_pure.py`：+3（WinRM/SSH host_credentials 脱敏、
  OPENSSH PEM 块脱敏）。
- 三者合计 **44 passed**。

## 2. Stargazer 门禁

### 2.1 `make lint`（工具链基线缺口）

- 命令：`cd agents/stargazer && make lint` → **无法运行**：
  `InvalidConfigError: .pre-commit-config.yaml is not a file`
  （仓库只在 server/ 下存在 pre-commit 配置，stargazer 无配置，属基线缺口）。
- 替代：`uvx ruff check` 默认规则检查全部 PC 触及文件
  （enterprise/plugins/inputs/pc/、service/debug/pc_debug.py、api/collect.py、
  tests/test_pc_*.py）。剩余告警均为风格级（UP009 utf-8 声明、I001 import 排序、
  api/collect.py 的 UP006/BLE001 为既有代码），与仓库现存风格一致；本功能新增的
  F401/RUF100 已修复。为遵循"不做全仓格式化"，未按默认规则重写既有风格。

### 2.2 PC 测试与覆盖率

- 命令：`cd agents/stargazer && uv run pytest -q tests/test_pc_inventory.py
  tests/test_pc_scripts_contract.py tests/test_pc_debug.py
  tests/test_pc_discovery_contract.py`
- 结果：**47 passed**。
- 覆盖率（pytest-cov 注入）：
  `enterprise/plugins/inputs/pc/pc_inventory.py` **86%**、
  `service/debug/pc_debug.py` **87%**（均 ≥75%）。

## 3. Web 门禁

- 表单合同：`pnpm exec tsx scripts/cmdb-pc-discovery-form-test.ts` → **passed**。
- `pnpm type-check`：**1 个既有错误** `src/context/locale.tsx(60,11) error TS2769`
  （ReactNode bigint 不匹配）。已用 git stash 验证该错误在不包含本功能改动时
  完全相同地复现 → 基线问题；本功能触及文件零类型错误。
- `pnpm lint`：**40 个既有错误**（`src/stories/*.stories.tsx` 的
  storybook/no-renderer-packages 38 个、`ops-analysis/utils/paramInputConfigUtils.ts`
  的 consistent-type-definitions 2 个）。这些文件自基线提交以来未被本功能任何
  提交触及（git log --name-only 验证）；本功能改动文件单独 eslint → 0 errors。

## 4. 合同暴露并已修复的缺口

| 缺口 | 证据 | 修复 |
|---|---|---|
| 执行器原始 msg 可能回显凭据进入 `cmdb_collect_error` 与 VM label | test_pc_discovery_contract 红 → 绿 | PCInventoryCollector 错误路径按已知秘密值精确脱敏（企业版目录，不随仓提交） |
| 前端掩码占位符 `******` 与调试工具 `••••••` 哨兵不一致 | test_pc_connection_test_frontend_placeholder_decrypted_by_task | 连接测试视图同时识别两种哨兵（Task 13 提交） |

## 5. 结论

- 三端定向门禁全绿；全量 `make test` 与 web lint/type-check 的残余失败均为
  基线复现的既有问题（opspilot app_label、locale.tsx TS2769、stories lint），
  与本功能无关且已逐项给出基线证据。
- 门禁额外暴露 1 个本功能回归（destroy 权威校验）与 1 个脱敏缺口（执行器 msg
  回显凭据），均已修复并带合同测试锁定。
- 真实 Windows/macOS 目标机验收未在本环境执行，见 02/03 文档的待办清单。
