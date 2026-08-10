# provider-model-config-api Specification

## Purpose
TBD - created by archiving change provider-model-team-filter. Update Purpose after archive.
## Requirements
### Requirement: 按供应商查询模型（配置场景）

系统 SHALL 提供 `by_vendor` 接口，允许用户按供应商 ID 查询该供应商下的所有模型，不过滤模型自身的 team 字段。

此接口用于配置场景（供应商详情页），与使用场景（Skill 选择模型）的 team 过滤逻辑分离。

#### Scenario: 成功获取供应商下所有模型

- **WHEN** 用户调用 `GET /opspilot/model_provider_mgmt/{type}/by_vendor/?vendor={vendor_id}`
- **AND** 用户的 current_team 在该供应商的 team 列表中
- **THEN** 系统返回该供应商下所有模型（不过滤模型的 team）

#### Scenario: 无权限访问供应商

- **WHEN** 用户调用 `GET /opspilot/model_provider_mgmt/{type}/by_vendor/?vendor={vendor_id}`
- **AND** 用户的 current_team 不在该供应商的 team 列表中
- **THEN** 系统返回空列表

#### Scenario: 缺少 vendor 参数

- **WHEN** 用户调用 `GET /opspilot/model_provider_mgmt/{type}/by_vendor/` 不带 vendor 参数
- **THEN** 系统返回错误响应，提示 vendor 参数必填

### Requirement: 支持所有模型类型

`by_vendor` 接口 SHALL 支持以下模型类型：
- `llm_model` - LLM 模型
- `embed_provider` - 向量模型
- `rerank_provider` - 重排模型
- `ocr_provider` - OCR 模型

#### Scenario: 各类型模型均可通过 by_vendor 查询

- **WHEN** 用户分别调用以下接口：
  - `GET /opspilot/model_provider_mgmt/llm_model/by_vendor/?vendor=1`
  - `GET /opspilot/model_provider_mgmt/embed_provider/by_vendor/?vendor=1`
  - `GET /opspilot/model_provider_mgmt/rerank_provider/by_vendor/?vendor=1`
  - `GET /opspilot/model_provider_mgmt/ocr_provider/by_vendor/?vendor=1`
- **AND** 用户对供应商 1 有权限
- **THEN** 每个接口返回对应类型的模型列表

### Requirement: 前端供应商详情页使用新接口

供应商详情页的模型管理组件 SHALL 使用 `by_vendor` 接口获取模型列表，以展示该供应商下所有模型。

#### Scenario: 供应商详情页展示所有模型

- **WHEN** 用户进入供应商详情页 `/opspilot/provider/detail?id={vendor_id}&tab=models`
- **AND** 用户对该供应商有权限
- **THEN** 页面展示该供应商下所有 LLM/Embed/Rerank/OCR 模型
- **AND** 不因模型的 team 字段而过滤任何模型
