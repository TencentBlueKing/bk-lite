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
