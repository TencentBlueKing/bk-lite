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
| 设计语义 | `web/DESIGN.md` | 视觉原则、组件选择、主题语义、布局/样式写法（Tailwind vs 行内）和使用边界 |
| 运行时 Token | `web/src/styles/globals.css` | `:root` 亮色值和 `.dark` 暗色值；代码中的最终颜色真相 |
| 组件所有权 | `web/COMPONENT_GOVERNANCE.md` | shared、primitive、app-local 的目录边界；治理时如何执行样式约束 |
| 组件契约 | Storybook `web/src/stories` | 组件 API、状态、变体和使用示例 |

Markdown 不复制维护运行时颜色值。修改品牌色或主题值时先改 `globals.css` 的同名语义变量，再用 Storybook 验证；本文只说明应该选择哪个变量以及它表达什么。

### Code Agent：短规则常驻，长文按需

日常改 UI **不要默认通读本文全文**。可执行短清单在根目录 `CLAUDE.md` / `AGENTS.md` →「Web UI 硬约束」（会话常驻）。

**仅当**新建视觉组件、改 token/设计语义、组件治理大迁移、设计走查，或短规则不够用时，再分段阅读本文相关章节（优先 **Overview**、**Layout & Styling**、**Do's and Don'ts**）和 `COMPONENT_GOVERNANCE.md`。做**实体网格列表页**时另读 **Components → Entity List Cards**；做**列表/表格上方搜索与操作**时另读 **List / Table Toolbar**；做**设置双栏 / 已选对象 / 对话**时另读 **Studio Workbench** 与 **Chat / AI Output**；做**详情页 / 概览页（KPI + 卡片分区 + 属性面板）**时另读 **Detail / Overview Workbench**；做**加载态**时另读 **Loading / Skeleton**。

### Code Agent / 开发者开始写 UI 前

1. 先跟短规则（上节）；需要时再读本文相关章节与 `COMPONENT_GOVERNANCE.md`。
2. 按“Ant Design → `src/components` → 当前 app 组件”的顺序检索，不凭记忆创建新组件。
3. 在 Storybook 查找相同交互或视觉契约，确认已有组件的 props 和状态。
4. 有合适组件时直接复用，不复制源码、不创建平行实现。
5. 布局与间距用 Tailwind `className`；颜色用语义 token；不要新增大段行内布局（见 Layout & Styling）。
6. 确实没有且当前只有一个 app 使用时，在 `src/app/<app>/components` 创建 app-local 组件。
7. 只有两个及以上真实 app 已经接入同一抽象时，才提升到 `src/components`；shared 组件必须同步 Storybook。
8. 完成后检查亮色、暗色、loading、empty、error、disabled 和长文本状态。

如果为了满足单一页面而修改 shared 组件，优先增加清晰、可复用的 variant；不能把业务字段、API 请求或 app 类型塞进 shared 组件。

视觉改造只动布局、间距、token 与组件壳。不要擅自改文案、展示字段、状态色，也不要增删或改换表单字段与控件。这些如果必须动，先讨论并确认。

## 1. Overview

**气质：浅色、克制的企业控制台（Light Operations Desk）**

BK-Lite Web 的默认气质是 **浅色、克制的企业控制台**：少装饰、少线框，用留白和浅底表达结构；让人觉得能工作，而不是在看科技展览。四个词：**干净、扁平、少框、留白分层**。

这不是「科技风」。科技大屏（深色、霓虹、发光、巨大指标）、营销 SaaS（大 hero、渐变标题、很满的卡片墙）、旧式后台（每块都描边、开关套开关、灰底输入框）都不属于默认界面。OpsPilot 的列表卡、智能体设置双栏、测试对话，以及 RUM 的会话/错误详情页与应用概览页，是这套气质的当前参考面；其他 app 做同类 UI 时靠过来，不要平行发明第二套皮肤。

界面服务于日常运维：发现资源、筛选对象、查看状态、处理告警、执行作业、确认高风险操作。友好来自清晰结构、可预期控件和及时反馈，而不是装饰。默认 register 是 product：顶栏、侧栏、筛选、表格、抽屉、弹窗、状态标签、批量操作。视觉策略是 restrained：白色/浅灰工作面 + 蓝色主操作 + 少量语义状态色。AI 出现时像工作助手，展示输入、输出、风险、下一步，不制造舞台感。

**Key Characteristics:**
- 干净：白底工作面，浅灰分区，品牌蓝只用于主操作和少量状态点。
- 扁平：靠边框和 `fill-*` 色阶分层，默认无阴影、无渐变、无玻璃拟态。
- 少框：外层最多一块面板；里面用标题、分割线、浅底小卡，不再套盒子。
- 过程让路：思考、工具、计划是可收起的旁白；正文和输入才是主体。可输入区域必须白底。
- 同构骨架：首次加载与整页刷新用与最终布局同构的骨架屏，不用居中 `Spin` 罩空白页。
- 密集但不拥挤：表格、筛选、详情可以信息密度高，但必须有清晰分组。
- 克制用色：`--color-primary` 只用于主操作、链接、选中、focus，不做装饰。智能体设置里的集合数量用非主色胶囊（技能包青绿、工具琥珀），列表卡 `+N` 保持原样。
- 可预测交互：按钮、表单、表格、弹窗沿用 Ant Design 语义，不自造控件词汇。
- 框架优先：新 UI 先使用 Ant Design、`web/src/components` 和当前模块已有组件。
- className 优先：布局/间距用 Tailwind；颜色走语义 token；行内 `style` 仅用于动态值与 AntD 契约例外。
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
| 设置页集合数量 | 技能包 `var(--color-count)` / `--color-count-bg`；工具 `var(--color-count-alt)` / `--color-count-alt-bg` | 主色蓝胶囊、无底色灰字、全页只用一种计数色 |
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

**去框分层：** 结构优先用留白、`border-t` / `divide-y` 和 `var(--color-fill-1)` 浅底，而不是给每个小组再套线框。一页外层最多一层面板（例如设置左栏 / 测试右栏各一块）；栏内禁止卡套卡。灰底只给只读弱容器，不给可输入区域。

### Shadow Vocabulary
- **Inset Content Edge** (`box-shadow: inset 0 6px 10px -6px rgba(0, 0, 0, 0.03)`): 主内容区顶部的轻微压线，来自 `.main-content`。
- **Popover Shadow** (`box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15)`): 顶部菜单 Popover 和临时浮层。
- **Light Card Shadow** (`shadow-sm` / blur <= 8px): 仅用于需要从聊天流、报告流中分离的小型卡片。
- **Micro Card Lift** (`box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03)`): 详情/概览页分区卡与 KPI 卡配 `1px` 边框时的微抬起，肉眼几乎不可见，只负责让卡从 `background-body` 上分离。

### Named Rules

**The Flat By Default Rule.** 表格、筛选区、详情区、设置页默认靠边框和背景分层。阴影不作为装饰。

**The No Ghost Card Rule.** 不要在同一元素上组合 `border: 1px solid ...` 和大于 `16px` 模糊的阴影。二选一，产品界面通常选边框。

**The De-box Rule.** 能用留白、分割线和 `fill-1` 就不要新边框。设置页内块、对话过程态、发送框默认无阴影、无灰底。

**The Z Index Rule.** 禁止随手写 `9999` / `10000`。现有 `.ant-dropdown { z-index: 10000; }` 是平台遗留，新增浮层应使用 Ant Design Portal 或集中 z-index token。

## 5. Layout & Styling（Tailwind / className / 行内样式）

BK-Lite Web 已启用 Tailwind。**布局、间距、对齐的默认且优先表达是 Tailwind `className`**，不是 `style={{ ... }}`，也不是为普通布局新建 SCSS Module。颜色与主题仍以 `globals.css` 语义 token 为准；Tailwind 负责结构节奏，token 负责主题语义，二者互补，不能互相替代。

组件所有权门禁见 `COMPONENT_GOVERNANCE.md`；本节约束页面与组件的样式写法。治理迁移触及 UI 时，须同时满足本节与所有权规则。持续清理任务见样式统一 loop（行内 → Tailwind）。

### 选型顺序

1. Ant Design 组件自带布局 / `styles` API（仅限组件契约需要的局部，如 `Modal` body 限高）。
2. **Tailwind `className`**（默认）：`flex`、`gap-*`、`p-*`、`w-*`、`min-h-0`、`truncate`、`text-[var(--color-text-1)]` 等（颜色类必须写完整 token 名；文档里不要写带星号的通配 class，会被 Tailwind 扫进 CSS）。
3. 已有 CSS Module / 全局语义类：仅用于 AntD 深层覆盖、复杂伪类/动画，或 Tailwind 无法稳定表达的局部；**禁止**为 flex/间距/宽高新开 module。
4. 最后才考虑 `style={{ ... }}`，且必须落入下方白名单例外。

### Named Rules

**The ClassName First Rule.** 新代码与治理触及的改动中，flex/grid、间距、宽高、对齐、换行、省略等布局样式必须写在 `className`。禁止新增大段 `style={{ display: 'flex', gap: 12, padding: 16, ... }}` 布局对象。

**The Token Via Class Or Var Rule.** 颜色、边框、背景、文字色使用语义 token：优先 Tailwind 已映射的语义写法，或 `className`/`style` 中的 `var(--color-…)`（写具体名字）。禁止 `#fff`、`#8c8c8c`、`#ff4d4f`、`white`、`bg-white`、`text-black` 等硬编码主题色。

**The Inline Style Exception Rule.** 仅允许下列情况使用行内 `style` / AntD `styles`：

| 允许 | 说明 |
| --- | --- |
| Ant Design 组件契约 | 如 `Modal`/`Drawer` 的 `styles.body` 限高滚动（见 Modals / Drawers Viewport Fit） |
| 运行时动态值 | 只能由数据决定的值：图表坐标、进度宽度、拖拽位置、虚拟列表 offset、用户自定义色板等 |
| 第三方/画布特例 | 拓扑、3D、ECharts 容器等无法用 class 稳定表达的瞬时尺寸 |
| 过渡期单点修补 | 修改旧页时若不动整块布局，可暂留原行内；**同次改动若重写该区块布局，必须改为 className** |

**The No Parallel Style System Rule.** 同一元素不要同时堆叠“完整行内布局对象 + 等价 Tailwind class”。新增 SCSS Module 前先确认 Tailwind 无法覆盖；禁止为改 4px 间距新建 module 或组件。清理存量时：**行内布局 → Tailwind**，优先于继续堆 CSS Module。

**The Migration Touch Rule.** 组件治理或功能改动触及的 JSX 区块，若含可用 Tailwind 表达的行内布局，应在同次改动中改为 `className`；不要只换组件壳、留下整段 `style={{ display:'flex' ... }}`。整页历史债可另开清理任务，但**禁止在新代码中扩大行内布局比例**。

### 断点

默认使用 Tailwind 断点（`sm`–`2xl`）。超宽屏增密使用 `3xl`（`1920px` / `120rem`），定义在 `web/src/styles/globals.css` 的 `@theme` 与 `web/tailwind.config.ts`。不要散落 `min-[1920px]:`。Ant Design Table 的 `responsive` 最宽档是 `xxl`（1600px），用来在宽屏放出次要列。

### 示例

```tsx
// Do
<div className="mb-3 flex w-full flex-wrap items-center gap-3">
  <Input.Search className="w-64" />
  <Button type="primary">创建</Button>
</div>

// Don't（布局行内化）
<div style={{ display: 'flex', gap: 12, marginBottom: 12, alignItems: 'center' }}>
  <Input.Search style={{ width: 200 }} />
</div>

// Don't（硬编码色）
<a style={{ color: '#ff4d4f' }}>删除</a>
<span style={{ color: 'var(--color-text-3, #8c8c8c)' }}>...</span>
// Do
<a className="text-[var(--color-fail)]">删除</a>
<span className="text-[var(--color-text-3)]">...</span>
```

## 6. Components

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
- **Background:** 主容器 `var(--color-bg)`，弱容器 `var(--color-fill-1)`。已选对象小卡用 `bg-[var(--color-fill-1)]/70`，不要再加描边和阴影。
- **Border:** 默认 `1px solid var(--color-border)`。禁止卡片左侧通高彩色 `border-left` / `border-right`（大于 `1px`）。章节标题允许 **约 `4×14px` 的品牌色短竖条** 作标记，不得铺满卡片高度；短竖条只用于**同一块面板内部**划分子章节（如设置长表单里的「基础配置 / 提示词」），**已经是独立卡片（自带边框、栏头、内边距）的栏头禁止再加竖条**——容器边界本身就是分组，再加竖条属重复装饰。
- **Shadow:** 独立卡片允许 `shadow-[0_1px_3px_rgba(0,0,0,0.03)]` 级别的微阴影配 `1px` 边框，用于让卡片从 `background-body` 上轻微抬起；不允许更大模糊（见 Elevation → No Ghost Card）。
- **Internal Padding:** 默认 `16px`，弹窗主体可用 `24px`，密集行内块用 `8px`；已选对象小卡用 `p-2.5`。
- **Nesting:** 禁止卡片套卡片。需要分组时用标题、分割线、表格分组或背景色阶。
- **已选对象小卡：** 技能包、工具、已挂载项等共用一套缩小解剖：标题行左「名称 + 数量胶囊」、右「+ 添加xxx」（AntD `link` + `small`）；下一句说明；下方网格小卡（`rounded-lg p-2.5`，左 `20×20` 图标容器 + 名称，右配置/删除）。有选中即启用，空列表即关闭，**不要再给集合加总开关**；后端仍传列表（空数组即关）。数量必须有底色小胶囊（少数允许 `rounded-full`）；技能包用青绿、工具用琥珀，不要再用主色蓝，也不要做成无底色数字。空列表不显示数量。参考：OpsPilot 智能体设置页的技能包 / 工具。列表实体卡底栏 `+N` 不走这套，保持原样。
- **新增前提:** 新卡片必须先说明现有 Card/primitive 为什么无法承载；不能因为局部间距或颜色不同就复制一个新卡片组件。

### Entity List Cards（统一实体列表卡）

控制台里「网格实体卡」类列表页（工作台、智能体、知识库、工具、记忆、供应商等）统一走同一套解剖与页壳，便于跨模块继用。OpsPilot 为首个完整落地；新模块或旧列表改造按本节执行，不要再发明平行卡片壳。

**参考实现（shared）：**

| 能力 | 路径 |
| --- | --- |
| 统一卡 | `web/src/components/grid-entity-card` |
| 列表页头 | `web/src/components/list-page-header` |
| 加载骨架 | `web/src/components/card-grid-skeleton` |
| 相对时间 | `web/src/utils/relativeTime.ts`（`updated_at` 优先，否则 `created_at`） |

OpsPilot 与系统管理已接入上述抽象。域内差异（置顶、厂商图标、模型色、暂停条）留在 app 包装层，不要再复制一份卡片壳。

#### 卡片解剖（Look B）

自上而下固定为：

1. **头行：** 左上图标（`40×40`、圆角 `md`、底 `fill-1`）+ 标题（`15px` / semibold / `leading-snug`，单行省略；完整内容用 `EllipsisWithTooltip`，**仅文字真正溢出时**出 tooltip）+ 右上置顶（可选）与更多菜单。
2. **副行（标题下）：** 有状态点 / 相对时间时渲染，并与图标顶对齐；**无内容时不占位**，标题与 `40×40` 图标垂直居中。类型 tag 不要塞进这一行。
3. **描述：** 最多两行，辅助色，无内容用 `--`。
4. **Meta tags（描述下，固定 `min-h-5`）：** 能力/类型/模型等短标签；可空。状态类 tag（上线/下线）**字重正常（400）**。与副行分工：副行 = 状态点/时间，meta = 类型标签。**来源类（内置 / 外部）不是能力 tag**：用 `SourceOriginBadge`（内置 primary、外部 success），禁止和能力标签混成同色灰片。计数、周期等度量不要写成 tag。
5. **底栏：** 默认 `Owner · 名称` 左、`Team · 名称`（多团队 `+N`）右；供应商类可用「模型数 + Switch」。分割线用 `fill-2`。

- 卡片 `min-h` 与 `h-full` 保证同排等高；meta 行保留 `min-h`。副行有无内容时卡头高度可不同，由下方弹性区消化。
- 颜色、边框、hover 洗色一律语义 token；禁止硬编码主题色。
- 图标用项目 iconfont `type`；模块内轮换图标池时用业务域图标，不要把别的模块图标集硬搬过来。
- 设置页里的技能包 / 工具小卡是这套解剖的缩小版（`20×20` 图标、无底栏），不是另一套皮肤。

#### 列表页壳

- **页头：** 见 **页眉两档**。只有进入页面后第一眼就是卡片、上面没有 Tab，才把标题、说明和操作放在同一行。
- **主新建按钮：** 文案统一为「新建」（`common.new`），`type="primary"` + `PlusOutlined`。弹窗标题仍可用「添加…」；导入类动作保留「导入…」等专名，不硬改成「新建」。
- **入口位置：** 新建在工具条主按钮，不在网格里塞「新增」空卡（除非产品明确要求）。
- **筛选 / 视图切换：** 分段/类型筛选放在搜索左侧、仍在右侧成组内；不要单独占一行，除非筛选项非常多。

### 页眉两档

页眉只有两种摆法。字号同一套，文案由各模块自己写。

- **标题：** `16px` / semibold / `text-1`
- **说明：** 标题下方，`12px` / `text-3`，最多两行，超出省略

**画布页眉。** 进入页面后第一眼就是卡片网格，上面没有 Tab，卡片直接铺在页面底上。标题、说明和操作同一行：左边标题和说明，右边搜索与操作成组。用公用组件 `ListPageHeader`（`web/src/components/list-page-header`）。不要在这行上面再叠一条只有标题的白卡。

参考：知识库、应用管理、通知渠道。

```
[标题]
[说明，最多两行]                    [筛选] [搜索] [刷新] [新建]
                                    └──────── 成组靠右 ────────┘
```

**独立页眉条。** 页眉上面还有 Tab，或者说明不在最外层卡片上时用。二级 Tab 下的页面、内容白卡里的表格、左右分栏、内容区自己的 Tab、对象身份加侧栏子页、纯表单，以及筛选条单独成行的目录页，都走这档。标题和说明单独一条，横在内容上面；这条里不放搜索和新建。高度随两行说明增长，不固定 `80px`，说明不强制单行。操作留在内容区，成组靠右。页内标题保留，文案用当前页的名字。

公用组件是 `TopSection`（`web/src/components/top-section`）。高度随说明增长，说明最多两行，图标 `40px`。各模块直接用它。

### List / Table Toolbar

搜索和操作是全平台最容易乱的一行。无论页眉在哪一档，操作都 **成组靠右**，中间不要拉空。

参考：`ListPageHeader`、`SearchActionBar`、`ToolbarSplitShell`。

画布页眉的操作在标题同一行右侧。独立页眉条下面的内容区只有操作：

```
                                        [筛选] [搜索] [刷新] [新建]
                                        └──────── 成组靠右 ────────┘
```

**左右：**
- **左：** 画布页眉放标题和说明。内容区工具条的左边只放视图切换（Segmented / Tabs 那种「这是哪一页数据」）。
- **右：** 筛选、搜索、次要按钮、主操作，**从左到右**固定为：`筛选 → 搜索 → 刷新/更多 → 新建`。
- 搜索不要单独贴左、新建不要单独贴右。二者必须紧挨着出现在右侧组里。

**间距（不要各写一套）：**
- 标题区与右侧组：`justify-between` + `gap-x-4`
- 右侧组内部：`gap-2`
- 换行：`flex-wrap` + `gap-y-3`，垂直居中 `items-center`
- 工具条到列表/表格：`mb-4`（16px）。内嵌在已有间距容器里用 `SearchActionBar` 的 `spacing="flush"`
- 搜索默认宽 `w-60`（240px），需要更长时再用 `w-80`，不要拉满整行

**实现：**
- 画布页眉：`ListPageHeader`，`actions` 里放搜索 + 新建。
- 独立页眉条下的内容区：`SearchActionBar`（搜索与 actions 已成组靠右），不再把页眉嵌进这一行。
- 左视图切换 + 右搜索操作：`ToolbarSplitShell`（`leading` / `trailing`）。
- 禁止手写 `justify-between` 把 `Input.Search` 和「新建」拆到两端。

**The Clustered Toolbar Rule.** 搜索和主操作必须成组靠右。画布页眉的标题在同一行左侧；独立页眉条的标题不进这一行。不要为了把一行撑满而把搜索和新建拉开。

#### 加载 / 刷新 / 空态

- **首次加载与整表刷新：** 用与卡片同解剖的**网格骨架屏**，不要用 `Spin` 罩住旧卡片。
- **分页加载更多：** 底部小 `Spin` 即可，不必整页骨架。
- **空态：** `Empty` / `CompactEmptyState` + 一句说明；有新建权限时给出主操作入口。
- **错误：** toast 或页内错误 + 可重试；失败时不要假骨架假装有数据。

#### 时间展示

- 接口有 `updated_at` 或 `created_at` 时，在标题下状态行展示相对时间（优先修改时间）。
- 没有时间字段则不展示、不造假；**不要为了列表展示单独改库表加字段**，除非产品明确要求并走正常迁移。

#### Named Rules

**The One List Card Rule.** 同一产品面的实体网格只保留一套卡片解剖；新列表复用或升 shared，不平行发明第二套头图+标签+底栏布局。

**The Refresh Skeleton Rule.** 列表整页 loading/refresh 用骨架网格，不用遮罩 Spin 盖住旧数据。

**The New Not Add Rule.** 列表页主创建按钮文案用「新建」；「添加」留给弹窗标题或表单项内追加行。

**The Preserve Meaning Rule.** 统一视觉不能改页面含义。文案、展示字段、状态色保持原样；也不要增删或改换表单字段与控件。这些如果必须动，先讨论、经确认后再改。

### Inputs / Fields
- **Style:** 使用 AntD 表单控件，桌面最小高度 `40px`，移动/触摸场景目标热区不低于 `44px`。
- **Editable surface:** 可输入区域必须是 `var(--color-bg)` 白底。`fill-1` 只给只读弱容器、禁用态或分组底。灰底输入框会被当成不能输入。
- **Focus:** 使用 `var(--color-primary)` 或 AntD 默认 focus ring，必须可见。
- **Validation:** 错误信息紧邻字段；多错误提交后焦点回到第一个错误字段。
- **Long Text:** 多行文本用 `TextArea` + `showCount` + `maxLength`。资源名、路径、命令要支持换行、横向滚动或 tooltip。
- **Switches:** 开关只表示独立偏好（如聊天历史、展示思考）。集合「有没有成员」用添加/删除表达，不要再套一层启用总开关。

### Studio Workbench（设置双栏）

配置 + 实时预览（如智能体设置）走同一套工作台，不要做成左右两堆互不相干的卡片墙。参考：`web/src/app/opspilot/(pages)/skill/detail/settings/page.tsx`。

- **两栏：** 仅适用于配置 + 实时预览这类设置工作台。各一块白底面板（`rounded-lg` + `1px` 边框），`h-full min-h-0` 内部滚动。禁止用 `calc(100vh - Npx)` 估高度。
- **树 + 表格页（如组织架构）：** 沿用 `PageLayout` 分层：标题条与内容区各一块白底圆角，**不加 1px 描边**；左右用背景和留白分开。不要套 Studio 设置双栏的线框。
- **嵌套侧栏：** 「左右各一块描边面板」不要用在树 + 表格页。内容已经套在 `SideMenu` 里时（应用管理的角色 / 数据权限 / 自定义菜单），内容区只铺 **一块** 白底圆角，**不加 1px 描边**；栏内主从用 `border-r` 和留白分割，不要再 `gap` 出第二套白卡，避免页面底色从缝里露出来（卡套卡）。
- **栏头：** `fill-1/60` 浅底 + 小图标 + 标题；右侧轻量徽章（ID、模型名），不要再套卡。
- **章节：** 短竖条 + `13px semibold` 标题；章节之间 `border-t` + 较大 `pt`。表单横向标签、统一标签宽。
- **设置行：** 开关做成「一行一项」`divide-y`，不要每个开关一张小卡。
- **已选项：** 见上方「已选对象小卡」。添加按钮在标题行右上，与「添加技能包」对齐，不要单独再占一行。
- **底栏：** 栏内 sticky：左一句说明，右 AntD `primary`「保存」，圆角 `6px`。
- **加载：** 用 `OpsPilotStudioWorkbenchSkeleton`，左右栏、栏头、表单行、已选小卡、发送框占位与最终布局同构。禁止用居中 `Spin` 替换整页。

### Detail / Overview Workbench（详情页与概览页）

对象详情（会话、错误、告警、作业、实例）和应用概览（KPI + 趋势 + 分布 + 近期列表）走同一套骨架：**顶部 KPI 指标格 → 主区（左宽右窄）卡片分区 → 右栏属性面板**。它是 Entity List Cards / Studio Workbench 的姊妹页型，用同一套 Look B 卡片语言；新 app 做详情/概览时按本节执行，不要再发明第二套详情皮肤。

**参考实现（RUM，app-local）：**

| 能力 | 路径 |
| --- | --- |
| KPI 指标卡 / 指标格 | `web/src/app/rum/components/rum-metric-card.tsx`（`RumMetricCard` / `RumMetricGrid`） |
| 详情页（双栏 + 时间线 + 属性面板） | `web/src/app/rum/sessions/[sessionId]/page.tsx`、`web/src/app/rum/errors/detail/page.tsx` |
| 概览页（趋势 + 分布卡 + 近期列表） | `web/src/app/rum/applications/[name]/overview/page.tsx` |
| 同构骨架 | `web/src/app/rum/components/rum-skeleton.tsx`（`RumSessionDetailSkeleton` / `RumErrorDetailSkeleton` / `RumOverviewSkeleton`） |
| 图标小动作 | `web/src/app/rum/components/rum-icon-action.tsx` |

第二个真实 app 接入后再按 `COMPONENT_GOVERNANCE.md` 升 shared 并补 Storybook；升 shared 前禁止在别的 app 复制平行实现。

#### 页面骨架

```
[← 返回] 对象名  [类型 tag] [状态 badge]                      [主操作 primary]
副标题：所属 / 落地 / 时间

[KPI] [KPI] [KPI] [KPI]                         ← RumMetricGrid，2–6 格

┌ 主区卡片（flex-1）─────────────┐  ┌ 右栏（lg:w-[320px]）┐
│ 栏头：图标 标题 (计数)  [操作]  │  │ 栏头：标题   [状态] │
│ 正文：时间线 / 表格 / 堆栈      │  │ 属性行 · 属性行 …   │
└────────────────────────────────┘  └─────────────────────┘
```

- **主区 / 右栏：** `flex min-w-0 flex-col items-start gap-4 lg:flex-row`；主区 `flex-1 min-w-0`，右栏 `w-full shrink-0 lg:w-[320px]`（最宽 `xl:w-[340px]`）。窄屏自动堆叠，不写 `calc(100vh - N)`。
- **卡片间距：** 同栏卡片 `gap-4`；顶部 KPI 到主区 `gap-4`。
- **返回：** 页头左侧 `ArrowLeft` 图标按钮回到列表，不做面包屑双份。

#### 卡片容器与栏头（所有分区统一）

```tsx
<section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
    <div className="flex items-center gap-2">
      <CodeOutlined className="text-sm text-[var(--color-primary)]" />
      <h2 className="m-0 text-[13px] font-semibold text-[var(--color-text-1)]">堆栈追踪</h2>
      <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-1.5 text-xs font-semibold tabular-nums text-[var(--color-primary)]">12</span>
    </div>
    <Button size="small">复制堆栈</Button>
  </div>
  {/* 正文 */}
</section>
```

- **容器：** `rounded-lg` + `1px border-1` + 微阴影 `0_1px_3px_rgba(0,0,0,0.03)`；`overflow-hidden` 让栏头浅底贴边。
- **栏头：** `fill-1/35` 浅底 + `border-b border-1` + `px-4 py-2.5`。左：语义图标（`text-sm`，主色或该卡主题色）+ `13px semibold` 标题 + 可选计数胶囊；右：该卡的操作（Segmented、复制、查看全部、状态点）。**栏头不加短竖条**（见 Cards / Containers）。
- **正文内边距：** 属性行 `p-3`；图表/表格 `p-3.5`；表格类正文可 `p-0` 直接贴表。
- **一卡一职：** 每张卡只承载一种内容（时间线 / 堆栈 / 趋势 / 属性 / 近期列表）。卡内禁止再套卡；需要分组用浅底条目行或 `border-t`。

#### KPI 指标卡（Look B 超微弱光感容器）

- **容器：** 与分区卡同边框、同微阴影，`rounded-lg border border-[var(--color-border-1)] p-3 sm:px-3.5 sm:py-3 shadow-[0_1px_3px_rgba(0,0,0,0.03)]`。
- **底色：** 极弱水洗微光（浓度严格控制在 `1.5%`，高度收缩在顶部 `32%`），有状态时色相与数值呼应，常规卡片统一透淡蓝光，整排均有底光，绝不留局部纯白：
  - 常规 / 默认态：`linear-gradient(180deg, color-mix(in srgb, var(--color-primary) 1.5%, var(--color-bg)) 0%, var(--color-bg) 32%)`
  - 警告 / 危险 / 成功态：色相换为对应 token（`--color-warning` / `--color-fail` / `--color-success`），浓度保持极其轻薄的 `1.5%`，仅产生柔和氛围微光，绝不形成深色色斑。
  - 悬停态（可点击时）：浓度微提至 `3%`。
  - 解决痛点：既避免了“大红字大黄字顶上却透蓝光”的色彩拧巴，又通过极浅浓度（1.5%）和全员有光保证了整排卡片通透统一，彻底消除“红绿灯拼布感”。
- **语义状态：** 主体依然由数值本身的文字颜色（`font-bold font-mono` 配 `var(--color-fail)`、`var(--color-success)`、`var(--color-warning)` 等）清晰传达。
- **排版：** 上 label（`text-xs font-medium text-3`，保持纯文字，不加多余状态圆点），下数值 `font-mono tracking-tight tabular-nums`：短数值 `text-xl sm:text-2xl font-bold`；超过约 8 字符（带单位、时间戳、长字串）降到 `text-sm sm:text-base font-medium`，保持同排等高不折行。
- **可点击：** 作为筛选/钻取入口时必须是 `button`，`group cursor-pointer hover:border-[var(--color-primary)] hover:shadow-sm`，label `group-hover:text-[var(--color-primary)]`，并有 `focus-visible` outline。不可点的指标卡 `cursor-default`。
- **格数：** ≤3 格 `grid-cols-3`；4 格 `grid-cols-2 sm:grid-cols-4`；更多 `grid-cols-2 sm:grid-cols-3 lg:grid-cols-6`；间距 `gap-3`。

#### 属性面板（右栏 key-value）

- **条目化，不划线：** 每条属性一个浅底条目 `flex items-center justify-between rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2 transition-colors hover:bg-[var(--color-fill-1)]/60`，条目间 `space-y-2`，外层 `p-3 text-xs`。**不要**用 `divide-y` 把一排属性切成满屏实线。
- **左 key：** `text-[11px] font-medium text-3`，可带 `text-3` 小图标；**右 value：** `font-medium text-1`；代码类值（版本、指纹、UA）用 `font-mono text-xs font-semibold`，超长值 `truncate max-w-[170px]` + `title` / tooltip，旁边放复制小按钮。
- **空值：** 统一 `—`，不显示 `undefined` / `null` / 空字符串。

#### 计数胶囊（标题旁数字）

- **只放纯数字：** 紧跟标题或标签的计数胶囊显示 `24`，不拼「会话」「个」「条」等量词——上下文已由标题给出。需要单位时放正文里，不放胶囊。
- **必须有底色：** `h-5 min-w-[20px] rounded-full px-1.5 text-xs font-semibold tabular-nums`；主色胶囊用 `bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] text-[var(--color-primary)]`。禁止裸灰字悬空，禁止饱和实心色块。
- **主题分布卡：** 同页多张并列分布卡（国家 / 设备 / 环境 / 版本）可各取一色区分（图标 + 进度条 + 计数胶囊三处同色，`<hue>-500/10` 底 + `<hue>-600` 字），但每张卡**只用这一处彩色**，不再给栏头加彩色竖条或彩色边框。
- **零值不显示胶囊。** 设置页集合计数仍按 Colors 节的 count token，不与本条混用。

#### 可点击反馈（The Visible Affordance Rule）

- **表格行可钻取：** `onRow` 必须给 `cursor-pointer transition-colors hover:bg-[var(--color-fill-2)]`；主入口列（名称、ID、消息）默认 `text-1` 常规字重，hover `text-[var(--color-primary)] underline`。不要靠「整行变色」以外的猜测让用户发现能点。
- **卡片可钻取：** 与 KPI 可点击规则一致（边框变主色 + 微阴影 + label 变主色）。
- **图标小动作：** 幽灵图标按钮 hover 要有底色或下划线反馈，配 `aria-label`。
- **静态元素不许伪装：** 不能点的卡片、数字、标签不加 hover 变色，避免「看着能点其实不能」。

#### 去线（De-line）

- 时间线竖轴、图表网格虚线、次级分割线统一降到 `/60` 不透明度（如 `before:bg-[var(--color-border-2)]/60`、`border-dashed border-[var(--color-border-2)]/60`）。
- 卡片内部只保留栏头一条 `border-b`；正文分组靠浅底条目和 `space-y`，不再叠 `divide-y`。
- 全局 `Watermark` 走浅色低密度（透明度 ≤ 0.06、间距 ≥ 160px），不许为了单页把水印调深。

#### Named Rules

**The One Detail Shell Rule.** 同一产品面的详情/概览页只保留一套「KPI 格 + 分区卡 + 属性面板」骨架；新模块复用或升 shared，不平行发明第二套详情皮肤。

**The Card Header Without Accent Rule.** 独立卡片的栏头靠「浅底 + 图标 + 13px 标题 + 容器边框」表达层级，不加短竖条；竖条只留给同一面板内的子章节。

**The Bare Number Badge Rule.** 标题旁计数胶囊只放纯数字，必须有柔和底色；量词进正文，不进胶囊。

**The Unified Metric Wash Rule.** 指标卡微渐变必须严格克制在 1.5% 超浅浓度与顶部 32% 范围；微光色相与数值呼应，常规卡片统一透淡蓝光，整排均有底光，绝不留局部纯白。

### Loading / Skeleton

页面加载是界面的一部分，不是临时转圈。骨架必须 **复刻即将出现的结构**（栏数、栏头、字段行、卡片网格、底栏），占位条圆角跟最终控件一致（按钮/chip `6px`，卡片 `8px`）。

| 页面类型 | 骨架 | 不要 |
| --- | --- | --- |
| 实体网格列表 | `CardGridSkeleton`（与 Look B 卡同解剖） | `Spin` 罩住旧卡或空白网格 |
| 设置双栏 / Studio | `OpsPilotStudioWorkbenchSkeleton`（左右面板同构） | 整页居中 `Spin` |
| 详情页 / 概览页 | `RumSessionDetailSkeleton` / `RumErrorDetailSkeleton` / `RumOverviewSkeleton`（KPI 格 + 分区卡栏头 + 属性行同构） | 只留 KPI 转圈、主区空白 |
| 表格 | 表头保留，行用 Skeleton；或表格 `loading` 配骨架行 | 整表消失只剩转圈 |
| 分页加载更多 | 底部小 `Spin` | 再刷一整页骨架 |

参考实现：

| 能力 | 路径 |
| --- | --- |
| 列表卡骨架 | `web/src/components/card-grid-skeleton` |
| 设置双栏骨架 | `web/src/app/opspilot/components/opspilot-studio-workbench-skeleton` |
| 详情 / 概览骨架 | `web/src/app/rum/components/rum-skeleton.tsx` |

**The Layout-Isomorphic Skeleton Rule.** 骨架与最终布局同构：同样的分栏、同样的 header/footer 槽位、同样的内容节奏。失败时不要假骨架假装有数据；保存等局部提交只用按钮 `loading`。

### Tables
- **Density:** 表格可以高密度，但列头、操作列和筛选条件必须清晰。
- **Cells:** 主行 Body `14px` / 常规 / `text-1`；双行时副行 Label `12px` / `text-3`。禁止把 Title `16px` 或标题级 `semibold` 放进单元格。空值用 `text-3` 常规字重，不要做成标题。时间与数字列 `tabular-nums`。
- **Actions:** 操作列固定右侧，行内按钮保持 `link small`，不要混用大按钮。
- **Overflow:** 长文本用 `EllipsisWithTooltip`（**仅溢出时**出 tooltip），不要没超出也包一层常驻 Tooltip，也不要只用原生 `title`。
- **States:** loading 用 Skeleton，empty 用 `Empty` + 简短说明 + 下一步动作，error 用错误提示 + retry。
- **Pagination:** 默认 20 条，提供 10 / 20 / 50 / 100，显示总数。

### Navigation
- **Top Menu:** 顶栏背景跟随主题，active 使用 `var(--color-primary)` 或 active 背景。图标使用统一图标库，不手绘临时 SVG。应用顶栏（app-top）列出全部应用，空间不够时在顶栏内左右滚动，溢出侧只用小箭头提示，不要「详情 / 更多」文字。
- **Side Menu:** 侧栏默认 `var(--color-components-side-nav-bg)`，hover 用 `var(--color-components-side-nav-hover-bg)`，active 用 `var(--color-components-side-nav-text-active-bg)`。app-top 左栏 200px，可从底部图标按钮收起为 56px 纯图标栏；收起后移入只是浮出完整导航（不挤内容），点展开才真正占位。
- **Segmented:** 二级视图切换优先用 AntD Segmented 或项目 `sub-layout` 约定，保持 `gap-2` 节奏。

### Modals / Drawers
- **Header:** 弹窗头部使用 `var(--color-modal-header-color)`，标题 `16px / 600`。
- **Footer:** 按钮组统一 `flex justify-end gap-2`，不要给单个按钮加 `mr-*` / `ml-*`。
- **Confirmation:** 删除、重置、权限变更、凭据暴露等风险操作必须说明后果。
- **Viewport Fit（禁止触底）:** 弹窗必须自适应视口高度，任意屏幕下都不能触底（底部按钮被截断或贴住视口底边）。表单较长时给 `Modal` 主体限高并内部滚动：`styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }}`，保证底部按钮始终可见且与视口底部留有间距；若内容仍然过长、滚动割裂，改用 `Drawer`（抽屉）承载长表单。

### Chat / AI Output

对话是同一块白底工作面：问候、消息、输入是一条流，不要三块各带灰底的岛。参考：`web/src/app/opspilot/components/custom-chat-sse`。

- **引导语：** 当作第一条助手消息，不要外框卡。
- **快捷问答：** 圆角 `6px`（同保存按钮），底 `fill-1/70`（同已选技能包小卡）。不要胶囊大圆角、不要深灰、不要描边阴影。
- **用户问题：** 右对齐气泡，底 `fill-1/70`，尾巴圆角保留。单行上下 padding 约 `8px`，markdown 首尾 `p` 无外边距，不要被段落 margin 撑成方块。不要饱和的 `primary-bg-active`。
- **助手回复：** 左对齐纯文本，不要气泡壳。
- **消息操作：** 回复下方是无框幽灵图标行（复制优先，成功变勾约 1.6s），不要描边/灰底胶囊工具条，也不要在「更多」里重复复制和重新生成。图标与相对时间同为 `11px`，用 `text-4` 时间跟在后面。用户和助手都是悬停（或键盘聚焦）才出现，不要常驻。
- **思考 / 执行计划 / 工具：** 一行可折叠过程态（如 `▶ 已完成思考`、`▶ 执行计划 (已完成 n 步)`）。展开用 `fill-3` 的 `2px` 引用线，不是品牌色谱边，也不是灰底大卡。流式中默认展开，结束后可收起。过程态是旁白，回复才是主体。
- **发送框：** 白底 + `1px` `border-1`；聚焦才品牌描边 + ring。禁止灰底、禁止为「看起来像组件」而加阴影。
- **Reports:** 报告卡保持轻量正式，不做深色大屏化，不做渐变标题。
- **Commands:** 命令块必须可复制，复制失败有反馈，空命令有空状态。
- **Choices:** 用户选择必须使用真实 `button` / 表单控件，支持键盘、disabled、loading、已选择态。
- **Streaming:** 流式内容默认可见，不依赖动画 class 才显示。

## 7. Storybook 与完成标准

- shared component 的新增、API 变化、视觉变化必须同步 Storybook；Storybook 是组件契约中心，不是 shared 所有权证据。
- app-local 组件在交互复杂、状态较多或需要横向对比时也应进入对应 family story，但仍保留 app-local 所有权。
- 每个标准组件至少验证默认、loading、empty/error（适用时）、disabled/readonly（适用时）、长文本和窄容器。
- 所有视觉组件必须在 Storybook 或真实页面中分别检查亮色与暗色；不能只看默认主题截图。
- UI 改造交付时必须说明：复用了哪个组件、为何没有新建 shared；若新增 app-local，说明所属 app；若修改 shared，列出受影响 app 和 Storybook 更新。

## 8. Do's and Don'ts

### Do:
- **Do** 优先使用 `var(--color-…)`、Ant Design token 和 `web/src/components` 通用组件。
- **Do** 布局与间距优先用 Tailwind `className`（见 Layout & Styling），颜色走语义 token。
- **Do** 先查当前框架组件和已有业务组件，再写新组件；能组合就组合，不能组合才抽象。
- **Do** 新增业务组件默认放在 `src/app/<app>/components`，以真实跨 app 消费证明 shared 资格。
- **Do** 在亮色和暗色下验证所有新增或修改的视觉状态。
- **Do** 用 `gap-2` / `gap-3` 管理按钮组和标签组间距，不把 margin 散落到子按钮。
- **Do** 为表格数字列加 `font-variant-numeric: tabular-nums` 或等价 `tabular-nums` class。
- **Do** 为图标按钮提供 `aria-label`，为可展开区域提供 `aria-expanded` / `aria-controls`。
- **Do** 给 loading、empty、error、permission denied、readonly 状态写清楚下一步。
- **Do** 让中文、英文、长资源名、命令、路径、emoji 都能安全换行或省略。
- **Do** 保持浅色、克制的企业控制台：干净、扁平、少框、留白分层；让操作更清楚，而不是让界面更热闹。
- **Do** 页眉按「页眉两档」：最外层卡片网格用 `ListPageHeader`；其余说明单独成条，内容区操作成组靠右（`gap-2`，到内容 `mb-4`）。优先 `ListPageHeader` / `SearchActionBar` / `ToolbarSplitShell`。
- **Do** 设置双栏、已选对象小卡、对话过程态对齐 Studio Workbench 与 Chat 节；其他 app 靠这套，不要平行发明皮肤。
- **Do** 首次加载与整页刷新用与最终布局同构的骨架屏（列表卡网格 / 设置双栏 / 详情 KPI+分区卡）；局部提交用按钮 `loading`。
- **Do** 详情/概览页统一「KPI 指标格 → 主区分区卡 → 右栏属性面板」；分区卡栏头 = `fill-1/35` 浅底 + 语义图标 + `13px semibold` 标题 + 可选计数胶囊，右侧放该卡操作。见 Detail / Overview Workbench。
- **Do** 标题旁计数胶囊只放纯数字（`24`）并带 10–12% 柔和底色；属性面板用浅底条目行（`fill-1/35`，hover `/60`）代替 `divide-y`。
- **Do** 凡是能点的表格行、卡片、主入口文字、图标动作，都给明确 hover 反馈（行底 `fill-2` / 边框主色 / 文字主色 + 下划线）。
- **Do** 治理/功能改动触及的布局区块，把可替换的行内 flex/间距改为 `className`。

### Don't:
- **Don't** 做「科技风」大屏：深色、霓虹、发光、巨大指标，除非该路由明确是监控展示大屏。
- **Don't** 做营销感 SaaS 官网风：大 hero、巨大指标卡、渐变大标题、宣传话术都不属于控制台默认界面。
- **Don't** 给每个小组再套线框，或在对话里把问候 / 过程态 / 输入做成三块互不相干的灰底岛。
- **Don't** 给可输入区域加灰底或厚阴影（会像禁用）。灰底只给只读弱容器。
- **Don't** 给「已选技能/工具」再套启用总开关；有选中即开，空列表即关。
- **Don't** 把思考、工具执行、执行计划做成独立线框卡；用一行可折叠过程态。
- **Don't** 给快捷问答、普通按钮使用胶囊大圆角；与保存按钮一样用 `6px`。数量胶囊除外。
- **Don't** 用主色蓝给设置页集合计数上色，也不要把数量做成无底色灰字。技能包 / 工具各用一套 count token，不要全页一种计数色；不要改列表卡底栏 `+N`。
- **Don't** 使用卡片通高彩色 `border-left` / `border-right` 大于 `1px`。章节标题短竖条、对话引用线见 Cards / Chat 节。
- **Don't** 在已经有独立边框和栏头的卡片上再加短竖条；竖条只留给同一面板内的子章节。
- **Don't** 在计数胶囊里拼「会话」「个」「条」等量词，也不要把计数做成无底色裸灰字或饱和实心色块。
- **Don't** 用 `divide-y` 把详情页属性面板切成满屏实线；用浅底条目行 + `space-y-2`。
- **Don't** 指标卡渐变过深（超过 2%）或范围过大（超过 35%），也不要留下部分卡片没有微光呈现死白；保持 1.5% 超浅光感。
- **Don't** 让能钻取的表格行 / 卡片 / 主入口文字没有 hover 反馈，也不要给不能点的元素加 hover 变色伪装成可点。
- **Don't** 使用 gradient text、装饰性玻璃拟态、重复卡片网格、手绘 sketch SVG、条纹背景。
- **Don't** 为了视觉新鲜感重写 Ant Design 已有的 Button、Modal、Drawer、Table、Form、Select、Tabs、Segmented、Tooltip、Popover。
- **Don't** 在组件内直写品牌色或状态色 hex；需要时加 token 或语义映射。
- **Don't** 用 `bg-white`、`text-black`、固定浅灰边框等只适用于单一主题的样式代替语义 token。
- **Don't** 新增大段行内布局对象（`style={{ display:'flex', gap, padding, width... }}`）替代 Tailwind/`className`。
- **Don't** 复制已有组件只为改变颜色、圆角、边框或间距；优先复用现有 variant 或补一个稳定 variant。
- **Don't** 把搜索甩到最左、新建甩到最右，中间拉一条空白。搜索和主操作必须成组。
- **Don't** 为了统一卡片壳而改文案、替换展示字段、发明状态/时间、或抹平有含义的 tag 颜色；这些要改必须先讨论并确认。
- **Don't** 为实体列表另起一套卡片壳或用 Spin 罩住旧卡冒充刷新；没有时间字段时不要为展示去改后端加列。
- **Don't** 在文字没有溢出时给标题或单元格加常驻 Tooltip；省略场景用 `EllipsisWithTooltip`，只在真正截断时出现。
- **Don't** 用居中 `Spin` 代替整页加载。骨架必须与最终分栏、栏头、底栏同构；失败时不要假骨架假装有数据。
- **Don't** 用 placeholder 当 label，不要只靠 toast 汇总表单错误。
- **Don't** 把 `div onClick` 当按钮。可点击就用 `button`、AntD Button、链接或正确 ARIA 语义。
- **Don't** 给卡片、输入框、面板使用 `32px+` 大圆角。
- **Don't** 在卡片上叠加 `1px border` 和大模糊阴影。
- **Don't** 在新代码里继续扩大 `z-index: 9999/10000`、硬编码主题色 / 不必要的固定 `min-width`、全局覆盖 AntD 样式。
- **Don't** 让页面或容器出现非预期的横向滚动条（`overflow-x`）。布局必须自适应宽度：表格列宽随容器自适应（不要用固定宽度或强制 `scroll.x` 把内容撑出容器），长文本用换行 / 省略 / tooltip。横向滚动只允许出现在明确需要的局部（命令块、日志、超宽代码），不允许出现在整页或弹窗。
- **Don't** 让弹窗触底。长表单弹窗必须限高 + 主体内部滚动；实在过长、滚动割裂就改用抽屉（见 Modals / Drawers 的 Viewport Fit）。
