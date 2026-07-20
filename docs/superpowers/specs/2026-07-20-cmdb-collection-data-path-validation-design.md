# CMDB 配置采集数据链路验证设计

## 1. 背景

本设计验证 CMDB 配置采集的两段生产数据链路：

1. Stargazer 插件采集结果经过格式转换并写入 VictoriaMetrics（VM）；
2. CMDB 查询 VM 数据，经 `server/apps/cmdb/collection/collect_plugin` 清洗和模型字段映射后写入 FalkorDB。

当前 E2E 测试基础设施已经覆盖多个采集对象，但关键边界被测试替身绕过：

- `server/apps/cmdb/tests/e2e/pipeline.py::step2_push_to_vm` 直接构造 VM PromQL 响应，没有运行 Stargazer 的真实 Prometheus 文本转换、Line Protocol 转换、NATS、Telegraf 和 VM 摄取链路；
- E2E 默认使用 `fake_graph`，没有证明格式化结果可被真实 FalkorDB 接受并正确持久化；
- 现有 fixture 目录不能作为生产对象覆盖真相源，部分对象仍以缺 fixture、缺 schema、缺 expected 或 `pytest.skip` 的方式存在；
- 云对象现有样本缺少统一的官方 API 文档来源、API/SDK 版本和读取日期。

生产代码中的实际写入链路为：

```text
Stargazer 插件/SDK 原始结果
  → CollectionService._process_result
  → plugins.base_utils.convert_to_prometheus_format（自定义 Prometheus 文本生成）
  → influxdb_client.Point（转换为 InfluxDB Line Protocol）
  → NATS metrics subject
  → Telegraf inputs.nats_consumer / outputs.http
  → VictoriaMetrics
```

读取和图库写入链路为：

```text
VictoriaMetrics
  → collection.query_vm.Collection.query
  → CollectBase.run
  → collect_plugin.format_data / format_metrics / field_mapping
  → MetricsCannula
  → Management
  → GraphClient
  → FalkorDB 实体与关联
```

## 2. 目标

- 生产插件注册中心中的全部生产采集对象均通过两段离线契约验证；
- 已有真实环境 Mock 数据从插件原始结果开始运行真实转换代码；
- 云采集对象从官方 API 文档构造 SDK/API 响应边界 Mock，测试运行时保持离线；
- 严格验证 Prometheus 文本、Line Protocol、VM 查询、字段清洗、模型约束、实例名称和关联关系；
- 使用八类代表对象运行真实 NATS、Telegraf、VM、CMDB 和 FalkorDB 闭环烟测；
- 测试发现的生产缺陷在同一工作分支内按系统化调试和 TDD 完成最小修复；
- 所有分层测试、真实烟测和质量门禁全绿后才创建 PR。

## 3. 非目标

- 不连接真实云账号、生产 VictoriaMetrics、生产 NATS 或生产 FalkorDB；
- 不验证 `config_file` 的 NATS 回调链路，因为该链路不经过 VM；
- 不进行与测试揭示缺陷无关的采集架构重构；
- 不新增生产期 schema 校验服务、质量 dashboard 或长期监控系统；
- 不以 fixture 目录中历史归档、许可证阻塞或 placeholder 对象反向扩大生产覆盖范围。

## 4. 总体架构

采用“对象级分层契约 + 分类真实基础设施烟测”。

### 4.1 对象级分层契约

每个生产采集对象均运行两条相互独立的测试 Lane：

```text
Lane A：源数据 → Stargazer → Prometheus 文本 → Line Protocol → NATS 发布边界
Lane B：VM 查询响应 → collect_plugin → 模型实例 → Management 图写入意图
```

Lane A 与 Lane B 分开验证，确保失败能够定位到具体边界。Lane B 不伪装成真实 VM 摄取测试；真实传输兼容性由基础设施烟测负责。

### 4.2 真实基础设施烟测

在隔离容器环境中运行：

```text
Stargazer → NATS → Telegraf → VictoriaMetrics → CMDB → FalkorDB
```

烟测从 VM 实际查询数据驱动 CMDB，并从 FalkorDB 回读实体与关联完成最终断言。

## 5. 覆盖真相源与对象矩阵

### 5.1 真相源

生产插件注册中心是对象覆盖的唯一真相源。覆盖单位不是单一 `supported_model_id`，而是三元组：

```text
(task_type, supported_model_id, emitted_model_id)
```

测试从每个生产插件的 `metric_names`、`field_mapping`、`field_mappings`、`related_field_mappings` 及同类声明中展开全部 `emitted_model_id`。云、VMware、Host 等一个任务产生多个模型时，每个产出模型都必须独立进入验证矩阵；只有同一 fixture 和 Golden 确实覆盖全部产出模型时，才允许共享测试用例。

测试启动时动态取得上述生产启用三元组集合，并与显式维护的验证清单进行双向比较：

- 注册中心新增对象但验证清单未登记：失败；
- 验证清单登记对象但注册中心不存在或已停用：失败；
- 对象缺 fixture、schema 或 expected：失败；
- 生产对象不得用无理由 `skip` 或 `xfail` 冒充覆盖。

归档、许可证阻塞和 placeholder 对象可保留历史 fixture，但不计入生产对象通过率。它们应在独立的非生产清单中明确状态，避免与生产验证结果混淆。

### 5.2 真实烟测代表对象

按不同转换实现各选一个代表对象：

| 链路类型 | 代表对象 | 主要验证点 |
|---|---|---|
| Host | `host` | 主机字段、子资源和远程采集结构 |
| DB | `mysql` | DB 平铺字段、端口和实例名 |
| Protocol | `influxdb` | Protocol runner 与协议字段 |
| Middleware | `nginx` | `metric.result` JSON 解码 |
| Cloud | `qcloud` | 云 SDK Mock、多子模型和云字段清洗 |
| VMware | `vmware` | 多模型及关联关系 |
| K8s | `k8s` | K8s 特殊指标和字段清洗 |
| Network | `network` | SNMP、接口和拓扑关联 |

其他生产对象全部通过 Lane A 和 Lane B；不要求逐对象启动完整基础设施。

## 6. Fixture 设计

### 6.1 两类来源

#### 真实环境 Mock

- 从已有真实插件采集结果开始，脱敏后冻结；
- 保留能暴露转换缺陷的合法边界值，包括 `0`、`False`、空字符串、Unicode、引号、反斜杠、换行和大数值；
- 不把中间转换后的数据冒充插件原始结果。

#### 云 API 文档 Mock

- 只使用厂商官方 API 文档和与代码匹配的 API/SDK 版本；
- Mock 固定在云厂商 SDK/API 响应边界，后续 Stargazer 格式化逻辑必须运行真实代码；
- 新增或更新 fixture 时允许查阅官方文档，自动测试运行时不得联网；
- 每个云 API 至少覆盖成功单页、分页、空结果、缺失可选字段和文档化错误响应；
- 不根据现有 formatter 反向臆造厂商响应字段。

### 6.2 统一证据包

每个对象的测试证据包含以下逻辑制品；实现时可在保持现有目录兼容的前提下采用等价文件名：

| 制品 | 内容 |
|---|---|
| `00_provenance.json` | 来源类型、厂商、服务、API 操作、API/SDK 版本、官方文档链接、读取日期、脱敏说明 |
| `01_source_raw.json` | 真实插件结果或厂商 SDK/API 原始响应 |
| `02_prometheus.txt` | Stargazer 真实转换后的期望 Prometheus 语义 |
| `03_line_protocol.txt` | `influxdb_client.Point` 生成的期望 Line Protocol 语义 |
| `04_vm_response.json` | 与真实 VM 查询结果结构一致的 Lane B 输入 |
| `05_expected_cmdb.json` | 独立编写的最终模型实例、字段和关联 Golden |
| `schemas/source.schema.json` | 插件结果或 SDK/API 原始响应契约 |
| `schemas/vm.schema.json` | VM vector 查询响应契约 |
| `schemas/cmdb.schema.json` | 最终模型实例及关联契约 |

动态时间戳不做脆弱的整行文本比较，而是解析后校验精度、范围和传播关系。所有 fixture 在提交前执行凭据、Token、密钥和真实环境标识扫描。

## 7. Lane A：Stargazer 到 VM 写入契约

Lane A 运行真实生产函数，测试边界停在 NATS 发布调用之前。

### A1 原始响应契约

- 校验插件或 SDK 响应结构；
- 校验列表、单对象、分页、空结果和错误结构；
- 云 fixture 校验 provenance 与响应 API 版本一致。

### A2 Prometheus 文本语义

- 调用真实 Stargazer 插件适配及 `convert_to_prometheus_format`；
- 使用语义解析比较 metric、label、value、timestamp，而非仅做字符串包含；
- 校验 label 转义、指标名合法性、毫秒时间戳及 `model_id`、`collect_status` 等必要标签；
- 对 `0`、`False` 和空字符串设置显式期望，防止因 truthiness 过滤而静默丢失；
- 敏感字段不得进入任何 label 或错误指标。

### A3 Line Protocol 语义

- 调用真实 `convert_prometheus_to_influx` 和 `influxdb_client.Point`；
- 校验 measurement、tags、field 名、field 类型和纳秒时间戳；
- 校验公共 tags 覆盖优先级和特殊字符转义；
- 校验 NaN/Inf、非法时间戳和无法解析行的明确处理结果。

### A4 NATS 发布边界

- 捕获真实 `publish_metrics_to_nats` 对 NATS 客户端的调用；
- 校验 subject、消息行数、顺序无关语义和任务标识；
- 校验零投递、部分投递和已检测投递后的重试策略；
- 不在对象级测试中启动 NATS，真实传输由烟测覆盖。

## 8. Lane B：VM 查询到模型和图库写入契约

### B1 VM 查询契约

- 校验 `Collection.query` 的 URL、POST 参数、超时、重试和 4xx/5xx 行为；
- 校验 `CollectBase.prom_sql` 生成的 metric 集合及 `instance_id=cmdb_<task_id>`；
- 校验 `last_over_time(...[1h])` 查询包装。

### B2 VM 响应解析

- 使用与真实 VM 查询一致的 vector 响应；
- 校验响应状态、value 时间、数据新鲜度和 `collect_status`；
- 校验业务字段在顶层 label 或 `metric.result` JSON 中的实际形态；
- 禁止测试 helper 直接依据生产 field mapping 生成最终 VM 响应。

### B3 字段清洗与映射

- 运行对象真实 `format_data`、`format_metrics` 和绑定后的 `field_mapping`；
- 校验字段重命名、时间格式、布尔转换、容量/速率单位、状态枚举、`inst_name` 和关联字段；
- 独立 Golden 必须明确期望最终值，不能只断言字段存在；
- 生产字段缺失、类型错误或错误重命名直接失败；
- 厂商新增但尚未映射的可选原始字段进入 drift 报告，不阻断测试。

### B4 模型约束

- 通过模型反射校验必填字段、字段类型、枚举和允许字段；
- 排除 `_id`、采集时间等运行时生成且不稳定的系统字段；
- 模型反射与独立 Golden 同时通过才算字段对齐。

### B5 图写入意图

- 使用可观测的 GraphClient 测试替身运行 `MetricsCannula` 和 `Management`；
- 精确校验新增、更新、删除及 association 集合；
- 校验组织、采集任务、自动采集标识和采集时间等写入元数据；
- 真实 FalkorDB 接受性和回读结果由烟测验证。

## 9. 真实基础设施烟测设计

### 9.1 环境

烟测只启动隔离的 NATS、Telegraf、VictoriaMetrics、FalkorDB 和必要的 CMDB 测试服务。不得复用生产地址、生产凭据或真实云账号。

### 9.2 执行流程

1. 为本次运行生成唯一 `run_id`、task ID、NATS subject 标识和模型实例标识；
2. 使用条件健康检查等待 NATS、Telegraf、VM 和 FalkorDB 就绪，不使用固定长时间 sleep；
3. 运行代表对象的 Stargazer 生产转换并发布 NATS；
4. 轮询 VM，直到出现满足 run ID 和时间边界的实际数据或达到硬超时；
5. 运行真实 CMDB 查询和 collect task；
6. 从 FalkorDB 回读实体、字段和关联并与 Golden 精确比较；
7. 成功或失败均执行精准清理，再确认 VM 测试数据和图实体残留为零；
8. 失败时保留脱敏日志、NATS 发布摘要、VM 查询快照、CMDB 格式化结果和残留审计结果。

### 9.3 安全边界

- 默认只允许 loopback 或测试容器网络；
- 通过显式环境门禁启用写操作，避免误连外部服务；
- 所有资源带唯一 run ID，清理只处理账本记录的本次资源；
- 设置总运行时长、单次请求、消息量、实例量和日志大小上限；
- 清理必须幂等，无法证明归属的资源不得删除；
- 失败清理不覆盖原始失败，最终报告同时展示业务失败和清理失败。

## 10. 失败诊断与漂移报告

每个失败至少输出：

- `model_id`；
- 阶段编号（A1–A4、B1–B5 或 smoke）；
- 字段路径；
- 原始字段名和脱敏后的原始值；
- expected 与 actual；
- fixture provenance；
- 对应 plugin、runner 或 model mapping。

所有对象参数化运行并汇总结果，不因首个对象失败而隐藏其他漂移。生产契约错误使测试失败；新增可选原始字段只写入结构化 drift 报告。

## 11. 缺陷处理流程

测试发现异常时严格执行：

1. 记录错误、稳定复现步骤和组件边界证据；
2. 沿数据流回溯根因，比较相同类别的正常对象；
3. 建立单一根因假设并最小化验证；
4. 写入能够稳定复现的 RED 测试，并确认失败原因正确；
5. 实施只针对根因的最小生产修复；
6. 确认定向测试 GREEN，并运行同类对象和全量回归；
7. 每个缺陷独立提交，避免混入无关重构；
8. 不使用 `skip` 或 `xfail` 掩盖生产对象缺陷。

如果连续三次修复尝试仍失败，应停止继续打补丁，回到架构层讨论。

## 12. 验收标准

仅在以下条件全部满足后允许创建 PR：

- 生产注册中心展开的 `(task_type, supported_model_id, emitted_model_id)` 与验证矩阵双向一致，覆盖率为 100%；
- 每个生产对象同时通过 Lane A 和 Lane B；
- 生产对象没有无理由 `skip` 或 `xfail`；
- 真实环境 fixture 已脱敏，云 fixture 的官方来源和 API/SDK 版本完整；
- 必填字段、类型、枚举、Golden 值、`0`/`False`/空值、单位、时间、名称和关联全部正确；
- 八个代表对象的真实 NATS → Telegraf → VM → CMDB → FalkorDB 烟测全部通过；
- 烟测最终残留为零，失败证据和清理证据完整；
- 测试发现的生产缺陷全部完成根因调查、RED、最小修复和 GREEN；
- Stargazer 定向测试、CMDB 定向/全量测试和触及文件静态门禁通过；
- 触及代码覆盖率不低于 75%；
- 测试输出无未解释的错误、警告或敏感信息；
- 完整工作完成后再创建 PR，不提交只覆盖部分对象的中间 PR。

## 13. 交付物

- 本设计文档；
- 后续详细实施计划；
- 生产对象验证矩阵；
- 真实环境与云文档溯源 fixture；
- Lane A、Lane B 参数化测试基础设施；
- 隔离真实基础设施 smoke runner；
- 字段漂移和失败诊断报告；
- 缺陷修复的 RED/GREEN 证据；
- 最终验证报告与 PR。
