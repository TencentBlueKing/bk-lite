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
