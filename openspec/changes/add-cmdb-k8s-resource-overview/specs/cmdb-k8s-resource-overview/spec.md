## ADDED Requirements

### Requirement: K8S 集群资源详情一级入口
系统 SHALL 仅在 `k8s_cluster` 实例详情提供一级菜单「资源详情」，该菜单 SHALL 与「基础信息」「关联关系」「变更记录」并列，并 SHALL 保留现有通用关联关系页面及其能力。

#### Scenario: K8S 集群显示资源详情
- **WHEN** 用户具有目标 `k8s_cluster` 实例的查看权限并打开其实例详情
- **THEN** 系统在实例详情一级导航中显示「资源详情」入口
- **AND** 「资源详情」排列在「基础信息」之后、「关联关系」之前
- **AND** 用户进入该入口后看到独立的 K8S 资源导航与内容区域

#### Scenario: 非 K8S 集群不显示资源详情
- **WHEN** 用户打开非 `k8s_cluster` 模型的实例详情
- **THEN** 系统不显示「资源详情」入口

#### Scenario: 通用关联关系保持独立
- **WHEN** 用户在 `k8s_cluster` 实例详情选择「关联关系」
- **THEN** 系统继续展示现有通用关联关系页面
- **AND** 不把 K8S 资源详情嵌入该页面的子视图

### Requirement: 不展示未实现页签
系统 SHALL 仅注册和展示 v1 已交付能力对应的导航入口，并 MUST NOT 为后续迭代预留空白、禁用或不可用页签。

#### Scenario: 资源详情渲染 v1 导航
- **WHEN** 用户打开 K8S「资源详情」
- **THEN** 系统仅展示当前可用的概览和资源类型导航
- **AND** 不展示「关系拓扑」「网络流向」或其他尚未实现的页签

#### Scenario: 后续能力尚未交付
- **WHEN** 某个规划能力尚未包含在当前版本
- **THEN** 该能力的页签、路由入口和占位文案均不存在

### Requirement: 三栏桌面布局与二级导航折叠
系统 SHALL 在现有实例一级导航、K8S 二级资源导航和内容区组成的三栏桌面布局中，为二级资源导航提供折叠和窄屏覆盖模式，并 SHALL 避免通过挤压内容区或外层横向滚动适配窄屏。

#### Scenario: 标准桌面宽度
- **WHEN** 可用页面宽度足以容纳三栏且内容区不少于 1100px
- **THEN** K8S 二级资源导航默认以 220px 宽度展开
- **AND** 用户可以手动折叠为 56px 图标栏

#### Scenario: 内容区宽度不足
- **WHEN** 展开的二级资源导航会使内容区宽度低于 1100px
- **THEN** 系统自动将二级资源导航折叠为 56px
- **AND** 用户临时展开时导航以覆盖式面板显示，不继续压缩内容区

#### Scenario: 保留会话折叠状态
- **WHEN** 用户在当前会话中手动折叠或展开二级资源导航
- **THEN** 页面在资源子视图切换期间保持该状态

#### Scenario: 桌面端边界
- **WHEN** 用户在宽度不低于 1280px 的桌面浏览器访问资源详情
- **THEN** 拓扑和表格在内容区内自适应
- **AND** 页面外层不产生横向滚动条
- **AND** v1 不承诺独立移动端布局

### Requirement: 默认资源概览
系统 SHALL 在首次进入视图时展示当前集群下用户可见的 Cluster、Namespace、Workload 和 Node 节点，且 MUST NOT 首屏加载具体 Pod 节点。

#### Scenario: 首屏加载基础拓扑
- **WHEN** 用户首次打开 K8S 资源视图
- **THEN** 系统返回并展示 Cluster、Namespace、Workload、Node 及其现有 CMDB 关联
- **AND** 系统不请求或展示具体 Pod 节点

#### Scenario: 默认显示资源统计
- **WHEN** 基础视图加载成功
- **THEN** 系统展示当前用户可见的 Namespace、业务 Workload、Pod、Node 数量
- **AND** Pod 数量同时包含有 Workload 归属和未归属 Pod

### Requirement: 概览信息不侵占资源列表
系统 SHALL 仅在二级导航选择“概览”时展示资源指标卡和分层拓扑，并 MUST NOT 展示采集事实区域，也 MUST NOT 在 Namespace、Workload、Pod、Node 资源列表页重复展示这些概览区域。

#### Scenario: 打开概览
- **WHEN** 用户选择二级导航“概览”
- **THEN** 页面展示资源指标卡和分层拓扑
- **AND** 不展示最近上报、最近成功采集、最近结果或采集任务等采集事实

#### Scenario: 打开资源列表
- **WHEN** 用户选择 Namespace、任一 Workload 分类、Pod 或 Node
- **THEN** 页面内容区仅展示当前资源标题、适用的关联筛选、名称搜索、刷新和资源列表
- **AND** 不展示资源指标卡或概览拓扑

#### Scenario: 从列表返回概览
- **WHEN** 用户从资源列表返回“概览”
- **THEN** 页面恢复离开概览前的 Workload 展开集合和已加载分支缓存

### Requirement: 五列 DIV 分层拓扑视觉结构
系统 SHALL 使用 CSS Grid、DIV 节点和轻量 SVG 关系线表达固定列头 `Cluster | Namespace | Workload | Pod | Node`，并 MUST NOT 使用 X6 通用画布组件。

#### Scenario: 首屏渲染五列结构
- **WHEN** 用户打开概览
- **THEN** 页面固定展示 Cluster、Namespace、Workload、Pod、Node 五个列头
- **AND** 列头与节点由 DOM 元素渲染
- **AND** Pod 列在未展开 Workload 时不创建占位节点
- **AND** Node 列展示首屏已加载的可见 Node

#### Scenario: 展开 Pod 后保持 Node 唯一
- **WHEN** 用户展开一个或多个 Workload
- **THEN** Pod 节点出现在 Pod 列并关联到 Node 列中的既有唯一 Node
- **AND** 既有 Cluster、Namespace、Workload、Node 的位置保持稳定

#### Scenario: 长列使用共享滚动
- **WHEN** 任一拓扑列的节点超出当前拓扑内容区
- **THEN** 五列在同一个纵向滚动容器中同步滚动
- **AND** 列头保持固定
- **AND** 各列不创建独立滚动条
- **AND** 页面不额外生成横向滚动条

#### Scenario: DOM 变化后关系线保持对齐
- **WHEN** 容器尺寸、节点集合、Pod 展开状态或基础层批次发生变化
- **THEN** 系统根据节点 DOM 位置重新计算 SVG 关系线端点
- **AND** 滚动、展开或收起后关系线仍连接正确节点
- **AND** SVG 关系层不接收鼠标或键盘事件

#### Scenario: 不展示非 v1 层级与工具
- **WHEN** 系统渲染 v1 分层拓扑
- **THEN** 不显示 Container、Service 列
- **AND** 不显示缩略图、放大、缩小、适应画布、画布拖动、拓扑导出或独立拓扑刷新

#### Scenario: 保持资源类型视觉编码
- **WHEN** 用户选择拓扑节点
- **THEN** 节点使用蓝色描边表达选中状态
- **AND** 节点原有资源类型颜色保持不变

### Requirement: 基础拓扑分层增量展示
系统 SHALL 对 Namespace、Workload、Node 使用明确的服务端增量展示，首批分别最多展示 20、50、50 个节点，并 SHALL 显示每层已展示数量和当前可见总数，不得静默截断。

#### Scenario: 首次加载基础拓扑批次
- **WHEN** 当前集群的可见 Namespace、Workload 或 Node 超过对应首批数量
- **THEN** 系统首批最多展示 20 个 Namespace、50 个 Workload 和 50 个 Node
- **AND** 每层显示“已展示 N / 总数”和“展开更多”入口

#### Scenario: 加载更多基础节点
- **WHEN** 用户点击某层“展开更多”
- **THEN** Namespace 每次最多增加 20 个，Workload 和 Node 每次最多增加 50 个
- **AND** 已有节点不重复且已展示数量按实际结果更新

#### Scenario: 基础节点稳定排序
- **WHEN** 用户连续加载多批节点或刷新同一数据快照
- **THEN** Namespace 和 Node 按名称稳定排序
- **AND** Workload 按 Namespace 名称、类型、名称稳定排序

#### Scenario: Workload 父节点完整
- **WHEN** 系统返回一批 Workload 节点
- **THEN** 每个 Workload 的父 Namespace 必须已经在图中
- **AND** Workload 增量查询仅在当前已加载 Namespace 范围内计算可加载集合

#### Scenario: 完整资源仍可查询
- **WHEN** 某层拓扑尚未加载全部节点
- **THEN** 对应资源列表仍可分页查询当前 Cluster 下全部用户可见资源

### Requirement: 单击聚焦与右键菜单操作分离
系统 SHALL 将节点单击限定为拓扑聚焦，并 SHALL 通过节点右键上下文菜单执行 Pod 展开/收起和其他只读操作；单击 Workload MUST NOT 发起 Pod 请求。

#### Scenario: 单击 Namespace 聚焦
- **WHEN** 用户单击 Namespace 节点
- **THEN** 系统高亮该 Namespace 及其当前可见下游路径
- **AND** 其他分支降低透明度但不被隐藏

#### Scenario: 单击 Workload 聚焦
- **WHEN** 用户单击 Workload 节点
- **THEN** 系统仅聚焦该 Workload 及其当前可见路径
- **AND** 不展开、收起或请求 Pod

#### Scenario: 单击 Pod 或 Node 聚焦
- **WHEN** 用户单击 Pod
- **THEN** 系统高亮该 Pod 对应的 `Namespace → Workload → Pod → Node` 可见路径
- **WHEN** 用户单击 Node
- **THEN** 系统高亮当前已经加载且关联该 Node 的 Pod 和路径
- **AND** 不为尚未加载的 Pod 发起批量请求

#### Scenario: 清除聚焦
- **WHEN** 用户再次单击当前节点或单击画布空白区域
- **THEN** 系统清除聚焦并恢复全图正常透明度

#### Scenario: 右键展开或收起 Workload
- **WHEN** 用户右键 Workload 节点
- **THEN** 系统打开只读上下文菜单
- **AND** 菜单根据当前分支状态提供“展开 Pod”或“收起 Pod”
- **AND** 只有用户选择对应菜单项后系统才改变分支状态或发起请求

#### Scenario: 右键菜单只提供只读操作
- **WHEN** 用户打开任意拓扑节点上下文菜单
- **THEN** 菜单仅提供适用的展开/收起、查看关联资源列表和查看 CMDB 实例详情操作
- **AND** 不提供创建、编辑、删除或 YAML 操作

#### Scenario: 键盘打开上下文菜单
- **WHEN** 键盘焦点位于拓扑节点且用户按下菜单键或 `Shift+F10`
- **THEN** 系统打开与右键相同的上下文菜单
- **AND** 用户可以使用键盘选择菜单项或按 `Escape` 关闭

### Requirement: Workload 分类导航
系统 SHALL 提供概览、Namespace、Deployment、StatefulSet、DaemonSet、Job、CronJob、其他工作负载、Pod 和 Node 导航，并 SHALL 为每个导航项提供当前集群范围内的资源列表。

#### Scenario: 展示业务 Workload 分类
- **WHEN** 用户打开资源导航
- **THEN** 系统分别显示五类业务 Workload 导航
- **AND** 独立 ReplicaSet 或其他非五类 Workload 进入“其他工作负载”

#### Scenario: Namespace 与 Node 列表
- **WHEN** 用户选择 Namespace 或 Node 导航
- **THEN** 系统展示当前集群下用户可见的对应资源列表

#### Scenario: Pod 与 Node 使用独立导航分组
- **WHEN** 用户打开 K8S 资源二级导航
- **THEN** Deployment、StatefulSet、DaemonSet、Job、CronJob 和其他工作负载显示在“工作负载”分组
- **AND** Pod 显示在独立“Pod”分组
- **AND** Node 显示在独立“Node”分组
- **AND** Pod、Node 不显示为“工作负载”的子项

### Requirement: 多 Workload Pod 展开
系统 SHALL 允许用户同时展开多个 Workload，并 SHALL 为每个 Workload 独立维护未加载、等待加载、加载中、部分加载、全部加载和加载失败状态。

#### Scenario: 同时展开多个 Workload
- **WHEN** 用户依次展开多个 Workload
- **THEN** 系统保留所有已展开分支
- **AND** 每个分支独立加载和展示 Pod

#### Scenario: 限制并发请求
- **WHEN** 同时存在超过四个尚未完成的 Pod 分支请求
- **THEN** 系统最多并行执行四个请求
- **AND** 其余分支显示等待加载并按队列继续执行

#### Scenario: 收起 Workload
- **WHEN** 用户收起已展开 Workload
- **THEN** 系统从拓扑移除该 Workload 的 Pod 节点及相关边
- **AND** 保留 Cluster、Namespace、Workload、Node 及其他已展开分支

### Requirement: Pod 分页加载
系统 SHALL 为每个 Workload 首次加载最多 50 个 Pod，并 SHALL 明确展示已加载数量、可见总数和继续加载入口，不得静默截断。

#### Scenario: Workload Pod 超过 50 个
- **WHEN** Workload 有 137 个用户可见 Pod 且用户首次展开
- **THEN** 系统展示前 50 个 Pod 和“已显示 50 / 137”
- **AND** 系统提供继续加载和查看完整列表入口

#### Scenario: 继续加载 Pod
- **WHEN** 用户对部分加载分支执行继续加载
- **THEN** 系统加载下一页且不重复已有 Pod
- **AND** 已加载数量按实际结果更新

#### Scenario: Workload 没有 Pod
- **WHEN** 用户展开可见 Pod 数为零的 Workload
- **THEN** 系统明确显示 `Pod 0`
- **AND** 不创建空白或伪造节点

### Requirement: Pod 与 Node 关系展示
系统 SHALL 在展开 Workload 时使用现有 CMDB 实例关联生成 `Workload → Pod` 和 `Pod → Node` 边，并 SHALL 将 Pod 关联到首屏已存在的唯一 Node 节点。

#### Scenario: Pod 关联已有 Node
- **WHEN** 展开的 Pod 与当前视图中的可见 Node 存在关联
- **THEN** 系统复用该 Node 节点并展示 `Pod → Node` 边
- **AND** 不为同一 Node 创建重复节点

#### Scenario: Pod 未调度
- **WHEN** Pod 没有 Node 关联
- **THEN** 系统将其关联到“未调度”虚拟节点

#### Scenario: Node 未匹配
- **WHEN** Pod 记录了 Node 关联但对应 Node 不存在于当前集群采集结果
- **THEN** 系统将其关联到“Node 未匹配”虚拟节点

#### Scenario: 目标 Node 无权限
- **WHEN** Pod 可见但其目标 Node 被权限过滤
- **THEN** 系统将其关联到“目标 Node 无权限”虚拟节点
- **AND** 不返回或展示目标 Node 的名称及其他属性

### Requirement: 未归属 Pod 展示
系统 SHALL 统计和展示未关联到 Workload 的 Pod，并 SHALL 在 Namespace 下提供独立的未归属 Pod 聚合入口。

#### Scenario: Namespace 存在未归属 Pod
- **WHEN** 可见 Pod 直接关联 Namespace 而未关联 Workload
- **THEN** 系统在对应 Namespace 下展示未归属 Pod 数量和展开入口
- **AND** 这些 Pod 计入 Pod 总数和 Pod 资源列表

### Requirement: 资源列表查询
系统 SHALL 为每种导航资源提供分页、搜索、排序和集群范围约束，并 SHALL 支持按 Namespace、Workload 或 Node 进行适用的关联过滤。

#### Scenario: 从 Node 反查 Pod
- **WHEN** 用户在 Pod 列表中使用 `node_id` 过滤
- **THEN** 系统仅返回当前集群内关联该 Node 且用户可见的 Pod

#### Scenario: 从 Namespace 查看 Workload
- **WHEN** 用户在 Workload 列表中使用 `namespace_id` 过滤
- **THEN** 系统仅返回当前集群内关联该 Namespace 且用户可见的 Workload

#### Scenario: 搜索与分页保持集群边界
- **WHEN** 用户组合使用搜索、排序和分页参数
- **THEN** 所有返回结果仍限定于当前 Cluster 和用户可见范围

### Requirement: 资源列表严格只读
系统 SHALL 将 v1 资源列表限定为查询和查看用途，仅提供关联筛选、名称搜索、刷新、分页以及进入现有 CMDB 实例详情的操作，并 MUST NOT 提供任何资源写入或未交付的管理入口。

#### Scenario: 查看资源实例详情
- **WHEN** 用户点击资源列表中的资源名称
- **THEN** 系统在新的浏览器标签页打开该资源现有的 CMDB 基础信息页
- **AND** 新页面携带目标模型、实例 ID 和实例名称
- **AND** 原标签页保留当前 K8S 资源列表及筛选上下文
- **AND** 不在 K8S 资源详情页面内执行资源变更

#### Scenario: 不展示写操作
- **WHEN** 用户打开任意 K8S 资源列表
- **THEN** 页面不展示创建、编辑、删除、查看或编辑 YAML、“更多”写操作和批量选择入口

#### Scenario: 不展示未交付工具
- **WHEN** 下载导出、列设置或其他管理工具未包含在 v1 规格中
- **THEN** 页面不渲染对应按钮、禁用控件或占位菜单

#### Scenario: 资源表格与资产实例列表保持一致
- **WHEN** 用户打开任意 K8S 资源列表
- **THEN** 页面使用资产管理实例列表相同的 `CustomTable` 和紧凑表格密度
- **AND** 表头、行高、列宽交互、滚动区域、加载态、空态和底部分页保持一致
- **AND** 搜索与关联筛选位于工具栏左侧，刷新位于工具栏右侧
- **AND** 表格外层不增加独立卡片边框和大内边距

#### Scenario: 资源列表只保留一个纵向滚动区域
- **WHEN** 资源列表高度超过当前实例详情内容区可用高度
- **THEN** `CustomTable` 根据实际父容器剩余高度计算表体滚动区域
- **AND** 页面不使用固定视口偏移量计算表格高度
- **AND** 实例详情外层和 K8S 内容区不额外产生纵向滚动条
- **AND** 概览页仍可按页面内容正常纵向滚动

### Requirement: 按资源类型展示固定业务列
系统 SHALL 为每种 K8S 资源列表配置固定业务列，并 SHALL 仅展示现有模型或可靠聚合能够提供的数据；字段缺失时 MUST 显示 `—`，不得伪造值或因原型占位新增无来源字段。

#### Scenario: Namespace 列表字段
- **WHEN** 用户打开 Namespace 列表
- **THEN** 页面展示名称、Workload 数和 Pod 数

#### Scenario: Workload 列表字段
- **WHEN** 用户打开五类业务 Workload 或其他工作负载列表
- **THEN** 页面展示名称、Namespace、实际类型、副本数和 Pod 数
- **AND** 某类型没有可靠副本数据时对应单元格显示 `—`

#### Scenario: Pod 列表字段
- **WHEN** 用户打开 Pod 列表
- **THEN** 页面展示名称、Namespace、所属 Workload、Node、Pod IP 和资源请求/限制

#### Scenario: Node 列表字段
- **WHEN** 用户打开 Node 列表
- **THEN** 页面展示名称、角色、CPU、内存和临时存储容量

#### Scenario: 原型字段没有可靠来源
- **WHEN** 镜像、运行状态、创建时间或其他原型字段无法从当前模型和采集链路可靠获得
- **THEN** 页面不配置该列

### Requirement: 分层权限过滤
系统 MUST 先校验目标 Cluster 实例查看权限，再分别按 Namespace、Workload、Pod、Node 的模型和实例权限过滤子资源；指标、拓扑和列表 SHALL 复用同一可见资源口径。

#### Scenario: 无 Cluster 权限
- **WHEN** 用户没有目标 Cluster 实例查看权限
- **THEN** 所有 K8S 资源视图接口返回拒绝访问

#### Scenario: 仅有部分子资源权限
- **WHEN** 用户可以查看 Cluster 但仅能查看部分子资源
- **THEN** 指标、拓扑和列表仅包含有权资源
- **AND** 响应不泄露无权资源名称、属性或精确数量

#### Scenario: 父资源不可见
- **WHEN** 子资源自身可见但其父 Namespace 或 Workload 不可见
- **THEN** 系统不在拓扑中将该子资源作为悬空节点展示

### Requirement: 集群归属参数校验
系统 MUST 验证请求中的 Workload、Namespace、Pod 和 Node 标识属于 URL 指定的 Cluster，不得仅验证对象存在。

#### Scenario: 跨集群 Workload 标识
- **WHEN** 用户使用其他 Cluster 的 `workload_id` 请求 Pod 分支
- **THEN** 系统拒绝请求且不返回任何目标资源信息

#### Scenario: 跨集群列表过滤标识
- **WHEN** 用户使用其他 Cluster 的 `namespace_id`、`workload_id` 或 `node_id` 过滤资源列表
- **THEN** 系统拒绝请求或返回空结果
- **AND** 不泄露该标识对应的资源属性

### Requirement: 局部失败与状态恢复
系统 SHALL 隔离基础视图、资源列表和各 Pod 分支的请求状态，并 SHALL 支持局部重试、多分支缓存和 URL 展开状态恢复。

#### Scenario: 单分支加载失败
- **WHEN** 一个 Workload 的 Pod 请求失败
- **THEN** 仅该分支显示错误和重试入口
- **AND** 其他已加载分支及基础拓扑保持可用

#### Scenario: 收起后重新展开
- **WHEN** 用户在同一页面会话中收起并重新展开已加载 Workload
- **THEN** 系统复用该分支缓存而不重复请求

#### Scenario: 手动刷新
- **WHEN** 用户执行资源视图刷新
- **THEN** 系统清除分支缓存并重新加载基础视图及 URL 指定的展开分支

#### Scenario: URL 恢复多个展开分支
- **WHEN** 用户访问包含多个有效 Workload ID 的展开状态 URL
- **THEN** 系统恢复这些展开分支并从每个分支第一页开始加载
