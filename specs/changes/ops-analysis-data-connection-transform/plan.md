# 运营分析：数据连接与可选 Python 转换实施计划

Status: ready

产品契约：[`spec.md`](./spec.md)（本变更唯一需求真源）

原始需求存档：[`references/original-requirement.md`](./references/original-requirement.md)（只读对照，不作为实施依据）

Runner 运维上下文：[`runner-deployment-context.md`](./runner-deployment-context.md)（服务依赖、环境变量、安全边界与验收要求）

## 1. 结论与交付边界

本期补齐运营分析的 E（连接复用）与最小 T（数据转换），不建设通用 BI/ETL 平台：

- **数据连接**：组织内复用 MySQL、PostgreSQL、REST 的物理连接和凭据。
- **数据源**：仍是组件唯一绑定对象，保存 SQL、REST 请求、Excel 文件、可选转换与字段定义。
- **MySQL/PostgreSQL**：连接 + 数据源自己的 SELECT/表查询；不提供 Python。
- **REST**：单次 HTTP 响应解析为完整行集后，可选实时执行 Python。
- **Excel**：保存原文件，可选执行 Python 并生成物化结果；组件只读当前成功结果。
- **NATS/Prometheus**：保持现状，不并入数据连接，不增加 Python。

实施顺序允许“数据连接先发布”，但 Python 功能只能在独立 Runner 达到安全门槛后开启；不存在回退为 Server 同权子进程的兼容路径。

| 类型 | 获取 | 转换 | 组件消费 |
|---|---|---|---|
| MySQL/PostgreSQL | 公共连接或历史内联配置 | SQL/表查询 | 查询结果 |
| REST | Base URL + 相对路径/请求配置 | 可选 Python，运行时执行 | 转换结果 |
| Excel | 已保存原文件 | 可选 Python，生成候选结果 | 当前成功结果 |
| NATS/Prometheus | 保持现状 | 不新增 | 保持现状 |

本计划只描述如何实现 [`spec.md`](./spec.md) 中已经确认的产品契约。原始需求与最终结论的差异统一记录在 Spec 的「Confirmed Changes from the Original Requirement」章节，不在 Plan 另建第二套产品语义。如两份文件冲突，以 Spec 为准；如需新增偏离，必须先回到产品讨论并更新 Spec。

## 2. 数据模型与不变量

### 2.1 数据连接

新增 `DataConnection`：

- 通用字段：名称、类型、描述、`groups`、`is_active`、审计字段。
- MySQL/PostgreSQL V1：主机、端口、默认数据库、用户名、密码；不新增 TLS/SSH 隧道。
- REST V1：Base URL 与公共 Headers；不新增 OAuth、Token 刷新或 HMAC 等认证流程。
- 密码和 Header 值加密存储；详情只返回占位符，占位符回传表示保留原值。
- 连接类型创建后不可修改。
- 修改立即影响所有引用方；修改端点、用户名、密码或 Headers 前展示引用数并确认影响。
- 停用连接后，引用它的数据源明确失败；有引用时删除受 `PROTECT` 保护。
- 数据源的 `groups` 必须是连接 `groups` 的子集；数据源保存和运行时都要 fail closed 校验。
- 缩小连接 `groups` 时，若已有引用数据源会超出新范围，拒绝保存并列出冲突数据源。
- 权限沿用现有数据源增删改查权限（菜单可见性与 API 均绑定 `data_source`，不新增 `data_connection-*`）；这包括新增的 Python 脚本编辑权限，属于已确认的 V1 权限扩展。

### 2.2 数据源引用

扩展 `DataSourceAPIModel`：

- 增加可空 `connection` 外键；存量 `connection_config` 继续作为内联模式，不强制迁移。
- 新建 MySQL/PostgreSQL/REST 优先选择公共连接，同时保留“独立配置”兼容入口。
- 数据库数据源只能覆盖数据库名；REST 数据源保存方法、相对路径、Query、Body、超时和响应路径。
- REST 禁止绝对 path、`//host`、跨源重定向凭据转发及绕过 Base URL 的路径。
- 内联数据源提供“提取为数据连接”；服务端在一个事务中创建连接、校验组织范围并切换引用。
- 数据库、REST、Excel 继续持久化 `chart_type=["table"]`；服务端也要拒绝越权图表类型。
- 转换配置统一为 `transform_config = {enabled, language: "python", script}`，仅 REST/Excel 允许持久化。

### 2.3 Excel 成功/候选槽位

增加最小 Excel 物化记录，不建设通用版本或资产平台：

- 每个槽位绑定数据源、原文件、脚本快照/哈希、处理状态、安全错误摘要、行列数和物化结果。
- 数据源最多维护一个当前成功槽位与一个候选槽位，不向用户提供历史版本列表。
- 新文件、脚本修改或开关变化都生成新候选；已提交的候选始终使用自身脚本快照，不读取后续编辑中的值。
- 候选成功后事务性切换为当前成功结果；旧任务不得覆盖更新候选。
- 候选失败时，已有成功结果继续服务并返回 warning；首次创建没有成功结果时不可运行。
- 原 `.xlsx` 和物化结果使用项目现有对象存储能力；关系数据库只保存元数据和地址，不继续把新结果写入 `query_config.imported_items`。
- 存量 Excel 的 `imported_items` 继续可运行；修改名称、描述、标签、授权组织或字段展示不触发迁移，只有用户显式重新上传原文件时才进入新槽位模型。

## 3. 三个必要深模块

不建立覆盖所有数源和画布的全能执行管线，只在三个真实变化缝建立小接口、深实现的模块。

### 3.1 `ConnectionResolver`

唯一公开能力是按数据源和当前组织解析一份可执行连接配置。模块内部负责：

- 公共连接/历史内联双模兼容。
- 停用、不存在和组织子集校验。
- 解密及只允许的 database/path 覆盖。
- 返回脱敏错误，不向调用者暴露凭据存储细节。

预览、测连、组件运行、分享和报表链路均调用此接口，不各自合并 JSON。

### 3.2 `TransformExecutor`

Server 侧只暴露 `execute(rows, params, script)` 一个执行接口，其适配器是独立 Runner：

- Server 完成 REST/Excel 取数，只将行数据、空 `params` 和脚本交给 Runner；不传递数据库凭据、REST Headers、Django 配置或用户 Token。
- Runner 是独立容器/运行单元，不与 Server 共享 UID、文件系统、环境变量或业务网络权限。
- Runner 非 root、只读根文件系统、禁止业务网和公网出站，并设置 CPU、内存、PID、临时空间和执行超时上限。
- AST/import 白名单用于限制脚本能力，不宣称其为安全边界。V1 只允许 `json`、`math`、`datetime`、`collections`。
- 脚本契约固定为 `transform(rows, params) -> list[dict]`；REST/Excel V1 的 `params` 均为空对象。
- 输入和输出各最多 10,000 行，并分别受可配置的序列化字节上限保护；执行超时 5 秒。超限、超时、非法导入或非 `list[dict]` 返回均失败，不截断、不回退原始数据。
- 组织并发限额在 Runner 执行入口统一兑现。V1 部署锁定单 Runner 副本与单 Web Worker（`--workers 1`），进程内计数即为全局上限；默认同组织 3 个，超出返回可区分的容量错误，不排队。多副本共享租约留待扩容前实现，扩容前不得水平扩展 Runner。
- Runner 不可用不影响 Server 启动和无脚本数据源；有脚本 REST 明确失败，Excel 候选失败但保留旧成功结果。
- Runner 不参与 `batch_init`，不在 Server Supervisor 中启动，不形成启动期循环依赖。
- 脚本、输入行和结果不写入日志，不作为任务队列消息正文持久化；日志只保留请求 ID、组织、行数、耗时和错误码。

### 3.3 `ExcelMaterializer`

唯一公开能力是“用某个候选槽位的原文件和脚本快照生成结果并尝试切换”：

- 候选生成由运行期 Celery 任务触发，异步失败不得阻断 Server 启动。
- 任务读取候选绑定的原文件，探测第 10,001 条数据；超过 10,000 行明确失败，不得使用 `nrows=10000` 静默截断。
- V1 保持现有 `.xlsx` 与 2MB 文件上限；文件大小与行数分别校验。
- 无脚本时直接物化解析结果；有脚本时通过 `TransformExecutor` 转换。
- 切换时重新确认候选仍是最新候选，再在事务中更新当前成功槽位、字段定义和状态。
- 只对基础设施短暂不可用做有限重试；脚本错误、格式错误和超限不重试。具体次数与退避时间是运行配置，不写死在产品契约。

## 4. REST 取数与转换顺序

REST 预览与组件运行必须共用同一个窄执行入口，顺序固定为：

```text
解析连接与请求配置
→ 发起单次 HTTP 请求
→ 读取受字节上限保护的完整响应
→ response_path
→ 归一化为完整行集
→ 探测并拒绝 >10,000 行
→ 可选 Python
→ 校验 list[dict] 与输出上限
→ 推断/应用字段
→ 预览采样或组件分页
```

“完整响应”只指当次 HTTP 响应中 `response_path` 选中的数组；V1 不跟踪第三方分页链接，不自动请求后续页。

REST 出站使用项目既有 `safe_request` 能力：

- 校验 Base URL 及每次重定向后的 scheme、DNS 解析和目标 IP。
- 继续遵守部署环境的出站白名单，不为运营分析创建第二套 SSRF 策略。
- 公共 Headers 不得在跨源重定向中继续携带；不允许 Host、Content-Length 等 hop-by-hop/受控 Header。
- 保留现有超时和 2MB 响应字节上限。

## 5. API 和导入导出

### 5.1 对外接口变化

- `/operation_analysis/api/data_connection/`：数据连接 CRUD。
- `/operation_analysis/api/data_connection/{id}/test_connection/`：即时测连，不持久化“连接健康度”。
- `/operation_analysis/api/data_connection/{id}/references/`：返回受影响数据源摘要。
- `/operation_analysis/api/data_source/{id}/extract_connection/`：原子提取历史内联连接。
- 数据源请求/响应增加 `connection_id`、允许的覆盖配置、`transform_config` 和 Excel 最小物化状态。
- 现有 preview、preview_config 和 `get_source_data` 路径及 `{data,warnings}` 运行时契约保持不变。
- 连接凭据只在服务端解析；列表、详情、分享、报表和引用列表均不返回可执行凭据。

### 5.2 YAML 导入导出

- 公共数据连接不作为 YAML 一级对象导出。
- 引用公共连接的数据源导出为脱敏内联配置；敏感值为占位符，导入不自动按名称关联公共连接。
- 新格式 Excel 数据源的 YAML 只保存名称、脚本、字段定义等非数据配置；不包含原 `.xlsx` 或物化行数据。
- 导入预检必须明确列出缺失凭据与“Excel 需重新上传”；导入后 Excel 数据源处于 `needs_upload` 且不可运行，不得呈现为可用数据源。
- 用户重新上传文件后生成候选，成功切换后恢复可用。
- 兼容旧 YAML：若包含 `query_config.imported_items`，继续按存量格式导入并保持可运行；之后重新上传才进入新物化模型。

## 6. 交互设计

### 6.1 信息架构

```text
ops-analysis/settings
├── dataConnection   # 组织内 MySQL/PostgreSQL/REST 连接
├── dataSource       # 组件绑定的逻辑数据源
└── namespace        # 现有 NATS 配置
```

数据连接页复用现有设置列表、搜索、表格和 Drawer：

- 列展示名称、类型、地址摘要、授权组织、启停状态、引用数和更新时间。
- 创建/编辑 Drawer 按类型显示基础连接字段，提供测连和保存。
- 从数据源选择器新建连接时打开 Modal，成功后自动选中，不丢失数据源草稿。
- 删除、停用和修改关键连接字段均明确说明影响；引用列表不暴露凭据。

### 6.2 数据源 Drawer

保留现有 Drawer 和单一表单状态，内容固定分为四段，用可跳转步骤导航或锚点辅助定位，不做强制线性 Wizard：

1. **基本信息**：名称、类型、标签、授权组织、描述。
2. **连接与取数**：选择/新建数据连接，或使用独立配置；编辑 database/SQL 或 REST 请求；Excel 上传原文件。
3. **转换与预览**：仅 REST/Excel 显示 Python 开关、契约和代码编辑器；预览显示原始样例与转换结果样例。
4. **字段与保存**：从转换结果应用字段定义，调整标题、类型和顺序，展示保存摘要。

四段可自由跳转；点击预览或保存时定位第一个错误字段。修改连接、请求、文件或脚本会使旧预览失效；关闭有未保存内容的 Drawer 时要求确认。

### 6.3 转换和 Excel 状态

- 复用现有 Python Code Editor，在运营分析 app 内组合契约说明、允许模块、行数/超时限制和错误位置。
- 预览用 Tabs 展示“原始样例 / 转换结果”，两者都是小样本；完整行集只在服务端执行链中使用。
- REST 预览失败时不展示未转换宽表作为降级结果；保存后的运行时也遵循同一失败语义。
- Excel 创建或更新后可见的核心状态为：`processing`、`ready`、`update_failed_using_previous`、`needs_upload`。
- 界面新建：同步导入成功才落可用数据源；失败丢弃新建，不留空壳。编辑失败保留旧成功结果。重试仅在已保存原文件且处理失败时展示。
- `processing` 且无成功结果时不可被组件使用；有旧成功结果时显示“更新中，当前使用上次结果”。
- `update_failed_using_previous` 显示上次成功时间、安全错误摘要和重试入口；组件响应在 `warnings` 中提示仍在使用旧结果。
- `needs_upload` 不可运行，用于 YAML/配置导入后待补文件；重新上传并成功处理后才可运行。

### 6.4 UI 验收范围

- 连接列表和 Drawer 覆盖 loading、empty/error、permission denied、readonly、长文本与窄容器。
- Python 预览和 Excel 状态以 app-local family story 覆盖关键状态；不要求建设通用脚本平台的全量 Storybook 矩阵。
- 复用 Ant Design、现有设置列表壳、Code Editor 和字段表；新增业务组合保持在 `src/app/ops-analysis/components`。
- 亮色/暗色主题均验证；不新建只有一个 app 消费的 shared 组件。

## 7. 交付切片

### Slice A：数据连接（可独立发布）

- 实现连接模型、加密、CRUD/测连/引用摘要、启停和删除保护。
- 实现 `ConnectionResolver`、组织子集不变量、内联兼容和原子提取。
- 上线数据连接设置页和数据源连接选择。
- 本切片不暴露 Python 开关，可在 Runner 之前独立交付。

### Slice B：薄 Runner 与 REST 转换

- 交付独立 Runner 的安全边界、`TransformExecutor` 和容量限制。
- 将 REST 执行收敛为第 4 节的唯一顺序，预览与运行时共用。
- 用 `safe_request` 替换裸 `requests`，覆盖重定向和 Header 安全。
- Runner 安全验收通过后才开启 REST Python UI。

**进度**：Runner / `TransformExecutor` / REST 转换链与 REST Python UI（开关、契约、原始/转换 Tabs）已落地。

### Slice C：Excel 原文件与候选物化

- 实现成功/候选槽位、原文件与结果存储、Celery 候选生成和原子切换。
- 实现第 10,001 行探测、2MB 文件限制和新旧 Excel 兼容。
- 完成上传、预览、处理状态、失败保留旧版与重试交互。
- Runner 未达到安全门槛时，Excel 可先上线“无脚本物化”，但不暴露 Python 开关。

**进度**：后端槽位/`ExcelMaterializer`/Celery/`submit_excel`（上传默认同步物化 + 新建 `discard_on_fail`）与前端上传、状态展示（processing/ready/update_failed_using_previous/needs_upload）、`can_retry`、Excel Python 开关与预览 Tabs 已落地。

### Slice D：YAML、分享/报表和文档收口

- 实现第 5.2 节的新格式导入导出与旧 `imported_items` 兼容。
- 验证分享页、报表渲染和组件运行均使用当前组织可执行的数据源，且不暴露凭据。
- 实现后同步运营分析 capability、安全/部署说明与发布记录。

**进度**：导出展开共享连接为脱敏内联、导出 `transform_config`、新 Excel 剥离物化行；导入写 `transform_config` 且不挂 `connection_id`；预检增加 `OA_EXCEL_NEEDS_UPLOAD`；capability ARD 已同步。分享/报表仍走既有 `get_source_data`（Excel 成功槽 / REST transform）。

## 8. 验证与验收

### 数据连接与授权

- 连接 CRUD、加密存储、占位符保留/替换、凭据不入日志和导出。
- 同一连接被两个不同 SQL 数据源引用；连接修改对两者立即生效。
- 保存数据源、运行数据源和缩小连接范围时均验证 groups 子集不变量。
- 连接停用、缺失、跨组织及删除被引用连接均返回可区分错误。
- 历史内联数据源保持可运行，提取为连接后结果一致。

### REST 与 Runner

- 转换一定在行数完整性校验之后、预览采样/分页之前执行。
- 无脚本与现网结果一致；有脚本时 preview、preview_config 和 `get_source_data` 结果一致。
- 输入/输出超限、超时、非法 import、非法返回和容量不足均明确失败且不返回宽表。
- 验证 Runner 无数据源凭据、无业务网出站、受 CPU/内存/PID/文件系统限制，且 Runner 不可用时 Server 仍正常启动。
- REST Base URL、DNS/IP、重定向和跨源 Header 行为均覆盖安全用例。

### Excel

- 准确探测 10,001 行并拒绝，不静默截成 1,000 或 10,000 行。
- 候选成功原子切换；候选失败、Runner 不可用或旧任务晚到都不会覆盖当前成功结果。
- 修改脚本后使用保存的原文件重算，不对旧物化结果二次转换。
- 首次处理、有旧结果的更新、更新失败和 `needs_upload` 的组件运行语义分别验证。
- 新 YAML 不包含 Excel 文件/物化数据，导入后不可运行直到重新上传；旧 `imported_items` YAML 仍可导入运行。

### 前端与回归

- 四段可跳转 Drawer、预览失效、首个错误定位和未保存关闭确认。
- 连接筛选只展示当前组织可用项，停用项不可新选，缩小组织范围显示冲突引用。
- 数据库/REST/Excel 只保存表格类型；MySQL/PostgreSQL 不出现 Python 入口。
- loading、empty/error、permission denied、readonly、长文本、窄容器、亮色/暗色主题均有新鲜验证。
- NATS、Prometheus、无脚本 MySQL/PostgreSQL/REST 以及存量 Excel 回归通过。

## 9. 发布与明确不做

- 模型和新字段向后兼容上线；Python 须在 Runner 达到生产最低安全门槛后正式可用（功能开关仅作故障熔断）。
- Runner 是运行期非关键依赖，不进入 `batch_init`；V1 部署锁定单副本与单 Worker，扩容前不得水平扩展。
- 必要指标：连接查询耗时、Runner 错误码/耗时/容量拒绝、Excel 候选处理成败；指标标签不包含脚本、输入数据或凭据。
- V1 不做：Dataset/语义层、MySQL/PostgreSQL/NATS/Prometheus Python、第三方包、脚本市场/版本中心/调试器、REST 自动翻页、REST 统一筛选参数、非表格图表、强制迁移内联数据源、Excel 多版本历史、>10,000 行分块/流式处理、全量 SQL hardening。
- MySQL/PostgreSQL 本期保持现有单 SELECT/行数护栏，产品文案推荐使用只读数据库账号；更强只读事务与 SQL 解析另立安全变更。
