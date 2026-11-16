# 日志提取器 Grok 类型

Status: implemented

## Problem Statement

日志提取器已经支持复制、拆分、键值对、正则提取、正则替换和 JSON 六类动作。非结构化文本日志（Nginx / Apache 访问日志、`/var/log/messages`、应用自定义格式）只能用「正则提取」抽字段：用户必须手写带命名捕获组的正则，例如 `(?P<status>\d+)`，写嵌套字段还要另填一段捕获组映射 JSON。对多数运维人员来说，这一步门槛过高，导致提取器建了却写不出能用的规则。

Filebeat nginx / apache 模块的字段解析原本依赖 Elasticsearch ingest pipeline；BK-Lite 的链路是采集端经 NATS 进入中心系统 Vector，不经过该 pipeline，所以这类访问日志进入平台时通常仍是一整行 `message`。这是最常见、最需要被降低门槛的场景。

## Solution

在日志提取器中新增第七种提取类型「Grok」。用户用 `%{IP:client} %{WORD:method} %{URIPATHPARAM:url.path}` 这样的内置模式名描述一行日志，模式名代替手写正则，冒号后面的名字直接就是写出的属性路径，不再需要捕获组映射。常见整行格式（Apache / Nginx combined、通用访问日志、syslog 行头）提供开箱即用的复合模式，一个 `%{COMBINEDAPACHELOG}` 即可得到一组标准命名的字段。

编辑弹窗提供分组可搜索的「插入模式」、模式说明与示例，并沿用现有历史样本预览：用户在保存前看到这条规则对真实日志的字段变化。

执行端仍是中心系统 Vector。服务端用 BK-Lite 自维护的模式库把 Grok 展开成 Rust regex 兼容的正则，复用现有正则提取的预览执行与 `parse_regex` 编译；不调用 Vector 原生 `parse_grok`。实例提取器与 syslog / snmptrap 类型级提取器都可使用该类型，条件、顺序执行、失败隔离、全局发布与权限语义全部不变。

## User Stories

1. As a 日志运维人员, I want to describe a log line with named Grok patterns such as `%{IP:client}`, so that I can extract fields without writing named-capture regular expressions.
2. As a 日志运维人员, I want the name after the colon to be the output attribute path, including nested paths such as `http.response.status_code`, so that I do not need to maintain a separate mapping JSON.
3. As a 日志运维人员, I want built-in composite patterns for Apache/Nginx combined access logs, common access logs and syslog line headers, so that the most common text formats work with one pattern.
4. As a 日志运维人员, I want to browse and search the built-in patterns by category, with a description and an example for each, and insert one into the pattern at my cursor, so that I can discover the right pattern without leaving the page.
5. As a 日志运维人员, I want to preview a Grok rule against recent real events before saving, so that I can see which fields would be added or changed.
6. As a 日志运维人员, I want an unknown pattern name, a type filter like `:int`, a duplicate output field or a protected output field to be rejected on save with a message that names the offending reference, so that I can fix the rule instead of breaking global publication.
7. As a 日志运维人员, I want a Grok rule that does not match an event to leave the event intact and let later rules continue, so that a parsing mistake never drops logs.
8. As a 日志管理员, I want Grok rules to run with the same linear-time regex engine as existing regex rules on the shared central Vector, so that one tenant's rule cannot slow down log ingestion for everyone.

## Implementation Decisions

### 1. 定位与边界

- Grok 是日志提取器的一种提取类型 `grok`，与现有六类并列；它不是新的处理阶段、不是独立解析器，也不引入用户可编辑的 VRL。
- 仅支持中心系统 Vector 0.48 执行；不改 fusion-collector、采集侧 Vector、webhookd 或 NodeMgmt 下发。
- 作用域、条件、20 条上限、完整调序、全局 generation、发布失败保留旧快照、操作审计、View / Operate 授权与类型级页面授权全部沿用 `log-file-extractor` 与 `log-extractor-passive-collect` 规格，不新增权限点。

### 2. 规则数据契约

| 字段 | `grok` 类型约束 |
| --- | --- |
| `extractor_type` | `grok`；模型提取类型枚举新增该值并随迁移发布 |
| `source_field` | 与其他类型相同，默认 `message` |
| `target_field` | 必须为空；输出路径全部来自模式 |
| `config` | 只允许 `pattern` 一个键，值为用户书写的 Grok 原文；不接受 `group_mapping` 或其他未声明键 |
| `delete_source` | 允许；输出路径在保存时可完全确定，按现有重叠规则校验 |

数据库只保存 Grok 原文，不保存展开后的正则。展开结果在保存校验、预览与编译三处由同一个展开器即时、确定地生成。

### 3. Grok 语法

- 引用形式只有两种：`%{模式名}`（只匹配、不写出）与 `%{模式名:属性路径}`（匹配并写出）。模式名必须存在于 BK-Lite 模式库。
- 属性路径只允许由 `[A-Za-z_][A-Za-z0-9_]*` 普通段以 `.` 连接，例如 `client`、`http.response.status_code`；不支持带引号的引用段。需要特殊字符的属性名请改用正则提取类型。
- 第三段类型过滤器（如 `%{NUMBER:bytes:int}`）保存即拒绝，提示「Grok 只写出字符串，如需数值比较请在查询中转换」。所有输出都是字符串，与正则提取一致，现有 `==` / `!=` 不做隐式类型转换的语义不变。
- 复合模式自带一组固定命名的输出，不能再给它命名：`%{COMBINEDAPACHELOG:x}` 保存即拒绝；原子模式不带内部命名。
- 引用以外的字面量按正则语法解释，兼容 Logstash 与阿里云 SLS 的写法（`\[%{HTTPDATE:log_time}\]`），并通过与正则提取相同的 Vector 0.48 兼容性校验（拒绝前后查找、反向引用等）。字面量中不允许出现命名捕获组，输出只能来自 `%{模式名:属性路径}` 与复合模式；普通分组与非捕获分组允许。
- 匹配语义与正则提取一致：不锚定，在源字符串中取第一处匹配；需要整行匹配时用户自行加 `^` / `$`。

### 4. 保存时校验

以下错误在保存与预览时都返回 400，并在消息中指出出错的引用序号或模式名，不回显整条样本：

- 原文长度 1–2000 字符；展开后正则长度不超过 16384 字符；单条规则最多 64 个 `%{}` 引用（含复合模式内部引用）。
- 引用语法错误、未知模式名、给复合模式命名、出现类型过滤器。
- 没有任何写出字段（既无 `%{X:path}` 也无复合模式）。
- 写出路径重复，或互为祖先 / 后代（如同时写出 `http` 与 `http.method`）。
- 写出路径以系统保护字段为根，或写出 `message`。复合模式的内置字段名在模式库内已避开这些字段，模式库单元测试保证这一点。
- 展开后的正则不是合法正则或不满足 Vector 0.48 兼容性校验。

### 5. 展开与执行

- 展开器把每个写出引用转为带内部组名的命名捕获组（组名由展开器按出现顺序生成，用户不可见），同时产出「内部组名 → 属性路径」的输出表；未命名引用转为非捕获组。复合模式的内部输出以相同方式进入输出表。
- 预览执行与 Vector 编译都消费「展开后正则 + 输出表」，行为等同于一条带捕获组映射的正则提取规则：
  - 源字段缺失 → `skipped`；源值不是字符串 → `skipped`。
  - 没有匹配 → `failed`；匹配但所有输出组都没有参与匹配 → `failed`。
  - 可选分组未参与匹配的字段不写出；其余字段按输出表写入，后写覆盖前写。
  - `delete_source` 只在至少一个字段写出后执行。
- 预览把 `grok` 纳入现有正则隔离执行路径，复用子进程、超时、并发与事件大小限制。
- 编译生成与正则提取相同形态的 VRL：`parse_regex` 加逐字段 `get` 与赋值，使用可失败调用分支，不使用会中断 transform 的 bang 调用。

### 6. BK-Lite 模式库

- 模式库是随代码发版的数据，每个条目包含：模式名、分类、展开定义（只能引用库内模式或使用 Rust regex 与 Python `re` 的公共子集）、是否复合、复合模式的输出字段列表、一条示例日志、中英文说明。
- 模式名与 Logstash / Elastic / 阿里云 SLS 的经典名称保持一致，降低迁移与查资料成本；定义可以与经典版本不同，以满足 Rust regex 约束，例如 IPv4 用 `\b` 边界代替前后查找。
- 第一版收录：

| 分类 | 模式 |
| --- | --- |
| 通用 | `WORD` `NOTSPACE` `SPACE` `DATA` `GREEDYDATA` `QUOTEDSTRING` `UUID` `USERNAME` `EMAILADDRESS` |
| 数字 | `INT` `POSINT` `NONNEGINT` `NUMBER` `BASE16NUM` |
| 网络 | `IPV4` `IPV6` `IP` `HOSTNAME` `IPORHOST` `HOSTPORT` `MAC` |
| 路径与 URL | `UNIXPATH` `WINPATH` `PATH` `URIPROTO` `URIHOST` `URIPATH` `URIPARAM` `URIPATHPARAM` `URI` |
| 日期时间 | `YEAR` `MONTH` `MONTHNUM` `MONTHDAY` `DAY` `HOUR` `MINUTE` `SECOND` `TIME` `DATE` `DATESTAMP` `TIMESTAMP_ISO8601` `HTTPDATE` `SYSLOGTIMESTAMP` |
| 日志级别与程序 | `LOGLEVEL` `PROG` `SYSLOGHOST` |
| 复合（整行格式） | `COMMONAPACHELOG` `COMBINEDAPACHELOG` `SYSLOGBASE` |

- 复合模式输出字段采用 ECS 风格命名，与平台已有 HTTP 日志字段（如 `http.response.status_code`、`url.path`）的命名体系一致；日志行内的时间文本统一写入 `log_time` 字符串，不写 `timestamp`，不影响日志服务端时间与 `_time` 索引：

| 复合模式 | 输出字段 |
| --- | --- |
| `COMMONAPACHELOG` | `source.address` `user.name` `log_time` `http.request.method` `url.original` `http.version` `http.response.status_code` `http.response.body.bytes` |
| `COMBINEDAPACHELOG` | 以上全部，加 `http.request.referrer` `user_agent.original`；说明中标注适用于 Nginx 默认 `combined` 格式 |
| `SYSLOGBASE` | `log_time` `host.hostname` `process.name` `process.pid` |

- 只追加、不随意改：已发布模式的定义变更会改变存量规则的运行结果。修改已有条目必须同时补回归样例、递增中心 Vector 配置契约版本，并在发布说明中写明；升级后由既有的重新发布命令生成新快照。新增条目不需要递增契约版本。
- 不支持用户自定义模式或别名。

### 7. 模式目录接口

- 日志模块新增一个只读的登录态业务接口，返回模式库目录：模式名、分类、说明（按当前语言）、示例、是否复合、复合输出字段。前端插入面板与说明只读取该接口，不在前端复制模式清单。
- 授权与提取器列表相同：能查看任一提取器作用域的用户即可读取；无 `current_team` 时 fail closed。目录不含租户数据，不经 OpenAPI 网关对外暴露。
- 规则 CRUD、预览、样本、调序与发布接口的参数和响应形态不变，只是 `extractor_type` 多一个合法值。

### 8. 编辑交互

- 类型下拉新增「Grok」。选中后隐藏目标属性与映射输入，显示：
  - 多行 Grok 模式输入框（等宽字体）。
  - 「插入模式」：按分类分组、可搜索的下拉；每项显示模式名、说明与示例；原子模式插入 `%{NAME:}` 并把光标停在冒号后，复合模式插入 `%{NAME}`。
  - 一行示例提示，例如 `%{IP:client} %{WORD:method} %{URIPATHPARAM:url.path}`。
- 历史样本预览、字段变化对比、四种结果状态与现有提取器完全一致；服务端校验错误沿用现有请求错误提示，编辑弹窗保持打开。
- 模式目录只在首次选择 Grok 时请求一次；失败时禁用「插入模式」并在控件下提示，不阻塞手写与保存。
- 搜索页「创建提取器」入口不变，仍以当前这条日志为预览样本，不预选类型、不反推模式。
- 遵守 Web UI 硬约束：复用 Ant Design 的 Input.TextArea / Select；布局用 Tailwind className；颜色使用语义 token。

## Testing Decisions

- 只测外部行为：通过规则业务模块、编译器、HTTP 视图、预览执行结果和前端纯函数观察，不断言展开器内部组名或 helper 调用次数。
- 共享契约样例：在现有 Python 预览与 Vector 0.48 同批契约样例中加入 Grok 用例，覆盖原子模式写出、嵌套路径、复合模式、可选分组未参与、未匹配失败保留、`delete_source`、与前序规则输出衔接。两端结果必须一致。
- 模式库表驱动测试：每个条目的示例日志能被自身匹配并写出预期字段；复合模式输出不含保护字段与 `message`；所有定义能通过 Vector 0.48 兼容性校验；模式库整体进入一次 Vector 0.48 `validate`。
- 语义校验表驱动测试：未知模式、类型过滤器、给复合模式命名、重复 / 祖先输出、保护字段输出、字面量命名组、长度与引用数上限、展开后不兼容正则，都以 400 拒绝。
- 编译器：Grok 规则生成 `parse_regex` 分支，不出现 `parse_grok` / `parse_groks`；同一规则状态逐字节稳定。
- 视图：Grok 规则的创建 / 编辑 / 删除各使全局 generation 只加 1；模式目录接口在无 `current_team` 时拒绝，有查看权限时返回目录。
- 前端：在现有提取器交互脚本中覆盖 Grok 表单序列化（`config` 只有 `pattern`、`target_field` 为空）与插入模式后的文本拼接。
- 既有先例：`test_log_extractor_semantics_pure.py`、`test_log_extractor_compiler_pure.py`、`log_extractor_contract_cases.py`、`test_log_extractor_vector_contract.py`、`test_log_extractor_views.py`、`web/scripts/log-extractor-interaction-test.ts`。

## Out of Scope

- Vector 原生 `parse_grok` / `parse_groks`、Oniguruma 等回溯型正则引擎。
- 用户自定义模式、别名、`alias_sources`。
- 一条规则内多个模式择一（Elastic `patterns` 列表、Datadog 多条匹配规则）。
- 类型转换过滤器与数值输出。
- Logstash / ELK Grok 规则原样迁移兼容。
- 搜索页选中文本反推 Grok、AI 自动生成模式（Datadog Tap to Parse 一类）。
- Loki `pattern` 风格的占位符语法。
- 历史日志重新提取。

## Further Notes

- 产品决策记忆：`docs/design/product-decisions/log-extractor-grok.md`。
- 基线规格：`specs/changes/log-file-extractor/spec.md`（六类动作、发布与契约测试）、`specs/changes/log-extractor-passive-collect/spec.md`（类型级作用域与授权）。本规格只新增一个提取类型，不修订二者的已实现语义。
- 不用原生 Grok 的证据：Vector 0.48 依赖 VRL 0.25.0；VRL 0.25.0 依赖 `grok = "2.1"` 默认特性，即 Oniguruma 回溯引擎，`parse_groks` 另有 Datadog Grok 语义与 `alias_sources` 读取 Vector 本机文件。中心 Vector 为全租户共享管道，单条正文可达约 10 MiB 且运行时没有单条正则超时。
- 竞品参照（2026-11 查阅官方文档）：

| 产品 | Grok 形态 | 本规格借鉴 |
| --- | --- | --- |
| 阿里云 SLS 数据加工 | `grok()` 把模式展开成正则交给 `e_regex`；复合模式不能命名；支持 `extend` 自定义 | 同样的「展开为正则」架构、复合模式不可命名 |
| Graylog | 从一条消息创建 Grok 提取器并当场测试；「仅命名捕获」；附加条件 | 从当前日志创建并预览、未命名引用不写出 |
| Elastic ingest | `pattern_definitions` 自定义、`patterns` 多选一、`:int` 类型转换、ECS 字段命名、Grok Debugger | ECS 风格字段名；自定义与类型转换后置 |
| Datadog | `%{MATCHER:EXTRACT:FILTER}`、辅助规则、样本匹配状态、Tap to Parse | 样本结果状态；辅助规则与自动生成后置 |
| Grafana Loki | `pattern` 解析器 `<field>` / `<_>` 占位符，比正则更易写、更快 | 记录为后续可选的更低门槛语法 |

- 实现说明：模式库 50 条全部收录；IPv4 用 `\b` 边界，IPv6 不含 IPv4-mapped 与 zone 形式。新增模式不递增中心 Vector 配置契约版本（仍为 1）。目录说明按 `request.user.locale` 返回，缺省 `zh-Hans`。
- 完成证据（2026-11-16，本机需在 `INSTALL_APPS` 中补 `cmdb`，否则 `monitor` 导入 cmdb 模型导致 Django 启动失败，与本变更无关）：
  - `uv run pytest apps/log/tests/test_log_extractor_semantics_pure.py apps/log/tests/test_log_extractor_compiler_pure.py apps/log/tests/test_log_extractor_grok_patterns.py apps/log/tests/test_log_extractor_views.py apps/log/tests/test_log_extractor_rules_service.py apps/log/tests/test_log_extractor_vector_contract.py -m "not integration" --no-cov`：131 passed。
  - `test_vector_048_validates_and_runs_grok_pattern_library`（Docker，`timberio/vector:0.48.0-debian`）：passed，50 条模式 `vector validate` 与 `vector vrl` 结果和 Python 预览一致。
  - 7 条 Grok 共享契约样例单独编译后在 Vector 0.48 `vector vrl` 运行：7/7 一致。
  - 既有问题，未在本变更修复：`test_vector_048_runs_shared_contract_cases` 在 `vector vrl` 阶段报 `E104 unnecessary error assignment`，位置是既有 JSON / KV 根合并的 `., _merge_err = merge(., _parsed)`；去掉全部 Grok 样例后同样失败，`vector validate` 通过。`test_vector_048_uses_central_receive_time_and_preserves_upstream_timestamp` 偶发失败，原因是 arm64 宿主经 QEMU 运行 amd64 镜像时容器时钟早约 75ms。
  - `pnpm test:log-extractor-interaction`：passed。本次改动的前端文件 eslint 0 error；全量 `pnpm lint` / `pnpm type-check` 的失败均在未改动文件（`cmdb` selectionActionBar、`opspilot`、日志策略与搜索页的既有测试文件）。
  - 本机验证（Docker 底座 + 本机后端 / 前端 / Celery）：执行 `0032` 迁移；在日志接收页的 Kafka 订阅实例上新建 Grok 提取器，模式目录分组加载，插入原子模式得到 `%{NAME:}`；历史样本预览对匹配日志显示「提取成功」及 7 个新增字段，对不匹配日志显示 `regex_no_match`；写 `message` 时服务端拒绝且弹窗保持打开；保存后经 Celery 发布，从真实配置接口拉到的全局 YAML 只含 `parse_regex`、不含 `parse_grok`；把该 YAML 的输入输出换成 stdin / console 后，用 Vector 0.48 运行，匹配行拆出 ECS 字段，不匹配行和其他实例的日志保持原样。
  - 未覆盖：中心 Vector 常驻消费 NATS 后，再写入 VictoriaLogs 的提取结果。本机 Colima 空闲内存约 200MB，常驻 Vector 回放 Kafka 积压日志时 Docker 无响应，已停掉。
  - 发现既有问题（与本变更无关）：历史样本预览切换样本时不清空上一次的预览结果，「字段变化」会用旧结果对比新样本。

