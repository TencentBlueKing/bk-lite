# 2026 05 11 Provider Model Team Filter

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-11-provider-model-team-filter/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

供应商详情页存在"配置链路"和"数据链路"混用问题：供应商列表页显示有 N 个模型，但进入详情页后因模型被 team 过滤而看不到。这导致管理员无法在配置页面管理该供应商下的所有模型。

模型的 `team` 字段本意是"使用权限"（谁能用这个模型），而非"归属权限"（模型属于谁）。配置场景应展示供应商下所有模型，使用场景才需要按 team 过滤。

## What Changes

- 后端新增 `by_vendor` action，用于配置场景获取供应商下所有模型（不过滤模型的 team）
- 新接口包含安全校验：验证用户对该供应商有权限（vendor.team 包含 current_team）
- 前端供应商详情页改用新接口获取模型列表
- 其他使用场景（如 Skill 设置页选择模型）保持现有 team 过滤逻辑不变

## Capabilities

### New Capabilities

- `provider-model-config-api`: 供应商模型配置接口，提供按供应商查询模型的能力（不过滤模型 team，但验证供应商权限）

### Modified Capabilities

（无，不修改现有 spec 级别的行为）

## Impact

**后端**:
- `server/apps/opspilot/viewsets/llm_view.py` - LLMModelViewSet
- `server/apps/opspilot/viewsets/embed_view.py` - EmbedProviderViewSet
- `server/apps/opspilot/viewsets/rerank_view.py` - RerankProviderViewSet
- `server/apps/opspilot/viewsets/ocr_view.py` - OCRProviderViewSet

**前端**:
- `web/src/app/opspilot/api/provider.ts` - API 层
- `web/src/app/opspilot/components/provider/modelManagement.tsx` - 供应商详情页组件

**API**:
- 新增: `GET /opspilot/model_provider_mgmt/{type}/by_vendor/?vendor={id}`
- 现有接口行为不变

## Implementation Decisions

## Context

当前系统中，供应商(ModelVendor)和模型(LLMModel/EmbedProvider/RerankProvider/OCRProvider)各自有独立的 `team` 字段（JSONField，存储 team ID 列表）。

现有 API 行为：
- `GET /opspilot/model_provider_mgmt/{type}/` 通过 `AuthViewSet.query_by_groups()` 按 `model.team` 过滤
- 供应商详情页调用此接口时，只能看到 `model.team` 包含当前 team 的模型

这在"使用场景"（如 Skill 选择模型）是正确的，但在"配置场景"（供应商详情页管理模型）是错误的。

## Goals / Non-Goals

**Goals:**
- 供应商详情页能展示该供应商下所有模型（不过滤模型的 team）
- 保证安全性：用户必须对供应商有权限才能查看其下的模型
- 不影响现有使用场景的 team 过滤逻辑

**Non-Goals:**
- 不修改现有 list 接口的行为
- 不修改供应商列表页的 model_count 统计逻辑
- 不修改 Skill 设置页等使用场景的模型选择逻辑

## Decisions

### 1. 新增 action 而非修改现有接口

**决策**: 在 ViewSet 中新增 `by_vendor` action，而非给现有 list 接口加参数。

**理由**:
- 职责分离：配置场景和使用场景有不同的过滤逻辑
- 安全性：避免通过参数绕过 team 过滤的风险
- 向后兼容：不影响现有调用方

**替代方案（否决）**: 给 list 接口加 `skip_team_filter` 参数 → 安全风险高

### 2. 通过 vendor.team 验证权限

**决策**: `by_vendor` 接口通过 `vendor__team__contains=current_team` 验证用户对供应商的权限。

**理由**:
- 复用现有的 team 权限体系
- 确保用户只能查看有权限的供应商下的模型
- 不需要额外的权限配置

### 3. 前端只改供应商详情页

**决策**: 只修改 `modelManagement.tsx` 调用新接口，其他页面保持不变。

**理由**:
- 最小改动原则
- 其他页面（Skill 设置等）的 team 过滤是正确的业务逻辑

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 新接口可能被滥用绕过 team 过滤 | 接口验证 vendor.team 权限，只返回有权限供应商下的模型 |
| 前端改动可能遗漏其他调用点 | 只有 modelManagement.tsx 需要改，已确认无其他调用点 |

## Capability Deltas

### provider-model-config-api

## ADDED Requirements

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

## Work Checklist

## 1. 后端：新增 by_vendor action

- [x] 1.1 在 `LLMModelViewSet` 中新增 `by_vendor` action
- [x] 1.2 在 `EmbedProviderViewSet` 中新增 `by_vendor` action
- [x] 1.3 在 `RerankProviderViewSet` 中新增 `by_vendor` action
- [x] 1.4 在 `OCRProviderViewSet` 中新增 `by_vendor` action

## 2. 前端：调用新接口

- [x] 2.1 在 `provider.ts` 中新增 `fetchModelsByVendor` 方法
- [x] 2.2 修改 `modelManagement.tsx` 使用新接口获取模型列表

## 3. 验证

- [x] 3.1 后端 lint 检查通过
- [x] 3.2 前端 type-check 通过
- [x] 3.3 手动测试：供应商详情页能展示所有模型（不受模型 team 过滤）
- [x] 3.4 手动测试：无权限的供应商返回空列表
