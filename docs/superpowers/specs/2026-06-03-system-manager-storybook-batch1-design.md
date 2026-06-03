# system-manager 组件 Storybook 首批补齐与巡检设计说明

## 背景

`web/` 已经有 Storybook 基础设施，当前 `src/stories/` 下也已有一批通用组件 stories，但 `system-manager` 模块的大量业务组件尚未进入 Storybook。这样会带来两个问题：

1. 复用组件缺少独立预览入口，样式、空态、交互态只能在页面里联调。
2. 做组件级回归时，无法快速逐个打开检查，容易把问题埋在复杂页面上下文里。

这轮目标不是一次性把整个 `system-manager` 页面体系搬进 Storybook，而是建立一条可重复执行的“补 stories -> 打开检查 -> 发现问题就修”的最小闭环。

## 已确认事实

1. `web/package.json` 已存在 `storybook` 和 `build-storybook` 脚本。
2. 现有 stories 主要放在 `web/src/stories/`，并未覆盖 `system-manager` 的组件族。
3. `system-manager` 目录中同时存在页面级容器、接口 hooks、纯组件和一些中等复用度的业务组件。
4. 用户已经明确本轮优先级为：**system-manager 的基础/可复用组件**，且采用**小批量补齐后逐个巡检**的节奏。
5. 首批业务线已明确为：**用户与组织相关组件**。

## 问题定义

当前缺的不是“再加几个 story 文件”本身，而是一个稳定的筛选标准与执行节奏：

1. 哪些 `system-manager` 组件值得先进入 Storybook；
2. 每个组件最低要覆盖哪些状态；
3. 巡检时如何避免把页面级问题和组件级问题混在一起；
4. 如何保证这一批完成后，后续可以按同一规则继续扫下一批。

## 目标

1. 为 `system-manager` 用户与组织相关组件建立首批 Storybook 覆盖。
2. 首批只挑 4-6 个基础/可复用组件，保证范围可控。
3. 每个组件至少具备默认态、边界态、关键交互态三类 story。
4. stories 补齐后，启动 Storybook 并逐个打开人工巡检。
5. 将明显的展示问题直接在同一批内修复，避免“只建 story 不验组件”。

## 非目标

1. 本轮不覆盖 `system-manager` 全量组件。
2. 本轮不处理页面级路由容器和整页布局。
3. 本轮不为所有 hooks、utils、api 层写 story。
4. 本轮不追求把所有业务状态都建成完整设计系统文档。

## 方案选项

### 方案 A：首批只做高复用组件，小批量补 stories 后逐个巡检（推荐）

先从“用户与组织”相关组件里挑出 4-6 个复用度高、依赖相对可控的组件，补齐最小 stories；随后直接启动 Storybook，逐个打开人工检查。

**优点**
- 范围小，能很快形成完整闭环。
- 更适合边补边发现依赖问题和展示问题。
- 产出可以直接复用到下一批组件扫描。

**缺点**
- 首轮覆盖面有限，不能立即反映整个 `system-manager` 模块全貌。

### 方案 B：先把“用户与组织”整条线全部补 stories，再统一巡检

先覆盖完整业务线里的大多数组件，再集中进入 Storybook 检查。

**优点**
- 组件清单更完整。

**缺点**
- 前期堆积太多未验证 story，出问题时不容易定位是某个组件还是整体策略有误。
- 更容易把这一轮做成大范围搬运。

### 方案 C：先只做组件清单和缺口盘点，不落 stories

先形成组件 inventory 和优先级，等下一轮再真正写 stories。

**优点**
- 风险低。

**缺点**
- 不能直接产生可检查的 Storybook 资产，和用户当前目标不一致。

## 推荐方案

采用方案 A。

这轮最重要的是建立“可持续批量扫组件”的方法，而不是一次性追求覆盖率。小批量补 stories 后立刻巡检，最容易发现真实阻碍：例如组件依赖页面上下文、props 边界不清、样式在独立环境下失真等。这些问题越早暴露，后续批次越顺。

## 首批组件选择规则

首批只从 `system-manager` 用户与组织相关目录里选 4-6 个组件，满足以下优先级：

1. **复用优先**：会在多个页面或多个交互流程中复用。
2. **组件优先于页面**：优先选 modal、tree、transfer、table cell/column renderer 这类可独立渲染单元。
3. **依赖可剥离**：能通过 mock props、假数据、轻量 wrapper 独立运行。
4. **交互明确**：适合用 stories 展示默认态、空态、禁用态、选择态或弹窗开关态。

按当前目录结构，首批候选优先关注：

1. `components/user/permissionModal.tsx`
2. `components/user/passwordModal.tsx`
3. `components/user/GroupTree.tsx`
4. `components/user/TransferLeftTree.tsx`
5. `components/user/TransferRightTree.tsx`
6. `components/group/GroupEditModal.tsx`

最终实际入选数量允许根据依赖复杂度缩到 4 个，但不超过 6 个。

## Story 设计规则

每个入选组件至少提供三类 story：

1. **默认态**：组件在最常见输入下的正常展示。
2. **边界态**：空数据、禁用态、超长文本、无权限、无可选项等。
3. **关键交互态**：例如 modal 打开、树节点选中、穿梭目标已存在、表单校验错误等。

如果某组件天然没有三类状态，也至少保证：

1. 一个稳定可渲染的基础 story；
2. 一个能体现边界或异常输入的 story。

stories 应尽量用本地 mock props 驱动，不把真实接口请求、页面路由依赖、全局会话依赖带进来。确实有上下文依赖时，优先通过最小 wrapper 在 story 内隔离，而不是把整个页面搬进 Storybook。

## 巡检流程

完成首批 stories 后，执行顺序固定为：

1. 启动 Storybook。
2. 逐个打开这批 story。
3. 每个 story 至少检查以下项目：
   - 能否正常渲染
   - 文本/布局是否溢出
   - Ant Design 交互态是否可用
   - 空态/边界态是否还能看懂
   - 控件在独立环境下是否缺少必要上下文
4. 发现问题时，优先直接修组件或 story；
5. 若问题本质是组件和页面耦合过深，则在本轮记录为“需拆分/补 wrapper”的后续项，但不顺手做无关重构。

## 文件组织

本轮 stories 沿用现有 `web/src/stories/` 目录，不在 `system-manager` 目录内分散创建 story 文件。命名上按组件能力聚合，保证后续还能按业务线继续追加。

建议命名风格：

1. `system-manager-user-permission-modal.stories.tsx`
2. `system-manager-user-group-tree.stories.tsx`
3. `system-manager-group-edit-modal.stories.tsx`

## 错误边界

如果某组件必须依赖页面级数据流、难以在 Storybook 独立运行，则本轮处理原则为：

1. 先判断能否通过最小 mock wrapper 隔离；
2. 如果不能，就移出首批范围，换下一个更适合的组件；
3. 不为了凑数量把页面容器硬塞进 Storybook。

## 验收标准

1. 首批完成 4-6 个 `system-manager` 用户与组织相关基础/可复用组件 stories。
2. 每个组件至少有默认态和边界/交互态覆盖。
3. 首批 stories 能在 Storybook 中正常打开。
4. 已对首批 stories 逐个进行人工巡检。
5. 巡检中发现的明显展示或交互问题，已在同一批中修复或明确记录原因。

