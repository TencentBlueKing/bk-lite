# CMDB 查询与拓扑生产级审查

## 1. Summary

查询域的正向骨架已经具备：实例列表以组织分支组合实例名/创建人规则并在图层分页；未指定排序时两种图驱动都按内部 ID 排序；全文检索的新接口把统计和按模型分页拆开且把 `page_size` 限为 100；实例详情、附件下载、拓扑中心节点都先做菜单和实例权限校验；通用拓扑会在内存剪掉不可见父节点及其子树，网络拓扑另有节点上限和 `truncated` 标记；导入行内 organization 已按当前组织/子组织范围 fail-closed。

但关系型读取与写入没有把授权传递到每个真实端点。关联列表只校验中心实例便返回对端完整实体；导出关联列复用该无权限 Service；导入虽然校验新实例 organization，却全量加载关联模型实例名并直接建边；通用和网络拓扑只取得中心模型的权限映射，再把它用于其他模型节点，而底层实例判权不核对映射属于哪个模型。于是同一根因同时形成跨组织读、跨组织关系写和拓扑泄露，本报告合并为一个主 Finding。

排序契约还存在可直接触发的安全和双驱动兼容问题：`order` 原样来自 HTTP，Service 把 `-field` 改写为 `field DESC` 却仍当作字段传递。Neo4j 驱动把字段原样拼进 Cypher，存在注入/越权查询面且降序会生成双方向语法；FalkorDB 会用字段白名单拒绝包含空格的 `field DESC`。直接调用验证器已确认 `validate_field("inst_name DESC")` 抛 `BaseAppException`。

规模边界也不一致。新全文按模型接口有限额，旧全文入口仍一次返回所有命中；普通列表 `page_size` 无上限；导入和导出会按模型全量加载图实例；通用拓扑虽限定深度，却先查询全部长度不超过 4 的路径，没有节点/路径上限，稠密图会产生路径爆炸。网络拓扑的节点上限不能补偿这些入口。

本域确认 4 个主 Finding：P0 2 个、P1 1 个、P2 1 个、P3 0 个，编号为 `CMDB-F14`–`CMDB-F17`。导入通过裸 `batch_save_entity` 修改实例、全量加载唯一候选且缺少 Operation/恢复，与 Task 3 `CMDB-F10/CMDB-F11` 同根因，本域只记录跨域证据，不重复计数。Recommendation 为 **Request changes**。

## 2. Findings

### Finding CMDB-F14：跨模型关系读写与拓扑只授权中心模型，未校验真实对端

- Severity: P0
- Location: `server/apps/cmdb/views/instance.py:707-746,840-861,983-1047`；`server/apps/cmdb/services/instance.py:334-435,948-1004,1446-1466,1523-1621`；`server/apps/cmdb/utils/Import.py:643-656,713-837`；`server/apps/cmdb/utils/export.py:241-268`
- Root cause category: 权限边界缺失
- Evidence: `instance_association_instance_list`/`instance_association` 只对请求中的中心实例调用 `require_instance_permission`，Service 随后查询两侧关系并在 `return_entity=True` 时返回对端完整实例，未按对端 `model_id`/organization 再判权。实例导出只裁剪根实例，`Export.format_inst_asst_name` 又调用同一无权限关联 Service，把所有对端 `inst_name` 写入 Excel。导入的 `allowed_org_ids` 只进入 Excel organization 单元格解析；`format_import_asso_data` 对当前模型和关联模型分别执行无权限、无分页全量查询，按名称解析任意对端，`add_asso_data` 直接 `create_edge`。通用/网络拓扑则只调用一次 `format_user_groups_permissions(..., center.model_id)`；`_has_topology_view_permission` 对不同 `instance.model_id` 仍复用这张 map，而 `has_object_permission` 的 instances 分支只看 organization/inst_name，不验证 map 所属 model。因此中心模型的组织全选可被误当成关联模型的全选权限。
- Trigger: 对可见中心实例查询关联或选择关联列导出，而关系对端属于用户无权组织/模型；在导入 Excel 关联列填入同名越权实例；从可见中心节点展开包含其他模型的通用/网络拓扑。
- Impact: 调用者可读取越权对端完整实体或至少实例名、模型与关系存在性；可把自己组织的实例与其他组织资产建立关系边并产生误导拓扑/审计；拓扑还可能泄露跨模型资产和接口连线。权限拒绝不是 fail-closed，而是沿关系跨模型扩散中心授权。
- Why existing tests missed it: `test_instance_views.py` 只断言中心实例校验和 Service 被调用，对端固定为同组织 Mock；导出测试直接 Mock 无权限 Service；导入关联测试用全局 Fake Graph 且不构造跨组织对端；指定六文件没有任何通用/网络拓扑权限测试。
- Minimal safe fix: 所有关联返回、导出列、导入建边和拓扑节点先按实际 `model_id` 分组，为每个模型独立构建权限映射并逐端点裁剪；关系只有两端均可见/可操作时才能返回或创建。导入目标应以 `(model_id, organization, inst_name)` 或稳定 ID 解析，重名必须拒绝。
- Required tests: 中心可见/对端不可见的关联 list/detail/export；同名跨组织对端；导入跨组织关联拒绝且零图写；多模型拓扑逐节点权限、隐藏父级子树 fail-closed、creator 路径和 include_children；两端均授权的正向回归。
- Long-term design note: 将“关系授权”定义为一等契约：读取要求两端 VIEW，写入要求两端 OPERATE，并由统一 Service 接收按模型权限上下文，禁止 View 层只校验起点后调用裸图查询。

### Finding CMDB-F15：实例排序字段可注入 Neo4j Cypher，且降序在两种驱动均不可用

- Severity: P0
- Location: `server/apps/cmdb/views/instance.py:232-280`；`server/apps/cmdb/services/instance.py:599-629`；`server/apps/cmdb/graph/neo4j.py:340-425`；`server/apps/cmdb/graph/falkordb.py:694-785`；`server/apps/cmdb/graph/validators.py:94-117`
- Root cause category: 输入验证与驱动契约缺陷
- Evidence: `search` 把 `request.data.order` 直接交给 `instance_list`。升序值不做字段白名单；降序把所有 `-` 删除后拼为 `field DESC`，但仍放在 `order` 字段。Neo4j `query_entity` 直接插值 `ORDER BY n.{order} {order_type}`，所以任意 Cypher 片段进入查询；正常 `-inst_name` 也成为 `ORDER BY n.inst_name DESC ASC`。FalkorDB 虽调用 `CQLValidator.validate_field(order)` 防注入，却会拒绝含空格的 `inst_name DESC`。本次用 `.venv/bin/python -c` 直接调用验证器，稳定得到 `Invalid field name: 'inst_name DESC'`。
- Trigger: 持有 `asset_info-View` 的调用者提交恶意 `order`；或任何用户提交文档支持的 `order=-inst_name`。
- Impact: Neo4j 模式下可形成查询注入面，最少造成 500/高成本查询，且可能通过 `UNION` 等语法绕过原权限过滤读取其他节点；正常降序在 Neo4j 生成非法语法，在 FalkorDB 被验证器拒绝。相同 API 在两种受支持驱动上行为不一致。
- Why existing tests missed it: `test_search_ok` Mock 掉 `InstanceManage.instance_list`，只检查 count；没有 order 正反向、恶意字段或两驱动查询构造测试。指定测试没有实际连接 FalkorDB/Neo4j。
- Minimal safe fix: View/Service 只接受模型 attrs 与固定系统字段白名单；把方向单独解析成 `order_type`，底层只接收已验证字段和 `ASC/DESC`。Neo4j 也必须复用 `CQLValidator`，并在业务层返回稳定 400 而不是驱动异常。
- Required tests: 合法升/降序在两驱动生成等价查询；非法字段、空格/点号/Cypher 关键字/`UNION` 均 400 且零图调用；相同排序值以内部 ID 作为二级键，跨页无重复/遗漏。
- Long-term design note: 图驱动接口应使用结构化 `Sort(field, direction, tie_breaker)`，禁止用字符串同时承载字段和方向。

### Finding CMDB-F16：列表、旧全文、导入导出和通用拓扑缺少统一硬资源上限

- Severity: P1
- Location: `server/apps/cmdb/views/instance.py:232-280,756-872`；`server/apps/cmdb/services/instance.py:599-629,1330-1424,1446-1512,1767-1802`；`server/apps/cmdb/utils/Import.py:643-739`；`server/apps/cmdb/graph/falkordb.py:1373-1401,1963-2062`
- Root cause category: 资源边界缺失
- Evidence: `search` 仅要求 `page_size>=1`，没有最大值，图查询会直接使用该 LIMIT；旧 `fulltext_search` 没有分页/limit，FalkorDB 对所有属性执行 ANY/CONTAINS 后返回全部实体。导入先按 `model_id` 全量加载 `exist_items`，有关联时再逐关联模型全量加载名称映射；导出 `inst_ids` 为空时全量读取所有授权实例并在 Python/openpyxl 内存生成工作簿，选择关联时还逐实例发起关系查询。`query_topo_lite` 固定请求 `depth+1`（当前 4）层的全部可变长路径，权限裁剪发生在查询完成后，没有路径/节点/字节上限。只有新全文 by-model 的 100 条上限与 network topology 的 node_limit 是有界的例外。
- Trigger: `search` 传入超大 `page_size`；旧全文用宽泛关键词匹配大模型；导入/导出大模型或选择关联列；在高扇出/环状关系图上打开通用拓扑。
- Impact: 图数据库长查询、应用与 openpyxl 内存膨胀、请求超时和 Worker/进程 OOM；导出关联形成 N+1；通用拓扑的路径数可按扇出指数增长，权限后置裁剪不能保护图服务。攻击者只需普通查看/搜索权限即可放大资源。
- Why existing tests missed it: 列表测试未断言 page_size 上限；六文件不调用全文三接口；导入/导出仅用少量 Fake 数据并只检查 xlsx 魔数/格式；拓扑主题测试不执行图查询。没有查询预算、峰值内存、超限响应或稠密图用例。
- Minimal safe fix: 普通列表与所有内部分页统一最大 100；旧全文下线或改为受限分页；导入/导出使用稳定 ID 游标和明确行数/文件大小/关联数上限，超限返回可识别错误；拓扑在图查询层限制节点/边/路径并尽早按模型权限收敛，返回 `truncated`。
- Required tests: 所有入口的边界值与超限零大查询；旧全文最大返回；导入文件行/关联列/目标模型上限；导出根实例与关联总量上限及无 N+1；稠密图在预算内截断、隐藏父级不穿透；超限错误不泄露内部异常。
- Long-term design note: 建立 QueryBudget（rows/nodes/edges/paths/bytes/deadline）并由 View、Service、驱动共同消费，不依赖每个入口各自记住 limit。

### Finding CMDB-F17：subnet 的 IPAM 主题契约与测试仍相互冲突

- Severity: P2
- Location: `server/apps/cmdb/services/topology_theme.py:32-43`；`server/apps/cmdb/tests/test_topology_theme.py:37-45`
- Root cause category: 契约漂移
- Evidence: 当前实现明确对 `model_id == "subnet"` 追加 `ipam`，但现有测试 `test_subnet_has_no_ipam_theme` 仍断言空列表。本次六文件真实运行稳定得到 `['ipam'] != []`；该现状与 projectmem 已登记 #0086 相同，仅作为当前代码证据，不另造历史结论。
- Trigger: 运行 CMDB 主题测试，或依赖测试定义的旧前端/接口契约发布。
- Impact: 模块门禁红；产品、后端实现和测试无法共同定义 subnet 应展示的主题，发布方无法区分产品变更还是回归。
- Why existing tests missed it: 并非未覆盖，而是覆盖锁定旧契约后实现发生变化，变更未同步测试/规格；主题单测全部 Mock 模型关联，不能证明主题对应服务可用。
- Minimal safe fix: 由产品契约确认 subnet 是否提供 IPAM；若是，更新测试并增加 `ipam_view` 权限/正向集成；若否，删除实现分支。不得仅跳过失败测试。
- Required tests: subnet/非 subnet 主题列表、主题与 `ipam_view` 可用性一致、无实例 VIEW 时主题入口不能绕过数据权限。
- Long-term design note: 主题注册应绑定 capability probe 与权限，而非散落的模型 ID 条件和独立测试期望。

### 跨域证据：导入实例批写引用 CMDB-F10 / CMDB-F11

- 主 Findings: `CMDB-F10`（批量唯一锁与全量候选，P1）、`CMDB-F11`（批量写无 Operation，P1）；本域不重复计数。
- Evidence: `inst_import_support_edit` 先按模型全量读取旧实例，再直接调用 `batch_save_entity`，随后依次创建关系、写审计并派发自动关系；没有 Idempotency-Key、唯一签名锁、Operation/Outbox 或阶段恢复。校验错误允许其他行已提交，接口又返回 `result=False`，调用方重试依赖底层名称匹配而非请求幂等状态。
- Required follow-up: 导入必须进入 Task 3 统一批写编排，并在此基础上再关闭本域 `CMDB-F14` 的关系双端授权与 `CMDB-F16` 的规模边界。

## 3. Test Review

在 `server/` 使用显式 `SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task4-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb` 和本地 MinIO 测试变量运行 brief 六文件，并添加五个查询/图模块的 coverage。首次在沙箱中因 uv 缓存 `.git` 无权限退出 2，未收集；受控读取缓存后最终 **115 passed、1 failed in 7.45s，exit 1**。唯一失败为 `test_subnet_has_no_ipam_theme`，对应 `CMDB-F17`。

覆盖率真实输出：`views/instance.py` **53%**（754/358 missed），`services/instance.py` **16%**（905/757 missed），`services/topology_theme.py` **95%**（19/1 missed），`graph/drivers/graph_client.py` **29%**（42/30 missed），合计 **33%**（1720/1146 missed）。虽然命令包含 `--cov=apps.cmdb.graph.falkordb`，该驱动未被测试路径导入，报告没有形成可声明的 FalkorDB 行覆盖率；因此不能把参数化查询或兼容性视为已测试。

有效证明包括：

- 列表拒绝缺失 model_id、非法 page，并把权限 map/creator 交给被 Mock 的 Service；实例详情对同名但不同组织的权限 fail-closed。
- `permission_util` 对组织全选、实例级授权、默认模型只读、同名跨组织拒绝的纯函数行为有明确断言。
- organization 导入支持名称/父子路径，越权组织被拒，缺少范围上下文 fail-closed；基础字段类型/表格/标签/枚举转换有覆盖。
- 关联导入/导出格式化、空组织、用户/枚举/表格输出有小数据行为断言；拓扑主题映射多数分支有直接断言。
- 附件下载测试确认 View 把实例读权限 callback 交给 Enterprise 扩展，上传/临时删除验证社区门面接线。

证明力不足包括：

- `search` Mock 掉 Service，未执行真实权限 CQL、排序、分页 count、超大 page_size、稳定二级排序或两驱动差异；全文三个 View/Service/驱动入口在六文件中均未调用。
- 关联 View 只验证中心实例；无对端权限负例。导出直接 Mock 返回对端名称；导入 Fake Graph 返回全局实体，没有跨组织目标与零图写断言。
- 没有通用/网络拓扑查询、跨模型权限、隐藏父级、深度、节点上限或路径预算测试。主题测试只 Mock 模型关联，且一个期望已漂移。
- 文件测试不执行真实 Enterprise overlay、对象存储、文件台账或下载 callback 内部拒绝路径；子模块未初始化，相关行为仍未验证。
- 没有真实 FalkorDB/Neo4j、MySQL/PostgreSQL、并发导入、大文件、稠密图、超时/OOM 或流式导出测试。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：新全文接口和网络拓扑注释清晰，但关系权限由 View、Service、Export、Import、拓扑各自拼接，实际边界难以从单点判断。
2. 新增同类插件是否需要复制代码：是。新增关系视图/主题必须手工记住两端权限和各模型 map，现有调用已漏三类路径。
3. 新增错误类型是否需改多个模块：是。参数错误有 DRF 400、`BaseAppException`、`JsonResponse result=False` 和捕获后拼 `str(e)` 多种契约。
4. 新增 callback 模式是否容易扩展：文件门面可扩展，但社区无法审计 overlay 内部是否真正调用权限 callback；关系导出没有权限 callback 契约。
5. 当前接口是否容易被误用：是。`instance_association_instance_list` 和 `Export` 看似业务 Service，实为无授权裸查询；`order` 用字符串混合字段/方向。
6. 日志是否足够且不泄密：导入异常接口把 `str(e)` 返回客户端且日志带堆栈；导出 info 记录请求 IDs/关联选择，未见资源/截断指标。
7. 状态异常时能否判断停在哪个阶段：查询失败只能看到驱动异常；导入部分提交没有持久化 operation，无法判断实例、关系、审计、自动关系停点。
8. 设计是否降低复杂度：参数化 FalkorDB 和网络 node_limit 是正向基础，但 Neo4j 未共享验证器、权限后置裁剪与多套查询入口把复杂度转移到安全审计。

## 5. Recommendation

**Request changes**。

先关闭两个 P0：所有关联/导出/导入/拓扑按真实端点模型重算权限，两端都授权才允许读写；将排序改为结构化白名单并让 Neo4j/FalkorDB 复用同一验证和方向契约。随后为列表、旧全文、导入导出和通用拓扑建立统一硬预算，并把导入接入 `CMDB-F10/F11` 的批写状态机。`CMDB-F17` 必须由产品契约明确后同步实现与测试。仅让现有 1 个失败测试变绿，或只给新全文/网络拓扑保留局部 limit，均不足以批准生产。
