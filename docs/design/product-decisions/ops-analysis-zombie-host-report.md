# 运营分析僵尸机报表产品决策记忆

- 最近更新：2026-09-09
- 当前规格：`specs/changes/ops-analysis-zombie-host-report/spec.md`
- 现场前置配置：`docs/operations/zombie-host-report-prerequisites.md`

## 产品定位

运营分析继续只做可视化与配置。僵尸机事实（主机指标均值/峰值、成功登录次数、授权过滤）留在监控与日志；主机选项和身份（含白名单）留在 CMDB。这是一张找闲机的内置 Report，不是主机综合盘，也不是 Flow / NTA。

## 已确认范围

- 第一期一张内置只读 Report：统一筛选 + 一张表格。
- 必须先勾选应用系统；未选空表，不退回全量。系统沿 CMDB `system_contains_application` → `application_run_host` 展开其下已监控主机。
- 入包量用主机网卡 `net_packets_recv_rate`，单位 pps（包/秒），不是百分比，也不是流量 bps。CPU/内存/IO 才是百分比。出表数值保留两位小数。
- Windows 与 Linux 都统计成功登录；只计成功，失败/解锁/sudo/网络登录不计。
- 时间跟运营分析现有控件，默认 7 天，用户可改日期。
- 默认阈值按 7 天闲机/可降配口径，不随窗口缩放；-1 表示不限；全部 AND。
- 单次最多 100 台（展开后）；超出报错不截断。

## 已确认设计决策

- 三个 NATS 分工，不在运营分析页面串查。原因：已确认运营分析不拼多源聚合，且禁止直连监控/CMDB/日志内部服务。
  - `cmdb/list_application_systems`：应用系统选项。
  - `cmdb/list_host_uuids_for_systems`：把系统展开为主机 UUID。
  - `cmdb/list_monitored_hosts`：已监控主机选项（报表 UI 第一期不绑定）。
  - `log/count_successful_logins_by_host`：成功登录次数与 `counted` / `uncollected`。
  - `monitor/get_zombie_host_report`：拼表、阈值、分页前过滤。
- 勾选对象以 CMDB 应用系统 `inst_uuid` 为键，展开后查询指标用主机回填的 `monitor_id`。原因：用户要求按应用系统维度圈主机。
- 未采集登录不得写成 0，且不参与登录次数上限过滤。原因：否则没接日志的主机会被误判为僵尸机。
- 统一筛选可绑定 `number`，min/max 用两个数字参数。原因：现有可绑定类型只有字符串和时间，截图需要阈值，但不新增 range 类型。
- 白名单是 CMDB 主机枚举字段 `zombie_whitelist`，不是运营分析本地名单。没有字段视为否。
- 不用 `get_host_resource_top`、Flow `query_metric_series`、客户 Presto SQL。

## 明确后置

- NetFlow / sFlow / Packetbeat 与主机访问打通。
- 登录失败与 Linux 更广的会话类型。
- 按窗口自动缩放阈值、降配建议列、每日预聚合。
- 未勾选时的全量扫描。
- 包内 IIS / MSSQL / 主机资产自定义采集脚本。
- 仪表盘 KPI、专用业务页、OpenAPI 对外暴露。

## 仍待确认

无。

## 已替代决策

- 「第一期用 Flow 访问量代替网卡入包」未采纳。原因：客户原口径是主机网卡；现有 Flow 查询轴是网络设备，且主机流量与设备 NetFlow 打通已后置。
- 「默认扫描全部授权主机，勾选只是过滤」未采纳。原因：用户要求必须先勾选范围，只对选中范围出结果。第一期勾选对象从主机改为应用系统。
- 「时间默认 30 天或写死 30 天」未采纳。原因：用户要求跟运营分析默认 7 天，页面可改日期。
- 「登录次数按 7/30 缩小默认阈值」未采纳为自动缩放；默认数字改为 7 天闲机口径，不再照抄客户 19/39/999。
- 「用 Dashboard 呈现或报表+KPI 双画布」未采纳。原因：用户要求第一期只用 Report。
- 「第一期只统计 Windows 登录或不算登录」未采纳。原因：用户要求 Windows 与 Linux 都统计成功登录。
- 「必须逐台勾选主机」已被用户改口：第一期改为应用系统筛选，去掉主机筛选。

## 决策来源

- 用户于 2026-09-09 确认：主机网卡入包；Windows+Linux 成功登录；时间默认 7 天可改；Report 呈现；白名单与 100 台上限无异议。同日改口：筛选改为应用系统维度并去掉主机筛选；默认阈值改为闲机口径，不再用客户初始化数字。
- 对照：客户 WeOps 僵尸机 SQL（CMDB + Influx 主机指标 + DataInsight Windows 登录）；`get_host_resource_top` 不做历史均值峰值；Flow 盘未选设备不退回全量；运营分析报表构建器已支持 table + 统一筛选。
- `specs/changes/ops-analysis-zombie-host-report/spec.md`
