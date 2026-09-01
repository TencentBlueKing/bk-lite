# OpsPilot 列表卡统一 Look B

日期：2026-09-01  
状态：待用户审阅  
参照：`web/src/stories/design-compare/opspilot-after-system.tsx`（`UnifiedOpsCard`）、`opspilot-page-effects.tsx`（六模块列表示意）

## 1. 目标

把 OpsPilot **列表页实体卡**统一成 Storybook Look B 解剖，去掉渐变头图 / 悬浮大圆标。  
**只换视觉壳与信息落位，不删现有业务字段与交互。** Footer 文案跟 Storybook：**Owner + Team**。

## 2. 范围

### 2.1 纳入（列表卡）

| 模块 | 现网入口 | Storybook footer |
|------|----------|------------------|
| 工作台 | `studioCard` → `entity-card` | `entity`（Owner/Team；可 Pin） |
| 智能体 | `skillCard` → `entity-card` | `entity` |
| 知识库 | `WikiCard` → `entity-card` | `entity`（可无 online） |
| 工具 | `tool/page` → 通用 `EntityList` | 跟 Story：内置等可用 `none`；有组织信息则 `entity` |
| 记忆 | `memory/page` 内联 `MemoryCard` | `memory` / `entity`（Owner·Team；meta 可含范围） |
| 模型 | `vendorCardGrid` | `provider`（模型数 + 启用开关） |

「新增」入口：虚线空态卡，**不**套 B 卡头图，也不套渐变头。

### 2.2 不纳入

- 对话内卡片（审批 / Diff / 报告等 SSE 卡）
- 详情页内 Ant Design `Card` 表单区块
- 控制台壳层（应用顶栏）——独立变更，本设计不改

## 3. 统一解剖（Look B）

固定自上而下：

1. 左：模块图标（40 方底）+ 标题  
2. 状态行（可选）：状态 pill + 相对时间（有则展示，无则省略整行）  
3. 右上：Pin（模块需要时）+ `⋮` 菜单  
4. 简介：最多 2 行省略（字段本身保留，不截断 API 数据）  
5. meta tags（类型 / 模型名 / Chatflow 等；无则不占空行策略与 Story 一致）  
6. 底部分隔线 + footer（按模块变体）

视觉：白底、细边、轻阴影、圆角；语义色走 `var(--color-*)`，禁止新增大面积装饰渐变。

## 4. 字段映射（不减信息）

| 现网 / 数据 | B 卡落位 |
|-------------|----------|
| `name` | 标题 |
| `introduction` / `description` | 简介（展示 2 行） |
| `online` | 状态 pill（上线/下线；文案可 i18n，布局跟 B） |
| `bot_type` / `skill_type` / `modelName` / `llm_model_name` / tags | meta chips |
| `created_by` | Owner |
| `team_name`（数组 join） | Team（多团队 `+N` 与 Story 一致） |
| `is_pinned` | Pin |
| 编辑 / 删除菜单 + 权限 | `⋮` Dropdown，权限包装保留 |
| 点击进详情 / 打开 | 整卡 click，菜单区 `stopPropagation` |
| provider：`model_count`、`enabled` | footer=`provider` |
| memory：范围（个人/团队）、条数等 | meta 或 footer 右侧，不丢现网已展示量 |

现网「管理组织:」文案改为 Story 的 **Team**；组织取值仍来自 `team_name`。  
`created_by` 现网多数列表卡未展示 → 统一后 **补出 Owner**，属于信息增强，不是删减。

无 `updatedAt` 的接口：首期不造假时间；状态行仅有 online 时只显示 pill。

## 5. 实现方案（已选 A）

1. 将 Storybook `UnifiedOpsCard` **产品化**到 `web/src/app/opspilot/components/`（建议 `opspilot-unified-card` 或并入既有 `opspilot-cards`），用 Tailwind + 语义 token，去掉示意用 inline 主题常量（或薄封装对齐 `afterSys`→CSS 变量）。  
2. 改写/替换：
   - `entity-card`（及重复的 `opspilot-entity-card` 若仍被引用）：渲染统一卡，props 适配层保留现有调用方签名，避免六处页面大改。  
   - `vendorCardGrid`：同一壳 + `footer=provider`。  
   - `memory/page` 的 `MemoryCard`：同一壳。  
   - `tool` 列表：`operateSection` / 卡片自定义区切到统一卡。  
3. 模块薄包装（`studioCard` / `skillCard` / `WikiCard`）只负责字段→统一卡 props。  
4. Storybook：生产组件可被 design-compare 引用，或保留示意并注明「生产已对齐」；避免长期双实现漂移。  
5. 回归：Pin、编辑/删除权限、跳转 query、provider 开关、空列表与新增入口。

## 6. 非目标

- 不改列表筛选条 / 搜索 / 分页契约（除非为对齐 Story 的纯视觉微调且另开确认）  
- 不改后端 API、不补 `updatedAt` 字段（除非后续单独立项）  
- 不做全仓 OpsPilot 详情页视觉翻新

## 7. 验收

- 六模块列表卡解剖一致，无渐变头图。  
- Owner / Team（或 provider footer）可见；原有名称、简介、状态、类型/模型 tag、Pin、菜单不丢。  
- 交互与权限与改前一致。  
- 浅/深色下使用语义 token，无硬编码主题蓝紫渐变。

## 8. 与既有设计关系

`2026-08-03-opspilot-memory-card-layout-design.md` 曾要求记忆列表对齐当时渐变实体卡、且不改其他模块。  
**本设计在「列表卡视觉语言」上取代该文档**：记忆与其它五模块一并切到 Look B；记忆页头/网格密度等非卡片解剖约定可继续沿用 08-03 中仍适用的部分。

## 9. 决策记录

- 范围：全部 OpsPilot **列表**卡（非对话卡）  
- Footer：跟 Storybook — Owner + Team（选项 1）  
- 实现：方案 A — 产品化 `UnifiedOpsCard`，各入口复用
