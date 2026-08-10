# 告警中心-权限与 Incident 协同边界

> Migrated from `spec/requirements/告警中心/20260517.告警中心-权限与Incident协同边界.md` as legacy capability evidence.

## 1. 背景与问题
当前告警中心中，`event`、`alert`、`incident` 的组织归属与权限边界不够清晰，主要存在以下问题：

1. `event` 作为外部推送进入的原始事件，当前缺少稳定、明确的组织归属口径。
2. `alert` 当前的组织字段语义与分派语义存在混用风险，容易把“数据归属”与“处理流转”混为一体。
3. `incident` 当前更像管理聚合对象，但在产品和权限口径上，尚未明确它是否会放大 `alert` 的可见性或修改权限。
4. 当前存在两种调整 `incident` 与 `alert` 关系的业务入口：
   - 从 `alert` 侧生成 `incident` 或加入已有 `incident`
   - 在 `incident` 详情中添加某个 `alert`
   两条路径本质一致，但需要统一业务语义和权限口径。

因此需要建立一套清晰、简洁、可验证的权限与归属规则，在保证单对象归属稳定的前提下，支持跨团队事故协同。

---

## 2. 目标与非目标
### 2.1 目标
- 明确 `event` 的单一组织归属口径。
- 明确 `alert` 的单一组织归属口径，并与分派语义解耦。
- 明确 `incident` 是协同管理对象，而不是新的数据归属对象。
- 支持一个 `incident` 关联多个 `alert`，并允许跨多个 team 做事故协同。
- 统一 `alert` 与 `incident` 成员关系调整的业务语义。
- 保持 `event`、`alert` 上的 team 相关字段尽量精简。

### 2.2 非目标（本期不做）
- 不在 `event`、`alert` 上增加多组复杂 team 字段。
- 不将 `incident` 设计为新的对象权限根。
- 不直接信任外部请求传入的 `team_id` 作为数据归属的最终依据。
- 不在本需求中展开具体数据库结构、接口字段或迁移实现方案。

---

## 3. 术语与口径
- 归属组织：对象在权限、审计、数据隔离意义上的所属 team。
- 单一归属：一个对象仅属于一个 team。
- `incident` 所属组织：用于定义 `incident` 管理权限的 team 范围，不等同于数据归属。
- 协同对象：用于组织多对象协同处理的管理对象，不直接承载原始数据归属。
- 对象权限：针对单条 `alert` 的查看、修改、处理权限。
- 协同可见性：用户在 `incident` 视角下看到事故上下文及关联对象的能力。

---

## 4. 需求项
### R1. Event 单一归属
- `event` 必须具备单一归属 team。
- `event` 的归属 team 由接入接口层根据 token / secret / source 绑定关系反推出并确定。
- 不允许仅依赖外部调用方传入的 `team_id` 直接决定 `event` 的归属 team。

### R2. Alert 单一归属
- `alert` 必须具备单一归属 team。
- `alert` 的归属 team 由相关性规则中的“分派组织”决定。
- 同一个 `alert` 可以由多个 team 下的 `event` 聚合形成（在相关性规则中，筛选条件用于控制 `event` 范围；前端默认筛选当前组织，支持多选 team，但用户可以修改）。
- `alert` 是数据权限根对象，用户对 `alert` 的查看、修改、处理权限均以该 `alert` 自身权限为准。

### R3. Incident 的对象定位
- 生成 `incident` 时，需要指定所属组织（允许多个）；该所属组织用于定义该 `incident` 的管理权限。
- `incident` 定义为协同管理对象，不定义为新的数据归属对象。
- `incident` 可以关联多个 `alert`。
- 一个 `incident` 允许关联来自不同归属 team 的 `alert`，用于跨团队事故协同。
- `incident` 不得改变其关联 `alert` 的归属 team，也不得替代 `alert` 的对象权限判断。
- `incident` 的所属 team 由 `incident` 管理员决定，用于定义管理该 `incident` 的权限（如修改、删除等）。
- `incident` 的可见性除可按所属 team 进行筛选外，协同人员也可以看到。

### R4. Incident 可见性边界
- 用户可见某个 `incident` 时，不等于自动获得该 `incident` 内所有 `alert` 的完整对象权限。
- `incident` 提供的是协同视图与事故上下文，不应自动放大 `alert` 的修改权限。
- `incident` 页面可展示关联 `alert` 的协同视图，但具体到单条 `alert` 的详情、敏感信息和可操作能力，仍需按该 `alert` 的对象权限裁剪。

### R5. Incident 管理员与成员口径
- `incident` 管理员可将当前组织范围内可见的 `alert` 加入该 `incident`。
- `incident` 管理员不因该身份自动获得这些 `alert` 的修改权限。
- `incident` 成员可将自己有权限访问的 `alert` 加入该 `incident`。
- `incident` 成员只能操作自己有权限的 `alert`。

### R6. Alert 与 Incident 成员关系调整规则
- 系统支持以下两种业务入口：
  1. 从 `alert` 侧生成 `incident` 或加入已有 `incident`
  2. 从 `incident` 详情中添加 `alert`
- 两种入口本质上均属于“修改 `incident` 的 `alert` 成员关系”。
- 两种入口必须遵循一致的业务规则与权限口径。
- 成员关系调整应支持以下统一语义：
  - 创建 `incident` 并关联一组 `alert`
  - 向已有 `incident` 增量加入一组 `alert`
  - 从已有 `incident` 增量移除一组 `alert`
- 不应依赖“前端读取全量成员后再整体覆盖”的方式调整 `incident` 成员。

### R7. Incident 与 Alert 的权限分层
- `incident` 元数据操作（如标题、备注、状态、协同关系）属于协同对象操作。
- `alert` 的确认、关闭、转派等操作属于对象级操作。
- 用户是否可修改某条 `alert`，始终按该 `alert` 的对象权限判断，不因其已被关联到某个 `incident` 而放大。

### R8. 事故协同边界
- `incident` 支持跨 team 协同，但不支持突破更高一级的数据隔离边界。
- `incident` 允许跨 team 聚合 `alert`，前提是这些 `alert` 处于同一租户 / 同一 workspace / 同一产品空间 / 同一事故上下文边界内。

---

## 5. 验收口径
### A1. Event 与 Alert 归属验收
- 每条 `event` 都能确定唯一归属 team。
- 每条 `alert` 都能确定唯一归属 team。
- 允许不同归属 team 的 `event` 聚合成同一个 `alert`。

### A2. Incident 边界验收
- `incident` 可关联多个 `alert`，且允许包含来自不同归属 team 的 `alert`。
- `incident` 不因关联关系改变任一 `alert` 的归属 team。
- `incident` 不自动赋予用户对其内全部 `alert` 的修改权限。

### A3. Incident 可见性验收
- 用户可进入 `incident` 页面时，可看到该 `incident` 的协同信息与关联 `alert` 的协同视图。
- 用户对自己无权限的 `alert`，不能在 `incident` 中执行对象级修改操作。
- 用户对自己有权限的 `alert`，可在 `incident` 中继续执行对象级操作。

### A4. 成员关系调整验收
- 从 `alert` 侧生成 / 加入 `incident` 与从 `incident` 详情中添加 `alert`，遵循一致的业务规则。
- 系统支持“创建并关联”“增量加入”“增量移除”三种明确语义。
- 成员关系调整不依赖前端全量覆盖整个 `incident.alert` 集合。

### A5. 协同角色验收
- `incident` 管理员可将当前组织范围内可见的 `alert` 加入 `incident`。
- `incident` 成员仅可将自己有权限访问的 `alert` 加入 `incident`。
- 无论是管理员还是成员，均不能因 `incident` 身份直接修改自己无对象权限的 `alert`。

---

## 6. 约束与边界
### In Scope
- `event`、`alert`、`incident` 的组织归属与权限边界口径。
- `incident` 的协同可见性与 `alert` 对象权限分层原则。
- `alert` 与 `incident` 成员关系调整的统一业务语义。

### Out of Scope
- 具体数据库字段设计与表结构调整。
- 具体接口协议、参数命名与返回格式。
- 前端页面的最终展示样式与交互细节。
- 历史数据迁移与兼容方案。

---

## 7. 最终原则
1. `event` 单一归属。
2. `alert` 单一归属。
3. `incident` 为协同管理对象，不是数据归属对象。
4. `incident` 可跨 team 聚合 `alert`，但不放大 `alert` 的对象修改权限。
5. `alert` 与 `incident` 的成员关系调整统一为明确、增量的业务语义。
