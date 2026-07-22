# Fix Ops Analysis Auth Visibility Consistency

Status: ready

## Migration Context

- Legacy source: `openspec/changes/fix-ops-analysis-auth-visibility-consistency/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

`operation_analysis` 当前存在两类相互关联但职责不同的权限一致性问题：

1. `DirectoryModelViewSet` 的目录写接口直接使用 ORM 处理创建和更新，请求只经过模块级 `@HasPermission` 校验，绕过了 `AuthViewSet` 的组织范围写入校验、`current_team` 属主校验和实例级 `Operate` 校验。这会让目录写请求退化为“只校验模块角色”，存在跨组织写入和跨实例修改风险。
2. 仪表盘、拓扑图、架构图虽然允许修改 `groups`，但侧边栏入口完全依赖目录树接口。目录树先按目录及祖先目录链做过滤，再拼出子对象节点。如果对象的目标 `groups` 超过其所属目录链的可见范围，保存后切换到新组织时对象不会出现在侧边栏，形成“保存成功但不可发现”的配置漂移。

这两个问题都属于 `operation_analysis` 资源权限模型的不一致：

- 写入授权链不一致
- 容器可见性约束缺失

本次 change 先收敛并修复这两项。对“对象可出现但运行时因数据源无权而失败”的保存时前置校验暂不纳入范围，继续保留现有运行时数据源访问控制。

## What Changes

- 修复目录写接口，要求 `DirectoryModelViewSet` 的 create/update/partial_update 复用 `AuthViewSet` 的统一写时授权链。
- 为仪表盘、拓扑图、架构图新增目录链可见性一致性校验：对象目标 `groups` 不得超过所属目录及其祖先目录链的可见范围。
- 在保存失败时返回明确的冲突信息，指出是目录写授权失败，还是目录链可见性不满足。

## Capabilities

### New Capabilities

- `operation-analysis-resource-write-auth`: `operation_analysis` 目录写接口必须执行与 `AuthViewSet` 一致的组织范围与实例级授权校验。
- `operation-analysis-container-visibility-consistency`: 非目录对象的目标 `groups` 必须被所属目录链完整覆盖，避免对象保存后在目标组织中不可发现。

### Modified Capabilities

<!-- 无需修改现有 spec -->

## Impact

- **后端代码**:
  - `server/apps/operation_analysis/views/view.py`
  - `server/apps/core/utils/viewset_utils.py`（复用现有能力，不要求新增通用规则）
  - 新增或调整 `operation_analysis` 服务层/校验逻辑，用于目录链一致性检查
- **前端交互**:
  - `web/src/app/ops-analysis/components/sidebar.tsx` 当前直接提交 `groups`，后续需消费更明确的错误反馈
- **API 行为变更**:
  - 目录写接口对无权组织或无权实例的请求返回 403，而不是仅凭模块角色放行
  - 画布保存接口在目标 `groups` 超出目录链可见范围时拒绝保存，并返回冲突明细
- **不在本次范围**:
  - 不新增画布引用数据源的保存时前置校验，继续保留现有运行时“无权访问当前数据源”拦截

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-20
```

## Capability Deltas

### operation-analysis-container-visibility-consistency

## ADDED Requirements

### Requirement: Canvas target groups MUST be covered by the full directory ancestry

仪表盘、拓扑图、架构图在保存时，其目标 `groups` 必须被所属目录及全部祖先目录的 `groups` 完整覆盖。系统不得接受“对象自身可见但目录链不可见”的配置。

#### Scenario: Reject canvas save when direct parent directory does not cover target groups

- **Given** 某仪表盘目标目录的 `groups = [1]`
- **When** 用户尝试将该仪表盘保存为 `groups = [1, 2]`
- **Then** 系统必须拒绝保存
- **And** 系统必须说明直属目录未覆盖组织 `2`

#### Scenario: Reject canvas save when ancestor directory does not cover target groups

- **Given** 某拓扑图所属子目录 `groups = [1, 2]`
- **And** 该子目录的父目录 `groups = [1]`
- **When** 用户尝试将该拓扑图保存为 `groups = [1, 2]`
- **Then** 系统必须拒绝保存
- **And** 系统必须说明祖先目录链未覆盖组织 `2`

#### Scenario: Allow canvas save when the entire directory chain covers target groups

- **Given** 某架构图所属目录及全部祖先目录的 `groups` 均包含 `1` 和 `2`
- **When** 用户将该架构图保存为 `groups = [1, 2]`
- **Then** 系统必须允许保存

### Requirement: Directory-chain validation errors SHOULD identify the conflicting containers

当对象保存因目录链可见性不一致而失败时，系统应返回足够的冲突信息，便于调用方明确是哪个目录阻止了对象在目标组织中被发现。

#### Scenario: Return structured conflict details for directory-chain mismatch

- **Given** 用户保存某仪表盘时，其目标组织超出了祖先目录的可见范围
- **When** 系统拒绝该保存请求
- **Then** 响应中应包含至少一个冲突目录的标识信息
- **And** 响应中应包含该目录缺失覆盖的组织 ID 信息

### operation-analysis-resource-write-auth

## ADDED Requirements

### Requirement: Directory write requests MUST use the unified AuthViewSet authorization chain

`operation_analysis` 的目录创建、更新、部分更新请求必须执行与其他 `AuthViewSet` 子类一致的写时授权校验，不得仅凭模块级菜单权限直接写库。

#### Scenario: Reject directory create with unauthorized target groups

- **Given** 用户具备目录模块新增菜单权限
- **And** 用户可管理组织仅包含 `1`
- **When** 用户提交目录创建请求，目标 `groups = [1, 2]`
- **Then** 系统必须拒绝创建请求并返回 403
- **And** 系统必须指出目标组织超出当前用户可管理范围

#### Scenario: Reject directory update without current-team ownership or instance operate permission

- **Given** 某目录对象存在且其 `groups` 不包含当前请求的 `current_team`
- **When** 用户提交目录更新请求
- **Then** 系统必须拒绝更新请求并返回 403

#### Scenario: Allow authorized directory write through shared viewset flow

- **Given** 用户具备目录模块写权限
- **And** 目标目录写入组织均在用户可管理范围内
- **And** 对于更新请求，用户对该目录实例具备操作权限
- **When** 用户提交目录创建或更新请求
- **Then** 系统必须允许请求通过统一写时授权链完成保存

### Requirement: Directory-specific business rules MUST NOT bypass authorization

目录特有业务规则（如内置目录只读）可以额外约束目录写操作，但不得替代组织范围校验或实例级授权校验。

#### Scenario: Built-in directory remains read-only after auth refactor

- **Given** 某目录对象为内置目录
- **And** 当前用户对其组织和实例权限均合法
- **When** 用户尝试更新该目录
- **Then** 系统必须拒绝该请求
- **And** 拒绝原因必须是内置目录只读，而非授权链被绕过

## Work Checklist

## 1. Directory Write Authorization

- [ ] 1.1 确认 `DirectoryModelViewSet.create/update/partial_update` 当前绕过 `AuthViewSet` 的具体差异点（组织字段校验、`current_team` 校验、实例级 `Operate` 校验）。
- [ ] 1.2 调整 `DirectoryModelViewSet.create`，移除 ORM 直写主路径，改为在目录特有校验后调用 `super().create()`。
- [ ] 1.3 调整 `DirectoryModelViewSet.update` 与 `partial_update`，保留内置目录只读限制，但改为在校验后调用 `super().update()` / `super().partial_update()`。
- [ ] 1.4 确认目录写接口仍然维持 `is_build_in` / `build_in_key` 只读语义，不允许客户端借写接口修改。

## 2. Container Visibility Consistency

- [ ] 2.1 梳理 dashboard/topology/architecture 保存时的目标 `groups` 与目标目录解析路径，覆盖 create/update/partial_update 三种场景。
- [ ] 2.2 新增共享的目录链一致性校验逻辑：从目标目录向上遍历祖先目录并检查目标 `groups` 是否被整条目录链覆盖。
- [ ] 2.3 在 dashboard/topology/architecture 保存前接入该校验，目录链不满足时拒绝保存。
- [ ] 2.4 设计并实现结构化错误反馈，至少包含冲突目录和缺失组织信息，便于前端展示。

## 3. Regression Coverage

- [ ] 3.1 补充目录写接口测试：无权写入目标组织时被拒绝；无实例级操作权时被拒绝；有权限时允许写入。
- [ ] 3.2 补充画布保存测试：对象 `groups` 超出直属目录 `groups` 时被拒绝；超出祖先目录 `groups` 时被拒绝；目录链完整覆盖时允许保存。
- [ ] 3.3 验证切组后目录树表现：符合目录链约束的对象在目标组织中可发现，不符合约束的对象无法保存进入系统。

## 4. Verification

- [ ] 4.1 运行 `operation_analysis` 相关后端测试或最小验证命令，确认目录写授权与目录链校验行为符合预期。
- [ ] 4.2 人工验证侧边栏切组场景，确认问题从“保存成功但切组后消失”收敛为“保存前被明确阻止”。
- [ ] 4.3 更新变更说明，明确本次不包含数据源保存时前置一致性校验，继续沿用现有运行时数据源访问控制。
