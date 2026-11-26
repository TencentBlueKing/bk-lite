# syslog 来源设备：身份字段与发现列表

Status: implemented

需求来源：p398_1041。属性补充（品牌、型号、设备类型）在 p398_1058，本规格不实现。
决策记忆：`docs/design/product-decisions/log-extractor-passive-collect.md`。

## Problem Statement

syslog 的 `instance_id` 固定为 `base`，事件上没有云区域。经中转时多台设备的 `source_ip` 相同，搜索和统计分不开发送设备。已收到的设备停发后，平台上也没有一张可回看的名单。

## Solution

- Linux Vector 的 syslog 补全段写入字符串 `cloud_region_id`，并只对 `hostname` 做去空白。`instance_id` 保持 `base`。
- 日志模块新增来源设备表。运行期每 5 分钟按云区域汇总最近 10 分钟的 syslog，只更新已出现的三元组。
- 来源设备是观测出来的对象，接入实例是用户配置出来的对象，两者分开放。「集成」下紧挨日志接收新增「来源设备」页，是这张只读表，菜单权限 `source_device-View`。日志接收只列有接入实例的类型，syslog 和 SNMP Trap 都不出现。系统日志详情侧栏只留配置、提取器、简介。点一行进入日志搜索。旧的详情地址跳到来源设备页。

## User Stories

1. 作为运维，我看到新 syslog 带有接收节点的云区域、源 IP 和 hostname，能在搜索、统计和提取器条件里使用这三个字段。
2. 作为运维，我从「集成 / 来源设备」看到谁在发系统日志、首次收到、最近收到，以及 24 小时内是否活跃。日志接收的「全部」仍只代表接入实例。
3. 作为运维，我点一行，日志搜索带上这三个字段，时间范围盖住该行的首次收到到现在。
4. 作为既有客户，历史日志不回填；非容器节点和 Windows Vector 配置不被这次模板改动改写；自定义配置不改。

## Implementation Decisions

### D1. 模板字段

改 `server/apps/node_mgmt/support-files/collectors/Vector.json` 里两份 Linux 模板（`x86_64`、`arm64`）的 `default_config.add_config`，只改 `transforms.syslog_enrich_base` 的 VRL。Windows 的 `add_config` 为空，保持不动。不要改 snmp trap 段。

```vrl
.collector = "Vector"
.collect_type = "syslog"
.instance_id = "base"
.cloud_region_id = "${node.cloud_region}"
.received_at = now()
if !exists(.timestamp) {
  .timestamp = now()
}

raw_hostname = ""
if exists(.hostname) && is_string(.hostname) {
  raw_hostname = strip_whitespace(string!(.hostname))
}
if raw_hostname == "" {
  .hostname = ""
} else {
  .hostname = raw_hostname
}
```

- 占位符必须是 `${node.cloud_region}`。节点变量表的键是 `node__cloud_region`，值是 `node.cloud_region_id`。`${node.cloud_region_id}` 不会被替换。
- `cloud_region_id` 必须是字符串。提取器 `==` 按 Python 类型比较，条件输入是字符串。
- hostname 只去首尾空白。缺失、非字符串、去空白后为空，写成 `""`。不用源 IP 填充，不把 `"-"` 转成空。
- `server/apps/log/support-files/plugins/Vector/syslog/collect_type.json` 的 `attrs` 增加 `cloud_region_id`。`default_query` 不变。`log_init` 已有的 `update_or_create` 会同步该文件，不另写迁移。

存量节点不新增刷新任务，不进 `batch_init`。升级步骤仍是：`node_init` 之后人工执行 `python manage.py repair_node_config`。实现代码不调用这条命令。

### D2. 来源设备表

新模型放在 `server/apps/log/models/`，并在 `models/__init__.py` 导入。表只服务 syslog，不加 `collect_type`，不复用 `CollectInstance`。

| 列 | 形状 |
|---|---|
| cloud_region_id | 字符串，非空 |
| source_ip | 字符串，非空 |
| hostname | 字符串，`blank=True`，`default=""`，禁止 NULL |
| first_seen | aware datetime |
| last_seen | aware datetime |

唯一约束：`(cloud_region_id, source_ip, hostname)`。空 hostname 是合法行。不建组织表，不按团队拆行。不预留品牌、型号、设备类型列。

### D3. 发现任务

注册到 `server/apps/log/config.py` 的 `CELERY_BEAT_SCHEDULE`，每 5 分钟一次。任务在日志进程内查 VictoriaLogs 并写本表。不从 `collector_init`、`batch_init` 或节点心跳入队。

查询复用 `VictoriaMetricsAPI.query`，不绕过它的 limit 钳制（默认最大 1000）。`_time` 是中心 Vector 消费到事件的时间，用它作为收到时间。对 `CloudRegion` 的每个 id 各查一次：

```text
collect_type:"syslog" AND cloud_region_id:"<id>" | stats by (cloud_region_id, source_ip, hostname) min(_time) as first_seen, max(_time) as last_seen
```

时间窗是现在往前 10 分钟，用 `query` 的 `start` / `end`，limit 用 `QUERY_LIMIT_MAX`。

写入规则：

- 没有 `source_ip`，或 `cloud_region_id` 为空的聚合行跳过。`hostname` 缺失或空白按 `""`。
- 新三元组插入。已有行把 `first_seen` 取更早值，`last_seen` 取更晚值。重复窗口只把最近收到往后推。
- 某个云区域返回行数等于 limit：记一条有界警告（`truncated=true`、`cloud_region_id`、行数），仍写入已返回的行。
- 查询抛错：不写、不删，任务记一条带 `failed_stage` 和 `error_type` 的错误后结束。空结果是成功，已有行保留。
- 日志用 `apps.core.logger` 的 log logger。INFO 只记开始和结束汇总（区域数、写入行数、截断区域数）。不记查询正文、报文和逐行明细。

不在库里的云区域 id 不扫描。模板只会打上节点上的云区域 id。

### D4. 列表接口

控制台接口，挂在 `server/apps/log/urls.py`，不走 OpenAPI 网关，不新增对外端点。

`GET /api/v1/log/syslog_source_devices/`

权限跟来源设备页一致：先 `LogAccessScopeService.get_data_scope`，没有当前团队时拒绝；超管放行；其他人需要 `source_device-View`。只有日志集成或日志接收的查看权限不够。通过后返回全部行，不按团队过滤。

`server/support-files/system_mgmt/menus/log.json` 的 Integration 下新增 `source_device`，操作只有 `View`，`normal` 角色默认授予 `source_device-View`。`manager` 角色由 `init_realm_resource` 自动拿到全部菜单。自定义角色需要管理员手工勾选。

查询参数：`cloud_region_id` 匹配云区域 id 或名称；`source_ip`、`hostname` 为包含匹配；`keyword` 对源 IP 和主机名做或匹配；`status` 为 `active` 或 `silent`；分页。状态不落库：`last_seen` 距现在不超过 24 小时为 `active`，否则为 `silent`。阈值是代码常量。

每行返回：`cloud_region_id`、`cloud_region_name`、`source_ip`、`hostname`、`first_seen`、`last_seen`、`status`、`search_query`、`search_start`、`search_end`。`cloud_region_name` 用云区域页同一套显示名：按 id 找到 `CloudRegion.name`，再取当前语言的 `cloud_region.<name>.name`；没有语言包时用存储名。对不上区域就返回空名称，由页面显示 id。`search_query` 是：

```text
collect_type:"syslog" AND cloud_region_id:"..." AND source_ip:"..." AND hostname:"..."
```

值按 LogsQL 引用转义。`search_start` 是 `first_seen` 的毫秒，`search_end` 是现在的毫秒。没有新建、修改、删除接口。

### D5. 页面

来源设备不放在 syslog 集成详情侧栏。`buildPassiveIntegrationDetailMenu` 对 syslog 和 snmptrap 都只保留配置、提取器、简介。

列表是独立页 `web/src/app/log/(pages)/integration/source-device/page.tsx`，路由 `/log/integration/source-device`，菜单名 `source_device`，在「集成」下排在日志接收之后。日志接收的树只列有接入实例的类型：`syslog`、`snmp_trap` 都不进树，「全部」只代表接入实例。

`/log/integration/list/detail/source-device` 保留为隐藏路由，并重定向到 `/log/integration/source-device`。

表格用 Ant Design 和现有语义色，不新建 SCSS Module。列是接收类型（当前只有系统日志）、云区域、源 IP、hostname、首次收到、最近收到、状态。工具条靠右只留搜索，匹配源 IP 或主机名。状态用表头筛选，单选活跃或静默。没有操作列。点一行用 `buildSearchJumpUrl` 打开 `/log/search`，query 用接口返回的 `search_query`，时间用 `search_start` / `search_end`。中英文文案都补。

## Out of Scope

- p398_1058 的品牌、型号、设备类型、CMDB 匹配。
- p398_1059 的 Trap 来源清单。
- 历史日志回填，新建刷新任务，调用 `repair_node_config`。
- 手工新建、改身份、删除、静默阈值设置、按团队拆分、按设备拆提取器。
- 把来源设备写进日志集成卡片列表。
- 把来源设备写成 `CollectInstance`，或在日志接收里给它删除、组织和采集节点操作。

## Acceptance

1. 两份 Linux 模板的 syslog 补全段含 D1 的 VRL 和 `${node.cloud_region}`；Windows `add_config` 仍为空；`attrs` 含 `cloud_region_id`。
2. 同一三元组再次出现只把 `last_seen` 推向更晚，`first_seen` 只向更早。空 hostname 占独立行。查询异常或空结果后，原有行还在。
3. 24 小时边界：恰好 24 小时内为 active，超过为 silent。
4. 无当前团队时列表拒绝。只有日志集成或日志接收查看权限时拒绝。有 `source_device-View` 时不按团队过滤。
5. `search_query` 带三个字段；空 hostname 仍是空字符串条件。
6. 「集成」下日志接收之后有「来源设备」页；日志接收树不出现系统日志和 SNMP Trap；系统日志和 snmptrap 详情侧栏都没有「来源设备」。点行后的搜索 url 带 query 和起止时间。详情旧地址跳到来源设备页。
7. 服务端测试用 sqlite：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest <新增测试> --no-cov`。前端跑与改动对应的测试。

## Completion

2026-11-25：服务端 14 passed，前端 3 passed。本机 `server/.env` 的 `INSTALL_APPS` 不含 `cmdb` 且含 `monitor`，未覆盖该变量时 Django 在启动期导入 CMDB 模型失败；用 `pytest_env_setup.py` 的默认 `INSTALL_APPS` 覆盖后，上述服务端测试通过。未调用 `repair_node_config`，未回填历史日志。

同日把列表从「系统日志」叶子改成「系统日志 / 来源设备」，筛选收进筛选框。列表接口测试 3 passed，前端树和文案测试 7 passed。随后去掉筛选按钮，状态改到表头筛选。

同日用户确认来源设备和接入实例不是一类对象，放在日志接收树里会让「全部」和括号计数说不清；普通角色也没有日志接收权限，看不到这张表。列表改为「集成 / 来源设备」独立页，新增菜单权限 `source_device-View`。
