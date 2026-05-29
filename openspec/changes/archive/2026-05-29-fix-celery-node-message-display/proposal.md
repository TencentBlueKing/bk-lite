# Proposal: 修复定时触发节点配置抽屉缺少 message 输入框

## 问题描述

在 workflow 流程设置的前端，当配置"定时触发"(celery) 节点时，配置抽屉（右侧面板）中缺少 `message` 输入框。

**现象**：
- 数据库中存储了 `message` 字段（如 "帮我看下 https://github.com/TencentBlueKing/bk-lite..."）
- 配置抽屉只显示：节点名称、输入参数、输出参数、触发频率、触发时间
- **缺少 `message` 输入框**，用户无法配置/查看输入信息

**用户反馈**：之前是有这个输入框的，某次修改后被隐藏了。

## 根因分析

问题定位在 `web/src/app/opspilot/components/chatflow/components/nodeConfigs/CeleryNodeConfig.tsx`：

该组件只包含频率和时间相关的表单项，没有 `message` 字段的 Form.Item。

## 解决方案

在 `CeleryNodeConfig.tsx` 中添加 `message` 输入框（TextArea），放在触发时间配置之后。

## 影响范围

- **文件**: `web/src/app/opspilot/components/chatflow/components/nodeConfigs/CeleryNodeConfig.tsx`
- **组件**: 定时触发节点的配置抽屉
- **风险**: 低 - 仅增加表单项，数据结构已存在

## 验收标准

1. 配置抽屉中显示 `message` 输入框（多行文本框）
2. 可以输入和保存 message 内容
3. 已有的 message 数据能正确回显
4. 不影响其他配置项
