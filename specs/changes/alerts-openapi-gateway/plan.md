# 告警中心 OpenAPI 网关接入 Implementation Plan

> **For agentic workers:** 本计划在当前会话内联执行。规格见同目录 `spec.md`。

**Goal:** 作业字段绑定支持告警 ID；告警 OpenAPI 整组挂到统一网关，锚点为业务 `alert_id`；接口关闭允许待响应/处理中且不校验处理人。

**Architecture:** 包装现有 `AlertsOpenAPIService`。`AlertOperator` 增加 API 关闭模式；FilterSet 补 `resource_type`/`resource_id`；`@openapi_expose` 注册网关端点；旧 `/api/open` 保留并共用 service。

**Tech Stack:** Django / DRF、`apps.core.openapi`、告警 OpenAPI service、告警前端动作规则绑定表

---

### Task 1: API 关闭模式（AlertOperator）

- Modify: `server/apps/alerts/service/alter_operator.py`
- Test: `server/apps/alerts/tests/test_alert_operator.py`

- [x] API 关闭：待响应/处理中可关，不校验处理人；默认路径不变

### Task 2: 列表筛选补 resource_type / resource_id

- Modify: `server/apps/alerts/filters/alert.py`
- Test: `server/apps/alerts/tests/test_filters.py`

- [x] 精确匹配过滤对页面、旧 OpenAPI、网关同时生效

### Task 3: OpenAPI service 走 API 关闭模式

- Modify: `server/apps/alerts/open_api/services.py`
- Modify: `server/apps/alerts/open_api/auth.py`（`from_gateway`）
- Test: `server/apps/alerts/tests/test_open_api_operator_service.py`

- [x] 网关与旧路径共用 service，关闭行为对齐

### Task 4: 网关暴露

- Create: `server/apps/alerts/openapi_serializers.py`
- Create: `server/apps/alerts/openapi_api.py`
- Modify: `server/apps/alerts/apps.py` ready 导入
- Test: `server/apps/alerts/tests/test_openapi_gateway.py`
- Modify: `server/apps/core/openapi/tests/tenant_coverage.py`

- [x] 8 个 path 全部登记双租户测试

### Task 5: 作业参数告警 ID

- Modify: `web/src/app/alarm/(pages)/settings/actionRules/components/fieldBindingTable.tsx`
- Test: `web/scripts/alarm-job-binding-alert-id-test.ts`

- [x] 绑定下拉含告警 ID；匹配规则不扩

### Task 6: 契约文档

- Modify: `server/apps/alerts/docs/open_api.md`
- Modify: `specs/capabilities/legacy-ard-modules-alerts.md`
- Modify: `specs/capabilities/legacy-fuctionlist-03-告警中心-功能清单.md`

- [x] 网关入口、关闭口径、resource 筛选已写入契约文档
