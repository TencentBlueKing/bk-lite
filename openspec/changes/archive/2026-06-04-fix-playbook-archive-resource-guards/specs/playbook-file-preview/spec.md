## ADDED Requirements

### Requirement: 预览前必须校验归档资源上限

系统 SHALL 在 Playbook 文件预览前校验归档总大小和可接受的 archive 元数据范围，避免通过预览路径触发整包高内存处理。

#### Scenario: 超大归档预览被拒绝
- **WHEN** 用户请求预览的 Playbook 归档总大小超过配置限制
- **THEN** 系统返回拒绝结果而不是先将整包读入内存

#### Scenario: 合法归档仍可预览目标文件
- **WHEN** 用户请求预览的 Playbook 归档在配置限制内且目标成员满足现有文本预览规则
- **THEN** 系统正常返回目标文件内容
