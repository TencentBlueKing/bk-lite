---
name: BK-Lite Web Console
description: AI First lightweight O&M product UI for daily operations work.
scope: web
runtimeTokenSource: src/styles/globals.css
componentOwnershipSource: COMPONENT_GOVERNANCE.md
componentContractSource: src/stories
themes:
  - light
  - dark
---

# Design System: BK-Lite Web Console

## 0. 文档职责与执行顺序

本文位于 `web/` 是有意的：它只约束 Web Console。仓库根目录的 `DESIGN.md` 负责跨端导航，Mobile 的差异规则由 `mobile/DESIGN.md` 维护。

设计系统有四个互补的真相源，不能用其中一个替代其他三个：

| 层级 | 真相源 | 负责什么 |
| --- | --- | --- |
| 设计语义 | `web/DESIGN.md` | 视觉原则、组件选择、主题语义和使用边界 |
| 运行时 Token | `web/src/styles/globals.css` | `:root` 亮色值和 `.dark` 暗色值；代码中的最终颜色真相 |
| 组件所有权 | `web/COMPONENT_GOVERNANCE.md` | shared、primitive、app-local 的目录边界 |
| 组件契约 | Storybook `web/src/stories` | 组件 API、状态、变体和使用示例 |

Markdown 不复制维护运行时颜色值。修改品牌色或主题值时先改 `globals.css` 的同名语义变量，再用 Storybook 验证；本文只说明应该选择哪个变量以及它表达什么。

### Code Agent / 开发者开始写 UI 前

1. 阅读本文和 `COMPONENT_GOVERNANCE.md`。
2. 按“Ant Design → `src/components` → 当前 app 组件”的顺序检索，不凭记忆创建新组件。
3. 在 Storybook 查找相同交互或视觉契约，确认已有组件的 props 和状态。
4. 有合适组件时直接复用，不复制源码、不创建平行实现。
5. 确实没有且当前只有一个 app 使用时，在 `src/app/<app>/components` 创建 app-local 组件。
6. 只有两个及以上真实 app 已经接入同一抽象时，才提升到 `src/components`；shared 组件必须同步 Storybook。
7. 完成后检查亮色、暗色、loading、empty、error、disabled 和长文本状态。

如果为了满足单一页面而修改 shared 组件，优先增加清晰、可复用的 variant；不能把业务字段、API 请求或 app 类型塞进 shared 组件。

## 1. Overview

**Creative North Star: "Light Operations Desk"**

BK-Lite Web 是面向运维管理员的产品界面，不是营销页、数据大屏或视觉实验场。设计服务于日常运维动作：发现资源、筛选对象、查看状态、处理告警、执行作业、确认高风险操作。界面应当轻量、智能、友好，但这种友好来自清晰结构、可预期控件和及时反馈，而不是装饰。

默认 register 是 product。优先保留熟悉的企业后台模式：顶栏、侧栏、筛选区、表格、抽屉、弹窗、状态标签、批量操作。视觉策略是 restrained：白色/浅灰工作面 + 蓝色主操作 + 少量语义状态色。AI 能力出现时要像一个明确的工作助手，展示输入、输出、风险、下一步，而不是制造舞台感。

**Key Characteristics:**
- 密集但不拥挤：表格、筛选、详情和操作区可以信息密度高，但必须有清晰分组。
- 克制用色：`--color-primary` 只用于主操作、链接、选中、focus，不做装饰。
- 可预测交互：按钮、表单、表格、弹窗沿用 Ant Design 语义，不自造控件词汇。
- 框架优先：新 UI 先使用 Ant Design、`web/src/components` 和当前模块已有组件，避免重写已有控件。
- 渐进展示：空状态、错误状态、加载状态都要告诉用户下一步。
- 中英双语安全：中文、英文和长资源名都必须能换行、省略或 tooltip 展示完整内容。

## 2. Colors

BK-Lite Web 的颜色系统是“低压工作台”：中性底色承载长时间工作，蓝色只在需要行动或定位当前状态时出现，业务状态色必须语义化成组使用。

### 语义 Token

| 用途 | 使用 | 不要使用 |
| --- | --- | --- |
| 主操作、链接、选中、focus | `var(--color-primary)` | 任意品牌蓝 hex、仅为装饰的大面积蓝色 |
| 选中或弱提示背景 | `var(--color-primary-bg-active)` | 对亮色背景做透明度猜测 |
| 页面/应用壳背景 | `var(--color-background-body)` | 固定白色或固定深色背景 |
| 主容器、卡片、弹窗、表格 | `var(--color-bg)` | `#fff`、`white`、`bg-white` |
| 二级面、筛选区、分组头 | `var(--color-fill-1)` / `var(--color-fill-2)` | 临时灰色 hex |
| 默认边框与分割线 | `var(--color-border)`，按层级使用 `--color-border-1` 至 `-4` | 固定浅灰边框 |
| 标题、正文、辅助、disabled | `var(--color-text-1)` 至 `--color-text-4` | 固定黑色、白色或不透明度猜测 |
| 成功/健康 | `var(--color-success)` | 仅用绿色表达状态 |
| 失败/危险 | `var(--color-fail)` | 仅用红色表达状态 |
| 导航、弹窗等组件级语义 | `--color-components-*`、`--color-modal-*` | 页面内覆盖 Ant Design 全局样式 |

### 明暗主题契约

- `:root` 定义亮色主题，`.dark` 必须为同一组语义变量提供暗色值；组件不能判断主题后选择两个硬编码颜色。
- 新增语义变量必须同时提供亮色和暗色值。只定义一个主题视为未完成。
- 组件代码只消费语义变量或 Ant Design token，不使用 `dark:` 分支重新拼一套品牌色；布局差异与必要的主题特例除外。
- 透明色仍然必须通过语义变量表达，不能假设 `rgba(0, 0, 0, …)` 在暗色下可读。
- 图片、图表、代码块和第三方控件也必须在两套主题下检查对比度、边框和 hover/focus 状态。
- 颜色不能作为状态的唯一载体；成功、警告、错误和信息必须同时配文案、图标或形状。

### Named Rules

**The Token First Rule.** 新代码使用 `web/src/styles/globals.css` 里的 `--color-*` token。组件内禁止直写品牌色、状态色和主题相关中性色；需要新语义时先命名变量，并同步亮暗主题。

**The Semantic Triple Rule.** 业务语义色以 `dot/bg/text` 或 `icon/bg/text` 成组出现。成功、警告、错误、信息不能只用灰度或只用色块表达。

**The Dark Mode Independence Rule.** 暗色模式必须独立定义 token，不允许靠亮度反转、透明黑白叠加或 CSS filter 生成。

## 3. Typography

**Display Font:** system UI stack  
**Body Font:** system UI stack  
**Label/Mono Font:** system UI stack for UI, monospace only for code and command output

**Character:** BK-Lite Web 使用单一系统无衬线字体族，优先稳定、清晰和跨平台一致。产品 UI 不使用展示字体，不使用流体大标题，不用夸张字距制造品牌感。

### Hierarchy
- **Title** (`font-semibold`, `16px`, `line-height: 1.5`): 页面标题、弹窗标题、模块介绍标题。
- **Section / Card Title** (`font-semibold` or `font-medium`, `14px`, `line-height: 1.5`): 卡片标题、表头、分组头。
- **Body** (`font-normal`, `14px`, `line-height: 1.5`): 正文、表格单元格、按钮文字、表单内容。
- **Label** (`font-medium`, `12px`, `line-height: 1.5`): 辅助标签、状态说明、时间戳、副标题。
- **Micro** (`10px`, only when space is constrained): 极少量密集辅助信息。正文禁止低于 `12px`。
- **Code / Command** (`monospace`, `12px` or `13px`): 命令、日志、配置片段。必须允许复制和横向滚动。

### Named Rules

**The Product Scale Rule.** 产品界面用固定字号阶梯，不用 `clamp()` 做 UI 标题缩放。真正的页面 H1 上限是 `16px`，工具面板内标题按密度降级。

**The Tabular Numbers Rule.** 数字列、计数、时间、资源用量必须使用 `font-variant-numeric: tabular-nums`，避免表格列抖动。

**The Visible Label Rule.** 表单字段必须有可见 label。placeholder 只能作为输入提示，不能替代字段名。

## 4. Elevation

BK-Lite Web 以边框和色阶分层为主，阴影为辅。默认面板不应该漂浮，只有弹窗、Popover、Dropdown、悬浮菜单、少量工作台入口可以使用阴影。卡片如果已经有 `1px` 边框，就不要再叠加大模糊阴影。

### Shadow Vocabulary
- **Inset Content Edge** (`box-shadow: inset 0 6px 10px -6px rgba(0, 0, 0, 0.03)`): 主内容区顶部的轻微压线，来自 `.main-content`。
- **Popover Shadow** (`box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15)`): 顶部菜单 Popover 和临时浮层。
- **Light Card Shadow** (`shadow-sm` / blur <= 8px): 仅用于需要从聊天流、报告流中分离的小型卡片。

### Named Rules

**The Flat By Default Rule.** 表格、筛选区、详情区、设置页默认靠边框和背景分层。阴影不作为装饰。

**The No Ghost Card Rule.** 不要在同一元素上组合 `border: 1px solid ...` 和大于 `16px` 模糊的阴影。二选一，产品界面通常选边框。

**The Z Index Rule.** 禁止随手写 `9999` / `10000`。现有 `.ant-dropdown { z-index: 10000; }` 是平台遗留，新增浮层应使用 Ant Design Portal 或集中 z-index token。

## 5. Components

组件以 Ant Design 为基础，业务组件只做组合和约束，不重新发明控件。新模块优先复用 `web/src/components` 下的通用组件，例如 `CustomTable`、`sub-layout`、`operate-modal`、`ellipsis-with-tooltip`、`content-drawer`、`time-selector` 和 `permission`。机器可读的 shared 清单以 `component-ownership.manifest.json` 为准，不以组件名称或 Storybook 是否引用来猜测归属。

**The Framework First Rule.** 写任何新界面前，先按顺序查找：1) Ant Design 是否已有对应组件；2) `web/src/components` 是否已有项目封装；3) 当前业务模块是否已有同类组件或样式；4) 只有前三者无法覆盖交互、权限、状态或领域语义时，才新增组件。新增组件必须沿用现有 token、AntD 交互语义和模块目录风格。

### 组件创建与放置

| 场景 | 做法 |
| --- | --- |
| Ant Design 已覆盖 | 直接使用 Ant Design，并通过 token 做轻量约束 |
| 项目 shared 已覆盖 | 直接复用 `src/components` 的公开入口，不从内部子路径导入 |
| 当前 app 已有同类实现 | 复用或扩展该 app 的唯一实现 |
| 只有当前 app 需要的新业务组件 | 创建到 `src/app/<app>/components`，允许进入 Storybook，但不因此变成 shared |
| 两个以上 app 已出现同一稳定模式 | 先明确差异维度和 props，再迁移为 shared 并补 Storybook 契约 |

禁止“先放 `src/components`，以后再看是否复用”。组件默认是 app-local，跨 app 复用由真实消费者证明。

### Buttons
- **Shape:** 默认 `6px`，不要为普通按钮使用大圆角卡片式外观。
- **Primary:** AntD `type="primary"`，高度默认 `40px`，用于创建、保存、提交、确认。
- **Secondary:** AntD `default`，用于取消、返回、普通动作。
- **Inline:** AntD `link` + `small`，用于表格行内查看、编辑、复制。
- **Destructive:** 行内删除用 `type="link" danger`；主破坏操作用 `danger`，并配 Modal/Popconfirm 二次确认。
- **Loading:** 所有触发 API 的按钮必须有 `loading` 或 disabled 防重复提交。
- **Icon:** 图标按钮必须有 `aria-label`，图标本身 `aria-hidden="true"`。

### Cards / Containers
- **选择顺序:** 普通容器优先 Ant Design `Card`；指标摘要用 `SummaryMetricCard`；可选择卡片组用 `SelectableCardGrid`；页面表单头用 `PageFormHeaderCard`；故障排查语义用 `TroubleshootingCard`。实体、技能、集成等业务卡片保持 app-local，并组合已有 primitive。
- **Corner Style:** 默认 `8px`，业务卡片可用 `12px`。不要超过 `16px`。
- **Background:** 主容器 `var(--color-bg)`，弱容器 `var(--color-fill-1)`。
- **Border:** 默认 `1px solid var(--color-border)`。不要用 `border-left` / `border-right` 大于 `1px` 做彩色侧边条。
- **Internal Padding:** 默认 `16px`，弹窗主体可用 `24px`，密集行内块用 `8px`。
- **Nesting:** 禁止卡片套卡片。需要分组时用标题、分割线、表格分组或背景色阶。
- **新增前提:** 新卡片必须先说明现有 Card/primitive 为什么无法承载；不能因为局部间距或颜色不同就复制一个新卡片组件。

### Inputs / Fields
- **Style:** 使用 AntD 表单控件，桌面最小高度 `40px`，移动/触摸场景目标热区不低于 `44px`。
- **Focus:** 使用 `var(--color-primary)` 或 AntD 默认 focus ring，必须可见。
- **Validation:** 错误信息紧邻字段；多错误提交后焦点回到第一个错误字段。
- **Long Text:** 多行文本用 `TextArea` + `showCount` + `maxLength`。资源名、路径、命令要支持换行、横向滚动或 tooltip。

### Tables
- **Density:** 表格可以高密度，但列头、操作列和筛选条件必须清晰。
- **Actions:** 操作列固定右侧，行内按钮保持 `link small`，不要混用大按钮。
- **Overflow:** 长文本用 `EllipsisWithTooltip`，不要只用原生 `title`。
- **States:** loading 用 Skeleton，empty 用 `Empty` + 简短说明 + 下一步动作，error 用错误提示 + retry。
- **Pagination:** 默认 20 条，提供 10 / 20 / 50 / 100，显示总数。

### Navigation
- **Top Menu:** 顶栏背景跟随主题，active 使用 `var(--color-primary)` 或 active 背景。图标使用统一图标库，不手绘临时 SVG。
- **Side Menu:** 侧栏默认 `var(--color-components-side-nav-bg)`，hover 用 `var(--color-components-side-nav-hover-bg)`，active 用 `var(--color-components-side-nav-text-active-bg)`。
- **Segmented:** 二级视图切换优先用 AntD Segmented 或项目 `sub-layout` 约定，保持 `gap-2` 节奏。

### Modals / Drawers
- **Header:** 弹窗头部使用 `var(--color-modal-header-color)`，标题 `16px / 600`。
- **Footer:** 按钮组统一 `flex justify-end gap-2`，不要给单个按钮加 `mr-*` / `ml-*`。
- **Confirmation:** 删除、重置、权限变更、凭据暴露等风险操作必须说明后果。
- **Viewport Fit（禁止触底）:** 弹窗必须自适应视口高度，任意屏幕下都不能触底（底部按钮被截断或贴住视口底边）。表单较长时给 `Modal` 主体限高并内部滚动：`styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }}`，保证底部按钮始终可见且与视口底部留有间距；若内容仍然过长、滚动割裂，改用 `Drawer`（抽屉）承载长表单。

### Chat / AI Output
- **Reports:** 聊天区中的报告卡保持轻量正式，不做深色大屏化，不做渐变标题。
- **Commands:** 命令块必须可复制，复制失败有反馈，空命令有空状态。
- **Choices:** 用户选择必须使用真实 `button` / 表单控件，支持键盘、disabled、loading、已选择态。
- **Streaming:** 流式内容默认可见，不依赖动画 class 才显示。

## 6. Storybook 与完成标准

- shared component 的新增、API 变化、视觉变化必须同步 Storybook；Storybook 是组件契约中心，不是 shared 所有权证据。
- app-local 组件在交互复杂、状态较多或需要横向对比时也应进入对应 family story，但仍保留 app-local 所有权。
- 每个标准组件至少验证默认、loading、empty/error（适用时）、disabled/readonly（适用时）、长文本和窄容器。
- 所有视觉组件必须在 Storybook 或真实页面中分别检查亮色与暗色；不能只看默认主题截图。
- UI 改造交付时必须说明：复用了哪个组件、为何没有新建 shared；若新增 app-local，说明所属 app；若修改 shared，列出受影响 app 和 Storybook 更新。

## 7. Do's and Don'ts

### Do:
- **Do** 优先使用 `var(--color-*)`、Ant Design token 和 `web/src/components` 通用组件。
- **Do** 先查当前框架组件和已有业务组件，再写新组件；能组合就组合，不能组合才抽象。
- **Do** 新增业务组件默认放在 `src/app/<app>/components`，以真实跨 app 消费证明 shared 资格。
- **Do** 在亮色和暗色下验证所有新增或修改的视觉状态。
- **Do** 用 `gap-2` / `gap-3` 管理按钮组和标签组间距，不把 margin 散落到子按钮。
- **Do** 为表格数字列加 `font-variant-numeric: tabular-nums`。
- **Do** 为图标按钮提供 `aria-label`，为可展开区域提供 `aria-expanded` / `aria-controls`。
- **Do** 给 loading、empty、error、permission denied、readonly 状态写清楚下一步。
- **Do** 让中文、英文、长资源名、命令、路径、emoji 都能安全换行或省略。
- **Do** 保持产品界面轻量、智能、友好：让操作更清楚，而不是让界面更热闹。

### Don't:
- **Don't** 做深色运维大屏化，除非该路由明确是监控展示大屏。
- **Don't** 做营销感 SaaS 官网风：大 hero、巨大指标卡、渐变大标题、宣传话术都不属于控制台默认界面。
- **Don't** 使用 `border-left` 或 `border-right` 大于 `1px` 作为彩色侧边强调。
- **Don't** 使用 gradient text、装饰性玻璃拟态、重复卡片网格、手绘 sketch SVG、条纹背景。
- **Don't** 为了视觉新鲜感重写 Ant Design 已有的 Button、Modal、Drawer、Table、Form、Select、Tabs、Segmented、Tooltip、Popover。
- **Don't** 在组件内直写品牌色或状态色 hex；需要时加 token 或语义映射。
- **Don't** 用 `bg-white`、`text-black`、固定浅灰边框等只适用于单一主题的样式代替语义 token。
- **Don't** 复制已有组件只为改变颜色、圆角、边框或间距；优先复用现有 variant 或补一个稳定 variant。
- **Don't** 用 placeholder 当 label，不要只靠 toast 汇总表单错误。
- **Don't** 把 `div onClick` 当按钮。可点击就用 `button`、AntD Button、链接或正确 ARIA 语义。
- **Don't** 给卡片、输入框、面板使用 `32px+` 大圆角。
- **Don't** 在卡片上叠加 `1px border` 和大模糊阴影。
- **Don't** 在新代码里继续扩大 `z-index: 9999/10000`、硬编码 `min-width`、全局覆盖 AntD 样式。
- **Don't** 让页面或容器出现非预期的横向滚动条（`overflow-x`）。布局必须自适应宽度：表格列宽随容器自适应（不要用固定宽度或强制 `scroll.x` 把内容撑出容器），长文本用换行 / 省略 / tooltip。横向滚动只允许出现在明确需要的局部（命令块、日志、超宽代码），不允许出现在整页或弹窗。
- **Don't** 让弹窗触底。长表单弹窗必须限高 + 主体内部滚动；实在过长、滚动割裂就改用抽屉（见 Modals / Drawers 的 Viewport Fit）。
