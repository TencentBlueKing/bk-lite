# Task 5 日志模块直接归属数据权限报告

## 状态

DONE

## 实现范围

- 日志分组、采集实例、策略、节点查询全部先按 `current_team` 解析数据范围，超级管理员不再绕过。
- 普通用户继续叠加原对象权限，最终可见范围为“对象权限与当前组织数据范围的交集”。
- 分配组织使用可分配组织集合，允许把本人有权管理的组织分配给对象；读取响应仅投影当前组织范围。
- VictoriaLogs 查询在访问外部服务前完成日志分组范围校验。
- NATS 日志查询携带并校验明确的用户、域、当前组织与子组织开关；无效或伪造上下文拒绝全部数据。
- 本任务只处理直接绑定组织的数据。告警、事件等继承策略组织的数据链由 Task 6 处理，未在本任务扩展。

## 主要文件

- `server/apps/log/services/access_scope.py`
- `server/apps/log/nats/log.py`
- `server/apps/log/views/collect_config.py`
- `server/apps/log/views/node.py`
- `server/apps/log/views/policy.py`
- `server/apps/log/serializers/log_group.py`
- `server/apps/log/serializers/policy.py`
- `server/apps/log/services/collect_type.py`
- `server/apps/log/tests/test_current_team_data_scope.py`
- `server/apps/log/tests/test_nats_log_pure.py`
- `server/apps/log/tests/test_collect_instance_permission_guards.py`
- `server/apps/log/tests/test_node_proxy_address.py`

## TDD 证据

- RED：日志分组和 VictoriaLogs 场景 5/6 失败；NATS 新增场景 5 个失败；采集实例新增场景 4/4 失败；节点超级管理员场景 2/2 失败；策略直接归属场景 4/4 失败。
- GREEN：核心权限矩阵先达到 96 passed；扩展回归最终为 234 passed（22.91s）。
- 差异覆盖率：`diff-cover` 相对基线 `b01779f1f954d0f84c64c85aa7386a90e789598d` 为 76%（160 行变更，37 行未覆盖），达到项目要求的 75%。

## 静态与结构检查

- Black（Python 3.12）检查通过。
- isort 检查通过。
- Flake8 对本次生产代码和新增/修改测试通过；`test_collect_instance_permission_guards.py` 基线已有两个未使用导入，未做无关清理。
- `python -m compileall -q apps/log` 通过。
- `python manage.py makemigrations --check --dry-run log`：`No changes detected in app 'log'`。
- `git diff --check` 通过。
- 差异中未引入 `RawSQL`、`.raw()` 或 `cursor.execute`。

## 已知非本任务问题

- Projectmem #0079：旧 `APIClient` 日志分组视图测试在基线即被认证中间件返回 401；本任务使用 `APIRequestFactory` 直接视图测试覆盖权限行为，未改认证测试基础设施。

## 提交

提交 SHA 在提交完成后由交付消息提供。

## 复审修复（2026-07-21）

本轮针对权限复审发现的边界继续补强：

- SystemMgmt NATS 不再信任调用方传入的 `is_superuser`，改为依据数据库中的用户与继承角色判定；同一判定同时用于查询范围和可分配组织范围。
- 采集实例更新在任何副作用前一次性校验全部子配置/基础配置的归属、采集类型和角色，阻断跨实例 IDOR 及子/基础配置混用。
- 共享采集实例的响应组织字段仅展示 `current_team` 数据范围内的组织。
- 策略数、采集实例数先按 `current_team` 数据范围过滤，再叠加普通用户对象权限。
- 策略创建后直接读取刚创建的对象，避免用当前组织读取范围反查导致“可分配兄弟组织但创建响应失败”；响应仍按当前范围投影。
- NATS 日志查询解析出拒绝全部范围后直接返回空数据，不调用 VictoriaLogs，同时保留参数合法性校验。
- 日志分组组织 ID 统一执行严格规范化：仅接受正整数或无前导零的 ASCII 数字字符串；创建必填，PUT/PATCH 省略时保留，显式空列表拒绝。

### 复审验证

- TDD RED：伪造超管、数据库超管反向标记、跨实例配置、配置角色混用、共享组织投影、计数越界、策略跨组织创建回读、NATS 拒绝范围外调、非规范组织 ID 均由新增测试复现。
- 最终联合回归：`313 passed, 1 deselected`（24.78s）。唯一排除项依赖本地 `nats_client.default_registry`，属于已确认环境基线。
- 差异覆盖率：相对 `c7af5098359cd52fd50f17eb7ec4799833eabff9` 为 `88%`（75 行变更，9 行未覆盖），达到 75% 门禁。
- Black、isort、flake8、compileall、`makemigrations --check --dry-run log system_mgmt`、`git diff --check` 均通过。
- 差异中未引入 `RawSQL`、`.raw()` 或 `cursor.execute`；告警/事件 Task 6 文件未在本轮修改。

## 最终复审：NATS caller 超管伪造

- RED：普通数据库用户在合法 `current_team=A` 下伪造 `user_info.is_superuser=true` 时，`log_search` 和 `log_hits` 均绕过对象权限并返回无权日志，新增两条参数化场景稳定失败。
- 修复：`get_authorized_groups_scoped` 在响应中返回由持久化用户角色判定的 `is_superuser`；日志 NATS 不再读取或透传 caller 的同名字段，仅在服务端结果严格为 `True` 时使用超管当前组织范围，否则始终叠加日志分组对象权限。
- 正向：数据库真实超管即使 caller 标记为 false，仍按服务端真值正常读取当前组织范围；普通用户伪造 true 时 search/hits 均返回空且不调用 VictoriaLogs。
- 最终联合回归：`315 passed, 1 deselected`（44.92s）；唯一排除项仍为已确认的本地 `nats_client.default_registry` 依赖基线。
- 相对 `c25ed0d81` 的生产代码差异覆盖率为 `100%`；Black、isort、flake8、compileall、迁移检查、diff 检查与原生 SQL 扫描均通过。
