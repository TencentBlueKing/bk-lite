# 监控插件列表接口无损性能优化设计

## 背景

监控插件列表接口：

```text
GET /api/v1/monitor/api/monitor_plugin/?monitor_object_id=
```

由 Web 端通过 `/api/proxy/monitor/api/monitor_plugin` 转发。集成列表页初始进入“全部”视图时会传递空的 `monitor_object_id`，后端按现有契约返回全部插件，因此该请求不是异常调用，也不能通过拒绝空参数或强制分页规避。

本地数据库当前有 301 个插件。对接口的只读分析和 SQL 捕获结果如下：

| 场景 | 返回插件数 | SQL 数 | 观测耗时 |
|---|---:|---:|---:|
| 空 `monitor_object_id`，完整接口稳定态 | 301 | 904 | 约 6.06 秒 |
| 空 `monitor_object_id`，完整接口冷请求 | 301 | 904 | 约 10.43 秒 |
| `monitor_object_id=3` | 86 | 259 | 约 1.37 秒 |
| 预取关系并复用缓存的对照实验 | 301 | 2 | 约 0.13 秒 |

完整响应约 474 KB。Next.js 代理只负责透传请求和响应，不是主要耗时来源；主要瓶颈发生在 Django ORM 关系加载和 DRF 序列化阶段。

## 根因

`MonitorPluginSerializer` 使用 `fields = "__all__"`，其中 `monitor_object` 是多对多字段。列表 queryset 没有预取该关系，因此序列化每个插件时会查询一次关联对象。

同一 serializer 的 `parent_monitor_object` 字段又调用：

```python
parent_objects = obj.monitor_object.filter(parent__isnull=True)
if parent_objects.exists():
    return parent_objects.first().id
```

每个插件因此再产生一次 `exists()` 查询和一次 `first()` 查询。接口整体形成约 `3N + 1` 次 SQL；301 个插件对应 904 次 SQL。数据库往返次数随插件数量线性增长，是本次性能问题的根因。

## 目标

- 保持接口 URL、请求参数和认证权限行为不变。
- 保持响应外层结构、字段集合、字段类型、字段值和列表顺序不变。
- 保持空 `monitor_object_id` 返回全部插件的现有语义。
- 保持 `monitor_object_id`、`name`、`template_type`、`template_id` 的过滤语义不变。
- 保持 `display_name`、`display_description` 和 `is_custom` 的计算与国际化回退语义不变。
- 将列表查询的 SQL 数从随数据量增长的 `3N + 1` 收敛为常量，目标为 2～3 次。
- 不引入数据库迁移、新依赖或跨请求缓存。

## 非目标

- 不修改创建、更新、删除、导入、导出及模板相关接口。
- 不裁剪列表响应字段，不引入新的轻量 serializer。
- 不改变默认不分页的行为，也不要求前端增加 `page_size`。
- 不修改前端调用方式，不移除空查询参数。
- 不通过 Redis、进程缓存或 HTTP 缓存掩盖 ORM 查询问题。
- 不在本次变更中优化语言文件冷启动加载。

## 方案选择

### 采用：列表级关系预取 + serializer 复用关系结果

仅在 `MonitorPluginViewSet.list()` 的过滤后 queryset 上预取 `monitor_object`。这样不会让详情、创建、更新或删除路径承担额外查询。

`MonitorPluginSerializer.get_parent_monitor_object()` 改为遍历 `obj.monitor_object.all()` 得到的关联对象，并返回按 `MonitorObject.Meta.ordering` 排序后的第一个父对象 ID。列表路径会直接命中预取缓存；serializer 在其他路径单独使用时最多执行一次关系查询。

必须保留模型默认的 `type__order, order, id` 排序，不能简化成选择最小 ID。原实现的关联 queryset 继承 `MonitorObject.Meta.ordering`，因此 `.first()` 会返回该排序下的第一条记录；普通 `prefetch_related("monitor_object")` 同样按该默认顺序填充关系缓存。

### 不采用：轻量列表 serializer

轻量 serializer 能缩小约 474 KB 的响应，但当前列表被多个页面复用，裁剪字段容易破坏隐含调用契约。该优化可在未来完成调用方字段审计后独立实施。

### 不采用：默认分页或缓存

默认分页会改变“全部插件”页面的数据完整性及响应结构；跨请求缓存会增加失效、权限和国际化一致性风险。两者均不符合本次无功能影响约束。

## 数据流

优化后的请求流程：

1. ViewSet 获取基础 `MonitorPlugin` queryset。
2. 现有 `MonitorPluginFilter` 原样执行请求参数过滤。
3. 过滤后的 queryset 通过 `prefetch_related("monitor_object")` 批量加载插件及其监控对象关系。
4. DRF 序列化 `monitor_object` 时读取预取缓存。
5. `parent_monitor_object` 按预取列表的模型默认顺序筛选第一个 `parent_id is None` 的对象并返回其 ID；没有父对象时仍返回 `None`。
6. ViewSet 原样执行国际化名称、描述和 `is_custom` 补充逻辑。
7. `WebUtils.response_success()` 原样返回结果。

## 兼容性约束

以下行为必须由自动化测试锁定：

- 空参数、缺少参数和 `monitor_object_id=""` 的结果一致。
- 指定对象时只返回与该对象绑定的插件。
- 一个插件绑定多个对象时，`monitor_object` ID 集合与原实现一致。
- 同时存在多个父对象时，`parent_monitor_object` 仍取 `MonitorObject.Meta.ordering`（`type__order, order, id`）下的第一条记录。
- 仅绑定子对象或没有父对象时，`parent_monitor_object` 仍为 `None`。
- 返回插件的默认顺序不因预取发生变化。
- 中文、英文 locale 下的展示名称和描述保持原样。
- 自定义插件的 `display_name`、`display_description`、`is_custom` 保持原样。
- 详情与写操作继续使用原有 queryset 和 serializer 行为。

## 测试设计

### 查询数量回归

新增聚焦测试，创建多个插件并分别绑定父对象和子对象，通过真实 ViewSet 列表路径请求接口。使用 Django 查询捕获工具断言：

- 返回多个插件时 SQL 数保持常量，不随插件数线性增长。
- 目标查询数为 2～3 次；若测试环境中的公共认证或中间件增加固定查询，断言应隔离这些公共查询，不能放宽为随数据量增长的上限。

### 响应等价回归

构造包含以下形态的数据：

- 单父对象绑定；
- 父对象与子对象同时绑定；
- 多父对象绑定且 `order` 顺序与主键顺序相反；
- 仅子对象绑定；
- 内置插件与自定义 `api`、`pull`、`snmp` 插件。

对空参数和指定对象请求断言完整响应字段、值、顺序及父对象选择语义。测试关注外部行为，不依赖 serializer 内部实现。

### 回归门禁

至少执行：

```bash
cd server
.venv/bin/pytest apps/monitor/tests/<新增测试文件> -q
.venv/bin/black --check apps/monitor/views/plugin.py apps/monitor/serializers/plugin.py apps/monitor/tests/<新增测试文件>
.venv/bin/isort --check-only apps/monitor/views/plugin.py apps/monitor/serializers/plugin.py apps/monitor/tests/<新增测试文件>
.venv/bin/flake8 apps/monitor/views/plugin.py apps/monitor/serializers/plugin.py apps/monitor/tests/<新增测试文件>
.venv/bin/python manage.py makemigrations --check --dry-run
```

再运行仓库中现有 monitor plugin 相关测试；若全量 `make test` 被已知环境或非 monitor 模块问题阻断，需记录完整阻断证据，同时保证本次聚焦回归全部通过。

## 性能验收

性能验收以确定性的 SQL 数为主要门禁，以本地耗时为辅助观察：

- 301 个插件的列表序列化 SQL 数由 904 次降至 2～3 次。
- 查询数不随插件数量线性增加。
- 本地同一数据集的稳定态耗时应显著低于优化前约 6 秒；对照实验约为 0.13 秒，但不把绝对时间写成容易受机器、数据库和冷缓存影响的单元测试断言。
- 完整响应大小允许保持约 474 KB，因为本次不修改字段契约。

## 风险与控制

| 风险 | 控制措施 |
|---|---|
| Python 侧选择父对象与原 `first()` 顺序不一致 | 复用预取列表的 `MonitorObject.Meta.ordering`，并用 `order` 与主键相反的多父对象测试锁定 |
| 预取意外影响其他 ViewSet action | 仅在 `list()` 的过滤后 queryset 上增加预取 |
| 测试只验证查询数而遗漏功能回归 | 同时增加完整响应等价测试 |
| 固定 SQL 数断言受认证公共查询干扰 | 使用强制认证或在 serializer/list 核心边界捕获查询 |
| 仅优化空参数而让指定对象仍有 N+1 | 查询数量测试同时覆盖空参数和指定对象 |

## 发布与回滚

本变更不涉及迁移、配置或前端发布依赖，可随常规 Server 版本发布。上线后比较该接口的响应耗时和数据库查询负载；若出现未被测试覆盖的响应差异，可直接回滚 ViewSet 预取和 serializer 关系读取两处改动，不涉及数据恢复。
