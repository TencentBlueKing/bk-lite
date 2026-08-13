# 运营分析：数据连接库与可选 Python 清洗

Status: ready

> 变更目录：`specs/changes/ops-analysis-data-connection-transform/`
> 施工计划：同目录 [`plan.md`](./plan.md)
> 重方案对照（不采用）：[`references/plan-gpt-heavy.md`](./references/plan-gpt-heavy.md)

## Problem Statement

运营分析的数据源今天把「连到哪里」和「取什么 / 怎么给组件」绑在同一条配置里。MySQL、PostgreSQL、REST API 的主机与认证散落在每个数据源的连接配置中：同一套凭据无法复用，密码或地址变更要改多处，也容易改漏。

对 MySQL / PostgreSQL，取数形态本身已是 SELECT（或按表限量拉取）：同一连接上配置不同 SQL，就能得到不同的组件就绪结果，不需要再套一层脚本清洗。缺的是可复用的公共连接。

对 REST API / Excel，经常先接到宽表（例如上百列），组件需要裁剪、过滤或聚合后的窄结果。现有链路只有直连取数和组件侧展示适配，没有可复用、可预览、带护栏的服务端清洗层。没有清洗时又必须保持与今天完全一致的直连行为。

历史上部分「转换」被推到 NATS 内置接口，导致命名空间侧接口膨胀；外部数据与 NATS 都不能无限承载 T。需要把 E（连接）下沉为可复用对象，把 REST/Excel 的 T 收回数据源侧，且不推翻现有 NATS / Prometheus / 内联兼容路径。

## Solution

在运营分析管理侧增加组织隔离的「数据连接」对象（连接库），供 MySQL、PostgreSQL、REST API 数据源引用；连接可修改、可停用，有引用时不可删除，修改后对后续取数生效。数据源仍是组件唯一绑定对象。

- **MySQL / PostgreSQL**：只走「公共连接 + 各数据源自己的 SELECT / 取数配置」。不提供 Python 清洗；加工下推到 SQL。
- **REST API**：取数成功后支持可选 Python 清洗（平台先取数，再洗 `rows`）；**每次预览与运行时实时执行**。未配置脚本则跳过，与现网直连一致。
- **Excel**：上传后可选 Python；**预览成功并「应用」后把清洗结果固化进现有 `query_config.imported_*`**；组件取数只读固化窄表，运行时不再跑脚本。无脚本时行为与现网一致（预览后缓存行）。
- 脚本在 **Server 侧受限子进程** 中执行（超时、行数、并发、import 白名单）；失败不回退到未清洗宽表。V1 **不上**独立 Runner / 对象存储版本态机。

NATS 继续使用既有命名空间，本变更不并入连接库、不加 Python。组件取数契约仍为统一的 `{ data, warnings }`，无需改绑定方式。

## User Stories

1. As a 运营分析数据源管理者, I want 把 MySQL / PostgreSQL / REST 的主机与认证存成组织内可复用的数据连接, so that 新建数据源时不必重复填写凭据。
2. As a 运营分析数据源管理者, I want 多个 MySQL / PostgreSQL 数据源引用同一连接但各自配置不同的 SELECT, so that 同一套库凭据能产出多套组件就绪结果。
3. As a 运营分析数据源管理者, I want 在一处修改连接的密码或地址且对引用它的数据源生效, so that 对端凭据轮换时不必逐个改数据源。
4. As a 运营分析数据源管理者, I want 在仍被数据源引用时无法删除连接、但可以停用连接, so that 既防止误删，又能安全切断取数。
5. As a 运营分析数据源管理者, I want 数据源引用连接时可覆盖库名或 REST 的具体 path，但不能覆盖主机与认证, so that 同一实例或多 path 网关可复用连接，同时凭据仍集中管理。
6. As a 运营分析数据源管理者, I want 在 REST / Excel 数据源上可选编写 Python 清洗脚本, so that 宽表结果能变成组件可用的窄结构并被多个组件复用。
7. As a 运营分析数据源管理者, I want 未配置清洗脚本时 REST / Excel 取数与现网完全一致（跳过清洗）, so that 存量与简单数据源不受影响。
8. As a 运营分析数据源管理者, I want REST 的预览与组件取数走同一套取数加清洗链路；Excel 预览应用后的固化结果与组件取数一致, so that 所见即所得，并能回填清洗后的字段定义。
9. As a 运营分析平台, I want 清洗超时、超行或过载时中断执行并给出明确失败, so that 错误脚本不会拖垮取数服务或静默少数据。
10. As a 运营分析数据源管理者, I want 继续使用内联连接配置，并在需要时提取为连接库中的连接, so that 现网数据源不必强制迁移。

## Implementation Decisions

### 产品分层与能力矩阵（V1）

| 类型 | 连接库 | 取数 / 加工 | Python 清洗 |
|---|---|---|---|
| MySQL / PostgreSQL | 要 | 各数据源自己的 SELECT（或按表限量） | **否** |
| REST API | 要 | 连接 + path/查询配置 | **可选，运行时实时** |
| Excel | 否 | 上传 / `imported_*` 缓存行 | **可选，预览应用后固化** |
| NATS | 既有 NameSpace | 下游接口 | **否** |
| Prometheus | 否（本变更不改） | PromQL | **否** |

- 不引入独立 Dataset / 语义模型；组件仍只绑定数据源。
- MySQL / PostgreSQL 的「清洗」就是 SQL，不在库连接器后再挂 Python。
- REST / Excel 的清洗挂在数据源上，供多组件复用；不是组件级 Transform。
- 不限制 REST/Excel 只能选表格组件；仍由数据源 `chart_type` 与字段决定。
- 行业对标：MySQL / PG 接近 Superset「Database + SQL Dataset」；REST / Excel 宽表再加工用可选脚本补齐。

### 数据连接（连接库）

- 新增组织隔离的数据连接对象，V1 类型覆盖 MySQL、PostgreSQL、REST API。
- 连接承载可复用的「连到哪台 / 哪个服务」：主机、端口、账号、密码或等价认证、TLS 等；REST 为 base URL 与 Auth（含可复用 Headers）。
- 敏感字段**加密存储**（对齐 NameSpace）；编辑回显与保留策略用 `******` / 未改不覆盖。
- Excel 不进入连接库；NATS 继续只用既有命名空间，本变更不合并、不迁移命名空间。
- 连接按组织隔离（与数据源一致）。命名空间是平台共享；连接库刻意不跟命名空间共享模型走。
- 生命周期：修改立即作用于后续取数（保存前展示引用数提示）；停用后引用该连接的数据源取数失败并明确提示；仍被引用时禁止删除，并提示引用列表。
- 权限：连接的增删改查与现有「数据源管理」同权，不另开权限矩阵。
- V1 **不做**「数据源 groups 必须是连接 groups 子集」硬校验；各自按当前组织可见与可写即可。

### 数据源与连接的关系

- MySQL / PostgreSQL / REST 数据源支持双模：引用连接，或继续使用内联连接配置。
- 新建引导优先「选择连接」；编辑支持将内联配置提取为连接供复用。
- 引用连接时允许覆盖：MySQL / PostgreSQL 可覆盖 database；REST 可覆盖具体 path / query 相关部分。禁止在数据源上覆盖主机与认证。
- REST 引用连接时 path 应为相对路径（相对连接 Base URL）；禁止借 path 跳到绝对跨源 URL（防凭据复用被绕开）。
- 取数配置、参数模板、图表类型、字段定义仍留在数据源。

### Python 清洗（仅 REST / Excel，可选）

- 适用范围 V1：**仅 REST API、Excel**。MySQL、PostgreSQL、NATS、Prometheus **不加**。
- 执行模型为「平台先取数，再清洗」：先得到行数据，再执行脚本；脚本不能获得数据库句柄、不能出网、不能读写磁盘。
- 脚本契约：只读输入 `rows`（`list[dict]`）与可选只读 `params`；必须返回 `list[dict]`，字段名稳定。
- **REST**：预览与 `get_source_data` 均实时执行清洗；`params` 可接收已声明参数的解析值 / 预览手填值。V1 **不承诺**与统一筛选完整打通（现网非 NATS 本就不传业务筛选进连接器）。
- **Excel**：仅在预览 / 「应用清洗结果」时执行；应用后写入 `imported_*` + `field_schema`；运行时只读固化结果。Excel 脚本侧 `params` 固定为空（或不使用）。改文件或改脚本后须重新预览并应用，否则组件仍读旧固化数据。
- 未配置脚本或脚本为空：跳过清洗，与现网一致。
- 脚本失败：本次预览/取数失败并返回明确错误；不得静默回退到未清洗宽表。
- `import` 白名单（如 `math`、`datetime`、`collections`、`json`）；禁止 `os`、`subprocess`、`requests` 等。
- 写 / 改 Python 与数据源管理同权。
- V1 执行载体：Server 内**受限子进程**（可后续替换为独立 Runner，接口形状预留 `execute(rows, params)`）。**不上**独立 `agents/` 服务、不上对象存储多版本物化。

### 护栏（V1 默认，仅 Python 路径）

- 脚本超时：5 秒；超时杀子进程。
- 送入脚本与脚本输出最大行数：各 1 万行。
  - **有脚本且输入超限**：**失败**（不截断后继续洗，避免图表静默变少）。
  - 预览可为排查提供「仅看前 N 行」的显式调试能力，但不得与正式预览/运行时成功语义混淆。
- 每组织同时执行的清洗脚本数约 3；超出则**拒绝**（可区分错误，如 429），不做排队。
- 隔离：子进程；禁网、禁写盘、受限 import；清洗不可用时不得阻断 Server `batch_init` / 启动。无脚本数据源不受影响；有脚本的 REST 返回依赖/执行失败。
- MySQL / PostgreSQL 仍沿用既有 SQL / 预览护栏（如仅 SELECT）；本期不借机扩大 SQL 危险语法 hardening 范围。
- Excel 文件上限与现网对齐（当前连接器 2MB）；不在本期默默放大到 10MB。

### 运行时与 API 行为

- 组件绑定与响应外壳不变：仍通过数据源 id 取数，统一返回 `{ data, warnings }`。
- 解析连接：若数据源引用连接，则合并连接与允许的覆盖项后再执行连接器；若连接停用或不存在，取数失败并明确提示。
- 内联连接配置的旧数据源保持可运行、可编辑；不强制一次性迁移。
- REST：清洗插在「连接器取数成功得到行数据之后、返回给调用方之前」；无脚本则 no-op。
- Excel：`get_source_data` 读已保存的 `imported_*`；清洗只发生在管理侧预览应用路径。
- MySQL / PostgreSQL：取数结束即返回，无清洗步骤；拒绝持久化/执行 Python 配置。

### 前端

- 设置区增加「数据连接」管理（列表、创建、编辑、停用、删除拦截、测试连接）；菜单顺序：数据连接 → 数据源 → 命名空间。
- 文案区分：数据连接（组织内，MySQL/PG/REST）≠ 命名空间（NATS，平台共享）；避免都叫「公共连接」而不加限定。
- 数据源表单：在现有 Drawer 上演进（分区/折叠），**不做**四步向导重构；MySQL/PG/REST 优先选连接；仅 REST/Excel 提供可选 Python；Excel 增加「应用清洗结果」。
- 组件选择与画布取数 UI 不因本变更改绑定模型。

### 导入导出（V1）

- 公共连接不作为 YAML 一级对象导出/导入（避免跨组织凭据扩散）。
- 导出引用型数据源时，将非敏感连接信息扁平为兼容内联结构，密文用占位符。
- 导入后为独立内联数据源并提示需补凭据；不自动关联同名连接。
- Excel 的行数据按现有导入导出能力处理；不引入「对象存储地址」交换。

## Testing Decisions

- 好测外部行为：连接 CRUD / 停用 / 删除拦截、引用合并与覆盖规则、同一连接多数据源不同 SELECT、REST 无脚本透传与有脚本清洗成败、超限失败、并发拒绝、Excel 应用固化后运行时不跑脚本、预览与运行时（REST）一致、组织隔离、双模兼容；并断言 MySQL / PostgreSQL **不接受 / 不执行** Python。
- 最高测试缝优先复用现有 `get_source_data`、preview / preview_config；连接对象用独立 API 缝测生命周期。
- 不测子进程内部实现细节；不强制本期交付独立 Runner 容器矩阵。

## Out of Scope

- 独立 Dataset / 语义层 / 计算列产品。
- MySQL / PostgreSQL 数据源上的 Python 清洗。
- 脚本内自行连库或发 HTTP（「脚本主执行」模式）。
- NATS 命名空间并入连接库；NATS / Prometheus 数据源上的 Python 清洗。
- 强制迁移存量内联 `connection_config`。
- 跨组织共享连接。
- 单独的「仅管理员可写 Python」权限位。
- **独立 Transform Runner 服务、对象存储多版本物化、Celery 异步候选版本切换**（愿景见 references，本期不做）。
- 超过 1 万行的分块 / 流式 / 计算引擎。
- 组件侧 Grafana 式 Transform 管道重构。
- 场景组件专用取数链路改造。
- 借机全面 hardening MySQL/PG 危险语法（只读事务扩展等可另立项）。
- 数据源与连接的组织子集硬约束、REST/Excel 强制仅表格组件、四步向导 IA 重构。

## Further Notes

- 与 NameSpace：产品叙事都是「连接类配置」，实现上保持两个对象；V1 不强行统一。
- 交付前应回写运营分析管理 PRD / 功能清单中「非 NATS 使用自身连接配置」的表述；本文件为变更共识。
- 相对早期草案：Excel「物化」收窄为「写入现有 `imported_*` 缓存」，不是独立数仓/对象存储版本系统；与「不希望一开始设计太重」一致。
