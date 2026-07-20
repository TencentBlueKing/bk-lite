# Task 3 报告：收紧监控直接归属对象和组织分配

> 状态：DONE

## 完成范围

- `MonitorPolicy`、`MonitorCondition`、`MonitorInstance`、`MonitorObjectOrganizationRule` 的列表、详情和写操作统一叠加 `current_team` 数据范围。
- 超级管理员只在当前范围内隐式拥有全部动作权限，不再获得跨组织数据旁路。
- 普通用户仍消费原有对象权限，最终结果为“对象权限 ∩ current_team 数据范围”。
- 实例、策略、条件和组织规则的目标组织改用独立的可分配组织授权；允许把当前可操作对象分配给有权的其他组织，拒绝不可分配组织，超级管理员同样受限。
- 节点监控服务携带统一 `data_scope`，采集配置、实例访问和纳管节点组织均从当前范围派生；后台无请求上下文的既有系统任务语义保持不变。
- 组织规则采用共享对象交集语义，并通过实际绑定实例的监控对象做授权，兼容派生对象规则引用父实例；响应中的组织关联只投影当前数据范围，避免泄露兄弟组织。

## TDD 证据

RED：新增权限守卫测试后，7 个用例按预期失败，覆盖超管跨组织读取/操作、兄弟组织分配和规则绑定实例越权；组织规则响应投影另有 1 个失败用例，节点监控服务超管范围另有 1 个失败用例。

GREEN：实现统一范围后，先后完成核心、兼容和扩大回归；最终命令：

```bash
cd server
uv run --extra dev pytest -o addopts='' \
  apps/monitor/tests/test_monitor_views_extra.py \
  apps/monitor/tests/test_monitor_policy_view_helpers.py \
  apps/monitor/tests/test_monitor_policy_destroy_transaction_4040.py \
  apps/monitor/tests/test_collect_detect_service.py \
  apps/monitor/tests/test_manual_collect_validators.py \
  apps/monitor/tests/test_flow_env_config.py \
  apps/monitor/tests/test_flow_onboarding_service.py \
  apps/monitor/tests/test_monitor_instance_projection.py \
  apps/monitor/tests/test_monitor_permission_business_flows.py \
  apps/monitor/tests/test_monitor_permission_guards.py \
  apps/monitor/tests/test_monitor_instance_view.py \
  apps/monitor/tests/test_monitor_object_view_extra.py \
  apps/monitor/tests/test_node_mgmt_service.py -q
```

结果：`231 passed in 44.75s`。

覆盖率重新生成后，`diff-cover --compare-branch=HEAD --fail-under=75` 结果为 `148` 个差异可执行行、`21` 行未覆盖、差异覆盖率 `85%`。

## 门禁结果

- `python -m py_compile`：通过。
- `isort 5.10.1 --check-only`（生产文件）：通过。
- `flake8 7.1.1`（生产文件）：通过。
- `makemigrations --check --dry-run`：通过，`No changes detected`。
- `git diff --check`：通过。
- 原生 SQL 扫描：未发现 `RawSQL`、`.raw()` 或 `cursor.execute`。
- `black 23.1.0 --check`：仅 `monitor_policy.py` 与 `services/node_mgmt.py` 的既有基线行仍会被格式化；对 `HEAD` 原文件执行相同检查同样失败。本次新增代码均已符合 Black。

## 兼容性修正

- 派生组织规则不再错误地使用子规则对象授权，而是使用绑定父实例的真实监控对象授权。
- `allow_missing=True` 的派生实例仍允许没有落库实例行；已存在的实例行继续强制 current_team 校验。
- 受统一 resolver 影响的旧测试 fixture 补齐 current_team 授权 RPC，并把成功场景数据放入当前组织，不改变原测试意图。

## 文件范围

生产代码仅涉及监控直接归属和节点监控上下文：

- `server/apps/monitor/serializers/monitor_object.py`
- `server/apps/monitor/services/node_mgmt.py`
- `server/apps/monitor/views/monitor_condition.py`
- `server/apps/monitor/views/monitor_instance.py`
- `server/apps/monitor/views/monitor_policy.py`
- `server/apps/monitor/views/node_mgmt.py`
- `server/apps/monitor/views/organization_rule.py`

本任务未修改告警、事件、快照、原始数据和日志模块；它们分别由后续继承权限链任务处理。

## 独立审查修复（2026-07-21）

### 修复内容

- 组织规则持久化 `organizations` 复用 Task 1 的规范正组织 ID 解析；bool、float、前导零、空集合及混合非法快照整行不可授权，不再宽松转换或跳过坏元素。
- `OrganizationRule` 普通 PATCH 未携带 `organizations` 时不再重新校验旧共享组织；PUT 与显式 PATCH 仍严格校验目标组织，绑定实例和源对象操作权限保持不变。
- Policy、Condition、Instance、OrganizationRule 的显式组织写入不再跳过空值；创建、替换、显式 PATCH 与批量设置在数据库、调度任务和服务调用前 fail-closed。实例仅改名称时以 `organizations=None` 保留原关联。
- 修正 DRF `partial_update -> self.update(partial=True)` 的二次进入：Policy、Condition 与 OrganizationRule 的 PATCH 只执行一次组织校验和业务副作用。
- Policy serializer、MonitorObjectService 和 InstanceSearch 的组织响应按 `current_team.data_team_ids` 投影；共享对象仍可见，数据库中的完整组织关联不变。

### TDD 与回归证据

- RED：规则 bool/float/前导零/混合非法/空快照 6 项失败；Policy、Condition、Instance 空/None 组织 helper 6 项失败；Policy、Instance service/search 投影 3 项失败；共享 Rule 普通 PATCH 首次因 DRF 二次进入误拒。
- GREEN：严格快照、空组织、投影、共享 PATCH、合法 sibling 分配与零副作用专项全部通过。
- 扩大回归：Task 3 原回归集合并入新增用例后 `259 passed in 46.63s`；覆盖率复跑同一集合 `259 passed in 76.24s`。
- 差异覆盖率：`42` 个差异可执行行、`6` 行未覆盖，`85%`，高于 `75%` 门禁。

### 静态门禁

- `python -m py_compile`、`git diff --check`、原生 SQL 扫描、`makemigrations --check --dry-run` 通过。
- isort 5.10.1 对本次新增 import 所在生产文件与业务测试通过；未改 import 的 service/既有测试仍保留基线格式，不做机械格式化。
- Black 23.1 对本次新增且无基线格式债务的 5 个触及文件通过；`monitor_policy.py`、`monitor_object.py`、`monitor_instance.py`、既有 projection/object-extra 测试仍复现 HEAD 基线格式差异。
- flake8 7.1.1 除既有 `C901` 与测试 `F841` 基线外通过；本次引入的 `E303` 已修复。
