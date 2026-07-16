# Task 3 实现报告：节点同步配置与全局执行权限、健康合同

## 结论

已按 Task 3 brief 完成最小范围实现：`task` 与 `config` 两条兼容路由按 HTTP 方法统一分派权限，GET 仅需 View、PUT 必须 Execute；`run_sync` 与 `run_collect` 除 Execute 外必须为平台超级管理员；配置响应增加稳定的五字段 `health` 合同；间隔限制为 1..1440；同步关闭且自动采集开启时允许保存，但节点配置健康状态持久化为 `waiting_sync`。

未实施 Task 4 系统查询、Task 7 节点配置下发补偿或 Task 8 执行状态机。

## TDD 证据

### RED

先新增 `server/apps/cmdb/tests/test_node_mgmt_sync_views.py`，覆盖：

- `task` / `config` 两条 URL 的 GET/PUT 权限矩阵；
- 普通 Execute 用户不能发起两类全局执行，且服务不被调用；
- 超级管理员可发起全局执行；
- latest/display/detail 只接受 View；
- `health` 精确五字段合同；
- 两个 interval 字段的 1..1440 边界和 API 400；
- sync 关闭、collect 开启时 `waiting_sync`。

有效 RED 命令使用 SQLite 内存库隔离本机 `.env`，结果为 **12 failed / 5 passed**。失败均对应缺失行为：PUT 仍要求 View、普通 Execute 可执行全局任务、无嵌套 health、无区间校验、健康仍为 reconciling。

### GREEN

同一聚焦测试最终结果：**18 passed**。

## 实现说明

### 权限

- `task` action 不直接绑定固定权限，按 GET/PUT 分派到 `_get_task` / `_update_task`。
- 两个 helper 分别使用现有函数装饰器 `HasPermission("auto_collection-View")` 与 `HasPermission("auto_collection-Execute")`。
- `config` 兼容 action 复用同一分派函数，不再叠加 View 装饰器，因此没有双重或错误权限。
- `run_sync` / `run_collect` 保留 Execute 装饰器，并在方法体入口检查 `request.user.is_superuser`；非超管稳定返回 403 和固定中文消息。
- 未修改全局 `HasPermission`。

### 配置与健康合同

- service 在写库前统一解析并校验 `sync_interval_minutes` / `collect_interval_minutes`，仅接受 1..1440；API 将校验失败稳定映射为 400。
- `serialize_task` 保留既有扁平字段以避免破坏当前消费者，并新增：
  - `schedule_status`
  - `node_config_status`
  - `last_reconciled_at`
  - `reason_code`
  - `message`
- `message` 只读取已持久化、由 reconciler 脱敏后的 `reconcile_error_message`。
- sync 关闭且 collect 开启时写入 `waiting_sync`，并禁止该次配置更新触发节点参数下发；后续恢复下发仍由 Task 7 处理。
- 首次 GET 仍调用 `get_task_payload(reconcile=True)`，Task 2 首次对账未被权限重构破坏。

仓库中不存在 `server/apps/cmdb/serializers/node_mgmt_sync.py`；本任务没有创建空壳 serializer，而是在真实写入口 `NodeMgmtSyncService.update_task` 做最小集中校验，并由 View 映射 400。

## 验证

- 聚焦权限/健康：**18 passed**。
- Task 3 + Task 2 reconciler + helpers + resilience + models：**67 passed**。
- 最终生产新增可执行行覆盖率：**91.18%（31/34）**；其中 View 新增 16/16、Service 新增 15/18。
- `git diff --check`：通过。
- black：View 与新增测试通过；未对历史 service 做全文件格式化。
- isort：三个触及 Python 文件通过。
- flake8：排除 service 在 HEAD 已存在且本任务未触及的 E125/E231/W503 后通过；未扩 scope 修复历史格式债务。
- `py_compile`：三个触及 Python 文件通过。

## 文件

- 修改 `server/apps/cmdb/views/node_mgmt_sync.py`
- 修改 `server/apps/cmdb/services/node_mgmt_sync_service.py`
- 新增 `server/apps/cmdb/tests/test_node_mgmt_sync_views.py`
- 更新 `.superpowers/sdd/task-3-report.md`

## 自审

- 权限判定发生在服务调用前，拒绝路径测试明确断言服务未执行。
- `config` 与 `task` 共享同一方法分派，避免兼容路由权限漂移。
- 未引入原生 SQL、全局权限框架变更、下发补偿或执行状态机。
- interval 校验发生在 `get_task()` 前，非法请求不会意外创建默认配置。
- health 的字段名与数量由精确字典断言固定，错误摘要不从运行时异常直接拼装。
- 最终 diff 已清除 black 对历史 service 产生的格式噪音，仅保留需求相关代码。

## Concerns

- `node_mgmt_sync_service.py` 的 HEAD 基线仍有三处 E231、两处 W503 和一处 E125；均不在本任务改动行，按最小 diff 原则保留。
- 项目环境未安装 `diff-cover`；覆盖率使用 pytest-cov XML 与 `git diff --unified=0` 交叉计算，结果 91.18%。
- Task 7 实现前，sync 重新开启后 `waiting_sync` 的节点配置补偿不会在本任务中自动下发；这是 brief 明确保留的后续边界。

## Important 审查修复：严格整数 interval 合同

### 问题

初版 `_validate_task_update` 先执行 `int(value)`，因此 JSON `1440.9` / `5.0` 会被截断，`true` 会按 Python `bool` 的整数子类语义变为 `1`，违反 interval 必须是整数分钟的 API 合同。

### RED

先为 `task` 与 `config` 两条真实 PUT action 增加参数化 API 回归，覆盖：

- 拒绝 JSON float：`1440.9`、`5.0`；
- 拒绝 JSON bool：`true`、`false`；
- 拒绝非整数字符串：`"5.0"`、`"five"`；
- 固定既有兼容合同：纯 ASCII 数字字符串 `"5"` 继续接受并序列化为整数 `5`；
- 拒绝响应固定为 HTTP 400、`result=false` 和字段级稳定消息。

RED 命令：

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test \
MINIO_USE_HTTPS=false ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb \
DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -q -o addopts='' -o log_cli=false \
apps/cmdb/tests/test_node_mgmt_sync_views.py \
-k 'non_integer_interval_types or decimal_integer_string'
```

结果：**6 failed / 8 passed / 18 deselected**。失败精确证明两条路由均错误接受 float 与 `true`；`false` 因转成 0、非整数字符串因解析失败已返回 400，纯数字字符串兼容测试通过。

### GREEN

校验现先检查原始 JSON 类型：

- `bool` 显式拒绝；
- float 与其他非 `int` / `str` 类型拒绝；
- 字符串必须同时满足 `isascii()` 与 `isdecimal()`，再转换为 int；
- 最终统一校验 1..1440。

同一定向命令结果：**14 passed / 18 deselected**。

完整回归与覆盖命令在上述环境下执行 `test_node_mgmt_sync_views.py`、`test_node_mgmt_sync_reconciler.py`、`test_node_mgmt_sync_helpers.py`、`test_node_mgmt_sync_resilience.py`、`test_node_mgmt_sync_models.py`，结果：**81 passed**。

本轮生产新增可执行行覆盖率：**100%（7/7）**；由 pytest-cov XML 与相对上一 Task 3 commit 的 `git diff --unified=0` 交叉计算。

静态复验：新增测试 black 通过；service/测试 isort 通过；排除 service 既有 E125/E231/W503 后 flake8 通过；两文件 `py_compile` 通过；`git diff --check` 通过。
