# 运营分析、告警、CMDB 交互统一设计

日期：2026-07-15
范围：`web/src/app/ops-analysis`、`web/src/app/alarm`、`web/src/app/cmdb`

## 背景

运营分析、告警、CMDB 都是 BK-Lite Web 控制台里的高频运维模块，但页面形态差异很大：

- 运营分析包含 settings 管理页、dashboard/topology/screen/architecture 等画布页，以及统一筛选和 widget 配置。
- 告警包含告警处理台、事件处理台、接入集成页、规则配置页、全局配置和详情页。
- CMDB 包含资产搜索、资产数据左树右表、模型管理、自动发现、采集任务、订阅、关系拓扑、机柜/机房和 K8s 资源视图。

本次目标不是把三个模块改成同一种外观，而是统一交互语义和布局安全边界：说明文案、工具栏、筛选、表格、表单、弹窗/抽屉、空/错/加载态、长文本、英文切换、宽高自适应和特殊页面例外规则。

## 目标

- 全量覆盖三模块页面，按页面类型处理，而不是只处理用户点名的头部说明卡片。
- 统一普通解释说明的展示方式，字段、按钮、表格列、图标解释优先使用 Tooltip。
- 保留特殊页面场景，不为了统一而破坏资产搜索、宽表、画布、大屏、拓扑、3D 等页面的领域体验。
- 消除明显的宽度、高度、内容增长、英文长文案、缩放和父子 overflow 风险。
- 抽出薄的共享组件和工具，减少各模块重复手写页面壳、工具栏、表格滚动和表单弹窗规则。
- 建立可验证的验收矩阵，避免只凭主观观感判断“已统一”。

## 非目标

- 不重做三模块信息架构和业务流程。
- 不把所有页面强制改成同一种 Card 或同一种 header。
- 不一次性重构复杂业务逻辑，例如告警派发规则、CMDB 采集任务流程、运营分析画布数据流。
- 不扩大到 monitor、log、job、opspilot 等模块。
- 不把必须显式展示的风险提示藏进 Tooltip。
- 不以全仓格式化、全仓颜色替换或机械迁移为目标。

## 当前基线

新 worktree：`/Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification`
分支：`codex/ui-interaction-unification`

前端依赖已安装。三模块基线类型检查命令：

```bash
cd web && NEXTAPI_INSTALL_APP=ops-analysis,alarm,cmdb pnpm type-check
```

当前失败原因属于既有基线问题，主要包括：

- 缺少或无法解析三模块实际引用的依赖/类型：`react-activation`、`@dnd-kit/*`、`@antv/xflow`、`zustand`、`gridstack`、`three`、`@isoflow/*` 等。
- 告警模块存在少量既有 TypeScript 错误：`relatedAlertsPanel` 类型转换、`alarm/api/incidents.ts` 中 `del` 未定义等。

后续实现验证需要先处理依赖基线，或至少用专项脚本和页面级检查隔离本次改造影响。

## 页面分类

### 标准管理页

适用：

- `ops-analysis/(pages)/settings/*`
- `alarm/(pages)/settings/*`
- `cmdb/(pages)/assetManage/management/*`
- `cmdb/(pages)/assetManage/operationLog/*`
- `cmdb/(pages)/assetManage/customReporting/*`
- `cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/*`

统一点：

- 页面说明统一由 `PageIntro` 承载。
- 查询、刷新、添加、导入、导出、更多操作统一放入 `ResponsiveActionBar`。
- 表格外层统一由管理页壳控制高度，不在每个页面散落 `calc(100vh - xxxpx)`。
- 操作列统一右侧固定、link small、危险操作 danger + 二次确认。
- 空状态、加载态、错误态使用统一组件和文案结构。

保留点：

- 模型管理的卡片式模型分组可以保留。
- 自动发现和采集任务的流程式页面可以保留自己的步骤结构。
- 公共枚举库、模型导入导出等复杂弹窗保留业务布局，但接入统一 Modal/Drawer 尺寸规则。

### 工作台页

适用：

- 告警列表、事件列表。
- CMDB 资产数据左树右表。
- 运营分析 view 的资源选择 + 画布页。

统一点：

- 主体必须是 flex/grid 自适应，不用整页固定最小宽撑开。
- 左侧筛选/树宽度可以固定，但右侧内容必须 `min-width: 0`。
- 工具栏长按钮在英文下可换行、折叠到更多菜单，或转为图标 + Tooltip。
- 表格、图表、画布只在局部滚动，不允许整页非预期横向滚动。

保留点：

- 告警的左侧筛选台、分布图和告警表格布局保留。
- CMDB 资产数据的左树、组织选择、筛选标签和宽表保留。
- 运营分析画布的资源侧栏、Toolbar、FilterBar、Canvas 保留。

### 特殊体验页

适用：

- CMDB 资产搜索首页。
- CMDB 关系拓扑、网络拓扑、K8s 资源图、机房/机柜类视图。
- 运营分析 screen、topology、architecture、Room3D、网络拓扑类能力。

统一点：

- 使用 token 或语义常量控制颜色，不把特殊页硬编码视觉扩散到普通管理页。
- 长标题、长资源名、长标签、英文按钮必须有省略、换行或 Tooltip。
- 画布/3D/拓扑容器在尺寸变化后必须能 resize 或重新布局。
- 浮层、详情面板、工具栏不能在缩放后遮挡关键内容。

保留点：

- 资产搜索首页可以保留更强的搜索入口视觉。
- 大屏和 3D 可以保留专属 chrome 和展示感。
- 拓扑类页面可以保留画布交互，不改成普通表格/卡片页。

## 共享组件设计

### PageIntro

替代 alarm/cmdb 重复的 `Introduction`，并对齐运营分析头部说明。

职责：

- 页面级标题和短说明。
- 可选右侧辅助操作。
- 可选轻量统计，但默认不做大卡片堆叠。
- 自适应宽度，禁止 `minWidth: 800px` 之类会撑出整页的写法。
- 说明文案过长时最多两行，完整内容用 Tooltip。

非职责：

- 不承载流程风险、错误、空状态。
- 不承载表单字段解释。
- 不承载复杂 markdown 文档。

### ResponsiveActionBar

用于管理页和工作台顶部操作区。

职责：

- 左侧放搜索、筛选、组织选择、时间选择等查询控件。
- 右侧放刷新、导入导出、新增、批量、更多等操作。
- 支持英文长按钮下自动换行或折叠到 More。
- 支持图标按钮统一 Tooltip。
- 支持测量宽度后折叠，复用 CMDB 资产数据页已有的 ResizeObserver 思路。

规则：

- 主操作最多一个 primary。
- 常规批量操作可进入 More。
- 高危操作不和普通操作混在一个视觉层级。
- 按钮文本不能靠固定宽度硬截断；需要截断时提供 Tooltip。

### ManagementPageShell

用于标准管理页。

职责：

- 管理 PageIntro、ActionBar、内容区、表格区的垂直布局。
- 通过 flex 自适应控制高度，减少 `calc(100vh - xxxpx)`。
- 页面内容区 `min-height: 0`，表格/列表内部滚动。
- 统一 padding、背景、边框和圆角。

规则：

- 页面整体不出现非预期横向滚动。
- 内容增长时优先内部滚动，不被父级 `overflow: hidden` 吃掉。
- 当页面嵌入侧栏/资源树时，右侧内容必须设置 `min-width: 0`。

### SafeText / TextWithTooltip

用于资源名、路径、标签、表格单元格、说明短句。

策略：

- 默认单行省略 + Tooltip。
- 说明短句允许两行 line clamp + Tooltip。
- 路径、命令、SQL、日志允许局部横向滚动或等宽展示。
- 表格数字列使用 tabular nums。
- Tag/Badge 内长文本需最大宽度和 Tooltip，不撑破工具栏。

### ModalBodyScroll / DrawerFormLayout

用于复杂表单和详情抽屉。

职责：

- Modal body 限高并内部滚动，footer 永远可见。
- 长表单优先 Drawer，而不是触底 Modal。
- Form.Item label、extra、help、error 展开后不遮挡下一项。
- Form.List 行内结构在英文和错误提示下可换行。

规则：

- 短表单用 Modal。
- 长表单、多步骤、左右分栏、动态列表用 Drawer。
- 删除、重置、凭据、规则生效范围等风险必须在 Modal content 或 Alert 中明示。

### tableScroll 工具

目标是减少每个页面手写 `scroll={{ y: 'calc(100vh - 430px)' }}`。

策略：

- 标准管理页优先让 Shell 提供可用高度，表格 `scroll.y` 使用容器高度。
- 宽表允许局部横向滚动，但不能让整页横滚。
- 详情页表格、抽屉表格、弹窗表格单独传入上下文。

## 说明文案规范

普通说明文案尽量统一为 Tooltip，但必须区分信息重要性。

### Tooltip 优先

适用：

- 字段含义。
- 按钮含义。
- 图标含义。
- 表格列说明。
- 状态标签说明。
- 截断文本完整内容。
- 非关键的补充解释。

形态：

- 图标统一为问号/说明图标，或图标按钮直接用 Tooltip。
- 触发方式支持 hover 和 focus。
- Tooltip 文案短句化，不塞长段落。
- Tooltip 不承载必须阅读的风险、错误或操作后果。

### PageIntro

适用：

- 页面级一句话背景说明。
- 用户进入页面时需要知道的用途。

规则：

- 标题 + 短说明。
- 说明过长时两行截断 + Tooltip。
- 不再使用大块卡片式说明堆占首屏。

### Alert / Modal content

适用：

- 风险、不可逆操作、规则生效影响。
- 前置条件缺失。
- 配置失败、权限不足、连接异常。
- 用户必须先看到再操作的信息。

规则：

- 不用 Tooltip 藏风险。
- Alert 文案可包含下一步动作。
- Modal content 必须说明破坏性操作后果。

### Form help / extra

适用：

- 校验错误。
- 输入格式。
- 必填缺失。
- 字段级操作建议。

规则：

- 错误用 `Form.Item help`。
- 简短格式提示可用 extra。
- 复杂解释放字段 label 后 Tooltip。
- placeholder 不能替代 label。

### Empty / Error block

适用：

- 空数据。
- 无权限。
- 加载失败。
- 查询无结果。

规则：

- 空状态给下一步动作或搜索建议。
- 错误态给重试或排查入口。
- 不用 Tooltip 解释空状态原因。

## 适配风险规则

### 宽度不足

检查对象：

- `min-width`、固定 `width`、`w-[...]`。
- 表格 `scroll.x`。
- 不换行按钮组。
- Tabs、Radio.Group、Segmented、Tag 列表。
- 左树 + 右表、左筛选 + 右内容布局。

处理：

- 页面主区域 `min-width: 0`。
- 工具栏允许换行或折叠。
- 表格只在局部横向滚动。
- 英文按钮长文本可转入 More 或 Tooltip。

### 高度不足

检查对象：

- `height: calc(100vh - xxxpx)`。
- 固定卡片高度。
- 父级 `overflow: hidden`。
- Modal/Drawer body。
- 表格 `scroll.y`。
- 图表、画布、3D 容器。

处理：

- 管理页使用 flex 自适应。
- 需要滚动的区域显式 `min-height: 0`。
- Modal/Drawer body 内部滚动，footer 可见。
- 图表和画布监听容器 resize。

### 内容增长

检查对象：

- 多标签、多按钮、多筛选条件。
- Form.List 动态项。
- 表格操作列按钮增多。
- 英文 label、长资源名、路径、组织名。
- 错误提示展开。

处理：

- 多项内容使用 wrap、collapse、More。
- 动态表单从行内固定宽改为响应式栅格或纵向堆叠。
- 表格操作列超过两个主操作后进入 More。

### 缩放和容器变化

检查对象：

- 浏览器缩放。
- 左侧栏折叠。
- 全屏模式。
- 画布 resize。
- 大屏缩放。
- 抽屉打开后内容宽度变化。

处理：

- 画布类组件在容器变化后重新计算。
- 浮层和详情面板不依赖固定像素绝对位置遮挡主内容。
- 工具栏和筛选栏不覆盖画布关键区域。

### 中英文切换

检查对象：

- locale key 缺失。
- 英文长度超过中文 2.2 倍且总长超过 24 字符。
- 按钮、Tabs、Radio、Checkbox、Tag、表格列、Form label、Modal title。
- 说明文案、Tooltip、Alert。

处理：

- 修齐 zh/en locale key。
- 长 label 使用 Tooltip 或换行。
- 表格列可配置 ellipsis。
- 按钮组折叠。
- Tooltip 和 PageIntro 承载完整说明。

## 模块处理计划

### 运营分析

重点：

- settings 管理页接入 PageIntro、ManagementPageShell、ResponsiveActionBar。
- dataSource 表格、参数表、字段表、预览面板统一长文本和高度策略。
- UnifiedFilterBar 保留现有语义，补齐长 label、长 option、按钮换行/折叠策略。
- dashboard/topology/screen/architecture 工具栏统一 ToolbarButton、Tooltip、按钮选中态 token。
- ViewWorkspace 保留作为画布页基准，消除硬编码背景色。

谨慎点：

- screen、大屏、Room3D、architecture 有特殊展示语义，不按普通管理页改。
- 图表主题走 `chartTheme`，普通 UI 走 CSS token。

### 告警

重点：

- 替换重复 Introduction。
- 告警列表和事件列表的左侧筛选 + 右侧内容保留，但修正固定宽度、工具栏挤压和表格高度。
- settings 页统一管理页壳。
- 规则类 Modal/Drawer 统一 footer、body 限高、字段说明 Tooltip。
- 告警等级、状态、通知失败原因等说明统一 Tooltip/Alert 分类。

谨慎点：

- 告警处理台必须保持处理效率，不把高频操作藏得太深。
- 风险操作和状态变更不能藏进 Tooltip。

### CMDB

重点：

- 修复 zh/en locale key 不对齐问题，避免英文切换直接显示 key。
- 替换重复 Introduction。
- 资产数据页保留左树右表，但推广已有 ResizeObserver 折叠动作区模式。
- 资产搜索首页保留特殊入口视觉，但限制固定宽度、硬编码色和长文案风险。
- 模型管理、字段管理、订阅、采集任务、自动发现统一表单和工具栏适配规则。
- 关系拓扑、K8s 资源、机柜/机房类页面只做安全边界，不抹掉场景特征。

谨慎点：

- CMDB 是宽表和复杂表单最多的模块，优先保证不横滚、不截断、footer 可达。
- 模型字段、采集任务、订阅规则的帮助文案要 Tooltip 化，但错误和风险保持显式。

## 验收矩阵

### 静态检查

- 三模块无新增硬编码品牌色、语义色、圆角和阴影。
- 新增说明文案都有 zh/en。
- locale key 对齐。
- 新增组件无 `any`，不扩大既有类型债。
- 无全仓格式化。

### 页面检查

每类页面至少抽样：

- 标准管理页：ops-analysis 数据源、alarm actionRules/correlationRules/globalConfig、cmdb 模型管理/operationLog。
- 工作台页：alarm alarms/incidents、cmdb assetData、ops-analysis view。
- 复杂表单：alarm 规则 Modal、cmdb 模型字段/订阅/采集任务、ops-analysis 数据源/统一筛选配置。
- 特殊页：cmdb assetSearch、cmdb relationships/k8sResources、ops-analysis topology/screen/architecture。

尺寸：

- 1440px。
- 1280px。
- 1024px。
- 高度 720px。
- 浏览器缩放 125%。

语言：

- 中文。
- 英文。

断言：

- 无整页非预期横向滚动。
- 工具栏不挤压内容。
- 表格分页和最后一行可见。
- Modal/Drawer footer 可见。
- Tooltip 可访问完整截断内容。
- Alert/错误态不会被 Tooltip 替代。
- 长 label 和校验错误不遮挡表单项。
- 特殊页核心内容不被统一壳破坏。

### 自动化建议

- 增加 locale key 对齐脚本。
- 增加中英文长度风险扫描脚本。
- 增加固定宽高/overflow 风险扫描脚本。
- 为共享组件写轻量 TypeScript/tsx 行为脚本。
- 条件允许时用 Playwright 对核心页面做截图/横滚检查。

## 实施顺序

虽然用户要求全量页面一次性处理，实际提交仍应按小步提交或至少按小步实现：

1. 建立共享组件和工具，不迁移业务页面。
2. 迁移标准管理页。
3. 迁移工作台页。
4. 迁移复杂表单和抽屉。
5. 处理特殊页安全边界。
6. 补 locale key 和静态扫描脚本。
7. 跑专项验证和可运行的最小门禁。

## 风险

- 三模块基线 type-check 当前失败，可能掩盖改造引入的问题。
- 全量页面一次性处理 diff 会很大，需要严格按页面类型分批自测。
- 特殊页如果误套管理页壳，会破坏原本业务体验。
- Tooltip 过度使用会隐藏重要信息，因此必须保留 Alert/Form help/Empty/Error 的边界。
- CMDB locale 缺口较大，修复文案可能牵动大量页面。

## 决策

- 统一交互规则，不统一所有页面外观。
- 普通解释尽量 Tooltip 化，风险和状态不藏 Tooltip。
- 保留特殊页面体验，但要求满足 token、i18n、响应式、overflow 和 resize 安全边界。
- 优先抽薄组件和布局工具，不重写业务流程。
- 后续实现前必须先写实施计划，并明确每一步验证命令和页面抽样清单。

## 最终验证记录

已通过：

- `pnpm test:ui-i18n-keys`：ops-analysis 616、alarm 620、cmdb 1175 个 locale key 对齐。
- `pnpm test:ui-shell-components`：共享 PageIntro、SafeText、ResponsiveActionBar、ManagementPageShell、form-layout 的静态契约检查通过。
- `pnpm test:ui-text-risk`：扫描命令通过并输出风险排名；剩余命中集中在特殊页、画布、大屏、历史宽表和局部滚动容器。
- `NEXTAPI_INSTALL_APP=ops-analysis,alarm,cmdb pnpm type-check`：通过。
- 目标文件 `git diff --check`：通过。
- 浏览器 smoke：使用 Node 24 和 3002 端口启动 Next dev 后，Tailwind native binding 问题已消除，核心路由可编译；未登录和缺少 `NEXTAPI_URL` 的本地环境会跳转登录页或触发登录接口 500，因此未完成登录态业务数据页面的完整截图验收。

未通过但判定为基线问题：

- `pnpm lint` 被未触碰文件阻塞，包括 storybook 直接导入 `@storybook/react`、monitor/log/opspilot 的既有 lint、CMDB changeRecords 既有 unused/indent。全仓 lint 输出未指向本次触达文件。

## Residual Exceptions

- `/cmdb/assetSearch` 保留 hero 背景、卡片化入口和较多装饰色，因为该页是资产搜索入口，不应被改成普通管理页。剩余 overflow/risk 扫描命中主要来自 hero、局部滚动列表、表格 fixed layout；已移除会造成整页横向压力的固定 `min-width`。
- `/cmdb/assetData/detail/relationships/*` 保留拓扑、机房平面、机柜立面等场景化固定节点尺寸，因为这些尺寸属于画布/设备图形语义。剩余溢出应限制在画布或详情抽屉内部。
- `/cmdb/assetData/detail/k8sResources` 保留拓扑五列层级、节点尺寸和固定视口高度，因为它表达 K8s 资源层级。已让列表筛选工具条换行收缩，未改拓扑布局语义。
- `/ops-analysis/(pages)/view/screen/*` 保留 1920x1080 等大屏设计分辨率和按比例缩放 UI，因为这是大屏编辑器的核心语义。只加固外层收缩和命名空间选择器换行。
- `/ops-analysis/(pages)/view/topology/*` 保留 X6 画布、节点默认尺寸、力导向布局宽高和局部面板尺寸，因为它们影响拓扑图交互和布局稳定性。只加固外层 `min-w-0`。
- `/ops-analysis/(pages)/view/architecture/*` 保留架构画布和全屏行为，避免把画布页套成普通管理页。
- 未登录 `/auth/signin` 在 1024/760 viewport 下存在 1280 宽外层横向滚动；这是认证页基线，不属于本次三模块业务页面统一范围，但会影响未登录 smoke 对业务路由的观测。
