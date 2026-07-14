# CMDB 专项资源视图生产级审查

## 1. Summary

专项资源入口已有正确的第一层防线：K8s 集群、应用/系统、机房和机柜入口均先要求 `asset_info-View` 并校验根实例 VIEW；K8s setup 的 token/命令要求 `auto_collection-Execute`，verify 要求 View，补充测试证明拒绝路径不会调用 Service。K8s 子模型分别构造 permission map，Namespace 候选以 500 条权限分页先收敛；Pod 页限制 50、资源列表限制 500，Workload Pod 会校验所属集群和自身权限。名称与空关系也有明确行为：机房同格机柜进入 `conflicts`，Excel sheet 重名会加后缀，空关系返回空列表/空分组而不是异常。

生产阻断点有两项。第一，公开 render token 的使用计数是 `cache.get` 后 `cache.set` 的非原子读改写，并且每次成功验证都会重新设置 1800 秒 TTL；并发请求可共同读取同一计数后全部成功，周期性并发可同时突破 5 次上限和固定有效期，继续换取包含 NATS 接入参数的安装 YAML。第二，K8s 通用资源列表只验证 workload/node ID 属于集群，没有验证该父实例对当前用户可见；概览统计也在 workload 权限收敛前展开 Pod 关系，因此可从不可见父级看到仍可见 Pod 的明细或数量。

查询次数优化尚未形成资源预算。K8s 默认概览固定为 5 次批量关系调用但每次仍全量返回边并在内存保存全部关系 ID；应用拓扑按节点 BFS 查询、永远返回 `truncated=False`，实例明细/Excel 的 `node_ids` 无条数限制；机房布局先全量取 rack，再逐 rack 查询设备形成 N+1。固定调用次数、分页实体和批量查询都不能约束边总量、节点总量、响应字节或同步请求时长。

本域确认 3 个新增主 Finding：P0 2 个、P1 1 个、P2/P3 0 个，编号 `CMDB-F41`–`CMDB-F43`。应用/机房用根模型 permission map 裁剪其他模型的对端，引用 `CMDB-F14`；应用拓扑的无界遍历契约同时引用 `CMDB-F18`，不重复计数。Recommendation 为 **Block**。

## 2. Findings

### Finding CMDB-F41：K8s 安装 token 的并发计数与过期时间都可被续用突破

- Severity: P0
- Location: `server/apps/cmdb/services/infra.py:20-80`；`server/apps/cmdb/services/k8s_setup.py:71-80`；`server/apps/cmdb/views/k8s_setup.py:44-56`；`server/apps/cmdb/constants/infra.py:4-8`
- Root cause category: 并发或幂等设计问题
- Evidence: token 创建时写入 `usage_count=0/max_usage=5` 并设置 1800 秒缓存 TTL。公开 render 请求进入 `validate_and_get_token_data`，先 `cache.get`，在进程内判断旧计数，再把 `usage_count+1` 通过 `cache.set(..., timeout=1800)` 写回；没有原子 increment、compare-and-set、锁或一次性代次。两个请求可同时读取 4、均通过并各自写回 5，两个都继续调用 NodeMgmt/Webhook 渲染 YAML；更多并发同理。每次写回还从当前时刻重置 TTL，返回给调用方的 `expire_seconds=1800` 实际成为滑动过期。render 无登录认证是 token 设计本身，YAML 参数包含 NATS username/password/server/CA，因此计数与绝对过期是公开凭据渲染的核心边界。
- Trigger: 获得一个尚未耗尽的安装 token，在接近使用上限时并发调用 `/open_api/k8s_setup/render/`；或在 token 到期前持续并发调用并利用丢失更新保持计数未耗尽。
- Impact: 同一 bearer token 可超过声明的 5 次和 1800 秒继续生成采集器 YAML，泄露或滥用 NATS 接入配置、部署未授权采集器；响应头的 remaining usage 也可能与真实成功次数不一致。
- Why existing tests missed it: `test_infra_service.py` 把 cache.get/set 分别 Mock，只断言单请求加一和 timeout 参数；没有双请求交错、真实缓存原子性、绝对过期或第五次并发。补充 setup View 测试只证明内部 token 生成权限，不覆盖公开 render 生命周期。
- Minimal safe fix: 将 token 状态放到支持原子条件更新的持久化/缓存原语中，以 `usage_count < max_usage AND expires_at > now` 一次抢占使用资格；保存不可延长的 `expires_at`，成功消费不得刷新绝对 TTL；消费资格确认后再渲染，渲染失败是否返还次数需形成明确且幂等的状态规则。
- Required tests: 两个请求在 usage=4 同时抢占时仅一个成功；高并发成功总数不超过 5；第 1 次使用不延长创建时的绝对 expires_at；跨进程/Redis 后端等价；过期、耗尽和渲染失败的计数语义；失败响应不返回 NATS 凭据或 token 明文。
- Long-term design note: 把安装凭证建模为带绝对过期、原子消费记录和审计的短期 credential，而不是可变 dict 缓存；CMDB 与 Monitor 应复用同一 token issuance/consume 组件。

### Finding CMDB-F42：K8s 资源筛选与概览在不可见 Workload/Node 父级下仍暴露 Pod

- Severity: P0
- Location: `server/apps/cmdb/services/k8s_resource_overview.py:117-197,431-450,496-568`
- Root cause category: 局部实现错误
- Evidence: Namespace 候选正确调用 `_visible_candidate_ids`，但 cluster 的 `node_ids` 只取原始关系 ID。Pod 列表收到 `node_id` 时只检查它存在于原始 `node_ids`，随后按该 Node 的关系枚举 Pod 并仅应用 Pod permission；`workload_id` 同样只检查原始 `all_workload_ids`。因此父 Workload/Node 不可见而 Pod 可见时仍返回 Pod 名称、IP、资源 request/limit 等字段。默认概览也对 Namespace 下全部 `workload_ids` 查询 Pod 边，未先收敛可见 Workload；`pod_count` 与 Namespace 卡片的 workload/pod 数量可包含隐藏父级的子资源。
- Trigger: 用户能查看集群和某些 Pod，但没有目标 Workload 或 Node 的 VIEW；向 `k8s_resource_list/{cluster}/pod` 传该隐藏父级 ID，或打开包含隐藏 Workload 子 Pod 的默认概览。
- Impact: 越过父级 fail-closed 契约读取隐藏工作负载/节点下 Pod 的名称、地址和容量配置，或通过计数推断隐藏资源规模；显式父 ID 还可作为存在性探针。
- Why existing tests missed it: 测试覆盖隐藏 Namespace 剪枝、`get_workload_pods` 的 Workload 自身权限和隐藏 Node 名称替换，但通用 `list_resources` 只用全部可见父级；概览权限测试把所有 Workload/Pod 设为可见，且明确接受原始 `pod_count=3`，没有“父不可见、子可见”的反向组合。
- Minimal safe fix: 在构造任何子候选前，分别用对应 model permission map 收敛 cluster 下可见 Namespace、Workload、Node；显式 `namespace_id/workload_id/node_id` 必须同时满足集群归属和父实例 VIEW；概览统计只基于可见父链，禁止以名称置空或 virtual 节点代替父级裁剪。
- Required tests: Workload/Node 不可见但 Pod 可见时显式过滤拒绝且零 Pod 查询；默认概览和 Namespace 卡片不计隐藏父级子 Pod；父可见/子不可见、父子均可见、同名跨组织、空父关系；权限分页超过 500 条时无漏项且查询次数受控。
- Long-term design note: 延续已批准的“父资源权限先收敛、再构造子资源候选”组件，把父链校验作为 K8s relation traversal 的强制入口，所有 overview/layer/list 共用。

### Finding CMDB-F43：专项视图只有局部分页/批量化，没有关系、节点、查询与响应总预算

- Severity: P1
- Location: `server/apps/cmdb/services/instance.py:1008-1058`；`server/apps/cmdb/services/k8s_resource_overview.py:117-197,456-568`；`server/apps/cmdb/services/application_resource_overview.py:113-184,310-454`；`server/apps/cmdb/serializers/application_resource_overview.py:14-18`；`server/apps/cmdb/services/rack_room.py:150-167,250-309`
- Root cause category: 资源边界缺失
- Evidence: `instance_association_map` 的批量查询对 src/dst 两侧执行无 LIMIT 的 `query_edge` 并返回完整边集合。K8s 默认概览测试只锁定 5 次关系调用和“不读 Pod 实体”，真实实现仍为全部 Namespace→Workload、Workload→Pod、Namespace→Pod 边创建 list/set；资源页的 500 条上限只限制最终实体，不限制候选边。应用拓扑按每个已发现节点调用一次 `instance_association_instance_list`，depth 最多 3 但无 node/edge/query/deadline 上限且固定 `truncated=False`；POST `node_ids` 没有 max_length，实例明细和 openpyxl 导出全量加载。机房布局读取全部 rack 后在循环内逐 rack 调 `_rack_device_instances`，形成 1+R 关联查询并全量计算 U 位。
- Trigger: 大集群包含大量 Workload/Pod 关系；高扇出应用深度 3；提交超大 node_ids 导出；或单机房包含大量 rack/设备后同步打开布局。
- Impact: 单请求可在图数据库、Django Worker 和 openpyxl 中放大全部边/节点/工作簿，查询数或内存随资产规模线性乃至按扇出增长，造成超时、图连接占用和进程 OOM；已有 page_size 与固定调用次数无法提供上界。
- Why existing tests missed it: K8s 测试只断言关系调用数为 5 和 Pod 实体零查询，不限制每次边数/候选总量；应用 View 测试完全 Mock Service，应用 Service 仅 20% 覆盖；rack 测试证明 Room3D 摘要批量化，却没有验证 `get_room_layout` 使用该批量路径或设置查询预算。所有数据规模都很小，无超限/truncated/字节断言。
- Minimal safe fix: 定义请求级 rows/relations/nodes/queries/bytes/deadline 预算；批量关系查询支持游标和硬上限。K8s 达预算返回明确 truncated/分层游标；应用 BFS 分层批查并限制节点/边，node_ids 设置条数上限，Excel 超限改异步；room 复用 `_rack_device_relation_map` 一次批查设备并限制 rack/设备总量。
- Required tests: K8s 单次边数和总候选上限、达到预算的稳定 truncated；应用高扇出/环路固定查询预算、node_ids 边界和超大 Excel 拒绝；机房 1/500/501 rack 的固定查询次数、设备总量上限和空关系；两图驱动的截断/游标等价与超时取消。
- Long-term design note: `CMDB-F18` 已要求统一 `GraphTraversalBudget`；专项视图应在同一组件上增加关系游标、响应字节与导出作业预算，而不是分别用 page_size、调用次数或局部 batch 充当资源上限。

### 跨域证据：应用与机房对端授权引用 CMDB-F14

- 主 Finding: `CMDB-F14`（跨模型关系读写与拓扑只授权中心模型，P0）；本域不重复计数。
- Evidence: 应用入口只按根 `system/application` 构造一个 permission map，BFS、节点明细和导出用它判断 application/host/database 等其他模型；room/rack 同样把中心模型 map 用于 rack 和任意设备。实例判权不验证 permission map 所属模型，因此这正是 `CMDB-F14` 的专项可达入口。
- Required follow-up: 按真实 `model_id` 分组构造 permission map；根、父级和对端逐层 fail-closed；增加应用与机房跨模型/跨组织正反向测试。

## 3. Test Review

在 `server/` 使用显式 SQLite、MinIO 和 Celery 环境运行 brief 五文件并对四个 Service 与 K8s setup View 采集 coverage。首次沙箱命令因 `~/.cache/uv/sdists-v9/.git` 无权限退出 2、未收集；受控缓存权限重跑为 **51 passed in 4.75s，exit 0**。

覆盖率：`k8s_resource_overview.py` **76%**、`application_resource_overview.py` **20%**、`infra.py` **95%**、`rack_room.py` **89%**，合计 **63%**。brief 五文件没有导入 `views/k8s_setup.py`，因此该命令没有可声明的 setup View 覆盖率。补充运行 `test_k8s_setup_views.py` 为 **6 passed in 0.15s**，`views/k8s_setup.py` **79%**、`services/k8s_setup.py` **34%**，证明三项内部权限正反向和拒绝路径零 Service 调用。

有效证明包括：

- K8s 根实例必须是 cluster；四个子模型分别构造 permission map；Namespace 父级权限先分页收敛。
- Pod 页最大 50，资源列表参数为 Choice/整数；Workload Pod 跨集群拒绝，当前页 Node 关系批查。
- 默认概览固定 5 次批量关系调用且不加载 Pod 实体；基础层 20/50/50 稳定分页。
- hidden Node 的真实名称不回传；rack/device 拒绝时从布局裁剪；Room3D 摘要批查关系和实例。
- 机柜同格冲突、U 位重叠/越界、未定位、枚举标量化和空关系返回有行为断言；infra HTTP timeout/非 200/缺 YAML 有错误映射。

证明力不足包括：

- token 测试是串行 Mock，不证明并发消费、绝对 TTL 或真实 Redis/多进程行为。
- K8s 没有不可见 Workload/Node + 可见 Pod 的组合，也没有限制单次批量关系返回的边数。
- 应用资源指定文件只测 View 接线并 Mock 全部 Service，20% 覆盖没有进入 BFS、跨模型权限、明细、Excel、名称冲突和空分组主路径。
- room 主路径仍逐 rack 查询，测试未断言 `get_room_layout` 查询次数；Room3D 的批量测试不能替代该入口。
- 未连接真实 FalkorDB/Neo4j、Redis、多 Worker、NodeMgmt/Webhook/VictoriaMetrics，也未测大集群、高扇出应用、大机房或响应字节峰值。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：K8s 层级常量和 rack 纯布局函数清楚，但权限与预算分散在 View、通用 Instance 私有 helper 和三个专项 Service。
2. 新增同类插件是否需要复制代码：是。新增资源层要手工复制根校验、每模型 permission map、父级收敛、关系 batch 和分页，当前 list 已漏父权限。
3. 新增错误类型是否需改多个模块：是。BaseAppException、DRF ValidationError、HTTP response_error 和返回体 `error=str(e)` 并存。
4. 新增 callback 模式是否容易扩展：安装渲染委派清晰，但 token consume 与外部渲染没有持久化状态或幂等回执。
5. 当前接口是否容易被误用：是。`permission_map` 不带 model_id 类型约束，`instance_association_map` 名为 batch 却无结果上限，node_ids 无最大长度。
6. 日志是否足够且不泄密：token 只记前缀较好；但 verify 和 infra 异常会把外部 `str(e)`/response text 进入日志或错误契约，该敏感错误面引用 `CMDB-F25`。
7. 状态异常时能否判断停在哪个阶段：不能。token 无消费审计，拓扑/布局无 query budget、截断原因和阶段指标，无法区分图查询、权限裁剪或 Excel 构造超时。
8. 设计是否降低复杂度：K8s 关系批查和 Room3D batch 降低了局部查询数，但尚未形成可复用的父链授权和资源预算，局部优化仍可被全量结果放大。

## 5. Recommendation

**Block**。

合并前必须关闭两个 P0：token 使用资格改为绝对过期且原子消费；所有 K8s 子候选先按真实父模型权限收敛。随后关闭 P1，为 K8s、应用和机房建立统一关系/节点/查询/字节预算，并让 `get_room_layout` 使用批量设备关系路径。应用和机房的跨模型权限必须随 `CMDB-F14` 一并修复；仅保留内部 setup 权限、限制最终 page_size 或固定关系调用次数都不足以批准生产。
