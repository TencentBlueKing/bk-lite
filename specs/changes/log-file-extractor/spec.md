# 日志提取器

Status: implemented

## Problem Statement

日志采集实例上报的事件通常把可检索信息留在 `message` 等文本字段中。运维人员无法在不修改采集端配置的前提下，把状态码、用户、路径、耗时等内容稳定提取为结构化字段，因而难以继续用于日志过滤、聚合、仪表盘与告警。

当前真实数据链路是：非默认云区域只部署 proxy 与 fusion-collector，将区域 NATS 数据转发至 Server NATS；只有默认部署运行中心系统 Vector，由它从 Server NATS 接收所有区域的日志、处理后写入 VictoriaLogs。fusion-collector 内把 logstash、syslog、SNMP 等输入写入 NATS 的采集侧 Vector，不是中心系统 Vector。现有日志采集模板已经为事件写入全局唯一的 `instance_id`，`CollectInstance.id` 就是该标识，实例组织关系与 View/Operate 权限也已存在。因此，按云区域生成配置、给实例补区域、经 NodeMgmt 或 webhookd 下发配置都会描述错误的执行链路，并扩大数据模型与部署耦合。

规则保存与运行配置发布还需要解耦：用户规则必须能可靠保存，但一次生成、任务投递或中心系统 Vector 拉取失败不得丢日志、阻断采集或销毁上一份有效配置。同时，产品只能表达 Server 已经发布配置，不能把“Vector 是否已经拉取并应用”伪装成可观测状态。

## Solution

在每个日志采集实例的管理入口中提供“日志提取器”抽屉。用户可以创建、编辑、删除、完整调序、用历史样本预览和手工重试规则发布。第一版支持 copy、split、kv、regex、regex_replace、json 六类动作；规则按实例顺序执行，后一规则可以读取前一规则生成的字段。

所有用户规则由 Server 编译成一份部署级完整 Vector YAML。任意规则事务提交后只递增一个全局 generation，并在提交后异步生成快照；只有最新 generation 可以原子替换最后成功发布的快照。默认部署的中心系统 Vector 使用 Vector 0.48 原生 HTTP configuration provider，每 30 秒凭部署级机器 Token 拉取最后成功快照。最新生成失败时，配置接口继续提供上一份有效 YAML。

事件始终先按不可绕过的 `instance_id` 匹配，再判断用户附加条件。缺少源字段、类型不适用或解析失败只跳过当前规则，后续规则仍继续，原事件仍进入 VictoriaLogs。系统保护字段不会被覆盖或删除，源字段也只会在当前规则成功后删除。

## User Stories

1. As a 日志运维人员, I want to manage ordered extractors on a collection instance, so that I can turn raw log text and nested attributes into searchable fields without changing collectors.
2. As a 日志运维人员, I want to choose nested source, condition and target attributes and preview a draft against recent instance events, so that I can verify the rule before saving it.
3. As a 日志运维人员, I want a skipped or failed rule to preserve the event and continue later rules, so that a parsing mistake cannot interrupt log delivery.
4. As a 日志管理员, I want extractor changes from every instance to share one publication status and retain the last valid configuration on failure, so that I can understand and retry publication safely.
5. As a 日志管理员, I want “published” to describe only what the Server can provide, so that I do not mistake it for configuration already applied by Vector.
6. As a 部署管理员, I want the central Vector to retrieve configuration through a dedicated machine-authenticated OpenAPI, so that it does not depend on an interactive user session.

## Implementation Decisions

### 1. 领域边界与真实链路

- “日志采集实例”是规则归属、运行时匹配、权限与数据范围的共同对象；“日志提取器”是一条绑定该实例的有序规则。第一版 API 与 UI 必须绑定真实日志采集实例，不允许创建无实例规则。
- 数据库外键保持可空，只为未来接入没有实例身份的日志预留数据演进空间。该可空性不是第一版业务状态：列表、创建、编辑、预览、编译均只处理实例非空的规则，接口不得接受或返回可创建空实例规则的能力。
- 不为提取器新增或回填 `CollectInstance.cloud_region_id`，也不在提取器冗余保存 `cloud_region_id`。存量 `CollectInstance` 无需迁移业务数据即可直接创建规则。
- 所有已经经过中心系统 Vector 的日志采集类型立即开放提取器入口，不维护采集类型能力矩阵，也不按 collector 名称做前后端显隐。
- 中心系统 Vector 是唯一提取执行端。区域 proxy、fusion-collector、采集侧 Vector、webhookd、新增云区域部署及 NodeMgmt 配置推送不参与提取器配置更新；不得设计 `NodeMgmt.update_system_vector_config` 或任何按区域 Token、generation、状态、配置文件。
- 配置运行时只按事件的全局唯一 `instance_id` 与 `CollectInstance.id` 精确匹配。用户条件永远只能附加在实例硬条件之内，不能替换、否定或绕过它。

### 2. 深模块与接口

采用两个深模块和一个认证适配器，调用方与测试均通过这些接口，不穿透内部状态：

- 规则业务模块的外部接口负责“创建规则、更新规则、删除规则、完整调序、预览规则、读取历史样本、重试发布”。它隐藏数量限制、排序锁、条件与类型校验、权限所需的实例解析、操作审计，以及一次业务事务只触发一次发布标脏。实例删除通过该模块一次删除其规则并触发一次发布，不依赖逐行信号造成多次 generation 递增。
- 全局配置发布模块只提供 `mark_dirty`、`publish_generation`、`get_published_snapshot` 三个外部接口。它隐藏全局锁、generation fencing、稳定编译、checksum、状态转换、Celery 投递、幂等与失败时保留旧快照。规则业务调用方不查询或修改发布状态表，也不理解 YAML、Vector、Token 或任务细节。
- 配置读取认证使用一个专用适配器解析 Bearer Token、校验摘要并产生仅能读取中心 Vector 配置的机器身份。只有这一种生产认证实现，不再为假想替换创建额外 port 或抽象层；用户 Session、普通平台 API Token、组织和云区域身份都不能通过该 OpenAPI。
- 规则规范化、保存校验、样本预览与 Vector 规则编译共享同一份类型定义和语义判断。允许预览执行器与 VRL 编译器作为发布模块内部接缝分别测试，但不得让 API、任务或 UI 各自复制类型规则。
- 模块删除测试成立：若删除规则业务模块，数量、排序、校验与审计会散落到多个接口；若删除发布模块，锁、fencing、编译、快照和失败保留会散落到 CRUD、任务与配置读取接口。这两个模块都应保持小接口和高行为杠杆。

### 3. 日志提取器数据模型

每条提取器记录包含：

| 字段 | 约束与语义 |
| --- | --- |
| `name` | 1–200 字符；同一非空实例内唯一 |
| `collect_instance` | 可空外键；删除实例时级联删除；第一版输入必填且更新时不可更换或清空 |
| `condition` | 结构化附加条件；空对象表示实例内全部事件 |
| `extractor_type` | `copy`、`split`、`kv`、`regex`、`regex_replace`、`json` 之一 |
| `source_field` | 合法的任意嵌套对象属性路径；默认 `message` |
| `target_field` | 合法的任意嵌套对象属性路径；单字段动作写入该路径，json 可用它指定整体对象的目标父路径，按类型决定必填或可空 |
| `delete_source` | 默认 false；只在当前动作成功后执行 |
| `config` | 经类型判别校验的 JSON 对象，不接受未声明键 |
| `sort_order` | 实例内从 0 开始连续；同一非空实例内唯一；不可由普通编辑接口修改 |
| 审计字段 | 复用创建/更新人、域与创建/更新时间字段 |

数据库使用实例内条件唯一约束保证 `name` 与 `sort_order` 唯一，并为 `(collect_instance, sort_order, id)` 的稳定读取建立索引。不得增加组织、云区域、单规则发布状态或启停字段。

单实例最多 20 条规则。创建在实例级锁内检查数量并追加到末尾；删除后压缩后续顺序；完整调序必须提交该实例当前全部规则 ID，集合必须完全相同、无重复、无其他实例 ID，并在一个事务内原子更新。名称冲突、数量超限、残缺调序和并发唯一冲突返回可定位的 400，不暴露数据库异常。

创建、编辑、删除与调序每次成功业务事务只调用一次 `mark_dirty`。普通编辑不能修改实例和 `sort_order`。删除日志采集实例时，规则删除与实例删除同处一个事务，并在提交后只递增一次全局 generation；不得让级联删除绕过发布刷新。

`source_field`、条件中的 `field` 与 `target_field` 使用同一属性路径契约：路径由一个或多个非空对象属性段组成，允许任意嵌套深度；普通属性段使用点分形式，包含点、空格、引号或其他合法字符的属性名使用带转义的引用段。数组下标不属于第一版属性路径。后端解析并输出唯一的规范形式，UI 通过属性选择器生成路径，不能把用户输入直接拼成 VRL。路径的相等、祖先与后代关系都在解析后的属性段序列上判断，不能用字符串前缀近似判断。

### 4. 条件模型

用户不能提交 VRL。`condition` 是由以下字段组成的结构化对象；空对象与空条件列表都表示没有用户附加条件：

| 字段 | 契约 |
| --- | --- |
| `mode` | `AND` 或 `OR`，省略时为 `AND` |
| `conditions` | 条件项列表；第一版不支持嵌套条件组 |
| 条件项 `field` | 当前规则动作执行前事件快照中的合法嵌套属性路径 |
| 条件项 `op` | 下述固定操作符之一 |
| 条件项 `value` | 除存在性操作符外必填的 JSON 标量 |

- 操作符只允许 `==`、`!=`、`contains`、`!contains`、`startswith`、`endswith`、`exists`、`!exists`。
- `exists` 与 `!exists` 不接受 `value`；其余操作符必须有 JSON 标量 `value`。`contains`、`!contains`、`startswith`、`endswith` 的值必须是字符串。
- 每条规则先取得动作执行前的事件快照，再对该快照求值全部条件，最后在条件命中时读取源属性并执行动作。快照包含原始事件和所有前序规则输出，不包含当前规则动作产生的字段；保存阶段不尝试静态推断动态输出是否存在。
- 字段不存在时：`exists` 为 false，`!exists` 为 true，其余操作符为 false；类型不适用于字符串操作时为 false，不产生事件错误。
- `==` 与 `!=` 按规范化后的 JSON 标量类型比较，不做隐式数值/字符串转换。
- 编译后的实际谓词始终是 `instance_id == collect_instance.id AND 用户附加条件`。即使用户条件为空、为 OR 或引用 `instance_id`，实例硬匹配也位于用户表达式之外且不可修改。

### 5. 六类提取动作

| 类型 | `target_field` | `config` | 成功输出 |
| --- | --- | --- | --- |
| `copy` | 必填 | 空对象 | 把源字段原值复制到目标字段，不做字符串转换 |
| `split` | 必填 | `delimiter` 非空字符串、`index` 非负整数 | 把源字符串按固定分隔符切分，写入指定下标元素 |
| `kv` | 留空 | `key_value_delimiter`、`field_delimiter` 为非空字符串；`field_mapping` 可选地把解析键映射到无重复的目标属性路径 | 有映射时只写映射中实际存在的键，否则把全部非保护键合并到事件根 |
| `regex` | 留空 | `pattern` 为 1–2000 字符且至少一个命名捕获组；`group_mapping` 可选地把捕获组映射到无重复的目标属性路径 | 有映射时按映射写入，否则以捕获组名写入事件根 |
| `regex_replace` | 可空 | `pattern` 为 1–2000 字符，`replacement` 为下述受控替换字符串 | 替换全部匹配；有目标字段时写目标字段，目标为空时覆盖源字段 |
| `json` | 可空 | 空对象 | 源字符串必须解析为 JSON 对象；有目标字段时把对象写入该嵌套父路径，否则把非保护字段合并到事件根；标量和数组不是成功结果 |

未声明的 `config` 键、非法字段路径、非法正则、越界 split 下标、错误源类型或不能产生输出的解析都不能被默认为成功。保存阶段能确定的结构错误返回 400；只有依赖样本内容的失败进入运行时隔离语义。

`field_mapping` 与 `group_mapping` 都是“解析键/捕获组名 → 规范化目标属性路径”的结构化映射：键必须非空且在同一映射内唯一，目标路径也不能重复；`group_mapping` 只能引用 pattern 中实际存在的命名捕获组。映射未列出的键或捕获组不写入事件。该映射让多输出动作也能选择合法的任意嵌套目标属性，而不是把动态名称当作未经校验的路径。

`regex_replace.replacement` 使用一套与 Vector 0.48 对齐的受控语法：`${name}` 引用已有命名捕获组，`${1}` 引用已有编号捕获组，`$$` 表示一个字面量 `$`；孤立 `$`、不存在的捕获组和其他 `$...` 形式保存时拒绝。反斜杠没有替换层特殊含义，只作为普通字符再由编译器做 VRL 字符串转义。编译器负责额外处理 Vector 配置环境插值所需的 `$` 转义，API 与数据库始终保存上述逻辑形式。模式没有匹配时本事件上的规则结果为 `failed`，不写目标、不覆盖或删除源；有匹配时替换全部匹配项。

保存 `delete_source=true` 前必须计算本规则的全部可能输出路径，并拒绝任何与源路径重叠的规则。重叠包括输出等于源、输出位于源子树内、源位于输出子树内；判断基于规范化属性段。copy、split、regex_replace 检查其单一目标，regex 检查映射后或默认的全部捕获组输出，带 `field_mapping` 的 kv 检查全部映射输出，带目标父路径的 json 检查该父路径。没有映射的 kv 与没有目标父路径的 json 输出取决于事件内容，无法在保存时穷尽，因此第一版不允许它们设置 `delete_source=true`。这样删除动作不会同时删除或破坏本规则刚写入的单字段或多字段输出。

### 6. 执行顺序、字段保护与失败隔离

- 一个事件仅进入其 `instance_id` 对应实例的规则序列。规则固定按 `sort_order`、`id` 执行；同序并发写由数据库约束阻止。
- 每条规则在当前事件上独立判断条件和源字段。前序成功输出立即进入事件，后序规则可以读取；多条规则写同一普通字段时后写覆盖前写。
- 源字段不存在时跳过当前规则。除 `copy` 外需要文本输入的动作在源值不是字符串时跳过；解析函数返回错误、split 下标不存在、JSON 不是对象、regex/regex_replace 无匹配或 kv 没有可写键时，本事件上的当前规则执行结果为失败。跳过或失败都继续下一规则。
- Vector remap 必须使用可失败调用的结果/错误分支，不使用会中断 transform 的 bang 调用；transform 设置 `drop_on_error: false`。条件不匹配、单规则失败和全部规则失败都保留当前事件，并继续进入 VictoriaLogs sink。
- `instance_id`、`source_type`、`timestamp` 是保护字段。任何源删除路径、目标路径、regex 默认/映射输出或 kv 映射输出以保护字段为根时，保存即拒绝；kv/json/regex 的动态根合并在运行时再次移除这些根字段。用户输入绝不能覆盖或删除原保护值。
- 保护字段与 `message` 均不能作为删除源字段的目标。`message` 可以被 `regex_replace` 显式覆盖以支持脱敏，但不能删除。目标为空的 `regex_replace` 与 `delete_source=true` 组合无意义，必须拒绝。
- `delete_source=true` 只在当前规则确认至少一个经过路径安全检查的预期输出成功写入后执行。条件不匹配、源缺失、类型不适用、解析失败或没有输出时，源字段保持不变。
- 字段路径、实例 ID、字符串、分隔符、replacement 与 regex 必须由编译器按其目标语法转义，不能直接拼接。规则名称等展示文本不进入 VRL 注释，避免换行或注释注入。

### 7. 历史样本与草稿预览

- 历史样本读取要求目标日志采集实例的 View 权限，并强制在查询最外层追加精确 `instance_id` 条件；用户附加查询不能移除该条件。第一版样本接口不接受自定义时间范围，由现有日志搜索模块应用其 15 分钟默认窗口；返回条数复用现有日志搜索的默认值与可配置硬上限，不新增 20/50 条或 24 小时等提取器专属产品限制。非法或超限 `limit` 返回 400 后不访问 VictoriaLogs。
- 样本查询失败只在抽屉内显示可重试错误，不影响编辑、保存或配置发布。服务端错误与日志不得记录完整原始事件。
- 预览请求包含一个选定事件和一条未保存的规范化草稿。服务端以真实实例 ID 覆盖请求事件中同名字段，防止跨实例伪造；预览不保存规则、不递增 generation、不写回 VictoriaLogs。
- 编辑已有规则时，先依序执行该规则之前的已保存规则，再执行草稿；新建规则时先执行该实例全部已保存规则，再把草稿作为末尾规则执行。这样预览与正式顺序一致。
- 每条预览结果使用四个穷尽状态：`success`（条件命中且动作产生输出）、`not_matched`（附加条件不命中）、`skipped`（源字段缺失或类型不适用）、`failed`（条件命中但解析、匹配、索引或输出失败）。响应返回规则后的事件副本和每条规则状态，但失败消息只含错误类别与字段定位，不回显凭据或整条原始日志。
- 预览执行器与 VRL 编译器共用一份表驱动契约样例，而不是各自维护相似测试。每个样例声明动作、动作前事件、AND/OR 条件、预期结果状态和动作后事件；同一批样例分别在 Python 预览与 Vector 0.48 运行，覆盖六类动作、缺字段、条件不匹配、解析失败保留、字段覆盖和 `delete_source`，两端输出必须一致。

### 8. API、权限与审计

- 登录态业务 API 提供按实例列表、创建、详情、编辑、删除、完整调序、历史样本、草稿预览、手工重试和全局发布状态查询。CRUD 响应返回已持久化资源及当时可观察的全局发布状态；不得伪造实例级或区域级状态。
- 上述业务 API 继续使用用户登录态、View/Operate 与 `current_team`。中心 Vector 不调用业务 API；它只调用日志模块 OpenAPI 的配置读取接口并使用部署级全局 Bearer Token。
- 列表、详情、历史样本与预览要求日志采集实例的 View 权限；创建、编辑、删除、调序与手工重试要求 Operate 权限。所有权限判断复用 `CollectInstance` 的既有权限规则与 `current_team` 数据范围，提取器不建立组织关系。
- 未提供有效 `current_team` 或权限系统明确拒绝时 fail closed。实例/提取器不在当前团队数据范围、资源不存在或 ID 属于另一实例时返回 404，避免对象枚举；对象可见但缺少所需动作权限时返回 403。超级管理员沿用实例模块现行语义。
- 后端始终从提取器反查实例后授权，不能仅凭提取器 ID 更新；完整调序和预览中的已有规则 ID 也必须属于已授权实例。前端按钮禁用只改善交互，不替代后端校验。
- 创建、编辑、删除、调序与手工重试成功后使用统一操作日志能力记录中文摘要，app 标识为 `log`；审计包含实例 ID、规则 ID/名称、动作和 generation（适用时），不包含规则生成的 YAML、Token、原始样本或未脱敏错误。操作日志失败不回滚业务。
- 规则事务提交后的 Celery 投递发生在 `transaction.on_commit` 回调内。发布模块必须在回调内部捕获投递异常：若该 generation 仍是最新且尚未发布，则记录脱敏错误并置为 `failed`，且绝不把异常重新抛回已完成的 CRUD 请求。客户端得到的是已保存资源和真实发布状态，不能因提交后投递失败收到暗示业务事务回滚的 500。

### 9. 全局发布状态与快照模型

系统只有一条 `scope=global` 的发布状态记录：

| 字段 | 语义 |
| --- | --- |
| `scope` | 固定且唯一为 `global` |
| `desired_generation` | 最新业务规则状态需要发布的 generation |
| `published_generation` | `published_content` 对应的最后成功 generation |
| `status` | `pending`、`generating`、`published`、`failed` 之一 |
| `published_content` | 最后成功发布的原始完整 YAML；初始发布前为空 |
| `published_checksum` | 原始 UTF-8 YAML 的 SHA-256，初始发布前为空 |
| `last_error` | 最新 generation 的脱敏错误类别与简短摘要，最长 500 字符 |
| `last_published_at` | 最后成功替换快照的时间，初始发布前为空 |

状态只描述 Server：

- `pending`：规则事务已提交，最新 generation 等待任务。
- `generating`：最新 generation 正在编译完整 YAML。
- `published`：Server 已原子保存该 generation 的快照；不表示中心系统 Vector 已拉取、校验、重载或对事件生效。
- `failed`：最新 generation 未能生成或保存快照；最后成功快照（若有）仍可读取。

不得出现 `applying`、`applied`、`succeeded`、区域状态、单规则状态或推测 Vector 在线情况的字段。全局状态可以是 `failed` 且 `published_generation < desired_generation`，这不是矛盾：它明确表示新规则尚未发布、旧快照仍在服务。

### 10. generation、并发与幂等

- `mark_dirty` 在规则业务事务内锁定全局状态，将 `desired_generation` 恰好加 1、状态置为 `pending`、清空当前 generation 的错误；同一创建、编辑、删除或完整调序事务不论影响多少行都只增加一次。
- Celery 投递只在业务事务提交后执行，并携带当时 generation。事务回滚不投递。broker 投递失败不回滚规则；发布模块仅在该 generation 仍最新且未发布时把状态置为 `failed` 并保存脱敏错误，用户可手工重试。
- `publish_generation(generation)` 的入口在任何状态写入前锁定并读取全局状态，首先判断 `published_generation >= generation`；成立时按“已完成”直接退出，不能把 `published` 改回 `generating`。尚未发布时再比较 `desired_generation`：不相等即作为过期任务退出且不改状态，只有相等的最新 generation 才置为 `generating`，随后查询全部实例规则并在锁外编译。
- 快照替换在一个短事务中锁定全局状态并再次比较 `desired_generation`。只有仍等于任务 generation 时才原子写入 content、checksum、`published_generation`、`published` 与时间。规则变更的 `mark_dirty` 使用同一行锁，因此“最终校验”和“新 generation 递增”有明确串行顺序。
- generation 是旧任务 fencing token。旧任务的成功或失败都不能覆盖新 generation 的状态或快照。
- 同 generation 重复任务必须幂等。成功回写以 `published_generation >= generation` 为完成条件；一个重复执行已发布后，另一个同 generation 的迟到失败不能把状态改成 `failed`。确定性编译保证同 generation 的成功任务得到相同字节与 checksum。
- 手工重试只允许目标实例具备 Operate 权限的用户触发，并始终针对当前全局 `desired_generation`；状态为 `failed`、`pending` 或 `generating` 时均可把同一 generation 重新置为 `pending` 并投递，不递增 generation。`published_generation == desired_generation` 且状态为 `published` 时返回 409，避免制造无意义新版本。重复投递由同 generation 幂等规则吸收。
- 发布任务采用 worker 丢失后重新入队的确认语义，并为可重试基础设施错误设置有界重试；任何正常异常都必须经过同一失败回写。即使 worker 在回写前退出，用户仍可重试相同 generation，不需要增加伪造的租约状态。
- 编译或持久化失败只把仍为最新且尚未发布的 generation 标记为 `failed`；不得清空或覆盖 `published_content`、`published_checksum`、`published_generation` 与 `last_published_at`。

### 11. 完整 Vector YAML 编译

- 每次发布查询所有实例的所有第一版有效规则，按 `collect_instance_id`、`sort_order`、规则主键稳定排序，生成一份全局完整 YAML。查询和编译不按组织、current_team、采集类型或云区域过滤。
- 同一份 YAML 可同时包含来自默认及非默认云区域的多个实例规则；运行时各分支只比较 `instance_id`。配置中不出现 `cloud_region_id`。
- 完整拓扑固定为 `Server NATS source → 现有事件 JSON 规范化 → log extractor remap → VictoriaLogs sink`。没有任何规则时仍保留相同 source、transform、sink，extractor transform 使用显式 no-op；不能因规则数量为零切换拓扑或返回空文件。
- 编译器只替换 extractor transform 的受控规则源，其余生产 source/sink、TLS、NATS 与 VictoriaLogs 环境占位符来自同一完整模板。YAML 使用安全解析/序列化，固定键顺序、换行与 UTF-8 编码；相同规则状态必须生成逐字节相同内容。
- 动态值全部经过 VRL 字符串、字段路径和 regex 转义。编译期间发现数据库中存在不符合现行规则规范的数据时，整个 generation 失败并保留旧快照，不能静默略过坏规则后发布部分配置。
- 发布前至少完成 YAML 结构、固定拓扑、VRL 片段与保护字段不变量校验。发布模块测试和部署验收使用固定 Vector 0.48 二进制/镜像验证完整远程 YAML；不以较新 Vector 的宽松行为替代 0.48 契约。
- `published_checksum` 是最终原始 UTF-8 YAML 字节的 SHA-256。GET 接口直接返回这些已存字节，不在请求中查询规则、重新编译、重新序列化或注入凭据。

### 12. 部署级机器 Token 与配置读取认证

- 一个默认部署只维护一个活动的高熵机器 Token，固定 `scope=global`，只允许读取中心系统 Vector 配置。Token 不关联用户、角色、组织、云区域或规则写权限。
- 管理命令负责首次生成与轮换。明文至少包含 256 bit 随机熵，数据库只保存带盐的单向摘要与创建/轮换审计时间，不保存可还原密文。明文不得进入应用日志、异常、指标、任务参数或操作日志。
- Token 校验使用常量时间的安全摘要验证。每次命令执行都会生成新 Token 并原子替换摘要；数据库提交成功后旧 Token 立即失效，不保留双 Token 宽限期，然后把新明文写到受控标准输出并提示操作者更新默认部署 Secret、重启中心系统 Vector。
- 数据库提交与标准输出无法形成同一原子事务，命令不得承诺操作者一定收到已提交 Token 的明文。如果提交后输出丢失、终端中断或操作者未保存明文，重复执行同一命令会再次轮换并输出另一个新 Token，前一次 Token 随新摘要提交而失效。任何输出失败都不得把明文补写到日志或数据库。
- 同一管理命令在首次安装时还确保全局状态与完整 no-op 快照存在。状态不存在时以 generation 1 编译当前全部规则并发布；状态存在但从未成功发布时，以当前 `desired_generation`（若为 0 则先置 1）编译并发布；一旦 `published_content` 存在，快照确保步骤不递增 generation、不重新编译也不覆盖快照。快照确保失败时不轮换 Token；快照成功后才进入上述每次执行均轮换 Token 的步骤。
- Token 缺失、格式错误或摘要不匹配统一返回 401，并带 `WWW-Authenticate: Bearer`；响应和日志不区分不存在与不匹配，不回显 Token。认证在读取快照之前完成。

### 13. 中心配置 GET 接口

中心配置读取是日志模块 OpenAPI，路由固定为 `GET /api/v1/log/open_api/system_vector/config/`。请求必须携带 `Authorization` 头，认证方案为 `Bearer`，凭据是部署级全局 Token；该契约是已确认接口设计，不是原型代码。

- 有有效 Token 且存在至少一份成功快照时返回 200，body 是 `published_content` 的原始字节，`Content-Type: application/yaml; charset=utf-8`。
- 200 响应包含 `X-Config-Checksum: sha256:<sha256-hex>`、`X-Config-Generation: <published_generation>` 与 `Cache-Control: no-store`。checksum 对应响应 body，generation 对应已发布版本而不是 desired generation。第一版不返回 ETag，因为 Vector 0.48 provider 不发条件请求，重复表达同一摘要没有当前消费者。
- 有效 Token 但尚无成功初始快照时返回 503。当前最新 generation 为 `pending`、`generating` 或 `failed`，只要旧快照存在就仍返回旧快照 200。
- 缺少、错误或已轮换失效的 Token 返回 401。接口不接受 Session 或普通平台 API Token 作为替代，也不提供写方法。
- 请求处理只调用 `get_published_snapshot`，不读取提取器表、不触发任务、不计算 YAML。读取失败不得返回半份内容。

### 14. Vector 0.48 HTTP provider 与部署顺序

- 默认部署中心系统 Vector 使用最小本地 bootstrap 配置，其中只能声明原生 HTTP provider：类型 `http`、配置 URL、30 秒 `poll_interval_secs`、`config_format: yaml`，以及从部署环境注入的 `Authorization: Bearer ...` 请求头。provider 配置与 sources/transforms/sinks 不能同时出现在 bootstrap 文件中。
- Vector 0.48 provider 配置不使用不存在的 `interpolate_env` 字段。URL 与 Token 通过 0.48 支持的标准环境变量占位符注入，真实 Token 只进入部署 Secret/环境，不进入远程 YAML 或仓库模板。
- 固定安装顺序是：数据库迁移 → 运行管理命令生成 Token并确保 no-op 初始快照 → 启动 Server → 携该 Token 探测配置接口并验证 200、checksum 与 generation → 启动中心系统 Vector。
- Vector 0.48 在首次 provider GET 或配置解析失败时无法构建初始拓扑；第一版由中心 Vector 容器重启策略重试，不增加 sidecar 或启动脚本轮询器。
- 运行中 provider 每 30 秒轮询。HTTP/网络失败或返回内容无法构建配置时保留当前拓扑并等待下次轮询；Server 侧又只暴露成功快照，因此失败 generation 不会替换运行端可拉取内容。
- 远程配置成功发布不等于运行端已应用。第一版没有回调、心跳、last-seen、精确 applied 状态、本地 sidecar、按区域配置或 Vector 控制接口。
- 默认部署资产新增中心 Vector bootstrap、Token Secret 注入和重启策略；非默认云区域部署、proxy、fusion-collector、采集侧 Vector、系统级 Telegraf 与 webhookd 资产保持不变。

### 15. 前端交互

- 入口位于日志集成的采集实例行操作中，对所有采集类型一致显示，打开“`<实例名称> · 日志提取器`”抽屉。不得从日志搜索页反向新建。
- 抽屉使用现有 Ant Design、表格/空状态/权限组件和日志模块局部组件。它展示按顺序的规则、名称、条件摘要、类型、源字段、目标摘要和操作；无规则时展示说明与“新建提取器”，不自动生成默认规则。
- 新增与编辑使用自适应视口的弹窗，包含可见 label、结构化条件编辑、类型专属字段、删除源字段与历史样本预览。较长内容在弹窗主体内滚动，保存/取消始终可见；错误紧邻字段并聚焦首个错误。
- 调序采用明确拖拽手柄并提交完整 ID 序列；键盘用户可以用上移/下移完成同一操作。删除有后果确认；所有写按钮有 loading/disabled 防重复提交。
- 抽屉展示的是“全局配置发布状态”，并明确可能受其他实例规则变更影响。文案分别为“等待发布 / 正在生成 / 已发布 / 发布失败”；“已发布”附 generation 与时间，并说明不代表 Vector 已拉取。失败展示脱敏摘要和 Operate 用户可见的“手工重试”。
- 保存成功后立即刷新规则与全局状态，不等待发布；发布状态以轮询刷新。View 用户可查看规则、状态、样本与预览，只有 Operate 用户能新建、编辑、删除、调序和重试。
- loading、empty、error、只读、权限受限、长名称、窄抽屉、亮色/暗色与中英文状态均需验证；颜色不是状态的唯一表达。第一版不新增 shared 组件，除非实现时已经出现两个以上真实 app 使用方。

### 16. 失败降级与运行可观测性

| 失败 | 对外行为 |
| --- | --- |
| 规则输入校验失败 | 400 字段级错误；不落库、不递增 generation |
| 实例越权或 ID 跨实例 | 403/404 按权限规则返回；无副作用 |
| 历史样本查询失败 | 抽屉可重试；不影响保存与发布 |
| 规则运行时缺字段/类型不适用 | 跳过当前规则，继续后续规则并保留事件 |
| regex/kv/json/split 运行失败 | 本事件上的当前规则预览/运行结果为 `failed`，不形成持久状态；继续后续规则并保留事件 |
| Celery 投递失败 | 规则保留；最新 generation 标记 `failed`；允许手工重试 |
| YAML/VRL 编译或快照写入失败 | 最新 generation 标记 `failed`；继续提供上一快照 |
| 旧或重复任务迟到 | fencing/幂等判断后无状态破坏 |
| 配置 GET 无/错 Token | 401；不泄露快照或 Token 信息 |
| 配置 GET 尚无初始快照 | 503；部署探测失败，中心 Vector 暂不启动 |
| Vector 首次拉取失败 | 进程启动失败，由容器重启重试 |
| Vector 运行中拉取/解析失败 | 保留当前拓扑，等待下一次轮询 |

产品状态中的 `last_error` 与业务 API 只暴露脱敏错误摘要。受控应用日志沿用现有可靠性与敏感信息规范，记录定位发布问题所需的 generation、published generation、checksum、规则数量、耗时、状态，以及清理敏感数据后的底层异常类型、消息和堆栈；不记录完整 YAML、Token、原始事件、条件比较值或 replacement。第一版不新增一套未经确认的强制指标集合，也不把内部可观测性升级为产品 applied 状态。

### 17. 兼容、迁移与回滚

- 数据迁移只新增提取器、全局状态和 Token 摘要所需表/约束；不修改或回填日志采集实例的云区域字段，不迁移旧分支的区域模型。
- 本功能没有旧生产提取器数据需要导入，无默认、内置或启动预置规则。旧 `codex/log-extractor` 分支不作为迁移来源，也不 cherry-pick。
- 上线前管理命令生成初始 no-op 快照，因此即使没有规则，中心系统 Vector 也能得到完整拓扑。非关键快照重建失败不得加入 Server 通用启动必经路径；部署探测负责阻止中心 Vector 在无快照时启动。
- 回滚应用版本时，最后成功快照仍保留在数据库；回退中心 Vector 部署可恢复原静态配置。删除新表前必须先停止 HTTP provider 并恢复静态中心配置，避免运行端在下一次重启时没有初始拓扑。
- 第一版发布是新增能力，不改变既有采集模板的 `instance_id`、区域转发、日志查询和 VictoriaLogs 存量数据；历史日志不重新处理。

## Testing Decisions

### 测试接缝

- 规则业务模块接口是 CRUD、排序、权限、预览和审计的主要测试面。测试可使用真实 Django ORM 与现有请求/权限 fixture，但只断言可观察结果，不依赖内部 helper 调用次数；发布模块只在一次事务一次 generation 这个接口契约处替换。
- 全局配置发布模块接口是并发、fencing、编译、快照、失败保留和读取的主要测试面。使用真实数据库事务验证状态转换，Celery 仅在任务投递适配器处替换；不直接修改状态表伪造成功路径之外的实现细节。
- 配置认证适配器通过真实 HTTP 请求测试 Bearer 解析、摘要校验和响应，不 mock 掉认证本身。
- 规则纯语义与编译器使用表驱动测试；部署集成使用固定 Vector 0.48 镜像验证 bootstrap provider 和完整远程 YAML。前端复用现有日志脚本测试方式覆盖纯交互逻辑，并在真实页面或 Storybook 验证状态与主题。
- 既有先例包括日志采集实例权限/current_team 测试、日志搜索服务测试、模板沙箱渲染测试、Celery 状态与事务测试、以及日志集成页的纯逻辑脚本。新测试沿用 `_pure`、`_service`、`_views` 分层和 unit/integration 标记。

### 必须覆盖的验收场景

1. 创建属于不同云区域来源的多个日志采集实例规则，编译结果只有一份完整 YAML，包含各实例的精确 `instance_id` 分支且不含区域字段。
2. 数据库没有规则时，初始及后续发布均得到包含 NATS source、no-op extractor transform、VictoriaLogs sink 的完整有效配置。
3. 创建、编辑、删除和一次完整调序各只使全局 `desired_generation` 增加 1；事务回滚不增加、不投递；删除实例及其多条规则也只增加 1。
4. `publish_generation` 收到 `published_generation >= generation` 时在任何状态变更前直接结束；旧 generation 在编译前或提交快照前发现过期时不覆盖新状态；同 generation 重复成功幂等；同 generation 的迟到失败不能把已发布状态改失败。
5. 编译、VRL 校验、Celery 投递或快照写入失败时规则仍保存，状态为 `failed`，GET 继续返回上一快照及其 checksum/generation；没有上一快照时返回 503。
6. Token 数据库和日志只有摘要；正确 Token 通过，缺失/错误返回 401；每次命令执行都轮换且旧 Token 立即失效；模拟摘要已提交但 stdout 丢失后，重复命令能轮换并输出可用的新 Token，且不把明文写入其他位置。
7. 日志 OpenAPI 配置接口 200 原样返回存储 YAML，`Content-Type`、checksum、generation 与 body 一致；401 不读取快照；503 只发生在没有成功快照时；登录态或普通平台 API Token 不能替代部署 Token。
8. View 用户可列出、查看样本和预览但不能写；Operate 用户可 CRUD、调序和重试；`current_team` 外实例与跨实例规则 ID 被拒绝，提取器没有组织关联。
9. 同一实例最多 20 条，实例内名称和连续顺序唯一；并发创建不会突破限制；残缺、重复、跨实例调序整体失败且顺序不变。
10. 六类提取动作、八类条件操作符、任意嵌套属性路径、前序输出供后序读取、普通字段后写覆盖均使用同一批表驱动样例，并在 Python 预览与 Vector 0.48 两端得到相同结果。
11. 用户条件在当前动作前的事件快照上求值且不能绕过实例硬匹配；缺字段、条件不匹配、类型不适用、单条/全部解析失败不丢事件且不阻断后续规则；删除源字段只在成功后发生。
12. `instance_id`、`source_type`、`timestamp` 不能被覆盖或删除；保存时拒绝 source 与任一已知输出路径相等或存在祖先/后代重叠，动态多输出动作在无法穷尽输出时不允许删除 source；`message` 不能删除但可显式 regex_replace 覆盖。
13. Vector 0.48 bootstrap 只包含 HTTP provider，30 秒轮询、Bearer 头和 `config_format: yaml`，不含 `interpolate_env`；首次 401/503 导致启动失败并由容器重试。
14. Vector 0.48 在有效远程配置更新时重载新拓扑；运行中网络失败或坏响应保留当前拓扑。Server 不发布未通过编译校验的 generation。
15. UI 对所有采集类型显示实例抽屉入口，无规则不预置；新增/编辑弹窗、完整调序、历史预览、全局四状态、只读权限、失败重试和“已发布非已应用”文案可观察。
16. `transaction.on_commit` 后 Celery 投递异常被发布模块捕获并把最新未发布 generation 标记为 `failed`；CRUD 仍返回已保存资源与真实发布状态，不返回伪事务失败 500。
17. 普通 CRUD、预览、调序、重试与状态查询只能通过登录态业务 API；中心 Vector 只能通过固定日志 OpenAPI 路由和部署 Token 读取配置。
18. 默认部署资产按迁移、Token/初始快照、Server 探测、中心 Vector 的顺序通过；webhookd、非默认云区域部署、proxy、fusion-collector、采集侧 Vector、系统 Telegraf 与 NodeMgmt 接口没有提取器相关变化。

## Out of Scope

- 无日志采集实例的规则创建、API 或 UI。
- 内置、默认、初始化预置或按采集类型推荐的提取器。
- 单规则启停、批量导入导出、搜索页选中文本反向新建、历史日志重新提取、AI/Grok 规则生成。
- 用户直接编辑 VRL 或完整 Vector YAML。
- 按云区域配置、状态、Token、generation 或下发；`CollectInstance.cloud_region_id`、提取器区域字段与区域回填。
- webhookd、新增云区域部署、fusion-collector/采集侧 Vector、NodeMgmt 配置推送和 `NodeMgmt.update_system_vector_config`。
- Vector 回调、心跳、精确 applied 状态、本地 sidecar、条件 GET 优化或多中心 Vector 高可用。
- Token 双活宽限、按用户/组织/区域授权或通过 UI 管理机器 Token。

## Further Notes

- 事实核对基线为 `origin/master` 的 `ea531804c`。当前 `CollectInstance` 已以字符串主键承载实例 ID，并通过既有组织关联和权限工具实施 View/Operate 与 `current_team` 范围；日志采集模板为 Filebeat、Vector、Packetbeat、Auditbeat、Winlogbeat 等事件写入 `instance_id`。
- Vector v0.48.0 源码中的 HTTP provider 默认 30 秒轮询，支持请求头与 YAML 格式，首次构建失败会阻止初始配置，运行中轮询构建失败不会发出 reload；同版本还明确禁止 provider bootstrap 与 sources/transforms/sinks 并存，且没有 `interpolate_env` 配置项。这些事实构成本规格的部署验收基线。
- 旧分支仅提供六类规则、顺序预览和失败隔离等历史行为证据；其中区域字段、区域状态、区域回填、NodeMgmt 下发、`applying/succeeded` 状态与“生效”文案均不进入本方案。
- 本轮审阅确认：单实例 20 条规则上限保留；每规则 10 条条件、样本 20/50 条、24 小时时间窗和强制指标集合没有仓库既有产品契约，已删除。样本只复用现有日志搜索的 15 分钟默认窗口与可配置结果上限，不新增提取器专属限制。
- 本变更没有新增 ADR：单中心全局快照是已确认部署事实下的局部实现选择，未来改为多中心时可以通过发布模块接口替换；它尚不同时满足“难逆转、意外、真实权衡”三个 ADR 条件。
- 用户已通过规格审阅门；实现、迁移、API、前端、部署资产与验收测试均以本规格为契约完成。
