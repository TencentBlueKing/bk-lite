---
name: BK-Lite Web Console
description: AI First lightweight O&M product UI for daily operations work.
colors:
  primary: "#155AEF"
  primary-bg-active: "#E1EDFC"
  body-bg: "#F2F4F7"
  surface: "#FFFFFF"
  surface-muted: "#F6F8F9"
  fill-soft: "#F4F5F8"
  fill-subtle: "#EDEFF3"
  border: "#EAECF0"
  border-strong: "#D1D7E1"
  text-strong: "#1E252E"
  text: "#475468"
  text-muted: "#7588A3"
  text-disabled: "#B2BDCC"
  success: "#27C274"
  danger: "#F43B2C"
typography:
  title:
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.5
rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "20px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    height: "40px"
    padding: "0 16px"
  button-link:
    backgroundColor: "transparent"
    textColor: "{colors.primary}"
    rounded: "{rounded.sm}"
    padding: "0"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: "16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-strong}"
    rounded: "{rounded.sm}"
    height: "40px"
---

# Design System: BK-Lite Web Console

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

### Primary
- **Operations Blue** (`#155AEF`, `var(--color-primary)`): 主按钮、链接、当前导航、选中态、focus ring。单屏使用面积应保持少量，不用于大面积背景。
- **Selected Blue Wash** (`#E1EDFC`, `var(--color-primary-bg-active)`): 浅色选中背景、弱提示背景。必须搭配深色正文，不用浅灰正文压在蓝底上。

### Neutral
- **Console Body** (`#F2F4F7`, `var(--color-secondary)`): 页面背景和应用壳底色。
- **Surface White** (`#FFFFFF`, `var(--color-bg)`, `var(--color-bg-1)`): 主内容容器、表格、弹窗、卡片。
- **Soft Fill** (`#F6F8F9`, `var(--color-fill-1)`): 二级面、筛选区、分组头、拖拽侧栏。
- **Quiet Fill** (`#F4F5F8`, `var(--color-fill-2)`): hover 背景、弱分隔背景。
- **Border Line** (`#EAECF0`, `var(--color-border)`): 默认分隔线和容器边框。
- **Strong Text** (`#1E252E`, `var(--color-text-1)`): 标题、关键数值、主要字段。
- **Body Text** (`#475468`, `var(--color-text-2)`): 正文、普通表格单元格、导航文本。
- **Muted Text** (`#7588A3`, `var(--color-text-3)`): 辅助说明、时间、次要 metadata。
- **Disabled Text** (`#B2BDCC`, `var(--color-text-4)`): disabled、占位、极弱提示。不要用于正文。

### Semantic
- **Success Green** (`#27C274`, `var(--color-success)`): 成功、健康、完成。必须配文案或图标，不只靠颜色。
- **Danger Red** (`#F43B2C`, `var(--color-fail)`): 失败、删除、严重风险。破坏性操作必须配二次确认。

### Named Rules

**The Token First Rule.** 新代码优先使用 `web/src/styles/globals.css` 里的 `--color-*` token。组件内禁止直写 `#155AEF`、`#1677ff`、`#52c41a` 等品牌/语义色；需要新语义色时集中成映射常量，并补暗色模式。

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

组件以 Ant Design 为基础，业务组件只做组合和约束，不重新发明控件。新模块优先复用 `web/src/components` 下的通用组件：`CustomTable`、`sub-layout`、`operate-modal`、`ellipsis-with-tooltip`、`content-drawer`、`time-selector`、`permission`。

**The Framework First Rule.** 写任何新界面前，先按顺序查找：1) Ant Design 是否已有对应组件；2) `web/src/components` 是否已有项目封装；3) 当前业务模块是否已有同类组件或样式；4) 只有前三者无法覆盖交互、权限、状态或领域语义时，才新增组件。新增组件必须沿用现有 token、AntD 交互语义和模块目录风格。

### Buttons
- **Shape:** 默认 `6px`，不要为普通按钮使用大圆角卡片式外观。
- **Primary:** AntD `type="primary"`，高度默认 `40px`，用于创建、保存、提交、确认。
- **Secondary:** AntD `default`，用于取消、返回、普通动作。
- **Inline:** AntD `link` + `small`，用于表格行内查看、编辑、复制。
- **Destructive:** 行内删除用 `type="link" danger`；主破坏操作用 `danger`，并配 Modal/Popconfirm 二次确认。
- **Loading:** 所有触发 API 的按钮必须有 `loading` 或 disabled 防重复提交。
- **Icon:** 图标按钮必须有 `aria-label`，图标本身 `aria-hidden="true"`。

### Cards / Containers
- **Corner Style:** 默认 `8px`，业务卡片可用 `12px`。不要超过 `16px`。
- **Background:** 主容器 `var(--color-bg)`，弱容器 `var(--color-fill-1)`。
- **Border:** 默认 `1px solid var(--color-border)`。不要用 `border-left` / `border-right` 大于 `1px` 做彩色侧边条。
- **Internal Padding:** 默认 `16px`，弹窗主体可用 `24px`，密集行内块用 `8px`。
- **Nesting:** 禁止卡片套卡片。需要分组时用标题、分割线、表格分组或背景色阶。

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

### Chat / AI Output
- **Reports:** 聊天区中的报告卡保持轻量正式，不做深色大屏化，不做渐变标题。
- **Commands:** 命令块必须可复制，复制失败有反馈，空命令有空状态。
- **Choices:** 用户选择必须使用真实 `button` / 表单控件，支持键盘、disabled、loading、已选择态。
- **Streaming:** 流式内容默认可见，不依赖动画 class 才显示。

## 6. Do's and Don'ts

### Do:
- **Do** 优先使用 `var(--color-*)`、Ant Design token 和 `web/src/components` 通用组件。
- **Do** 先查当前框架组件和已有业务组件，再写新组件；能组合就组合，不能组合才抽象。
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
- **Don't** 用 placeholder 当 label，不要只靠 toast 汇总表单错误。
- **Don't** 把 `div onClick` 当按钮。可点击就用 `button`、AntD Button、链接或正确 ARIA 语义。
- **Don't** 给卡片、输入框、面板使用 `32px+` 大圆角。
- **Don't** 在卡片上叠加 `1px border` 和大模糊阴影。
- **Don't** 在新代码里继续扩大 `z-index: 9999/10000`、硬编码 `min-width`、全局覆盖 AntD 样式。
