# 运营分析 · 管理

> Migrated from `spec/prd/运营分析/管理.md` as legacy capability evidence.

## 1. 背景与目标

管理维护运营分析的取数底座：数据源与命名空间，决定视图能从哪里、以何种连接取数。

## 2. 范围定义

- 数据源：供视图取数的连接与查询配置，支持 NATS、数据库、REST API、Excel 等来源。
- 命名空间：取数所用的消息连接配置。
- 场景组件接口：供网络状态拓扑等专用组件按固定参数取数。

## 3. 关键能力

### 3.1 数据源

- 维护供组件取数的数据源目录，记录名称、数据源类型、说明、查询参数定义、标签与支持的图表类型。
- 数据源类型支持：NATS、MySQL、PostgreSQL、REST API、Excel。
- 按数据源类型分别维护连接配置与取数配置；定义返回字段结构（字段名、显示名称、数据类型、描述），供表格列与图形标签复用。
- NATS 数据源可关联多个命名空间，组件查询时在运行时指定使用哪个；非 NATS 数据源按自身连接配置直接预览与取数。
- 支持增删改查、搜索与 YAML 导入导出，操作受权限控制。
- 运行时取数规则：取数入口仅接受数据源已声明的查询参数，以及运行时保留参数（命名空间、分页、查询条件），出现未声明参数则报错；时间范围参数支持分钟数、区间、起止三种形态并统一归一；标记为固定的参数强制使用配置默认值，不接受调用方覆盖。
- 数据源配置页支持测试连接 / 数据预览：数据库预览仅允许单条 `SELECT` 查询或按表限量取数；Excel 仅支持 `.xlsx` 文件并受文件大小限制。预览成功后可将识别出的返回字段一键回填为数据源默认字段定义，并支持手工增删、排序与校验唯一字段名。
- 系统随包提供内置数据源模板。内置项由系统稳定识别，用户可使用；定义内容（名称、接口、参数、字段）仍不能在常规界面编辑或删除；超管可改所属组织（空名单=全员可见，非空=白名单）。管理员执行明确的强制初始化时，才会将随包配置覆盖到已认领的内置项。相同接口地址的自定义数据源不因初始化而被转为内置。
- 数据源参数只有字符串、时间范围、日期范围、数字可标记为画布筛选项；其他类型仍可作为查询参数，但不参与统一筛选绑定。
- MySQL、PostgreSQL、REST API、Excel、Elasticsearch 使用与 NATS 相同的参数表。这五种数据源不提供条件过滤，并且只能保存一个 `timeRange` 或 `dateRange`。
- SQL、REST API、Elasticsearch 的参数名必须匹配 `^[A-Za-z_][A-Za-z0-9_]*$`。SQL 用 `:name`，范围用 `:name_start` 与 `:name_end`。SQL 结尾已有 `LIMIT`（数字或 `:参数名`，可带逗号形式或 `OFFSET`）时不再追加第二条。没有 `LIMIT` 时仍追加数字上限。REST API 和 Elasticsearch 用整段 `{{name}}`，范围用 `{{name_start}}` 与 `{{name_end}}`。REST 不替换 URL。GET 只替换查询参数，POST 同时替换请求体。`dateRange` 写入查询的结束日是最后一天的下一天，比较为大于等于开始并且小于结束。配置页预览先按用户时区把相对 `dateRange` 展开成绝对日期。
- Excel 的参数名是列名，可以是中文。取数和未保存文件的预览都先按已解析参数筛选全部已导入行，再按条数截断。已填值的列名在表头中不存在时返回 400，错误码 `param_placeholder_missing`。没填值的参数不参与筛选。
- 查询写了该数据源认识的占位符但该参数没有值时，取数返回 400，错误码 `param_value_missing`。请求里有已解析参数但查询没有对应占位符或列名时，取数返回 400，错误码 `param_placeholder_missing`。参数名用了另一种写法，而本数据源认识的占位符不在时，同样返回 400，错误码 `param_placeholder_missing`，那种写法不会被替换。字符串多选不展开成 `IN`，数组返回 400，错误码 `param_multiple_unsupported`。配置页预览保留参数表里声明的名字，包括 `page` 和 `page_size`。正式取数时，已声明的这些名字按参数自身类型取值，不再被页码规则盖掉。未声明时仍是分页和表格筛选的保留键。返回条数只在 `page_size` 为正整数时使用它。
- Prometheus 仍只保存 `query`、`query_type`、`time_range`、`step`、`max_series`。配置页不能增删或改名这些参数。

相关架构：[[legacy-ard-modules-operation-analysis#2. 数据模型与存储【已实现/已存在 / PostgreSQL】]]；对应功能清单：[[legacy-fuctionlist-09-运营分析-功能清单#5. 数据源管理]]
> 证据来源：server/apps/operation_analysis/common/builtin_datasource_identity.py:19-45，server/apps/operation_analysis/management/commands/init_source_api_data.py:95-160，server/apps/operation_analysis/serializers/datasource_serializers.py:65-83,221-243，server/apps/operation_analysis/services/datasource_params/binding.py，server/apps/operation_analysis/views/datasource_view.py:590-604，web/src/app/ops-analysis/(pages)/settings/dataSource/operateModalUtils.ts　|　同步基线：d2769559　|　【已实现】

### 3.2 命名空间

- 维护取数所用的消息（NATS）连接配置，记录名称、账号、加密密码、域名与 TLS 开关。
- 记录 NATS 命名空间标识（消息主题前缀，默认 `bklite`），用于下游消息主题寻址。
- 运行时决定视图取数连接的服务与鉴权。
- 支持增删改查与导入导出，密码加密存储、按需解密；编辑已有命名空间时若未修改密码，则保留原有密文配置，不要求用户重新输入。

### 3.3 场景组件接口

- 支持为专用场景组件提供固定形态的取数入口。
- 当前已实现网络状态拓扑接口，按模型、实例与深度参数返回拓扑关系数据。
- 当前已实现 3D 机房场景接口（包装 CMDB NATS `get_room_list` / `get_room3d_layout`），返回可见机房列表与指定机房的 row/col 网格、机柜 U 占用与设备摘要；payload 中机柜类型 `datacenter_type` 同时返回枚举 id 与可读名称 `rack_type_name`，机柜状态 `datacenter_state` 同时返回 `rack_state` / `rack_state_name`（启用/停用），无值时不带可读名。用户侧内置数据源「CMDB 机房列表（选项）」恢复为可用的动态选项源；「CMDB 3D机房布局」保持下架。
- 场景组件接口独立于普通数据源管理，不要求用户自行配置 REST API 路径。

## 4. 关键规则

- 自定义数据源按组织隔离且组织必填；内置数据源空组织对全员可见，非空为白名单。命名空间不按组织隔离（无组织归属），对全平台共享。
- 查询参数按定义的类型（字符串、数值、时间范围、下拉）约束。
- 场景组件接口参数由系统固定定义，调用方仅填写组件要求的业务参数，不走数据源参数模板校验。
- 3D 机房接口返回的机柜类型字段 `datacenter_type` 同时返回枚举 id 与可读名称 `rack_type_name`，机柜状态字段 `datacenter_state` 同时返回 `rack_state` / `rack_state_name`，由后端依据 `rack` 模型枚举属性解析；缺值时仅返回 id。
- 数据库预览仅支持单条 `SELECT`；系统会自动补齐或钳制预览条数上限，阻止多语句执行。
- 数据源默认字段定义中的字段名必须非空且唯一；展示名称、数据类型、描述可按数据预览结果回填后再人工修订。
- 数据源连接配置中的密码、令牌、密钥等敏感字段加密 / 脱敏处理，编辑时允许保留既有掩码值；命名空间编辑若沿用掩码占位则视为“密码不变”，不会覆盖原配置。

相关架构：[[legacy-ard-modules-operation-analysis#3. 接口【已实现/已存在】]]；对应功能清单：[[legacy-fuctionlist-09-运营分析-功能清单#5. 数据源管理]]
> 证据来源：server/apps/operation_analysis/serializers/datasource_serializers.py:11-43,66-103，web/src/app/ops-analysis/(pages)/settings/dataSource/operateModalUtils.ts:106-138，server/apps/operation_analysis/services/datasource_preview/database.py:15-45　|　同步基线：a9d981aeb　|　【已实现】

## 5. 关键技术架构选择

- NATS 数据源取数经命名空间对应的消息连接路由到下游服务，下游统一返回结构化结果后归一校验。
- 数据库、REST API、Excel 数据源支持在管理页内联预览，预览结果自动推断字段结构，并可一键生成或刷新数据源默认字段定义。
- 专用场景组件接口可绕过普通数据源目录，直接经模块服务层返回结构化结果。
- 配置支持 YAML 导入导出。

相关架构：[[legacy-ard-modules-operation-analysis#4. 依赖与通信【已实现/已存在】]]；对应功能清单：[[legacy-fuctionlist-09-运营分析-功能清单#7. 数据拉取与聚合]]
> 证据来源：server/apps/operation_analysis/views/datasource_view.py:72-79,411-529，server/apps/operation_analysis/services/datasource_preview/schema.py:1-33，web/src/app/ops-analysis/(pages)/settings/dataSource/previewPanel.tsx:63-81　|　同步基线：8a12d3b　|　【已实现】

## 6. 验收标准

- 用户可配置 NATS、数据库、REST API、Excel 四类以上数据源，并定义查询参数与默认返回字段结构。
- 命名空间可配置连接与鉴权，密码加密存储。
- 网络状态拓扑、3D 机房等专用组件可通过固定接口获取结构化场景数据；3D 机房接口返回字段含 `rack_type_name` 可读类型名。
- 自定义数据源按组织隔离且组织必填；内置数据源空组织对全员可见，非空为白名单。命名空间全平台共享；二者均可导入导出。
- 数据源配置页可在保存前完成连接测试或预览，且敏感配置不以明文回显。
