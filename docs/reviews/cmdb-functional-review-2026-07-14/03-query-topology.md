# CMDB 查询与拓扑生产级审查

## 1. Summary

查询域已有若干正确骨架：实例列表把组织分支与实例名/创建人规则组合后在图层分页，未指定排序时按内部 ID 排序；新全文接口将统计和按模型分页拆开，并把 `page_size` 限制为 100；实例详情、附件下载和拓扑中心节点先校验功能与实例权限；通用拓扑后置裁剪不可见父节点及其子树，网络拓扑另有节点上限与 `truncated`；导入行内 organization 已按当前组织范围 fail-closed。

生产阻断点在关系端点授权。关联读取只校验中心实例便返回真实对端，导出关联列复用该裸 Service，导入只约束新实例 organization 却无权限解析关联模型对端并建边；通用/网络拓扑则把中心模型 permission map 用于其他模型节点。中心实例授权契约没有覆盖真实关系端点，形成跨组织读取、关系写入与拓扑泄露。

排序存在确定的双驱动契约错误。HTTP `order` 未结构化校验；Service 把 `-field` 改写成 `field DESC` 后仍作为字段传递。Neo4j 原样把字段拼到 `ORDER BY` 尾部，调用者可注入排序尾部子句覆盖分页 `SKIP/LIMIT` 并放大单次返回量，但前置 WHERE 权限过滤仍然生效；正常降序还会生成冲突方向。FalkorDB 会拒绝包含空格的 `field DESC`，合法降序稳定 500。未配置 `FALKORDB_HOST` 时 GraphClient 实际选择 Neo4j，设置后选择 FalkorDB，两条路径均可达。

资源问题按直接根因拆为三项：在线列表与旧全文缺少请求级上限；导入/导出全量物化并在关联导出形成 N+1；通用拓扑在图层查询深度 4 的全部可变长路径、节点权限和裁剪均发生在查询之后。三者触发方式、影响面和安全修复不同，分别登记。

本域最终确认 6 个主 Finding：P0 1 个、P1 4 个、P2 1 个、P3 0 个，编号为 `CMDB-F14`–`CMDB-F19`。导入通过裸 `batch_save_entity` 修改实例、全量加载唯一候选且缺少 Operation/恢复，与 Task 3 `CMDB-F10/CMDB-F11` 同根因，本域只记录跨域证据。Recommendation 为 **Request changes**。

## 2. Findings

### Finding CMDB-F14：跨模型关系读写与拓扑只授权中心模型，未校验真实对端

- Severity: P0
- Location: `server/apps/cmdb/views/instance.py:707-746,840-861,983-1047`；`server/apps/cmdb/services/instance.py:334-435,948-1004,1446-1466,1523-1621`；`server/apps/cmdb/utils/Import.py:643-656,713-837`；`server/apps/cmdb/utils/export.py:290-317`
- Root cause category: 跨层契约不一致
- Evidence: 两个关联 View 都只对请求中的中心实例调用 `require_instance_permission`。其中 `instance_association_instance_list` 以 `return_entity=True` 查询边，并把对端完整实体加入 `inst_list`；`instance_association` 未设置 `return_entity=True`，只返回关系边元数据，但同样没有验证边的另一端是否可见。实例导出只裁剪根实例，`Export.format_inst_asst_name` 在 290–317 行调用前一个无权限 Service 并写入全部对端名称。导入的 `allowed_org_ids` 只进入 organization 单元格解析，`format_import_asso_data` 无权限全量查询关联模型并按名称解析对端，随后直接建边。通用/网络拓扑只构造中心模型的 permission map；`_has_topology_view_permission` 对其他模型仍复用该 map，而实例判权只读取 organization/inst_name，不验证 map 所属模型。
- Trigger: 查询或导出可见中心实例的关系，而对端属于无权组织/模型；导入 Excel 关联列填写越权对端名称；从可见中心节点展开包含其他模型的拓扑。
- Impact: 可读取越权对端完整实体或实例名、模型和关系存在性；可把授权组织实例连接到其他组织资产；拓扑可展示无权跨模型节点和接口连线。
- Why existing tests missed it: 关联 View 只断言中心实例校验；导出测试直接 Mock 对端列表；导入 Fake Graph 不构造跨组织对端；指定六文件没有任何跨模型拓扑权限测试。
- Minimal safe fix: 所有关联读取、导出、导入建边与拓扑按真实 `model_id` 分组并独立构建权限上下文；关系读取要求两端 VIEW，关系创建要求两端 OPERATE；导入目标按 `(model_id, organization, inst_name)` 或稳定 ID 解析，跨组织重名拒绝。
- Required tests: 中心可见/对端不可见的关联 list/detail/export；同名跨组织对端；导入越权关联拒绝且零图写；多模型拓扑逐节点权限、隐藏父级子树 fail-closed、creator/include_children 正反向用例。
- Long-term design note: 将关系双端授权定义为统一 Service 契约，禁止 View 只校验起点后调用裸关系或拓扑查询。

### Finding CMDB-F15：实例排序字段/方向契约跨 View、Service 与双驱动不一致

- Severity: P1
- Location: `server/apps/cmdb/views/instance.py:232-280`；`server/apps/cmdb/services/instance.py:599-629`；`server/apps/cmdb/graph/neo4j.py:340-425`；`server/apps/cmdb/graph/falkordb.py:694-785`；`server/apps/cmdb/graph/validators.py:94-117`
- Root cause category: 跨层契约不一致
- Evidence: `search` 把请求 `order` 直接交给 Service；Service 对降序生成 `field DESC`，但驱动接口本应分别接收 field/order_type。Neo4j 把 order 原样拼接进 `ORDER BY n.{order} {order_type}`，排序尾部输入可覆盖后续分页 `SKIP/LIMIT`，而前置 WHERE 仍保留；正常 `-inst_name` 生成冲突的 `DESC ASC`。FalkorDB 用 `validate_field` 拒绝 `inst_name DESC`；直接验证稳定抛 `Invalid field name`。GraphClient 在无 `FALKORDB_HOST` 时选择 Neo4j，配置该变量后选择 FalkorDB。
- Trigger: 提交 `order=-inst_name`；或在 Neo4j 路径提交包含排序尾部分页子句的 order。
- Impact: 合法降序在 Neo4j/FalkorDB 均失败；Neo4j 路径可绕过接口期望的页大小、放大单次返回量与查询资源，但不能据当前证据声称绕过前置权限 WHERE。
- Why existing tests missed it: `test_search_ok` Mock 掉 `InstanceManage.instance_list`；没有合法升降序、排序尾部输入、稳定分页或两驱动查询构造测试。
- Minimal safe fix: View/Service 只接受模型 attrs 与固定系统字段白名单，将方向解析为独立 `order_type`；两驱动复用字段/方向验证并对非法输入返回 400；排序字段相同值增加内部 ID 二级键。
- Required tests: 双驱动合法升降序等价；空格、点号、关键字和分页子句均 400 且零图调用；相同排序值跨页无重复/遗漏；验证前置权限条件不因排序变化而改变。
- Long-term design note: 驱动接口使用结构化 `Sort(field, direction, tie_breaker)`，禁止字符串混合字段、方向和查询片段。

### Finding CMDB-F16：在线实例列表与旧全文检索没有请求级返回上限

- Severity: P1
- Location: `server/apps/cmdb/views/instance.py:232-280,864-872`；`server/apps/cmdb/services/instance.py:599-629,1767-1802`；`server/apps/cmdb/graph/falkordb.py:1963-2062`；`server/apps/cmdb/graph/neo4j.py:983-1016`
- Root cause category: 资源边界缺失
- Evidence: 普通 `search` 只校验 `page_size>=1`，直接把任意大整数变成图查询 LIMIT；旧 `fulltext_search` 没有 page/page_size/limit。FalkorDB 在 1963–2062 行执行属性全文条件并返回全部命中实体；默认可达的 Neo4j 在 983–1016 行同样构造 `MATCH ... RETURN n` 且没有 SKIP/LIMIT。新 by-model 接口的 100 条限制没有覆盖这两个旧入口。
- Trigger: 具有 `asset_info-View` 的调用者提交超大 page_size；具有 `search-View` 的调用者用空泛/高命中关键词调用旧全文入口。
- Impact: 单请求可返回大量图节点并放大图查询、序列化和响应内存，造成接口超时、进程内存压力与其他在线请求延迟。
- Why existing tests missed it: 列表只测试缺 model、非法 page 和小数据成功；六文件不调用全文 View/Service/驱动，没有最大值或超限断言。
- Minimal safe fix: 列表统一限制 page_size≤100；旧全文下线或改为受限分页并返回明确 count/next；Service 与驱动保留防御性上限，超限稳定 400。
- Required tests: 1/100/101 边界、极大整数和非整数；旧全文最大返回、分页稳定性、宽泛关键词；超限零大查询且错误不回显驱动细节。
- Long-term design note: 所有在线实体查询共享请求级 rows/bytes/deadline 预算，而不是只有新接口局部限制。

### Finding CMDB-F17：实例导入导出全量物化，关联导出按实例 N+1 查询

- Severity: P1
- Location: `server/apps/cmdb/views/instance.py:756-861`；`server/apps/cmdb/services/instance.py:1330-1424,1470-1512`；`server/apps/cmdb/utils/Import.py:643-739`；`server/apps/cmdb/utils/export.py:192-268,285-317`
- Root cause category: 资源边界缺失
- Evidence: 导入前按 model_id 全量加载 `exist_items`，有关联列时又逐关联模型全量构造名称/ID映射；导出未传 ids 时一次读取所有授权实例，再由 openpyxl 在内存构造完整工作簿。选择关联列后，`export_inst_list` 对每个根实例单独调用 `instance_association_instance_list`，形成 N+1 图查询。入口没有文件行数、根实例数、关联目标数或生成字节数上限。
- Trigger: 对大模型导入含关联列的 Excel；导出不传 inst_ids，或导出大量根实例并选择关联列。
- Impact: 图结果和工作簿同时常驻内存，关联导出查询数随根实例线性增长；同步 HTTP 请求可超时、占满图连接或使应用进程 OOM。
- Why existing tests missed it: 导入/导出测试只用少量 Fake 实体并检查解析或 xlsx 魔数；关联导出直接 Mock 一次 Service，没有查询预算、峰值内存、超限响应或大模型数据。
- Minimal safe fix: 导入先限制上传字节/行/关联目标总数，并用稳定 ID 游标与有界候选解析；导出限制根行和关联总量，按批查询关系并流式/异步生成文件；超限返回可识别错误和建议分批。
- Required tests: 文件大小、行数、关联单元格和目标数边界；导出根实例/关联总量边界；固定批量关系查询预算、无 N+1；超限零部分文件、临时对象清理和内存上界。
- Long-term design note: 大批量导入导出应是有状态作业，以游标、进度、结果文件和过期回收表达，不在同步请求内全量物化。

### Finding CMDB-F18：通用拓扑在权限裁剪前执行无节点/路径预算的可变长查询

- Severity: P1
- Location: `server/apps/cmdb/services/instance.py:365-435,1446-1466`；`server/apps/cmdb/graph/falkordb.py:1373-1401`；`server/apps/cmdb/graph/neo4j.py:618-634`
- Root cause category: 资源边界缺失
- Evidence: `query_topo_lite` 把业务 depth 3 扩为 probe_depth 4，并对源/目标分别执行 `[*1..4]` 的全部路径查询。图层没有节点、边、路径、结果字节或执行时限预算；所有节点收集、实例批查、权限判定和父级剪枝都在路径结果返回后进行。网络拓扑已有 node_limit，但通用拓扑没有复用。
- Trigger: 普通资产查看者打开高扇出、存在多条并行路径或环路的实例拓扑，或反复展开高连接节点。
- Impact: 返回节点数有限也不能约束中间路径数；稠密图中路径数量按层级快速增长，图数据库 CPU/内存和应用路径解析成本可在权限裁剪前被放大，造成拓扑超时并影响共享图服务。
- Why existing tests missed it: 指定测试只覆盖主题字符串，不调用 `query_topo_lite`；没有稠密图、并行路径、环、超限、truncated 或图查询预算断言。
- Minimal safe fix: 在图层按允许模型/权限尽早收敛，并设置节点、边、路径与 deadline 上限；分层增量查询而非一次返回全部路径；达到预算返回 `truncated` 和稳定游标/展开令牌。
- Required tests: 高扇出、并行路径和环状图在预算内截断；源/目标双向总预算；隐藏父级不穿透；超时取消；FalkorDB/Neo4j 等价节点与截断语义。
- Long-term design note: 通用、网络和应用拓扑应共享统一 GraphTraversalBudget 与逐层遍历组件，避免每个主题重复定义资源控制。

### Finding CMDB-F19：应用拓扑旧分支意外回带已迁出左侧菜单的 subnet IPAM 主题

- Severity: P2
- Location: `server/apps/cmdb/services/topology_theme.py:32-43`；`server/apps/cmdb/tests/test_topology_theme.py:37-45`；历史提交 `f2f2ee211`、`c729f2299`
- Root cause category: 跨层契约不一致
- Evidence: `f2f2ee211` 的提交意图和 diff 明确写明 “drop subnet ipam topo theme (moved to dedicated left menu)”，同时删除 `TOPO_THEME_IPAM` 分支并把测试改为 subnet 返回空。后续 `c729f2299` 从不包含该删除的另一分支旧基线新增应用拓扑，在加入 `app_overview` 时把 `TOPO_THEME_IPAM` import 和 subnet 分支一并带回，却保留当前分支的“无 IPAM 主题”测试。两提交互不为祖先，当前实现是确定的旧版本回带业务回归。
- Trigger: subnet 详情请求拓扑主题，或运行 `test_subnet_has_no_ipam_theme`。
- Impact: IPAM 已迁到独立左侧菜单后又在关系主题中重复出现，形成重复/错误导航；模块测试稳定失败，阻断门禁。
- Why existing tests missed it: 回带提交来自并行旧基线，合并保留了正确测试却没有在提交后运行该测试，冲突没有形成文本级 merge conflict。
- Minimal safe fix: 删除 `TOPO_THEME_IPAM` import 和 `model_id == "subnet"` 回带分支，保留现有 `test_subnet_has_no_ipam_theme` 回归测试；本审查阶段只记录，不修改生产代码。
- Required tests: 保留 subnet/非 subnet 均无 IPAM 主题；system/application 仍有 app_overview；网络设备仍有 network；前端独立 IPAM 左侧菜单入口的路由回归。
- Long-term design note: 并行功能分支合并时对已删除能力使用语义回归清单，避免旧基线新增相邻功能时重新引入已迁移入口。

### 跨域证据：导入实例批写引用 CMDB-F10 / CMDB-F11

- 主 Findings: `CMDB-F10`（批量唯一锁与全量候选，P1）、`CMDB-F11`（批量写无 Operation，P1）；本域不重复计数。
- Evidence: `inst_import_support_edit` 全量读取旧实例后直接调用 `batch_save_entity`，再创建关系、写审计并派发自动关系；没有 Idempotency-Key、唯一签名锁、Operation/Outbox 或阶段恢复。
- Required follow-up: 导入接入 Task 3 统一批写编排，并在其上关闭本域 `CMDB-F14` 的双端授权与 `CMDB-F17` 的批量资源边界。

## 3. Test Review

在 `server/` 使用显式 `SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task4-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb` 和本地 MinIO 测试变量运行 brief 六文件，并添加五个查询/图模块 coverage。首次沙箱执行因 uv cache 无权限退出 2、未收集；受控缓存权限重跑最新为 **115 passed、1 failed in 7.38s，exit 1**。唯一失败是 `test_subnet_has_no_ipam_theme`，对应 `CMDB-F19`。

覆盖率：`views/instance.py` **53%**、`services/instance.py` **16%**、`services/topology_theme.py` **95%**、`graph/drivers/graph_client.py` **29%**，合计 **33%**。命令虽包含 FalkorDB coverage，但驱动未被测试路径导入，无可声明 FalkorDB 行覆盖率。

有效证明包括：

- 列表拒绝缺 model_id/非法 page；实例详情对同名不同组织权限 fail-closed。
- permission util 覆盖组织全选、实例级授权、默认模型只读、同名跨组织拒绝。
- organization 导入支持名称/父子路径，越权组织和缺少范围上下文 fail-closed。
- 小数据关联导入导出格式化、附件 View 到 Enterprise callback 接线、主题多数分支有断言。

证明力不足包括：

- search Mock 掉 Service，未测试 order、page_size 上限、稳定分页或两驱动；全文三个入口均未调用。
- 无关联真实对端权限、跨组织关联导入、通用/网络拓扑权限与路径预算测试。
- 导入导出均是小 Fake 数据，无 N+1、峰值内存、文件/行/字节上限验证。
- 未连接真实 FalkorDB/Neo4j；Enterprise 子模块未初始化；MySQL/PostgreSQL、并发、大文件和稠密图未验证。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：新全文和网络拓扑注释清晰，但关系权限与资源预算分散在 View、Service、Import、Export 和驱动。
2. 新增同类插件是否需要复制代码：是。新增关系/主题需手工补两端权限与预算，当前已漏多个入口。
3. 新增错误类型是否需改多个模块：是。参数错误有 DRF 400、BaseAppException、JsonResponse result=False 和驱动异常多种契约。
4. 新增 callback 模式是否容易扩展：文件门面可扩展，但关系导出/导入没有权限 callback 或预算契约。
5. 当前接口是否容易被误用：是。关联 Service 是裸查询；order 字符串混合字段和方向；拓扑“lite”只限制深度不限制路径。
6. 日志是否足够且不泄密：缺少查询预算、截断、N+1 和导入导出进度指标；导入异常还会向客户端拼接 str(e)。
7. 状态异常时能否判断停在哪个阶段：查询只有驱动错误；导入无持久化 operation，不能判断实例、关系、审计和自动关系停点。
8. 设计是否降低复杂度：局部参数化与 network node_limit 有价值，但未形成双驱动、关系授权和遍历预算的统一契约。

## 5. Recommendation

**Request changes**。

先关闭 P0 `CMDB-F14`，确保所有关系端点按真实模型做双端授权。随后修复 P1：结构化排序并统一双驱动契约；为在线列表/旧全文设置请求上限；把导入导出改为有界批次并消除关联 N+1；为通用拓扑建立图层遍历预算。`CMDB-F19` 应按历史决定删除 IPAM 回带分支并保留现有测试。仅更新失败测试、只限制新全文或只保留 network node_limit 均不足以批准生产。
