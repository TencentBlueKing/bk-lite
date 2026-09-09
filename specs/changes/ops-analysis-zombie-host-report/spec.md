# 运营分析僵尸机报表

Status: implemented

## Problem Statement

周大福一类客户用 WeOps 运营分析跑僵尸机报表：圈一批应用系统下的主机，按时间窗看登录次数、网卡入包、CPU / 内存 / IO 的均值和峰值，再用闲机口径阈值把闲机筛出来。BK-Lite 已有主机监控、CMDB 应用系统拓扑、Winlogbeat / 文件日志和 Report 表格，但没有「按应用系统展开已监控主机、服务端一次拼表、未选不退回全量」的查询。现有主机 Top10 只看当前使用率；Flow 盘按网络设备而不是主机；运营分析也不能在页面串查监控和日志。客户那份 Presto SQL 不能移植。

## Solution

监控提供僵尸机专用查询，CMDB 提供应用系统选项并把系统展开为已监控主机，日志提供成功登录次数。运营分析只登记数据源和一张内置 Report：顶栏统一筛选（时间默认 7 天、应用系统多选、系统类型、白名单、闲机口径阈值），正文一张表格。页面不拼多源数据，也不写 PromQL。

## User Stories

1. As an 运维人员, I want 在运营分析报表里按应用系统圈出其下已有监控 ID 的 CMDB 主机, so that 我不用逐台勾选主机，也不会选出没有指标的资产。
2. As an 运维人员, I want 未勾选应用系统时表格为空且不扫描全量, so that 我不会误看未选或无权主机。
3. As an 运维人员, I want 用运营分析现有时间控件查询，默认最近 7 天且可改日期, so that 窗口和别的运营分析画布一致。
4. As an 运维人员, I want 看到所选主机在时间窗内的 CPU / 内存 / IO / 网卡入包均值与峰值，以及成功登录次数, so that 能按客户规则判断疑似僵尸机和可降配机器。
5. As an 运维人员, I want 默认阈值按 7 天闲机/可降配口径，并能把某一维改成 -1 表示不限, so that 两组条件 AND 之后仍可放宽某一列。
6. As an 运维人员, I want 没有登录采集的主机显示为未采集，而不是 0, so that 「登录 < 10」不会把没接日志的机器当成闲机。
7. As an 运维人员, I want 一次最多查 100 台，超出时得到明确错误, so that 结果不会被静默截断。
8. As a 看板搭建者, I want 内置报表只读、数据源可复用到其它报表表格, so that 交付环境开箱即有这张表，又不必为此新做图表类型。

## Implementation Decisions

- 运营分析继续只做可视化与配置。拼表、PromQL、登录聚合、监控授权留在监控；主机选项和身份字段留在 CMDB；成功登录计数留在日志。运营分析禁止为该场景直连监控 / CMDB / 日志内部服务。
- 新 CMDB NATS `list_application_systems`：返回当前用户有权的应用系统，出参至少 `inst_uuid`、`inst_name`、`display_name`。另提供 `list_host_uuids_for_systems`：把已选且有权的系统沿 `system_contains_application` → `application_run_host` 展开为主机 UUID；无权系统省略。`list_monitored_hosts` 仍保留作出选项源，第一期报表 UI 不再绑定它。
- 新监控 NATS `get_zombie_host_report`：入参 `system_uuids`（报表必选多选；未选返回空成功）、`time`（运营分析 `timeRange`，默认 10080 分钟）、可选 `os_type`、`zombie_whitelist`，以及各指标 min/max。兼容入参 `inst_uuids` 供内部测试。超过 100 台（展开后）返回失败消息，不截断。先用 CMDB 解析身份和 `monitor_id`，再按监控授权过滤；无权或已失效的 `monitor_id` 省略。过滤后一台都没有则空成功。
- 阈值默认按 7 天闲机口径，不随窗口缩放，不再照抄客户 19/39/999：登录 max=2、入包峰值 max=200 pps、入包均值 max=50 pps、CPU 均值 max=8%、CPU 峰值 max=20%、内存均值 max=25%、内存峰值 max=40%、IO 峰值 max=10%；各维 min 默认 -1。-1 表示该边界不限。疑似僵尸机条件全部 AND。`login_status=uncollected` 的行不参与登录阈值，但仍参与其它指标过滤并出现在结果里（登录列展示未采集）。改时间窗不自动改阈值。
- 运营分析 `source_api.json` 登记内置数据源：CMDB 应用系统列表（`chart_type` 空，选项源）；僵尸机查询（`chart_type: [table]`）。应用系统参数 `system_uuids` 为字符串多选、`filterType=filter`，选项源指向 `cmdb/list_application_systems`，`valueField=inst_uuid`。时间、系统类型、白名单、各 min/max 均为 `filterType=filter`。统一筛选可绑定类型扩展 `number`。这些 NATS 不经 OpenAPI 网关对外暴露。
- 主机模型补人工枚举字段 `zombie_whitelist`（是 / 否），采集不得覆盖。没有该字段或空值视为否。业务名取主机所属组织显示名。系统类型沿用 CMDB `os_type`（1 Linux / 2 Windows / 3 AIX / 4 Unix / other）。
- 新日志 NATS `count_successful_logins_by_host`：按时间窗和一批主机名 / IP 返回每台 `login_count` 与 `login_status`。成功登录只计 Windows 安全日志 4624，以及 Linux SSH / 本地成功登录（如 `Accepted`）；失败、解锁、sudo、网络登录不计。优先主机名匹配，对不上再用 IP。对得上已接入的 Winlogbeat 或 Linux 鉴权日志采集实例则为 `counted`（次数可为 0）；对不上则为 `uncollected`，`login_count` 为空，不得写成 0。本变更不新增采集类型；现场需已配置对应日志采集。
- 指标按 `monitor_id` 查主机监控，Linux / Windows 指标名归并与主机综合盘同一口径。时间窗内用 `avg_over_time` / `max_over_time`：`cpu_usage_total`、`mem_used_percent`、`net_packets_recv_rate`；IO 用 `diskio_io_util`，先按盘取窗内峰值再取主机最大盘。不接受裸 PromQL，不用 NetFlow / sFlow，不复用 `get_host_resource_top`（无历史均值峰值）。
- 出参为表格行：`biz_name`、`host_name`、`os_type_label`、`ip`、`packets_recv_max`、`packets_recv_avg`、`login_count`、`login_status`、`cpu_max`、`cpu_avg`、`mem_max`、`mem_avg`、`io_max`、`zombie_whitelist`、`inst_uuid`、`monitor_id`。入包单位是 pps（网卡收包速率），CPU/内存/IO 是百分比；这些数值列出表时保留两位小数。登录次数仍是整数。表格组件按现有后端分页消费；过滤在分页前完成，展示舍入不改变过滤结果。
- 内置 Report YAML 随 `init_builtin_canvases` 加载（独立文件并入，与 Flow 盘相同）。报表只含一张 `table`，查看态展示上述筛选。内置报表只读。不新增图表类型，不做仪表盘 KPI。

## Testing Decisions

只测外部行为：选项源只含有 `monitor_id` 的授权主机；空选择不查监控和日志；超 100 台失败；无权 `monitor_id` 省略；阈值 -1 与 AND；未采集登录不按 0 过滤；Linux/Windows 指标归并；IO 按盘取最大；数据源定义与内置报表 YAML 绑定；统一筛选能绑定 number。

接缝：

- 纯函数：阈值（含 -1）、登录 `counted` / `uncollected`、IO 折叠、窗口时长（对齐主机盘）
- CMDB / 日志 / 监控 NATS handler：授权、空选择、上限、非法参数（对齐 `test_host_dashboard_handler.py`、`get_monitor_ids_by_inst_uuids` 权限测试）
- RPC 方法名转发（对齐 `test_monitor_forwarding.py`、`test_misc_forwarding.py`）
- 契约集合含新 handler（对齐 `test_nats_monitor_handlers.py`）
- `source_api.json` 与 number 可绑定类型（对齐 `test_host_dashboard_datasource_definitions.py`、运营分析统一筛选测试）
- YAML 可解析、随 `init_builtin_canvases` 进入内置报表、表格绑定僵尸机数据源、应用系统下拉绑定 CMDB 选项源

不测真实 VictoriaMetrics / VictoriaLogs、Winlogbeat 采集、前端 E2E、客户原 SQL。

## Out of Scope

- 未勾选时扫描全部授权主机
- NetFlow / sFlow / Packetbeat 作为入包或访问判定
- 登录失败、解锁、sudo、网络登录
- 按窗口自动缩放阈值或写死 30 天
- 降配建议列、每日预聚合、专用业务页、仪表盘 KPI
- 包内 Linux / Windows / IIS / MSSQL CMDB 资产脚本迁移
- 新增日志采集类型或强制开通采集
- 把该查询经 OpenAPI 网关对外暴露

## Further Notes

产品决策：`docs/design/product-decisions/ops-analysis-zombie-host-report.md`。  
替换对象是 WeOps 僵尸机报表，不是同包里的自定义采集插件。客户原文案按 30 天写「登录 < 10」；本变更默认 7 天且阈值不缩放，报表说明需写明当前时间窗。

验证（本机 sqlite）：

```
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest \
  apps/cmdb/tests/test_monitored_host.py \
  apps/cmdb/tests/test_list_monitored_hosts_handler.py \
  apps/log/tests/test_successful_login_count.py \
  apps/monitor/tests/test_zombie_host_report.py \
  apps/monitor/tests/test_zombie_host_report_handler.py \
  apps/rpc/tests/test_misc_forwarding.py \
  apps/rpc/tests/test_monitor_forwarding.py \
  apps/operation_analysis/tests/test_zombie_host_report_datasource.py \
  apps/operation_analysis/tests/test_zombie_host_report_yaml.py \
  --no-cov
```

结果：187 passed（`test_nats_monitor_handlers.py` 因 sqlite 迁移基线未纳入）。  
前端：`node_modules/.bin/tsx --test src/app/ops-analysis/utils/__tests__/dataSourceParamContract.number.test.ts` 与 `scripts/ops-analysis-param-contract-test.ts` 均通过。

演示机（生产镜像 Pyarmor）：以 overlay 热补丁注册 NATS，并导入内置报表「僵尸机报表」。现场行为：未选主机空表；超过 100 台返回「一次最多查询 100 台主机」；勾选已监控主机可查出 CPU/内存/IO/入包；默认阈值把忙碌演示机关掉（count=0）；阈值全 -1 出表；登录列为 uncollected（现场未接 Winlogbeat/文件鉴权采集）；CMDB `os_type` 枚举列表解成 Linux；PromQL 使用逻辑 instance_id。容器重建会丢失 overlay。
