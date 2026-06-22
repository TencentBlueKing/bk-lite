# system-manager 用户与组织组件 Storybook 第二批设计说明

## 背景

`system-manager` 的“用户与组织”组件已经完成首批 Storybook 补齐，当前已覆盖：

1. `GroupTree`
2. `TransferLeftTree`
3. `TransferRightTree`
4. `RoleTransfer`

但这一条线里仍有 3 个明显适合独立预览的 modal 组件尚未进入 Storybook：

1. `components/user/permissionModal.tsx`
2. `components/user/passwordModal.tsx`
3. `components/group/GroupEditModal.tsx`

同时，在继续补 stories 的过程中，已经能看到一些重复模式正在形成，例如 modal 的 `forwardRef + showModal` 驱动方式、打开时拉数据的状态骨架、story wrapper 的相似 mock 结构。

## 已确认事实

1. `web/src/stories/` 已经承接首批 system-manager stories，并有一份可复用的 `system-manager-user-org.fixtures.ts`。
2. 用户希望这轮 **两类工作都做**：继续找没进 Storybook 的组件，同时盘点重复模式。
3. 用户明确要求本轮 **优先找容易补 Storybook 的组件**，重复封装先列机会点，不做大规模抽象。
4. 范围仍然限定在 `system-manager` 的“用户与组织”相关组件，不扩到安全配置、应用菜单等其他业务线。

## 问题定义

当前要解决的不是“是否还能再加几个 story”，而是第二批该如何保持节奏稳定：

1. 继续挑选适合进入 Storybook 的用户/组织组件；
2. 保持 story 可独立运行，不把页面级依赖直接带进来；
3. 给这类 modal 组件补上最小 TDD 护栏；
4. 只记录重复封装机会点，不让这轮范围膨胀成重构批次。

## 目标

1. 为 3 个未覆盖的用户/组织 modal 组件补齐 Storybook。
2. 每个组件至少覆盖默认态、一个边界或 loading 态、一个关键交互态。
3. 对 story 驱动过程中暴露出的明显重复/错误加最小护栏修复。
4. 产出一份“重复封装机会点”清单，供下一批重构使用。

## 非目标

1. 本轮不做 system-manager 全量组件扫描。
2. 本轮不做通用 modal 框架抽象。
3. 本轮不做页面级容器 story。
4. 本轮不把 `tableColumns.tsx` 这类配置文件强行做成 story。
5. 本轮不把“补 stories”和“重复模式专项重构”合并成一个大任务。

## 方案选项

### 方案 A：先补 3 个 modal 的 Storybook，再列重复封装机会点（推荐）

围绕 `permissionModal`、`passwordModal`、`GroupEditModal` 建立第二批 stories，并只修阻碍 Storybook 或明显重复 bug 的小问题。

**优点**

- 和首批节奏一致，风险最低。
- Storybook 覆盖面继续扩大，收益直接。
- 能为下一批抽象工作提供更真实的输入。

**缺点**

- 重复模式不会在这一轮被彻底收敛。

### 方案 B：先抽一层 modal/story wrapper，再补 stories

先把 ref 驱动 modal、showModal、mock provider 等共性抽出来，再批量为 modal 组件补 stories。

**优点**

- 后续补 story 更快、更整齐。

**缺点**

- 前置抽象成本高，容易在边界未稳定前过度设计。

### 方案 C：先做重复模式专项清理，再回头补 Storybook

先梳理 modal 生命周期、数据拉取骨架和 story wrapper 共性，完成后再补 story。

**优点**

- 代码结构改善幅度更大。

**缺点**

- 不符合当前“优先拿到 Storybook 覆盖”的目标。

## 推荐方案

采用方案 A。

当前最重要的是继续建立“小批量补 stories -> 打开检查 -> 修真实问题”的稳定闭环。重复模式已经值得记录，但还不到一边补故事一边做大抽象的时机。先让第二批 stories 落地，再根据真实重复点决定第三批是否进入专项收敛，更稳妥。

## 组件范围

本轮固定覆盖以下 3 个组件：

1. `web/src/app/system-manager/components/user/permissionModal.tsx`
2. `web/src/app/system-manager/components/user/passwordModal.tsx`
3. `web/src/app/system-manager/components/group/GroupEditModal.tsx`

选择原因：

1. 都是明显的独立可视组件，不是页面级容器。
2. 都与“用户与组织”主线直接相关。
3. 都具备默认态、loading 态或关键交互态，适合用 Storybook 独立验证。

## Story 设计

### `permissionModal`

通过 story wrapper 提供 `visible`、`rules`、`node`、`onOk`、`onCancel` 等最小驱动参数。

至少覆盖：

1. 默认可编辑态
2. 已有权限规则回填态
3. 权限项加载态

验证重点：

1. app 列与权限选择列是否稳定渲染
2. 规则回填是否落到正确项
3. loading 时表格和选择控件是否仍可理解

### `passwordModal`

通过 `ref + showModal()` 的 story wrapper 驱动，不改业务组件 API。

至少覆盖：

1. modal 打开后的基础表单态
2. 密码规则 loading / 已加载态
3. 输入密码后的校验提示态

验证重点：

1. story wrapper 能否稳定打开 modal
2. 密码规则说明能否显示
3. 输入密码后校验提示是否可见

允许的顺手修复：

1. 去掉当前重复的 `useEffect(() => { if (visible) fetchPasswordRules() }, [visible])`

### `GroupEditModal`

同样通过 `ref + showModal()` 的 story wrapper 驱动。

至少覆盖：

1. 基础表单态
2. `RoleTransfer` loading 态
3. 已继承角色 / 允许继承开关态

验证重点：

1. group name、开关和 `RoleTransfer` 是否正常出现
2. 继承角色相关标签/状态是否可见
3. loading 时是否仍可判断组件状态

## TDD 护栏

这轮不追求为 modal 组件建立庞大的测试体系，但必须加最小 focused 护栏，避免 story 只是“摆出来”：

1. `permissionModal`：至少约束可见列与已有规则回填
2. `passwordModal`：至少约束 modal 打开与密码规则提示可见
3. `GroupEditModal`：至少约束 modal 打开后关键字段与 `RoleTransfer` 区域可见

护栏形式可以是：

1. story 的 `play` 断言；
2. 现有脚本式 Storybook 验证；
3. 必要时新增 focused 前端脚本校验。

选择原则是：**优先使用当前仓库已经存在的 Storybook/前端校验方式，不额外引入新测试框架。**

## 重复封装机会点记录

这轮只记录，不做大抽象。重点记录以下 3 类：

1. **Modal 驱动骨架重复**
   - `forwardRef`
   - `showModal`
   - `visible/currentId/resetFields`
   - confirm/cancel/loading 管理
2. **打开时拉数据的副作用骨架重复**
   - `visible => fetch`
   - loading/reset
   - error + message
3. **Story 层重复**
   - ref 驱动 wrapper
   - provider/mock 包装
   - 默认 args/fixtures 组织方式

这份机会点清单的作用是给下一批“专项收敛”提供输入，而不是在本轮直接抽公共基础设施。

## 文件组织

继续沿用 `web/src/stories/`，并与首批命名风格保持一致。建议新增：

1. `web/src/stories/system-manager-user-permission-modal.stories.tsx`
2. `web/src/stories/system-manager-user-password-modal.stories.tsx`
3. `web/src/stories/system-manager-group-edit-modal.stories.tsx`

如有需要，可新增一份与 modal 相关的 fixtures/helper 文件，但应保持在 stories 层，不把 Storybook 专用逻辑带入业务目录。

## 错误处理边界

如果某个 modal 在 Storybook 中必须依赖真实接口或复杂上下文，本轮处理顺序为：

1. 优先在 story 层补最小 mock / wrapper；
2. 如果仍无法独立运行，则记录为“依赖过重，需要单独拆分”的机会点；
3. 不为了 Storybook 去重写业务组件接口。

## 验收标准

1. 上述 3 个 modal 均新增 Storybook 覆盖。
2. 每个组件至少有默认态与一个边界/交互态。
3. Storybook 中能逐个打开并巡检这 3 个组件。
4. 巡检中发现的明显 Storybook 阻碍或小型重复 bug 已修复。
5. `web` 最终 `pnpm type-check` 通过。
6. 输出一份简短的“重复封装机会点”清单，作为下一批输入。
