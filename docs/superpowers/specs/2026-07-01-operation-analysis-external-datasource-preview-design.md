# 运营分析外部数据源快速预览链路设计

日期：2026-07-01

## 背景

当前运营分析的数据源主体模型已经具备 `name`、`rest_api`、`params`、`field_schema`、`chart_type` 等基础抽象，但运行时仍然围绕 NATS 命名空间和 NATS 调用链路展开。这个模式适合内部工程化接入，不适合 PLG 场景下的外部客户自助接入。

本设计聚焦第一阶段：先验证外部数据源从配置、连接、取样到前端表格预览的链路。它不是完整的数据集平台，也不是 OLAP 或 BI 语义层。

## 目标

第一阶段交付“外部数据源快速预览链路”：

1. 用户按数据来源类型创建数据源，而不是先理解 NATS 命名空间。
2. 支持外部来源的最小连接和取样能力。
3. 服务端统一返回原始表格数据、总数和字段推断结果。
4. 前端展示一个原始表格预览组件，验证取数链路成立。
5. 保留现有 NATS 数据源，不推翻已有模型和页面骨架。

## 非目标

第一阶段不做以下能力：

1. 完整 OLAP、跨源 Join、语义层、物化刷新。
2. 复杂图表自动生成。
3. 调度同步、增量同步、数据仓库存储。
4. 完整数据治理、血缘、口径管理。
5. Excel 的生产级数据管理。Excel 可作为后续导入型数据源处理。

## 分层判断

推荐产品和技术分层如下：

```text
外部数据来源
  ├─ 数据库 MySQL / PostgreSQL
  ├─ HTTP API REST API
  ├─ 文件导入 Excel
  └─ 内部高级来源 NATS
        ↓
连接器层
  - 连接、认证、连通性校验、取样、字段探测
        ↓
数据源层
  - 定义取数对象：表 / SQL / API path / Excel sheet / NATS method
  - 保存取数参数、分页、limit、返回路径
        ↓
数据集层
  - 字段结构、字段语义、维度/指标、默认过滤、复用配置
        ↓
轻分析层
  - 聚合、过滤、趋势、排行、明细查询
        ↓
视图与模板层
  - 表格、趋势图、柱状图、饼图、单值卡、TopN、仪表盘模板
        ↓
业务消费层
  - 日常分析、专题看板、大屏展示、运营复盘

横切能力
  - 权限、凭据、审计、脱敏、限流、超时、错误诊断
```

第一阶段只打通：

```text
连接器配置 -> 测试连接 -> 取样 preview -> 推断字段 -> 原始表格预览
```

原始表格预览可以绕过轻分析层。轻分析层是标准化配置后的增强能力，不是快速见数的前置条件。

## 推荐范围

推荐第一阶段采用“REST API + 数据库取样打透”的范围：

1. REST API：验证远程响应解析、认证、response path、字段推断。
2. MySQL / PostgreSQL：验证数据库连接、只读查询、limit、结果集标准化。
3. NATS：保留现有入口和运行链路，作为内部高级来源。
4. Excel：保留产品位置，后续作为导入型数据源处理。

这样能验证两类差异最大的来源：REST API 的响应解析，以及数据库的连接和查询执行。

## 数据模型建议

继续保留 `DataSourceAPIModel` 作为数据源主体。新增通用连接器字段，现有 `rest_api` 和 `namespaces` 用于兼容 NATS。

建议字段：

```text
source_type
  nats | mysql | postgresql | rest_api | excel

connection_config
  连接地址、端口、库名、账号、密码、REST URL、认证方式等

query_config
  表名、只读查询、REST method、headers、params、response_path、limit 等

field_schema
  字段配置。预览阶段由 fields 自动生成草稿，标准化阶段允许用户修正
```

`rest_api` 字段不再作为新连接器的统一运行字段。它保留给历史 NATS 数据源和存量导入导出兼容。

## 连接器执行器

后端增加连接器注册和执行器抽象：

```text
ConnectorRegistry
  - 根据 source_type 找到执行器

ConnectorExecutor
  - test_connection(config)
  - preview(config, query, limit)
  - infer_schema(items)
```

第一阶段执行器：

1. `NatsConnectorExecutor`：包装现有 `GetNatsData`，保持兼容。
2. `RestApiConnectorExecutor`：发起受限 HTTP 请求，解析 `response_path`。
3. `DatabaseConnectorExecutor`：支持 MySQL / PostgreSQL 连接和只读取样。

## 预览接口

建议提供两个入口：

```text
POST /operation_analysis/api/data_source/preview/
POST /operation_analysis/api/data_source/{id}/preview/
```

第一个用于保存前预览，第二个用于已保存数据源重新预览。

统一返回：

```json
{
  "items": [
    { "date": "2026-06-01", "channel": "官网", "users": 120 }
  ],
  "count": 1,
  "fields": [
    { "key": "date", "title": "date", "value_type": "datetime" },
    { "key": "channel", "title": "channel", "value_type": "string" },
    { "key": "users", "title": "users", "value_type": "number" }
  ]
}
```

字段含义：

1. `items`：当前样例数据行，表格展示的最小依赖。
2. `count`：总数或当前可确认数量，用于分页和用户感知。
3. `fields`：字段推断结果，用作 `field_schema` 草稿，不作为表格预览硬依赖。

前端容错规则：

```text
有 fields -> 按 fields 生成列
无 fields -> 从 items 第一行推断列
items 为空 -> 展示空状态和字段探测结果，如果有 fields
```

## fields 推断策略

第一阶段只做基础类型推断：

```text
boolean
  true / false

number
  多数非空值可解析为有限数字

datetime
  多数非空值可解析为日期时间

string
  默认类型
```

推断规则：

1. 找到第一条非空对象记录，使用这条记录的 key 生成字段列表。
2. 只针对已生成字段扫描前 50 到 100 行样例数据，用于判断基础类型。
3. 忽略空值后判断类型。
4. 类型冲突时降级为 `string`。
5. `title` 默认等于 `key`，后续由用户在标准化阶段修改。

第一阶段不合并样例数据中出现过的所有 key。这样可以降低实现复杂度，优先验证取数、预览和字段草稿链路。代价是：如果后续行出现第一条记录没有的稀疏字段，一期不会自动展示这些字段。

第一阶段不加入 `role`、`aggregation`、`unit`、`semantic_type` 等高级语义，避免把 fields 变成轻分析层配置。

## 前端交互

数据源创建入口调整为按来源类型开始：

```text
选择来源类型
  -> 填连接信息
  -> 测试连接
  -> 配置取样对象
  -> 点击预览
  -> 查看表格和字段
  -> 保存数据源
```

预览区展示：

1. 连接状态。
2. 错误信息和修复建议。
3. 字段列表：字段名、显示名、类型。
4. 前 N 行数据表格。
5. “使用当前字段配置”或保存时自动写入 `field_schema`。

前端可以复用现有表格解析能力。当前表格组件已经支持数组和 `{ items, count }` 结构，并可以从 `field_schema` 或首行数据推断列。

## 安全和权限

第一阶段必须保留最低安全边界。

数据库：

1. 产品建议使用只读账号。
2. 服务端强制 `limit`，默认 100，最大值需要配置上限。
3. 优先支持“选择表 + 自动 SELECT”。
4. 如允许 SQL，只允许单条 `SELECT`，禁止 DDL、DML、多语句。
5. 设置连接超时和查询超时。

REST API：

1. 设置请求超时。
2. 限制响应体大小。
3. Header、Token 等敏感字段加密存储、脱敏返回。
4. 保留 SSRF 防护扩展点。后续可复用现有网络白名单设计。

通用：

1. 沿用 `groups` 做组织范围隔离。
2. 预览、创建、修改、删除写入操作日志。
3. 凭据加密存储。
4. 前端不回显明文密钥。
5. 错误分类为连接失败、认证失败、查询失败、解析失败、无数据、权限不足。

## 可行性

可行性较高。

已有基础：

1. 后端已有 `DataSourceAPIModel`，可作为主体对象演进。
2. 前端已有表格组件，能消费数组和 `{ items, count }`。
3. 后端依赖已有 `sqlalchemy`、`pymysql`、`psycopg2-binary`、`httpx`、`requests`、`pandas`、`openpyxl`。
4. 现有 `field_schema` 可承接 `fields` 推断结果。

主要复杂度：

1. NATS 专用运行链路需要抽象成按 `source_type` 路由。
2. 数据库预览要做只读和 limit 约束。
3. REST API 要处理 response path、认证、超时和响应大小。
4. 凭据加密和脱敏需要避免泄漏。

## 复杂度估算

按 REST API + MySQL / PostgreSQL 取样打透估算：

| 模块 | 复杂度 | 说明 |
|---|---:|---|
| 模型扩展与迁移 | 中 | 新增 source_type、connection_config、query_config，兼容 NATS |
| 执行器抽象 | 中 | registry + executor 接口 |
| REST API preview | 中 | 请求、认证、response_path、错误处理 |
| DB preview | 中偏高 | 连接、只读限制、limit、类型转换 |
| fields 推断 | 低 | 基于第一条非空记录生成字段，扫描样例行推断基础类型 |
| 前端动态表单 | 中 | 按 source_type 展示不同配置 |
| 表格预览组件 | 低到中 | 复用现有表格能力 |
| 测试 | 中 | executor fake、错误分类、权限、参数校验 |

预计 8 到 12 个工作日可完成可联调版本。如果只做 REST API，预计 4 到 6 个工作日。

## 实施顺序

1. 增加数据源类型和通用配置字段，保持 NATS 兼容。
2. 增加连接器 registry 和 executor 抽象。
3. 实现 REST API preview，先打通最短链路。
4. 实现 MySQL / PostgreSQL preview，加入只读和 limit 约束。
5. 实现 `fields` 推断并写入预览返回。
6. 前端增加来源类型选择、动态连接表单和预览区。
7. 预览成功后允许将 `fields` 保存为 `field_schema` 草稿。
8. 补充测试和错误状态。

## 验收标准

1. 数据源入口可以按来源类型创建数据源。
2. REST API 数据源可以配置 URL、认证参数、response path，并预览表格。
3. MySQL / PostgreSQL 数据源可以测试连接并预览表格。
4. 预览接口返回 `items`、`count`、`fields`。
5. 没有 `fields` 时前端仍可从 `items` 推断表格列。
6. 预览失败能区分连接、认证、查询、解析、权限和空数据。
7. 敏感配置加密存储并脱敏返回。
8. NATS 存量数据源仍可使用现有取数链路。

## 后续演进

第二阶段可以在第一阶段基础上继续建设：

1. Excel 导入型数据源。
2. 合并样例数据中出现过的所有 key，提升稀疏字段发现能力。
3. 数据集层标准化配置。
4. 字段角色：时间、维度、指标。
5. 图表推荐。
6. 一份数据集多个组件复用。
7. 轻分析层的聚合、过滤、趋势、排行。
8. 调度刷新和缓存策略。

## 结论

第一阶段建议聚焦“外部数据源快速预览链路”。核心价值是让用户先把数据接进来并看到原始表格，再进入字段标准化和图表配置。

`fields` 应加入预览返回，但作为增强信息和 `field_schema` 草稿，不作为表格展示硬依赖。这样既能快速见数，又能为后续数据集和轻分析层留下稳定接口。
