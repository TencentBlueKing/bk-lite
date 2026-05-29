# Tasks: 修复定时触发节点配置抽屉缺少 message 输入框

## 任务列表

- [x] 在 CeleryNodeConfig.tsx 中添加 message 输入框
  - 文件: `web/src/app/opspilot/components/chatflow/components/nodeConfigs/CeleryNodeConfig.tsx`
  - 在所有频率配置之后添加 Form.Item，name="message"
  - 使用 Input.TextArea 组件，支持多行输入
  - 添加合适的 label（如"输入信息"或"触发消息"）

- [x] 添加国际化文案
  - 已有文案: `chatflow.triggerMessage` 和 `chatflow.triggerMessagePlaceholder`

- [x] 运行代码质量检查
  - 命令: `cd web && pnpm type-check`
  - 验证: 无类型错误
