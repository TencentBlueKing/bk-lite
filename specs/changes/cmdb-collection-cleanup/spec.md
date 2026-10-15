# CMDB 采集清理策略统一修复

## 问题与范围

VC 的过期删除原每日按 `task.model_id` 和整数 `collect_task` 查图，漏掉虚拟机及其他子模型、字符串归属的资产。相同缺陷影响云平台、存储等多模型任务。即时清理另存在 `_MODEL_ID` 门禁、空快照不删、非空部分结果误删，以及删除成功未进入详情的问题。

统一三种策略，以 `collection/cleanup.py` 为判定入口：当前任务拥有、非预选目标、完整快照差集；过期删除再按上次 `collect_time` 和快照时间计算严格超过 N×24 小时。不新增 missing_since 字段。无时区历史时间跳过，不中断其他候选。

## 实现与数据安全

- `MetricsCannula` 传递过期天数和预选目标，按采集实际模型查询整数/字符串归属；有轮次边界时使用轮次完成时间，重放历史轮次不使用当前时间触发过期删除。
- `Management` 完成新增、更新及心跳后再清理；写入或归属冲突跳过清理。图数据库条件删除原子检查实例 UUID、模型、任务和时间，保护并发刷新/转移归属的实例。
- 插件错误指标、身份不全、字段转换失败不能证明完整快照；模型级 manifest 判定保留否决权。
- 三种策略均保护预先选择的根/采集目标；VC 沿用来源锁和根优先更新。PC 过期清理由每日扫描移到完整软件快照，对本 PC 软件关系集合执行相同时间判定。
- 删除明细和审计使用真实成功/失败结果。停止注册每日时间扫描任务；保留旧 Celery 入口为无副作用返回，兼容已排队消息及遗留 Beat 记录。

## K8s 完整抓取协议 v1

`agents/webhookd/bk-lite-resource-collector.yaml` 的 Telegraf exec 输入先完整下载 KSM 响应，再输出原有 23 种资源指标、每种的计数（包括 0），及 `cmdb_k8s_snapshot_timestamp{snapshot_contract_version="1"}`。资源和标记采用同一原始样本时间；不在标签上增加轮次时间，避免无限序列增长。脚本仅请求原固定 KSM 地址，30 秒 HTTP 超时、64 MiB 响应限制、45 秒执行超时，退出清理临时文件；依赖镜像中的 sh、curl、awk、date、mktemp。

服务端在最近 10 分钟寻找新协议标记，再按该样本时间取资源与计数并核对每个指标。计数缺失、不符、错误指标时不清理；只有完整验证才能把空 Pod/节点/命名空间/工作负载集合解释为删除差集。副本数使用同一份抓取数据。Telegraf 使用 `prometheus_metric_version=2` 并保留来源时间，维持现有 `prometheus_` VM 指标命名。

## 发布与回滚

1. 先发布 Server，重启 Worker / Beat，使旧日清理入口退役。旧 K8s 采集器仍能增改，但不会清理。
2. 经现有安装入口重新生成并应用 resource 采集 YAML，更新 ConfigMap 后滚动重启 `telegraf-resource`（subPath 挂载不会自动刷新运行中的文件）。确认部署镜像包含脚本依赖，观察同时间资源和计数通过验证。K8s 未升级前不能宣称过期清理已恢复。
3. 新采集器对旧 Server 保留原资源指标名称、标签及上报主题，额外标记可被旧查询忽略。回滚采集器时，新 Server 自动退回只增改。
4. 不单独回滚 Server 到存在无快照日清理的版本；如必须回滚，先将受影响任务改为不清理。成功删除保留审计 before_data；可依据记录恢复误删数据，仍存在于来源的资产会在后续采集重建。

## 验证

回归覆盖三策略、29 个注册多模型族、VC 完整执行入口、K8s 完整/缺片/空结果、时间阈值、字符串/整数归属、预选目标、并发刷新、写入失败、删除重试、PC 关系隔离和审计，以及两个图驱动的条件删除参数。

本机验证使用 SQLite 和内存图边界；不连接生产。K8s 脚本以真实 sh/awk 执行、替换 HTTP 边界，并检查 YAML/TOML 和安装模板渲染。真实部署镜像、KSM → NATS → VM 全链路及真实图服务需要发布环境验证。

### 本地验证结果（2026-10-10）

- 服务端相关 22 个测试文件：691 通过；新增统一清理测试文件包含 162 个参数化场景。
- K8s 脚本 / YAML / TOML / 安装模板渲染：47 通过。
- 本次服务端变更可执行行覆盖率：136/158，86.1%。`git diff --check`、新增核心文件 flake8、两种语言包 JSON 解析通过。
- `test_falkordb_client.py::test_create_edge_persists_uuid_endpoints_and_strips_numeric_ids` 在完整回归中失败，已使用 HEAD 原始驱动独立复现（UUID 大小写），本次最终通过集仅排除该已确认基线失败，未修改其断言或生产行为。
- SQLite 测试使用 `--nomigrations`：原迁移基线存在 `NewSessionEventRelation has no field named event`，因此本次没有证明迁移链通过，也没有进行真实图数据库或采集集群联调。

Telegraf 解析器参数依据：[官方 Prometheus input data format 文档](https://docs.influxdata.com/telegraf/v1/data_formats/input/prometheus/)。
