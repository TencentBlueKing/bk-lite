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
