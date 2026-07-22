# Refactor Tool Call Display

Status: done

## Migration Context

- Legacy source: `openspec/changes/refactor-tool-call-display/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

智能体详情页面的对话测试区域中，工具调用展示当前采用横排多个 Tag 的布局方式，信息密度低且无法直观查看工具的输入输出。用户需要点击才能看到结果，且展示格式不够清晰。需要改为单行卡片式布局，默认折叠，展开后显示 Input/Output 详情，提升可读性和操作效率。

## What Changes

- 将工具调用展示从横排 `inline-block` 布局改为垂直单行卡片布局
- 每个工具卡片默认折叠，仅显示工具名称和状态图标
- 点击卡片可展开，显示 Input（Command + Input Params）和 Output 区域
- Input 区域展示工具命令和 JSON 格式的输入参数
- Output 区域展示工具执行结果
- 移除原有的浮动面板（floating panel）交互，改为内嵌展开式

## Capabilities

### New Capabilities

- `tool-call-card`: 可折叠的工具调用卡片组件，支持展示 Input/Output 详情

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- **涉及文件**: `web/src/app/opspilot/components/custom-chat-sse/toolCallRenderer.tsx`
- **影响范围**: 所有使用 `renderToolCallCard` 和 `renderAllToolCalls` 的对话测试区域
- **API 变化**: 无后端 API 变化，纯前端 UI 重构
- **依赖**: 无新增依赖，使用现有的 React + Tailwind CSS

## Implementation Decisions

## Context

当前 `toolCallRenderer.tsx` 使用纯 HTML 字符串拼接方式渲染工具调用 Tag，采用 `inline-block` 布局实现横排展示。点击 Tag 会触发全局浮动面板显示工具详情（result）。

现有数据结构 `ToolCallInfo` 已包含所需字段：
- `name`: 工具名称
- `args`: 输入参数 (JSON string) → Input
- `status`: 调用状态
- `result`: 执行结果 → Output

## Goals / Non-Goals

**Goals:**
- 将工具展示改为垂直单行卡片布局
- 实现可折叠/展开交互，默认折叠
- 展开时显示 Input（Command + Params）和 Output 区域
- 保持与现有消息流的视觉一致性

**Non-Goals:**
- 不修改后端 API 或数据结构
- 不改变工具调用的业务逻辑
- 不涉及工具选择器（toolSelector.tsx）的布局调整

## Decisions

### 1. 继续使用 HTML 字符串渲染 vs 改为 React 组件

**决定**: 继续使用 HTML 字符串渲染

**理由**:
- 当前架构基于 `dangerouslySetInnerHTML` 渲染 markdown 内容，工具调用嵌入其中
- 改为 React 组件需要重构整个消息渲染流程，超出本次范围
- HTML 字符串方式可通过全局事件委托实现交互

### 2. 折叠/展开状态管理

**决定**: 使用 DOM data 属性 + CSS 控制

**理由**:
- 通过 `data-expanded="true/false"` 属性控制展开状态
- CSS 使用 `[data-expanded="true"]` 选择器控制内容显示
- 点击事件通过现有的全局事件委托机制处理
- 无需引入额外状态管理

### 3. 布局方案

**决定**: 使用 `flex-direction: column` + 卡片容器

**结构**:
```
.tool-call-card (flex-col, 全宽)
├── .tool-call-header (flex, 点击区域)
│   ├── 图标 + 工具名 + 状态
│   └── 展开/折叠箭头
└── .tool-call-body (默认隐藏)
    ├── Input 区域
    │   ├── Command: $ {name}
    │   └── Input Params: {args JSON}
    └── Output 区域
        └── {result}
```

### 4. 样式方案

**决定**: 内联样式 + CSS 变量

**理由**:
- 与现有 `renderToolCallCard` 保持一致的样式注入方式
- 使用项目已有的 CSS 变量（`--color-text-*`, `--color-fill-*`）保持主题一致

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| HTML 字符串拼接可读性差 | 使用模板字符串分段，添加注释 |
| 长 JSON 内容影响布局 | 添加 `max-height` + `overflow: auto` |
| 全局事件委托可能冲突 | 使用唯一的 `data-tool-card-id` 标识 |
| 移除浮动面板可能影响其他使用场景 | 检查 `syncActiveToolCallPanel` 的调用点，确保无其他依赖 |

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-19
```

## Capability Deltas

### tool-call-card

## ADDED Requirements

### Requirement: 工具调用卡片垂直布局
系统 SHALL 将工具调用展示从横排布局改为垂直单行卡片布局，每个工具占据完整的一行宽度。

#### Scenario: 多个工具调用垂直排列
- **WHEN** 对话中存在多个工具调用
- **THEN** 每个工具卡片独占一行，从上到下垂直排列

### Requirement: 工具卡片默认折叠
系统 SHALL 默认以折叠状态展示工具卡片，仅显示工具名称和状态图标。

#### Scenario: 工具调用完成后的默认展示
- **WHEN** 工具调用完成并渲染到对话区域
- **THEN** 卡片显示为折叠状态，仅展示：工具图标、工具名称、状态图标（✓ 或 loading）、展开箭头（▶）

### Requirement: 工具卡片可展开
系统 SHALL 支持点击卡片展开，显示 Input 和 Output 详情区域。

#### Scenario: 点击折叠状态的卡片
- **WHEN** 用户点击处于折叠状态的工具卡片
- **THEN** 卡片展开，显示 Input 和 Output 区域，箭头变为向下（▼）

#### Scenario: 点击展开状态的卡片
- **WHEN** 用户点击处于展开状态的工具卡片
- **THEN** 卡片折叠，隐藏 Input 和 Output 区域，箭头变为向右（▶）

### Requirement: Input 区域展示
系统 SHALL 在展开状态下显示 Input 区域，包含 Command 和 Input Params 两部分。

#### Scenario: 展示工具输入信息
- **WHEN** 工具卡片处于展开状态
- **THEN** Input 区域显示：
  - Command 标签下显示 `$ {工具名称}`
  - Input Params 标签下显示格式化的 JSON 参数（args）

### Requirement: Output 区域展示
系统 SHALL 在展开状态下显示 Output 区域，展示工具执行结果。

#### Scenario: 展示工具输出结果
- **WHEN** 工具卡片处于展开状态且工具已完成执行
- **THEN** Output 区域显示工具的执行结果（result）

#### Scenario: 工具执行中无输出
- **WHEN** 工具卡片处于展开状态但工具仍在执行中
- **THEN** Output 区域显示加载状态或为空

### Requirement: 长内容处理
系统 SHALL 对过长的 Input/Output 内容进行合理的展示限制。

#### Scenario: JSON 参数过长
- **WHEN** Input Params 的 JSON 内容超过显示区域
- **THEN** 内容区域可滚动查看，不影响整体布局

#### Scenario: 输出结果过长
- **WHEN** Output 内容超过显示区域
- **THEN** 内容区域可滚动查看，不影响整体布局

## Work Checklist

## 1. 准备工作

- [x] 1.1 阅读并理解现有 `toolCallRenderer.tsx` 的完整代码结构
- [x] 1.2 确认 `syncActiveToolCallPanel` 的所有调用点，评估移除浮动面板的影响

## 2. 核心实现

- [x] 2.1 重构 `renderToolCallCard` 函数，实现垂直卡片布局结构
- [x] 2.2 添加折叠/展开的 HTML 结构（header + body），默认折叠
- [x] 2.3 实现 Input 区域渲染（Command + Input Params）
- [x] 2.4 实现 Output 区域渲染
- [x] 2.5 添加长内容的滚动处理样式（max-height + overflow）

## 3. 交互实现

- [x] 3.1 修改全局事件委托，支持卡片点击展开/折叠
- [x] 3.2 实现展开/折叠状态切换（data-expanded 属性）
- [x] 3.3 移除或保留原有浮动面板相关代码（根据 1.2 评估结果决定）

## 4. 样式优化

- [x] 4.1 调整卡片样式，确保与现有消息流视觉一致
- [x] 4.2 添加展开/折叠动画过渡效果
- [x] 4.3 确保深色/浅色主题兼容（使用 CSS 变量）

## 5. 验证

- [x] 5.1 在智能体详情页面测试工具调用展示效果
- [x] 5.2 验证多个工具调用的垂直排列
- [x] 5.3 验证折叠/展开交互正常
- [x] 5.4 验证长内容的滚动处理
- [x] 5.5 运行 `pnpm lint && pnpm type-check` 确保无错误
