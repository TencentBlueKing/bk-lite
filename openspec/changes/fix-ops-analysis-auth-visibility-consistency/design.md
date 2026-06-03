## Context

`operation_analysis` 的目录、仪表盘、拓扑图、架构图都使用 `groups` 作为组织边界，但当前实现存在两条不一致链路：

1. 目录写入链路不一致
   - `DashboardModelViewSet`、`TopologyModelViewSet`、`ArchitectureModelViewSet` 的写接口会回到 `AuthViewSet`
   - `DirectoryModelViewSet` 自己直接调用 `Directory.objects.create/update`
   - 结果是目录请求虽然有模块级 `@HasPermission`，但绕过了 `AuthViewSet.create/update` 中的组织范围与实例级授权

2. 容器可见性链路不一致
   - 侧边栏只依赖 `/operation_analysis/api/directory/tree/`
   - 目录树接口先过滤目录，再只查询这些目录下的 dashboard/topology/architecture
   - 多级目录通过父子关系拼树，父目录不可见时子对象即使自身 `groups` 覆盖目标组织，也不会出现在侧边栏

因此当前系统会出现两种错误状态：

- 用户能越权修改目录
- 用户能保存对象到新组织，但切组后该对象根本不可发现

## Goals / Non-Goals

**Goals:**

- 让目录写接口回到 `AuthViewSet` 统一写时授权链
- 保留目录特有业务规则（如内置目录不可编辑/删除），但不再保留目录特有授权旁路
- 在保存仪表盘、拓扑图、架构图时校验其目标 `groups` 是否被所属目录链完整覆盖
- 返回可定位问题的错误信息，区分“无权写入”与“目录链不可见”

**Non-Goals:**

- 不修改目录树读取逻辑
- 不修改数据源运行时访问控制
- 不新增“画布引用数据源保存时前置校验”
- 不自动同步目录或祖先目录的 `groups`

## Decisions

### 1. 目录写接口必须复用 `AuthViewSet`

`DirectoryModelViewSet.create/update/partial_update` 不再以 ORM 直写作为主路径，而是：

1. 先执行目录特有规则校验（如内置目录不可编辑）
2. 再调用 `super().create/update/partial_update()`

这样目录写请求将自动复用 `AuthViewSet` 已有的：

- 组织字段写入范围校验
- `current_team` 属主校验
- 实例级 `Operate` 校验

**理由**: 目录可以有业务特例，但不应有授权特例。继续保留目录自己的 ORM 直写分支，会使后续所有 `AuthViewSet` 安全修复继续漏掉目录。

### 2. 目录特有规则与授权规则分层处理

目录保留的特有规则只有：

- 内置目录不可编辑
- 内置目录不可删除

这些规则在目录 ViewSet 前置校验；组织范围、实例权限、序列化写入由通用基类负责。

**理由**: 把“这是不是一个可写的目录对象”和“当前用户是否有权修改它”拆开，职责更清晰，也便于测试。

### 3. 画布保存时增加目录链可见性校验

对 `Dashboard`、`Topology`、`Architecture` 的创建和更新，系统在保存前执行目录链一致性检查：

1. 解析本次目标 `groups`
   - create: 使用请求里的 `groups`
   - update/partial_update: 若请求未传 `groups`，则沿用现有对象的 `groups`
2. 解析目标所属目录
   - create: 使用请求里的 `directory`
   - update/partial_update: 若请求未传 `directory`，则沿用现有对象的 `directory`
3. 从目标目录向上遍历到根目录
4. 校验目标 `groups` 是否为整条目录链每一层 `groups` 的子集
5. 若任一层不满足，则拒绝保存

**理由**: 当前系统的可发现性依赖目录树过滤结果。只有把目录链覆盖关系提升为保存时约束，才能防止“保存成功但切组后根本找不到”。

### 4. 目录链冲突返回结构化错误信息

当目录链校验失败时，返回错误信息至少包含：

- 冲突目录 ID
- 冲突目录名称
- 缺失的组织 ID 列表

错误消息语义建议为：
`目标组织不在所属目录链的可见范围内，保存后对象不会出现在侧边栏`

**理由**: 纯字符串报错不足以支持前端后续优化，也不利于排查是直属目录还是祖先目录造成问题。

## Risks / Trade-offs

| 风险                                                                              | 缓解措施                                                |
| --------------------------------------------------------------------------------- | ------------------------------------------------------- |
| 目录写接口回到 serializer 主链后，响应体可能与当前“直接回显 request.data”略有差异 | 以 serializer 输出为准，并在变更说明中明确 API 行为收敛 |
| 现有前端允许用户仅修改对象 `groups`，不理解目录链约束                             | 后端返回明确错误信息；前端后续可补充表单提示            |
| 多级目录链校验会增加一次父链遍历                                                  | 单个对象的目录层级很浅，开销可控                        |
| 用户可能希望自动同步目录链 `groups`                                               | 本次明确不做自动同步，避免共享目录可见性被静默扩大      |

## Implementation Notes

- 目录写授权修复应优先落地，因为它属于安全边界问题。
- 目录链一致性校验建议抽成 `operation_analysis` 内部共享服务，避免 dashboard/topology/architecture 各自复制逻辑。
- 若后续要支持“一键同步目录链可见范围”，应作为单独 change 设计，而不是在本次修复中隐式引入。
