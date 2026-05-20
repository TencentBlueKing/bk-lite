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
