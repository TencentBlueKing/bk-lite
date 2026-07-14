# CMDB NATS / RPC 生产级审查

## 1. Summary

CMDB 在 `CmdbConfig.ready()` 中导入 `apps.cmdb.nats.nats`，26 个 `@nats_client.register` 由通用注册表按函数名注册为 `{NATS_NAMESPACE}.<函数名>`，全部使用 Core NATS request/reply 订阅而非 JetStream。通用 listener 只把消息体拆成 `args/kwargs` 后调用函数，不提供已认证 publisher、subject ACL claim 或服务身份；同步 handler 被放入线程执行，服务端没有统一 deadline、请求 schema 或资源预算。仓库内主要调用方是 Alerts 丰富、Operation Analysis 动态数据源、System Management 展示字段同步与 Stargazer callback；`apps.rpc.cmdb.CMDB` 还公开模型、实例、关系和计数门面，实例 CRUD 三个注册函数则没有仓库内类型化 RPC 门面。

当前实现的局部正向行为包括：Operation Analysis 会从 HTTP request 生成 `user_info`；部分统计和 Room3D 在缺少权限 map 时 fail-closed；配置文件 callback 用 `processed/error` 区分传输处理与业务结果；凭据 callback 会把单条/批量业务结果写入 ORM 并返回处理计数。但这些行为都没有在 NATS 边界绑定可信调用者。任何能向同一 namespace 发布请求的客户端都能直接调用裸查询/关系写入口，或伪造 `allowed_org_ids`、`organization_ids`、`user_info` 和 callback payload；仓库 NATS 配置只提供共享连接凭据/TLS 选项，没有可证明的 subject 级调用者授权。

### 1.1 注册函数与契约盘点

下表的“注册名”均省略共同前缀 `{NATS_NAMESPACE}.`；消息带 `reply` 时，外层 listener 把成功响应包装为 `{"success": true, "result": <handler返回值>}`，未捕获异常则包装为 `success=false`；单向 callback 没有 response envelope。表内“返回”描述 handler 内层 payload。

| # | 注册名 | 请求 schema / 主要调用方 | 授权上下文 | 返回与错误路径 |
|---:|---|---|---|---|
| 1 | `get_cmdb_module_data` | `module, child_module, page, page_size, group_id, user_info?`；权限模块动态调用 | 仅实例分支由 `user_info` 构造 map；任务/模型分支无用户裁剪，`group_id` 来自消息体 | `{count,items}`；非法 module 抛 `ValueError` |
| 2 | `get_cmdb_module_list` | 无参；`CMDB.get_module_list` | 无 | 返回全部可见分类/模型/任务类型；下游异常上抛 |
| 3 | `search_instances` | `params={model_id,inst_name?,_id?}`；Alerts legacy 单事件丰富 | 无 | 返回首个完整实例或 `{}`；查询异常上抛 |
| 4 | `search_instances_batch` | `params={model_id,ids?,inst_names?,organization_ids}`；Alerts 批量丰富 | 直接信任调用方 `organization_ids` | 返回 key→完整实例映射；非法组织 ID 抛 `ValueError` |
| 5 | `update_instance` | `params={inst_id/_id 或 model_id+inst_name,update_attr,operator?,scope}` | `allowed_org_ids/service_scope/user_info` 均来自消息体；名称定位先无权限查询 | 返回更新实例；参数/越界/Service 异常上抛 |
| 6 | `create_instance` | `params={model_id,instance_info,operator?,scope}` | 同上，scope 与目标 organization 只做自洽比较 | 返回新实例；参数/越界/Service 异常上抛 |
| 7 | `delete_instance` | `params={inst_ids/inst_id/_id 或 model_id+inst_name,operator?,scope}` | 同上；调用方 scope 转成 `user_groups` | `{result:true,deleted:[...]}`；参数/Service 异常上抛 |
| 8 | `list_instances` | `params={model_id,params?,page?,page_size?,order?,format?}`；`CMDB.list_instances` | 固定 `permission_map={}` | `{count,items}`；参数/图异常上抛 |
| 9 | `search_model_attrs` | `params={model_id}`；`CMDB.search_model_attrs` | 无模型对象权限 | 属性定义列表；缺参抛 `ValueError` |
| 10 | `search_models` | `params={classification_id?,include_hidden?}`；`CMDB.search_models` | 无 | 模型列表；下游异常上抛 |
| 11 | `search_classifications` | `params={include_hidden?}`；`CMDB.search_classifications` | 无 | 分类列表；下游异常上抛 |
| 12 | `search_model_associations` | `params={model_id}`；`CMDB.search_model_associations` | 无双端模型权限 | 模型关联定义；缺参抛 `ValueError` |
| 13 | `search_instance_associations` | `params={model_id,inst_id/_id}`；`CMDB.search_instance_associations` | 无中心/对端实例权限 | 关联实例分组；缺参抛 `ValueError` |
| 14 | `create_instance_association` | `params={src_inst_id,dst_inst_id,model_asst_id,...}`；`CMDB.create_instance_association` | 无双端授权或可信 operator | 返回关联边；参数/Service 异常上抛 |
| 15 | `delete_instance_association` | `params={asso_id/inst_asst_id/_id,operator?}`；`CMDB.delete_instance_association` | 无边及双端授权 | `{result:true,deleted:id}`；参数/Service 异常上抛 |
| 16 | `receive_config_file_result` | Stargazer `callback_subject` 单向 publish | 无 publisher 身份；业务层校验 task/execution payload | `{result:true,processed,error,changed,task_updated}`；Service 抛错时单向调用方无应用 ack；业务失败引用 `CMDB-F33` |
| 17 | `receive_collect_credential_result` | Stargazer 单条或 `{events,next_since}` 批量 publish | 无 publisher 身份 | 返回 `result/processed/failed/errors/next_since`；投递/cursor 引用 `CMDB-F31/F32` |
| 18 | `sync_display_fields` | `organizations?/users?`；System Management | 无 publisher 身份；完全信任变更数据 | 返回同步统计/任务结果；内部全图扫描异常上抛 |
| 19 | `get_cmdb_statistics` | `user_info`；Operation Analysis | 从消息体重建模型/实例 map；缺失时返回零 | `{result:true,data,message}`；下游异常上抛 |
| 20 | `get_room3d_layout` | `server_room_id,user_info`；Operation Analysis | 机房实例与 permission map fail-closed，机柜/设备复用裁剪 | 内层 `{result,data,message,code?}`；资源预算引用 `CMDB-F43` |
| 21 | `get_change_trend` | `time=[start,end],group_by,model_id?,user_info?`；Operation Analysis | 未使用 `user_info` 裁剪 ChangeRecord | 内层趋势 payload或 `result=false`；组织泄露引用 `CMDB-F59` |
| 22 | `get_instance_group_by` | `model_id,field,user_info`；Operation Analysis | permission map 缺失返回空 | 内层分组统计；缺参返回 `result=false`，查询异常上抛 |
| 23 | `get_model_inst_statistics` | `user_info`；Operation Analysis | 模型/实例 map fail-closed | 内层表格统计；异常上抛 |
| 24 | `get_cmdb_model_instance_top` | `limit?,classification_id?,user_info`；Operation Analysis | 模型/实例 map fail-closed | 内层 TopN；`limit` 只做正数校验、无最大值 |
| 25 | `get_cmdb_collect_statistics` | `user_info`；Operation Analysis | 仅按消息体 team/include_children 裁剪任务，不校验 user 对组织的真实授权 | 内层任务状态计数；ORM 异常上抛 |
| 26 | `model_inst_count` | 任意 `*args/**kwargs`；`CMDB.model_inst_count` | 固定 `permissions_map={}` 且忽略入参 | 返回全模型实例数量；图异常上抛 |

本域新增 3 个主 Finding：P0 1 个、P1 2 个，编号 `CMDB-F62`–`CMDB-F64`。关系对端授权、ChangeRecord、错误脱敏、callback 业务结果与投递语义分别引用既有 `CMDB-F14/F59/F25/F31/F33`，不重复计数。Recommendation 为 **Block**。

## 2. Findings

### Finding CMDB-F62：NATS handler 没有可信调用者身份，消息体 scope 与裸入口可跨租户读写和伪造 callback

- Severity: P0
- Location: `server/nats_client/handlers.py:6-18`；`server/nats_client/management/commands/nats_listener.py:88-126`；`server/config/components/nats.py:55-75`；`server/apps/cmdb/nats/nats.py:266-318,370-405,407-594,595-768,788-849,1193-1259,1426-1458`
- Root cause category: 跨层契约不一致
- Evidence: listener 只从 subject 查函数并把消息体 `args/kwargs` 原样传入，没有 publisher identity、service claim 或 handler allowlist。连接配置只有共享 user/password/token/TLS 选项，仓库中没有 subject ACL 证明。`search_instances/list_instances/model_inst_count` 分别无权限查询、固定 `permission_map={}` 或返回全局计数；实例/关系写入口接受消息体中的 `allowed_org_ids/service_scope/user_info`，因此 scope 只能证明“目标组织包含在调用方自己声明的集合”。`search_instances_batch` 同样直接把消息体 `organization_ids` 当权威。`receive_collect_credential_result` 与 `sync_display_fields` 还会根据未认证 payload 改写凭据命中状态或全图 `_display` 投影。架构约束明确要求 NATS 写入口不能把调用方组织 ID 当可信边界。
- Trigger: 任一能使用同一 NATS 连接凭据或取得同 namespace publish 权限的内部服务、错误配置组件或被攻陷 Worker，向 `bklite.create_instance/update_instance/delete_instance/search_instances/list_instances/create_instance_association/receive_collect_credential_result` 等 subject 发送自选 scope/payload。
- Impact: 调用方可读取其他组织完整实例与关系，伪造任意组织 scope 后创建、修改、删除实例或关系，污染凭据冷却/优先级及展示字段。破坏面跨图主数据、ORM 状态、审计和下游自动关系；仅依赖“调用方会诚实注入 user_info”不能形成租户安全边界。
- Why existing tests missed it: brief 的 CRUD 测试直接调用 handler、Mock `InstanceManage`，并把“显式 `allowed_org_ids` 被接受”写成正向断言；module_data 只覆盖一个实例分支的缺失 user_info；Room3D 测试 Mock `_build_nats_permission_map`。六文件没有经过真实 NATS listener、不同服务凭据、subject ACL、伪造 user_info/scope、裸查询/关系写或 callback provenance。未纳入 brief 的 `test_model_assoc_nats.py` 还明确断言 `list_instances` 使用空权限和关系写裸委托。
- Minimal safe fix: 通用 NATS 层必须从连接/subject ACL 或签名 service token 建立不可由 payload 覆盖的 `CallerContext`；按 handler 注册允许的 service identity 和 action。CMDB adapter 根据该 context 解析真实用户/组织/实例权限，删除公开 payload 中的 `allowed_org_ids/organization_ids` 权威语义；所有读写、关系和 callback 均 fail-closed。Stargazer callback 使用独立凭据、受限 subject、task/execution 绑定和防重放事件 ID。
- Required tests: 两个独立 NATS service identity 的 subject allow/deny；伪造 allowed_org_ids/user_info/organization_ids 仍 403 且零图/ORM写；裸实例/列表/计数/关系读写的组织与实例权限矩阵；伪造 callback、旧 execution、重复 event、跨 task credential 全部拒绝；拒绝响应不泄露目标是否存在。
- Long-term design note: `user_info` 是业务参数，不是身份凭证。NATS 框架应在 dispatch 前生成类型化 `CallerContext`，业务 handler 只消费可信 context 和已验证 DTO；共享 namespace 不能等同于共享超级用户权限。

### Finding CMDB-F63：NATS 错误协议回传原始异常对象并保留条件反序列化兼容路径

- Severity: P1
- Location: `server/nats_client/management/commands/nats_listener.py:128-157`；`server/nats_client/clients.py:113-151,184-222`
- Root cause category: 错误模型不清晰
- Evidence: listener 对所有带 `reply` 的异常响应同时写入异常类名、`str(e)`（`ValidationError` 为 message dict）和 `jsonpickle.encode(e)`。`request/request_v2` 对当前 listener 产生的非空 `error + message` 直接拼接文本，不会常规解码 `pickled_exc`；只有 `error == "BaseAppException"` 且缺少 message，或旧式响应同时缺少规范 `error/result` 时，才走 `jsonpickle.decode` fallback。直接用 `RuntimeError("password=canary-secret")` 做 codec 复现，序列化对象图包含 `py/reduce` 和明文 canary，decode 可还原同一 secret；该复现只证明异常对象在 wire codec 中被完整保留且兼容路径能够还原，不证明当前普通 listener 响应必经 decode。handler 还混用抛异常、内层 `result=false`、空列表 fail-closed 和 `result=true/processed=false`，调用方必须按函数特判业务错误与传输错误。
- Trigger: 当前协议触发——图数据库、MinIO、SDK、callback Service 或校验异常的 message/args 包含 token、连接串、配置正文或内部诊断，listener 会把原始文本和序列化对象一并放入 wire 响应。兼容 decode 触发——旧式/异构响应提供无 message 的 `BaseAppException`，或同时缺少规范 `error/result`，客户端进入 jsonpickle fallback；错误/恶意 responder 也可构造该形态。
- Impact: 当前异常响应会在 wire 同时暴露原始敏感文本与序列化对象，并可能由调用方错误文本/日志继续扩散；普通非空 `error + message` 响应不会因此自动反序列化。条件 fallback 仍保留跨进程对象图反序列化攻击面和 Python 类型耦合，且 Go/其他语言消费者无法安全复用该兼容协议；异常类或 jsonpickle 版本变化也会导致分叉。
- Why existing tests missed it: brief 六文件全部直接调用 handler，未启动 listener/客户端；没有 canary secret、wire envelope、非 Python consumer、当前文本分支与兼容 decode 对照。`server/apps/node_mgmt/tests/test_architecture_support.py:4358-4388` 已测试无 message 的 `BaseAppException` 会 fallback 到 pickled message，证明兼容分支仍在使用，但该文件不在 brief 六文件中，也没有断言当前普通 `error + message` 不 decode 或敏感信息不进入 wire。
- Minimal safe fix: 删除 `pickled_exc` 生成和 decode；统一返回版本化纯 JSON `ErrorEnvelope {code, category, retryable, safe_message, correlation_id, details?}`，服务端原始异常只进入受控日志并先按 `CMDB-F25` 统一脱敏。handler 的参数、权限、业务冲突和依赖失败映射为稳定 code，callback 的 transport ack 与 application result 使用显式字段。
- Required tests: canary password/token/连接串不出现在 wire、客户端异常或日志；ValidationError/权限/冲突/timeout/依赖失败映射为稳定 JSON；Python/非 Python consumer 契约；旧 `pickled_exc` 兼容窗口只读且默认禁用，恶意对象图永不 decode。
- Long-term design note: 跨服务错误必须是数据协议而非语言运行时对象。`CMDB-F25` 负责领域错误脱敏，本 Finding 负责通用 NATS adapter 的序列化、映射与跨语言兼容，根因独立。

### Finding CMDB-F64：NATS adapter 无统一 schema、批量预算和服务端 deadline

- Severity: P1
- Location: `server/nats_client/handlers.py:6-18`；`server/apps/cmdb/nats/nats.py:266-318,383-405,553-632,788-849,1163-1259,1381-1423`
- Root cause category: 资源边界缺失
- Evidence: registry 只保存 Python callable，不声明 DTO、消息字节、rows、batch、响应或 deadline；listener 把同步 handler 放入线程后不设置服务端执行截止时间。`get_cmdb_module_data/list_instances` 的 `page_size` 未钳制，`search_instances_batch/delete_instance` 的 ID 数无上限，凭据 callback 的 `events` 无上限，`sync_display_fields` 可接收任意数量 ID 后仍全量读取所有图实例，`get_change_trend` 按调用方任意小时范围逐格构造列表，`get_cmdb_model_instance_top` 的 limit 也无最大值。caller 的 60 秒 request timeout 只停止等待，不能取消已在线程中运行的图/ORM副作用。
- Trigger: 发送极大 page_size/ID/event 列表、数年或数十年 hour 时间范围、超大组织/用户变更，或并发多个在 caller timeout 后仍继续执行的请求。
- Impact: 单条请求可全量物化图数据、ChangeRecord 时间桶或 callback 事件，长期占用 listener 线程、数据库/图连接和内存；调用方超时重试后旧执行仍继续，进一步产生重复写和拥塞，拖慢同 namespace 的合法 RPC/callback。
- Why existing tests missed it: pure tests只验证 3 小时时间桶和 3 天列表；CRUD/Room3D 均是小 payload + Mock；六文件没有上限±1、消息/响应字节、峰值内存、并发、服务端 timeout/cancel 或超限零副作用断言。覆盖率 54%，上述批量和统计 handler 多数未执行。
- Minimal safe fix: 注册时声明并验证版本化 request/response schema 与 `ResourceBudget`（message bytes、rows、IDs/events、page size、response bytes、deadline）；超限在任何查询/写入前拒绝。长任务改为有界批次 + durable job/checkpoint；listener 传播服务端 deadline/cancellation，写操作用幂等键和 generation 避免 caller timeout 重投重复副作用。
- Required tests: 每个集合/page/time范围的上限−1/等于/＋1；超限零图/ORM写；caller timeout 后服务端停止或安全转后台 job；并发饱和、响应字节和峰值内存基准；批次中断续跑与幂等重投。
- Long-term design note: `CMDB-F23/F43/F61` 分别负责采集、专项视图和订阅领域预算；本 Finding 负责 NATS adapter 的统一入站预算和服务端执行约束，领域 handler 仍需在自身层保留更严格预算。

### 跨域证据与不重复计数风险

- `CMDB-F14`：实例关系 NATS 查询/创建/删除无双端授权，是本域 `CMDB-F62` 的裸入口证据；关系领域的双端权限语义仍由 F14 负责。
- `CMDB-F25`：callback `error_message` 与 listener 原始 `str(e)` 会扩散敏感文本；统一领域脱敏继续引用 F25，`CMDB-F63` 只负责框架对象序列化/反序列化与错误 envelope。
- `CMDB-F31/F32`：Stargazer publish/flush 未知投递和非唯一 cursor 已登记；本域只确认 CMDB callback subject 也是非 JetStream、无应用 ack，不重复计数。
- `CMDB-F33`：配置 callback 返回 `result=true, processed=false` 的业务结果分层已登记；Stargazer 单向 publish 不消费该返回值，传输 ack 与业务应用结果仍不能混为一谈。
- `CMDB-F43`：Room3D 的机房/机柜关系与设备查询总预算沿用专项资源 Finding；本域 `CMDB-F64` 只负责 adapter 的通用入站预算。
- `CMDB-F50`：Node 同步父任务把子投递当业务完成属于领域状态机；通用 NATS request/publish 不提供业务完成证明会放大该问题，但不新增 Finding。
- `CMDB-F59`：`get_change_trend` 直接使用全局 `ChangeRecord` queryset，与 ChangeRecord View 越权是同一数据授权根因；本域引用 F59，不另计。

## 3. Test Review

在 `server/` 使用显式 SQLite、Celery、MinIO 与 `SECRET_KEY` 环境运行 brief 六文件并采集 `apps.cmdb.nats.nats` 覆盖率。首次沙箱执行因无权读取 `~/.cache/uv/sdists-v9/.git` 退出 2、未收集；受控缓存权限重跑为 **64 passed in 2.90s，exit 0**。

覆盖率为 `apps/cmdb/nats/nats.py` **54%**（733 statements / 338 missed），远低于相关模块 80% 与核心业务 90% 目标。未执行的关键区段包括裸实例/批量查询、`list_instances`、模型/关系 handler、配置 callback、展示同步、绝大多数统计和 `model_inst_count`；通用 `server/nats_client` listener/handler/client 没有被本命令测量。

有效证明包括：

- `get_cmdb_module_data` 实例分支在 user_info/permission map 缺失时返回空，并把非空 map 传给 Service。
- 凭据 callback 的单条失败/成功与批量混合事件真实落入 ORM hit state，返回 processed/failed/next_since，日志只断言摘要字段。
- Room3D 对非法 ID、错误模型、缺权限和空布局 fail-closed，并把 permission map/user 传给机房及设备批量 Service；返回 payload、位置解析和 notice 断言较完整。
- CRUD 参数缺失、目标 organization 不在“声明 scope”时拒绝，能防止 payload 内部自相矛盾。

证明力不足包括：

- create/update/delete 全部 Mock `InstanceManage`，且把调用方任意 `allowed_org_ids` 作为合法输入；没有验证 scope 来源、NATS publisher、真实组织/实例权限或图/审计结果。
- module_data 只覆盖 PERMISSION_INSTANCES；任务/模型分支、裸 `search_instances/list_instances/model_inst_count` 与关系读写不在六文件中。
- pure tests只验证小时间桶和展示转换，没有长范围、page/batch/message bytes/deadline。
- 凭据 callback 没有 publisher 身份、跨 task/credential、批量上限、防重放、部分失败 application ack 或 canary secret；日志输出中仍可见 `auth failed`。
- Room3D 大量 Mock 图和权限 helper，未连接真实 NATS/图数据库，也未验证调用方伪造 user_info、机房规模预算和超时。
- brief 六文件没有测试 listener 的双层 envelope、`pickled_exc`、客户端 jsonpickle 条件 decode、跨语言兼容、异常脱敏、subject ACL 或真实 request/publish/reply。仓库另有 `server/apps/node_mgmt/tests/test_architecture_support.py:4358-4388` 锁定无 message `BaseAppException` 的 decode fallback，但不在本次 brief/coverage，且未覆盖当前普通 `error + message` 文本分支与 canary 脱敏。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：26 个 handler 集中在单个 1,458 行文件，但 schema、调用者、权限和错误语义不在注册表中，维护者必须从动态调用方反推真实契约。
2. 新增同类插件是否需要复制代码：是。新增跨模块查询/callback 需要自行解析 dict、构造 user_info、选择 inner result 或异常并重复权限/预算逻辑。
3. 新增错误类型是否需改多个模块：是。handler、listener、jsonpickle client、Operation Analysis normalizer 和具体调用方均需同步识别。
4. 新增 callback 模式是否容易扩展：表面只需加装饰器，但默认无 publisher provenance、durability、event ID、应用 ack 或重放状态，容易复制 F31/F33 类问题。
5. 当前接口是否容易被误用：非常容易。参数名 `allowed_org_ids/organization_ids/user_info` 暗示已授权，实际全部是调用方可伪造数据；`permission_map={}` 还被多个入口当作全局访问。
6. 日志是否足够且不泄密：handler 有 task/host 等摘要，但框架仍原样回传异常对象，领域 callback 也保留原始错误文本；缺少统一 correlation ID、safe code 与 redaction。
7. 状态异常时能否判断停在哪个阶段：request/reply 只能区分 listener 抛异常与 handler 返回；单向 callback 没有应用 ack、pending、重试或 dead letter，不能判断 broker 接收后是否完成业务写。
8. 设计是否降低复杂度：统一注册器与本地/NATS双客户端降低了调用样板，但把身份、schema、错误和资源治理全部下放给每个 handler，整体复杂度转移到安全事故和兼容分叉。

## 5. Recommendation

**Block**。

上线前必须先关闭 `CMDB-F62`：为 NATS dispatch 建立可信 service/caller identity、subject allowlist 与不可由 payload 伪造的授权上下文，并把所有裸查询、关系写和 callback 纳入统一 fail-closed 权限。随后移除 `pickled_exc/jsonpickle.decode`，采用脱敏、跨语言的稳定错误 envelope；为注册器和 handler 建立 schema、message/rows/batch/time/response/deadline 预算。跨域 `CMDB-F14/F25/F31/F33/F43/F50/F59` 必须一并收敛。仅要求调用方“正确传 user_info”、继续比较自报 scope，或只增加 caller timeout，均不足以批准生产。
