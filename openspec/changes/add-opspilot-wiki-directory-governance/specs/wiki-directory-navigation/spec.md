## ADDED Requirements

### Requirement: 知识页面使用真实目录树导航
知识列表 MUST 展示来自 active structure revision 的真实目录树，而不是按 `page_type` 模拟目录。树 MUST 包含虚拟“全部知识”、真实系统“待归类”、活动目录和无页面的空目录。

#### Scenario: 查看含空目录的知识库
- **WHEN** 用户打开知识页面且 active structure 包含空目录
- **THEN** 左侧树 MUST 显示空目录及其正确父子层级
- **AND** page type 筛选 MUST 作为独立筛选器存在，不能改变目录结构

#### Scenario: 查看待归类
- **WHEN** 用户点击系统待归类目录
- **THEN** 右侧列表 MUST 只显示直接归属该目录的页面，并明确该目录不可编辑

### Requirement: 目录选择区分直属与子树范围
点击普通目录时列表 MUST 默认查询直属页面；用户可以显式开启 `include_descendants`。目录、子树开关、分页、搜索和类型筛选 MUST 写入 URL 状态并在刷新或分享链接后恢复。

#### Scenario: 默认直属查询
- **WHEN** 用户点击包含子目录的父目录且未开启包含子目录
- **THEN** 列表 MUST 不混入后代目录页面，并显示直属页面计数

#### Scenario: 开启子树查询
- **WHEN** 用户开启包含子目录
- **THEN** 请求 MUST 携带 `directory_id` 与 `include_descendants=true`
- **AND** 返回页面 MUST 包含目录面包屑以区分具体归属

#### Scenario: 深链指向 merged 目录
- **WHEN** URL 中的 directory ID/key 已合并且存在持久 redirect
- **THEN** UI MUST 导航到活动目标、替换 URL 并提示发生了目录重定向

#### Scenario: 深链指向无 redirect 的 retired/archived 目录
- **WHEN** URL 中目录不可用于活动查询且没有合法目标
- **THEN** UI MUST 显示 tombstone 提示并安全回到“全部知识”，不得静默展示错误空列表

### Requirement: 页面列表暴露目录治理所需状态
页面列表与详情 MUST 返回并展示标题、主目录面包屑、page type、自动/人工归类模式、来源摘要、构建冲突提示和更新时间。机器目录 ID/key 与展示路径 MUST 分离。

#### Scenario: 从全部知识查看页面
- **WHEN** 用户在“全部知识”视图浏览页面
- **THEN** 每一行 MUST 显示完整主目录面包屑和归类模式

#### Scenario: 目录被重命名
- **WHEN** 页面目录名称变化但稳定 ID 不变
- **THEN** 列表 MUST 显示最新面包屑，页面 URL 和页面身份 MUST 保持有效

### Requirement: 日常浏览与结构编辑模式分离
普通目录树 MUST 只提供导航和页面操作；只有知识库管理员进入“编辑目录结构”模式后才能新增、重命名、移动、排序、合并、退役或归档目录。编辑器 MUST 保存完整结构快照而不是逐节点无版本写入。

#### Scenario: 浏览模式拖拽目录
- **WHEN** 用户未进入结构编辑模式时尝试拖拽目录
- **THEN** UI MUST 不发起结构写请求

#### Scenario: 编辑模式保存
- **WHEN** 管理员完成多项树调整并点击保存
- **THEN** UI MUST 提交完整快照与读取时的 `structure_version`、`base_generation_id`，成功后刷新 revision、generation、目录树和计数

### Requirement: 页面移动形成 manual lock
页面详情、行菜单和批量操作 MUST 支持移动到同知识库活动目录，并在成功后显示 manual 状态；页面 MUST 提供恢复自动归类操作。

#### Scenario: 批量移动页面
- **WHEN** 管理员在直属目录视图选择多个页面并移动到目标目录
- **THEN** UI MUST 在后端原子成功后更新所有行的目录和 manual 标记
- **AND** 任一跨知识库或非法目标错误 MUST 不显示部分成功

#### Scenario: 恢复自动归类后无合法目标
- **WHEN** 用户恢复自动归类且服务端把页面放入待归类
- **THEN** UI MUST 从原目录列表移除该行，并在结果提示中提供前往待归类的入口

### Requirement: 破坏性目录操作必须先展示影响预览
合并、退役和删除入口 MUST 先显示直属/递归页面、子目录、manual 页面、名称冲突和 redirect 结果。非空删除或冲突合并 MUST 在界面和服务端同时被阻止。

#### Scenario: 预览非空目录删除
- **WHEN** 管理员点击删除包含页面的目录
- **THEN** UI MUST 展示影响数量和阻止原因，且不能提供绕过服务端约束的确认动作

#### Scenario: 确认无冲突合并
- **WHEN** 预览无冲突且管理员确认合并
- **THEN** UI MUST 等待原子操作完成后刷新树、页面列表和 redirect 状态

### Requirement: 并发结构冲突保留用户本地修改
结构保存返回 `409 structure_version_conflict` 或 `409 base_generation_conflict` 时，前端 MUST 保留未保存的本地树，重新加载服务端最新 revision/generation，并提供差异或重新应用入口；不得静默丢弃或覆盖任何一方。

#### Scenario: 两个浏览器窗口并发编辑
- **WHEN** 后提交窗口收到 409
- **THEN** UI MUST 明确显示版本冲突、最新 revision 和本地未保存修改
- **AND** 用户关闭提示前本地编辑状态 MUST 保留

### Requirement: 关键词检索支持目录范围过滤
关键词页面检索和供 Agent 使用的非向量知识查询 MUST 支持 `directory_id + include_descendants`，并 MUST 在排序和 top-k 截断前应用目录范围。响应 MUST 单独返回知识目录面包屑，不能复用 Markdown `heading_path`。

#### Scenario: 在目录子树检索
- **WHEN** 请求指定父目录和 `include_descendants=true`
- **THEN** 候选集合 MUST 先限制在该子树，再执行关键词评分和 top-k
- **AND** 返回项 MUST 同时保留正文内部 heading path 与知识目录 breadcrumb

### Requirement: 图谱使用目录元数据过滤但不伪造语义关系
图谱节点 MUST 返回目录 ID/key/面包屑并支持当前目录或子树过滤。目录父子关系不能保存为 `PageRelation`，同目录关系不能自动增加语义权重。

#### Scenario: 按目录过滤图谱
- **WHEN** 用户在图谱页选择目录子树
- **THEN** 图谱 MUST 只展示 active generation 中属于该范围的页面节点和节点间有效关系

#### Scenario: 两页位于同一目录
- **WHEN** 两个页面没有 WikiLink、共享来源或 AI 识别关系但位于同一目录
- **THEN** 系统 MUST 不仅因同目录而创建 PageRelation 或提升关系权重

### Requirement: 灰度期间保留平面读取回退
目录能力 MUST 支持按知识库启用。未达到 readiness 条件或功能开关关闭时，现有平面列表读取 MUST 继续可用；关闭开关不能删除目录、revision 或 generation 数据。

#### Scenario: 知识库尚未完成回填
- **WHEN** 目录 readiness 检查未通过
- **THEN** UI MUST 使用旧平面视图并阻止目录写操作，同时给管理员显示未就绪原因

### Requirement: 浏览器真实点击是发布硬门禁
发布验收 MUST 使用浏览器工具从真实 UI 完成结构保存、资料上传、构建、页面移动、恢复自动归类、并发冲突、generation 失败隔离、导出导入及目录检索/图谱路径。写操作不能由直接调用 API 代替。

#### Scenario: 验证 UI 与后端连贯性
- **WHEN** 浏览器完成一条关键用户路径
- **THEN** 验收记录 MUST 同时包含关键步骤截图、网络响应、控制台错误检查和后端读回结果
- **AND** 必须关联 knowledge base ID、structure revision ID、build record ID 与 active generation ID

#### Scenario: 前端显示成功但后端失败
- **WHEN** UI 显示成功而网络请求失败、后端数据未变或控制台出现未处理错误
- **THEN** 该场景 MUST 判定失败并阻止发布

### Requirement: 目录功能不增加向量界面
目录树、列表、关键词和图谱改造 MUST 不新增 embedding 状态、向量重建、语义权重或混合检索配置 UI。

#### Scenario: 打开目录治理界面
- **WHEN** 用户浏览或编辑目录结构
- **THEN** UI MUST 只展示本变更的结构、页面、关键词与图谱能力，不要求用户执行向量操作
