## ADDED Requirements

### Requirement: YAML 冗余字段过滤
`get_kubernetes_resource_yaml` 工具 SHALL 在返回 YAML 前过滤冗余字段以减少体积。

#### Scenario: 过滤 managedFields
- **WHEN** 获取任何资源的 YAML
- **THEN** 返回结果 SHALL 不包含 `metadata.managedFields` 字段

#### Scenario: 过滤 status
- **WHEN** 获取资源 YAML 且未指定 `include_status=True`
- **THEN** 返回结果 SHALL 不包含顶层 `status` 字段

#### Scenario: 过滤冗余 annotations
- **WHEN** 获取资源 YAML
- **THEN** 返回结果 SHALL 移除 `metadata.annotations` 中 `kubectl.kubernetes.io/last-applied-configuration` 字段（该字段是完整配置的重复）

#### Scenario: 保留核心配置
- **WHEN** 过滤执行后
- **THEN** `metadata`（name/namespace/labels）、`spec` SHALL 完整保留
