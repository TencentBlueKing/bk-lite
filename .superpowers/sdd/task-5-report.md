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
