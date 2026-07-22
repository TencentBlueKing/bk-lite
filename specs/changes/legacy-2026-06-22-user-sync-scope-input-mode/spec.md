# Historical Superpowers change: 2026-06-22-user-sync-scope-input-mode

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-22-user-sync-scope-input-mode.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 provider manifest 驱动体系中，为 `user_sync` 的 `root_department_id` 字段引入 `input_mode`（`department_select` / `manual_input`）元数据，使前后端能按模式分别渲染和校验，本次仅搭建框架能力，不新增具体 AD provider。

**Architecture:** 通过扩展 `TemplateFieldManifest` / `TemplateField` schema 承载 `input_mode`；新增统一工具函数读取模式；前端按模式选择 `TreeSelect` 或 `Input`，后端按模式决定是否调用 `list_departments`；所有未声明 `input_mode` 的 provider 默认按 `department_select` 处理，保证飞书回归。

**Tech Stack:** Python 3.12 / Django 4.2 / DRF / Pydantic / pytest；Next.js 16 / React 19 / TypeScript / Ant Design / tsx 脚本测试。

**Commit policy:** 本次实施暂不集中 commit；每个 Task 完成验证后只保留工作区变更，最终由执行者统一决定提交时机与粒度。

## Execution Status

**Status Date:** 2026-06-23

- Core implementation completed and committed in `474adca90` (`feat(system_mgmt): support manual user sync scope input mode`).
- Related `system_mgmt` migration chain was linearized separately in `644de2aed` (`refactor(system_mgmt): linearize integration migrations`).
- Backend final verification completed with a recreated test database:
  - `cd server && .venv\Scripts\python.exe -m pytest --create-db apps/system_mgmt/tests/test_user_sync_service.py apps/system_mgmt/tests/test_user_sync_source_input_mode.py apps/system_mgmt/tests/test_provider_manifest.py -v`
  - Result: `43 passed`
- Frontend pure-function verification completed:
  - `cd web && pnpm exec tsx scripts/user-sync-input-mode-test.ts`
  - Result: `user sync input mode tests passed`
- Frontend targeted lint for files touched by this change completed:
  - `pnpm exec eslint src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx src/app/system-manager/types/integration-center.ts src/app/system-manager/utils/userSyncUtils.ts --ext .ts,.tsx`
  - Result: PASS
- Global frontend gates are currently blocked by pre-existing repository issues rather than this change:
  - `pnpm lint` fails on unrelated files under `cmdb` / `monitor` / `stories`
  - `pnpm type-check` does not reach `tsc` on Windows because the wrapper script runs `rm -rf .next`
- Manual smoke check completed.
- Manual smoke conclusion:
  - `department_select` mode still behaves correctly for Feishu, including department tree rendering in the view flow.
  - `manual_input` mode correctly switches `root_department_id` from `TreeSelect` to `Input`.
  - Existing sync sources under the same provider also switch to `manual_input` rendering after the provider manifest changes; this matches the current design because `input_mode` is resolved from the provider manifest rather than persisted per sync source.
  - In `manual_input` mode, `department_id_type` was selectable during create but not written back on edit. This is currently classified as a provider-specific field behavior difference rather than a blocker for the input-mode framework itself.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `server/apps/system_mgmt/providers/schemas.py` | 扩展 `TemplateFieldManifest`，支持 `input_mode` 字段 |
| `server/apps/system_mgmt/providers/manifests/feishu.py` | 为飞书 `root_department_id` 显式声明 `input_mode=department_select` |
| `server/apps/system_mgmt/services/user_sync_service.py` | 新增 `get_user_sync_root_department_input_mode()` 供 serializer / viewset 复用 |
| `server/apps/system_mgmt/serializers/user_sync_source_serializer.py` | 按 `input_mode` 分支校验 `root_department_id` |
| `server/apps/system_mgmt/viewset/user_sync_source_viewset.py` | `department_options` 对 `manual_input` provider 返回 400 |
| `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py` | 新增后端模式分支测试 |
| `web/src/app/system-manager/types/integration-center.ts` | 扩展 `TemplateField` 类型 |
| `web/src/app/system-manager/utils/userSyncUtils.ts` | 新增读取 `input_mode` 的工具函数 |
| `web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx` | 按模式渲染 `TreeSelect` 或 `Input` |
| `web/src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx` | 切换实例时按模式注入/清理默认值 |
| `web/scripts/user-sync-input-mode-test.ts` | 新增纯函数 tsx 测试脚本 |

---

## Task 1: Extend Backend Field Schema

**Files:**
- Modify: `server/apps/system_mgmt/providers/schemas.py`
- Test: `server/apps/system_mgmt/tests/test_provider_manifest.py`

- [ ] **Step 1: Write the failing test**

Add a test asserting that `TemplateFieldManifest` accepts `input_mode` and that `to_public_dict` preserves it.

```python
def test_template_field_manifest_supports_input_mode():
    from apps.system_mgmt.providers.schemas import ProviderManifest

    manifest = ProviderManifest.model_validate(
        {
            "key": "demo",
            "name": "Demo",
            "business_templates": {
                "user_sync_form": {
                    "title": "User Sync",
                    "groups": [
                        {
                            "key": "pull",
                            "title": "拉取配置",
                            "fields": [
                                {
                                    "key": "root_department_id",
                                    "label": "同步范围",
                                    "required": True,
                                    "input_mode": "manual_input",
                                }
                            ],
                        }
                    ],
                    "available_external_fields": ["user_id"],
                }
            },
            "capabilities": [
                {
                    "key": "user_sync",
                    "name": "User Sync",
                    "adapter_key": "demo.user_sync",
                    "adapter_path": "apps.system_mgmt.providers.adapters.base.BaseUserSyncAdapter",
                    "business_template": "user_sync_form",
                }
            ],
        }
    )

    public_dict = manifest.to_public_dict()
    root_field = public_dict["business_templates"]["user_sync_form"]["groups"][0]["fields"][0]
    assert root_field["input_mode"] == "manual_input"
```

Run: `uv run pytest server/apps/system_mgmt/tests/test_provider_manifest.py::test_template_field_manifest_supports_input_mode -v`
Expected: FAIL with `Extra inputs are not permitted` (Pydantic rejects unknown key).

- [ ] **Step 2: Extend `TemplateFieldManifest`**

Add the field and type alias:

```python
InputMode = Literal["department_select", "manual_input"]

class TemplateFieldManifest(BaseModel):
    key: str = Field(description="字段唯一键")
    label: str = Field(description="字段展示名称")
    field_type: FieldType = Field(default="string", description="字段类型")
    required: bool = Field(default=False, description="是否必填")
    secret: bool = Field(default=False, description="是否为敏感字段")
    write_only: bool = Field(default=False, description="是否仅写入不回显")
    mask_strategy: MaskStrategy = Field(default="full", description="敏感字段回显脱敏策略")
    default: Any = Field(default=None, description="默认值")
    placeholder: str = Field(default="", description="占位提示")
    help_text: str = Field(default="", description="帮助文案")
    options: list[dict[str, Any]] = Field(default_factory=list, description="选择型字段可选项")
    reset_capabilities: list[str] = Field(default_factory=list, description="字段变更后需要回退的 capability 列表")
    input_mode: InputMode | None = Field(default=None, description="范围字段输入模式")
```

Run: `uv run pytest server/apps/system_mgmt/tests/test_provider_manifest.py::test_template_field_manifest_supports_input_mode -v`
Expected: PASS.

- [ ] **Step 3: Stage changes (do not commit yet)**

Files changed:
- `server/apps/system_mgmt/providers/schemas.py`
- `server/apps/system_mgmt/tests/test_provider_manifest.py`

---

## Task 2: Extend Frontend Field Type

**Files:**
- Modify: `web/src/app/system-manager/types/integration-center.ts`
- Test: `web/scripts/user-sync-input-mode-test.ts` (created in Task 10)

- [ ] **Step 1: Add `input_mode` to `TemplateField`**

```typescript
export interface TemplateField {
  key: string;
  label: string;
  field_type: string;
  required: boolean;
  secret: boolean;
  write_only: boolean;
  mask_strategy: string;
  default: unknown;
  placeholder: string;
  help_text: string;
  options: Array<{ value: unknown; label: string }>;
  reset_capabilities: string[];
  input_mode?: 'department_select' | 'manual_input';
}
```

- [ ] **Step 2: Run TypeScript type check**

Run: `cd web && pnpm type-check`
Expected: PASS (no new errors).

- [ ] **Step 3: Stage changes (do not commit yet)**

Files changed:
- `web/src/app/system-manager/types/integration-center.ts`

---

## Task 3: Declare Feishu Input Mode

**Files:**
- Modify: `server/apps/system_mgmt/providers/manifests/feishu.py`

- [ ] **Step 1: Add `input_mode` to feishu `root_department_id`**

Locate the `root_department_id` field in `user_sync_form` and add the metadata:

```python
{
    "key": "root_department_id",
    "label": "根部门 ID",
    "field_type": "string",
    "required": True,
    "input_mode": "department_select",
},
```

- [ ] **Step 2: Verify manifest still validates**

Run: `uv run pytest server/apps/system_mgmt/tests/test_provider_manifest.py -v`
Expected: All PASS.

- [ ] **Step 3: Stage changes (do not commit yet)**

Files changed:
- `server/apps/system_mgmt/providers/manifests/feishu.py`

---

## Task 4: Add Shared Mode Resolver

**Files:**
- Modify: `server/apps/system_mgmt/services/user_sync_service.py`
- Test: `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py`

- [ ] **Step 1: Write the failing test**

Create `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py` with:

```python
import pytest
from apps.system_mgmt.providers.schemas import ProviderManifest
from apps.system_mgmt.services.user_sync_service import get_user_sync_root_department_input_mode


def test_mode_resolver_defaults_to_department_select_for_unknown_provider():
    assert get_user_sync_root_department_input_mode("nonexistent_provider") == "department_select"


def test_mode_resolver_reads_manual_input_from_manifest():
    manifest = ProviderManifest.model_validate(
        {
            "key": "demo_manual",
            "name": "Demo Manual",
            "business_templates": {
                "user_sync_form": {
                    "title": "User Sync",
                    "groups": [
                        {
                            "key": "pull",
                            "title": "拉取配置",
                            "fields": [
                                {
                                    "key": "root_department_id",
                                    "label": "同步范围",
                                    "required": True,
                                    "input_mode": "manual_input",
                                }
                            ],
                        }
                    ],
                    "available_external_fields": ["user_id"],
                }
            },
            "capabilities": [
                {
                    "key": "user_sync",
                    "name": "User Sync",
                    "adapter_key": "demo_manual.user_sync",
                    "adapter_path": "apps.system_mgmt.providers.adapters.base.BaseUserSyncAdapter",
                    "business_template": "user_sync_form",
                }
            ],
        }
    )
    from apps.system_mgmt.providers.registry import get_provider_registry, get_capability_adapter_registry
    from apps.system_mgmt.providers.adapters.base import BaseUserSyncAdapter

    registry = get_provider_registry()
    adapter_registry = get_capability_adapter_registry()
    registry.register(manifest)
    adapter_registry.register("demo_manual.user_sync", BaseUserSyncAdapter)

    try:
        assert get_user_sync_root_department_input_mode("demo_manual") == "manual_input"
    finally:
        registry._providers.pop("demo_manual", None)
        adapter_registry._adapters.pop("demo_manual.user_sync", None)
```

Run: `uv run pytest server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py::test_mode_resolver_reads_manual_input_from_manifest -v`
Expected: FAIL with `get_user_sync_root_department_input_mode` not defined.

- [ ] **Step 2: Implement the resolver**

Add to `server/apps/system_mgmt/services/user_sync_service.py`:

```python
def get_user_sync_root_department_input_mode(provider_key: str) -> str:
    """Return the input_mode for root_department_id in the user_sync capability.

    Defaults to department_select when the provider/manifest/field does not declare one.
    """
    runtime_service = RuntimeApplicationService()
    try:
        manifest = runtime_service.get_provider_manifest(provider_key)
    except ValueError:
        return "department_select"

    capability = manifest.get_capability("user_sync")
    if capability is None or not capability.business_template:
        return "department_select"

    business_template = manifest.business_templates.get(capability.business_template)
    if business_template is None:
        return "department_select"

    for group in business_template.groups:
        for field in group.fields:
            if field.key == "root_department_id":
                return field.input_mode or "department_select"
    return "department_select"
```

Run: `uv run pytest server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py::test_mode_resolver_reads_manual_input_from_manifest server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py::test_mode_resolver_defaults_to_department_select_for_unknown_provider -v`
Expected: PASS.

- [ ] **Step 3: Stage changes (do not commit yet)**

Files changed:
- `server/apps/system_mgmt/services/user_sync_service.py`
- `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py`

---

## Task 5: Branch Serializer Validation by Input Mode

**Files:**
- Modify: `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
- Test: `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py`

- [ ] **Step 1: Write failing tests for manual_input behavior**

Add to `test_user_sync_source_input_mode.py`:

```python
from unittest.mock import patch
import pytest
from apps.system_mgmt.models import IntegrationInstance
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.serializers.user_sync_source_serializer import UserSyncSourceSerializer


@pytest.fixture
def manual_input_instance(db):
    from apps.system_mgmt.providers.registry import get_provider_registry, get_capability_adapter_registry
    from apps.system_mgmt.providers.adapters.base import BaseUserSyncAdapter
    from apps.system_mgmt.providers.schemas import ProviderManifest

    manifest = ProviderManifest.model_validate(
        {
            "key": "test_manual",
            "name": "Test Manual",
            "business_templates": {
                "user_sync_form": {
                    "title": "User Sync",
                    "groups": [
                        {
                            "key": "pull",
                            "title": "拉取配置",
                            "fields": [
                                {
                                    "key": "root_department_id",
                                    "label": "同步范围",
                                    "required": True,
                                    "input_mode": "manual_input",
                                }
                            ],
                        }
                    ],
                    "available_external_fields": ["user_id"],
                }
            },
            "capabilities": [
                {
                    "key": "user_sync",
                    "name": "User Sync",
                    "adapter_key": "test_manual.user_sync",
                    "adapter_path": "apps.system_mgmt.providers.adapters.base.BaseUserSyncAdapter",
                    "business_template": "user_sync_form",
                }
            ],
        }
    )
    registry = get_provider_registry()
    adapter_registry = get_capability_adapter_registry()
    registry.register(manifest)
    adapter_registry.register("test_manual.user_sync", BaseUserSyncAdapter)

    instance = IntegrationInstance.objects.create(
        name="test-manual",
        provider_key="test_manual",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready"},
        config={},
    )
    yield instance
    registry._providers.pop("test_manual", None)
    adapter_registry._adapters.pop("test_manual.user_sync", None)


@pytest.mark.django_db
def test_manual_input_accepts_raw_scope_and_skips_list_departments(manual_input_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "manual-source",
            "integration_instance": manual_input_instance.id,
            "root_group_name": "Manual Root",
            "business_config": {
                "root_department_id": "ou=paas,dc=bktest,dc=com",
            },
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute") as mock_execute:
        assert serializer.is_valid(), serializer.errors

    mock_execute.assert_not_called()
    assert serializer.validated_data["business_config"]["root_department_id"] == "ou=paas,dc=bktest,dc=com"


@pytest.mark.django_db
def test_manual_input_ignores_department_id_type(manual_input_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "manual-source",
            "integration_instance": manual_input_instance.id,
            "root_group_name": "Manual Root",
            "business_config": {
                "root_department_id": "ou=paas,dc=bktest,dc=com",
                "department_id_type": "department_id",
            },
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute") as mock_execute:
        assert serializer.is_valid(), serializer.errors

    mock_execute.assert_not_called()
    assert "department_id_type" not in serializer.validated_data["business_config"]


@pytest.mark.django_db
def test_manual_input_rejects_empty_root_department(manual_input_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "manual-source",
            "integration_instance": manual_input_instance.id,
            "root_group_name": "Manual Root",
            "business_config": {
                "root_department_id": "",
            },
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    assert serializer.is_valid() is False
    assert "business_config" in serializer.errors
```

Run: `uv run pytest server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py -v`
Expected: FAIL (serializer still calls list_departments and rejects manual values).

- [ ] **Step 2: Implement serializer branching**

Modify `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`:

1. Import the resolver:

```python
from apps.system_mgmt.services.user_sync_service import (
    get_user_sync_root_department_input_mode,
)
```

2. Replace the unconditional department-tree validation block (lines 85-109) with:

```python
        root_department_id = str(business_config.get("root_department_id") or "")
        if not root_department_id:
            raise serializers.ValidationError({"business_config": "Root department is required"})

        input_mode = get_user_sync_root_department_input_mode(integration_instance.provider_key)
        if input_mode == "manual_input":
            business_config.pop("department_id_type", None)
            business_config["root_department_id"] = root_department_id
        else:
            runtime_service = RuntimeApplicationService()
            department_result = runtime_service.execute(
                provider_key=integration_instance.provider_key,
                capability_key="user_sync",
                operation="list_departments",
                config=integration_instance.get_runtime_config(),
                source=SimpleNamespace(name=getattr(self.instance, "name", ""), business_config=business_config),
                business_config=business_config,
            )
            if not department_result.success:
                raise serializers.ValidationError({"business_config": department_result.summary})

            normalized_root_department_id = user_sync_service.normalize_root_department_selection(
                root_department_id,
                department_result.payload,
            )
            valid_department_ids = user_sync_service.flatten_department_ids(department_result.payload.get("items") or [])
            valid_department_ids.add(str(department_result.payload.get("all_department_id") or ""))
            if normalized_root_department_id not in valid_department_ids:
                raise serializers.ValidationError({"business_config": "Selected root department is invalid"})
            business_config["root_department_id"] = normalized_root_department_id
```

Run: `uv run pytest server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py -v`
Expected: PASS.

- [ ] **Step 3: Run full user_sync tests to ensure no regression**

Run: `uv run pytest server/apps/system_mgmt/tests/test_user_sync_service.py -v`
Expected: All PASS.

- [ ] **Step 4: Stage changes (do not commit yet)**

Files changed:
- `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
- `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py`

---

## Task 6: Branch department_options by Input Mode

**Files:**
- Modify: `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
- Test: `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py`

- [ ] **Step 1: Write failing test**

Add to `test_user_sync_source_input_mode.py`:

```python
@pytest.mark.django_db
def test_department_options_returns_400_for_manual_input_provider(api_client, authenticated_user, manual_input_instance):
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    api_client.cookies["current_team"] = "1"

    response = api_client.get(
        "/api/v1/system_mgmt/user_sync_source/department_options/",
        {"integration_instance": manual_input_instance.id},
    )

    assert response.status_code == 400
    assert "manual_input" in response.json()["message"] or "部门树" in response.json()["message"]
```

Run: `uv run pytest server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py::test_department_options_returns_400_for_manual_input_provider -v`
Expected: FAIL (returns 200 with default tree data).

- [ ] **Step 2: Implement viewset guard**

Modify `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`:

1. Import the resolver:

```python
from apps.system_mgmt.services.user_sync_service import (
    ALL_DEPARTMENT_SELECTION_ID,
    flatten_department_ids,
    preview_user_sync,
    sync_source_now,
    get_user_sync_root_department_input_mode,
)
```

2. At the start of `department_options`, after fetching the integration instance and checking capability readiness, add:

```python
        input_mode = get_user_sync_root_department_input_mode(integration_instance.provider_key)
        if input_mode == "manual_input":
            return JsonResponse(
                {
                    "result": False,
                    "message": "Current provider uses manual_input mode and does not support department tree options",
                },
                status=400,
            )
```

Run: `uv run pytest server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py::test_department_options_returns_400_for_manual_input_provider -v`
Expected: PASS.

- [ ] **Step 3: Run existing department_options test**

Run: `uv run pytest server/apps/system_mgmt/tests/test_user_sync_service.py::test_user_sync_department_options_returns_all_selection_for_real_root -v`
Expected: PASS.

- [ ] **Step 4: Stage changes (do not commit yet)**

Files changed:
- `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
- `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py`

---

## Task 7: Add Frontend Mode Utilities

**Files:**
- Modify: `web/src/app/system-manager/utils/userSyncUtils.ts`
- Test: `web/scripts/user-sync-input-mode-test.ts`

- [ ] **Step 1: Add helper functions**

Add to `web/src/app/system-manager/utils/userSyncUtils.ts`:

```typescript
export function getRootDepartmentInputMode(
  template: BusinessTemplate | null,
): 'department_select' | 'manual_input' {
  if (!template) return 'department_select';
  for (const group of template.groups) {
    for (const field of group.fields) {
      if (field.key === 'root_department_id') {
        return field.input_mode === 'manual_input' ? 'manual_input' : 'department_select';
      }
    }
  }
  return 'department_select';
}

export function isDepartmentSelectMode(template: BusinessTemplate | null): boolean {
  return getRootDepartmentInputMode(template) === 'department_select';
}

export function isManualInputMode(template: BusinessTemplate | null): boolean {
  return getRootDepartmentInputMode(template) === 'manual_input';
}
```

- [ ] **Step 2: Write and run tsx pure-function test**

Create `web/scripts/user-sync-input-mode-test.ts`:

```typescript
import * as assert from 'node:assert/strict';
import {
  getRootDepartmentInputMode,
  isDepartmentSelectMode,
  isManualInputMode,
} from '../src/app/system-manager/utils/userSyncUtils';
import type { BusinessTemplate } from '../src/app/system-manager/types/integration-center';

const departmentSelectTemplate: BusinessTemplate = {
  title: 'User Sync',
  groups: [
    {
      key: 'pull',
      title: '拉取配置',
      description: '',
      fields: [
        {
          key: 'root_department_id',
          label: '根部门 ID',
          field_type: 'string',
          required: true,
          secret: false,
          write_only: false,
          mask_strategy: 'full',
          default: null,
          placeholder: '',
          help_text: '',
          options: [],
          reset_capabilities: [],
          input_mode: 'department_select',
        },
      ],
    },
  ],
  available_external_fields: [],
  matchable_fields: [],
  receivable_fields: [],
  default_external_match_field: '',
  default_external_receive_field: '',
};

const manualInputTemplate: BusinessTemplate = {
  ...departmentSelectTemplate,
  groups: [
    {
      ...departmentSelectTemplate.groups[0],
      fields: [
        {
          ...departmentSelectTemplate.groups[0].fields[0],
          input_mode: 'manual_input',
        },
      ],
    },
  ],
};

assert.equal(getRootDepartmentInputMode(null), 'department_select');
assert.equal(getRootDepartmentInputMode(departmentSelectTemplate), 'department_select');
assert.equal(getRootDepartmentInputMode(manualInputTemplate), 'manual_input');
assert.equal(isDepartmentSelectMode(departmentSelectTemplate), true);
assert.equal(isManualInputMode(manualInputTemplate), true);

console.log('user sync input mode tests passed');
```

Run: `cd web && pnpm exec tsx scripts/user-sync-input-mode-test.ts`
Expected: PASS.

- [ ] **Step 3: Stage changes (do not commit yet)**

Files changed:
- `web/src/app/system-manager/utils/userSyncUtils.ts`
- `web/scripts/user-sync-input-mode-test.ts`

---

## Task 8: Branch Frontend Config Field Rendering

**Files:**
- Modify: `web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx`

- [ ] **Step 1: Guard department_options fetch by mode**

In `UserSyncConfigFields.tsx`, after `const departmentTreeData = useMemo(...)` add:

```typescript
const inputMode = useMemo(() => getRootDepartmentInputMode(resolvedTemplate), [resolvedTemplate]);
```

Update the `useEffect` that fetches department options. At the top of `fetchDepartmentOptions`, add:

```typescript
      if (inputMode !== 'department_select') {
        setDepartmentNodes([]);
        setDepartmentSelectionMissing(false);
        setDepartmentLoadError('');
        setDepartmentLoading(false);
        return;
      }
```

And change the dependency array to include `inputMode`:

```typescript
  }, [departmentIdType, form, inputMode, selectedInstanceId, t]);
```

- [ ] **Step 2: Render Input for manual_input mode**

In `renderManifestField`, replace the `if (field.key === 'root_department_id')` block with:

```typescript
    if (field.key === 'root_department_id') {
      if (inputMode === 'manual_input') {
        return (
          <div key={field.key} className={wrapperClassName}>
            <Form.Item
              name={namePath}
              label={field.label}
              required={field.required}
              rules={rules}
              tooltip={field.help_text || undefined}
            >
              <Input placeholder={placeholder} />
            </Form.Item>
          </div>
        );
      }

      return (
        <div key={field.key} className={wrapperClassName}>
          {departmentSelectionMissing ? (
            <Alert
              className="mb-4"
              message={t('system.user.userSyncPage.departmentSelectionInvalid')}
              type="warning"
              showIcon
            />
          ) : null}
          {departmentLoadError ? (
            <Alert
              className="mb-4"
              message={departmentLoadError}
              type="error"
              showIcon
            />
          ) : null}
          <Form.Item
            name={namePath}
            label={field.label}
            required={field.required}
            rules={[{ required: field.required }]}
          >
            <TreeSelect
              treeData={departmentTreeData}
              treeDefaultExpandAll
              loading={departmentLoading}
              disabled={!selectedInstanceId || !!departmentLoadError}
              placeholder={departmentLoading
                ? t('system.user.userSyncPage.departmentOptionsLoading')
                : t('system.user.userSyncPage.rootDepartmentPlaceholder')}
              onChange={() => {
                form.setFields([{ name: namePath, errors: [] }]);
                setDepartmentSelectionMissing(false);
              }}
            />
          </Form.Item>
        </div>
      );
    }
```

- [ ] **Step 3: Import the helper**

Ensure the import from `userSyncUtils.ts` includes `getRootDepartmentInputMode`:

```typescript
import {
  getDefaultDepartmentIdType,
  getRootDepartmentInputMode,
  getWriteOnlyKeys,
  resolveUserSyncTemplate,
} from '@/app/system-manager/utils/userSyncUtils';
```

- [ ] **Step 4: Run lint and type-check**

Run: `cd web && pnpm lint`
Run: `cd web && pnpm type-check`
Expected: PASS (no new errors).

- [ ] **Step 5: Stage changes (do not commit yet)**

Files changed:
- `web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx`

---

## Task 9: Conditional Default Values in Operate Modal

**Files:**
- Modify: `web/src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx`

- [ ] **Step 1: Update instance change effect**

Replace the `useEffect` that sets default business config (lines 75-89) with:

```typescript
  useEffect(() => {
    if (!open || !selectedInstanceId) return;
    if (previousInstanceIdRef.current === selectedInstanceId) return;
    previousInstanceIdRef.current = selectedInstanceId;

    const nextBusinessConfig: Record<string, unknown> = {
      ...(form.getFieldValue('business_config') || {}),
    };

    if (isDepartmentSelectMode(resolvedTemplate)) {
      nextBusinessConfig.root_department_id = '__all__';
      const defaultDepartmentIdType = getDefaultDepartmentIdType(resolvedTemplate);
      if (defaultDepartmentIdType) {
        nextBusinessConfig.department_id_type = defaultDepartmentIdType;
      }
    } else {
      delete nextBusinessConfig.root_department_id;
      delete nextBusinessConfig.department_id_type;
    }

    form.setFieldValue('business_config', nextBusinessConfig);
  }, [form, open, resolvedTemplate, selectedInstanceId]);
```

- [ ] **Step 2: Update imports**

Change the import from `userSyncUtils.ts` to:

```typescript
import {
  getDefaultDepartmentIdType,
  getWriteOnlyKeys,
  isDepartmentSelectMode,
  resolveUserSyncTemplate,
} from '@/app/system-manager/utils/userSyncUtils';
```

- [ ] **Step 3: Run lint and type-check**

Run: `cd web && pnpm lint -- --ext .ts,.tsx src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx`
Run: `cd web && pnpm type-check`
Expected: PASS.

- [ ] **Step 4: Stage changes (do not commit yet)**

Files changed:
- `web/src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx`

---

## Task 10: Backend Regression Tests for Feishu

**Files:**
- Test: `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py`

- [ ] **Step 1: Add feishu regression tests**

Append to `test_user_sync_source_input_mode.py`:

```python
@pytest.mark.django_db
def test_department_select_still_calls_list_departments_and_normalizes_all(ready_integration_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "feishu-source",
            "integration_instance": ready_integration_instance.id,
            "root_group_name": "Feishu Root",
            "business_config": {
                "root_department_id": "__all__",
                "department_id_type": "department_id",
            },
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "all_department_id": "0",
            "items": [
                {"id": "__all__", "name": "全部部门", "parent_id": None, "children": []},
            ],
        },
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute", return_value=payload) as mock_execute:
        assert serializer.is_valid(), serializer.errors

    mock_execute.assert_called_once()
    assert serializer.validated_data["business_config"]["root_department_id"] == "0"


@pytest.mark.django_db
def test_department_select_rejects_invalid_department(ready_integration_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "feishu-source",
            "integration_instance": ready_integration_instance.id,
            "root_group_name": "Feishu Root",
            "business_config": {
                "root_department_id": "stale-dept",
            },
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "all_department_id": "0",
            "items": [
                {"id": "__all__", "name": "全部部门", "parent_id": None, "children": []},
            ],
        },
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute", return_value=payload):
        assert serializer.is_valid() is False

    assert "business_config" in serializer.errors
```

Add import at top:

```python
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
```

Run: `uv run pytest server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py -v`
Expected: PASS.

- [ ] **Step 2: Stage changes (do not commit yet)**

Files changed:
- `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py`

---

## Task 11: Final Verification

- [x] **Step 1: Run backend test suite**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_user_sync_service.py apps/system_mgmt/tests/test_user_sync_source_input_mode.py apps/system_mgmt/tests/test_provider_manifest.py -v`
Expected: All PASS.

- [ ] **Step 2: Run frontend checks**

Run: `cd web && pnpm exec tsx scripts/user-sync-input-mode-test.ts`
Expected: `user sync input mode tests passed`.

Run: `cd web && pnpm lint`
Expected: PASS (no new errors).

Run: `cd web && pnpm type-check`
Expected: PASS.

Actual result on 2026-06-23:
- `pnpm exec tsx scripts/user-sync-input-mode-test.ts`: PASS
- targeted lint on changed files: PASS
- `pnpm lint`: blocked by unrelated existing repo errors in `cmdb` / `monitor` / `stories`
- `pnpm type-check`: blocked by the existing Windows-incompatible `rm -rf .next` wrapper in `pnpm clean`
- direct `pnpm exec tsc -p tsconfig.lint.json --noEmit`: fails on unrelated existing type errors outside this change scope

- [x] **Step 3: Manual smoke check (optional but recommended)**

Start the dev server and verify:
1. 创建飞书用户同步源仍展示部门树选择器，切换实例后默认选中全部部门。
2. 如果临时构造一个 `manual_input` provider（本地仅验证），创建页展示普通输入框，保存时 `department_options` 返回 400。

Actual result on 2026-06-23:
- Feishu under `department_select` mode behaved normally in the UI flow.
- After temporarily switching the provider manifest to `manual_input`, the root scope field rendered as a plain input and the create/edit flow remained usable.
- Existing sync sources under the same provider also rendered with the new mode, which matches the current provider-manifest-driven design.
- `department_id_type` was not written back in `manual_input` edit flow; this is recorded as a provider-field behavior difference and does not block acceptance of this framework task.

- [ ] **Step 4: Wrap-up**

Review all staged changes. If any fixes were needed during verification, keep them staged. Summarize current diff without committing:

```bash
git diff --stat
```

---

## Self-Review Checklist

- [x] **Spec coverage**: Each section of `docs/superpowers/specs/2026-06-22-user-sync-scope-input-mode-design.md` maps to at least one task above.
- [x] **Placeholder scan**: No `TBD`, `TODO`, or vague steps remain in the implementation plan itself.
- [x] **Type consistency**: `input_mode` is always `"department_select" | "manual_input" | None/undefined"` in both frontend and backend.
- [ ] **Test completeness**: Backend coverage, frontend pure-function / targeted lint verification, and manual smoke are complete, but global frontend lint/type-check are still blocked by unrelated existing repository issues.

## specs: 2026-06-22-user-sync-scope-input-mode-design.md

> 说明：本文档记录系统管理处“用户同步拉取范围输入方式”设计，仅覆盖集成实例 `user_sync` 能力的范围配置，不包含企业微信私域地址、登录认证或其他集成中心议题。

## 背景

当前系统管理的用户同步配置已经接入 provider manifest 驱动能力：

- 前端通过 provider `business_template` 渲染 `user_sync` 配置表单
- 后端通过 provider `adapter` 执行 `list_departments`、`sync_users`
- `business_config.root_department_id` 作为同步范围的核心配置值贯穿保存、预览和正式同步

但当前实现对 `root_department_id` 有固定假设：

- 前端固定将 `root_department_id` 渲染为部门树选择器
- 后端固定通过 `list_departments` 返回值校验 `root_department_id` 合法性

这使当前实现仅适合“可枚举部门树”的 provider，例如飞书；对于 AD 一类“拉取范围是 DN/OU 字符串”的 provider，例如 `ou=paas,dc=bktest,dc=com`，现状无法支持手工输入范围。

## 目标

1. 保持现有 `user_sync` 配置仍以 provider manifest 为中心，不引入新的页面特判体系
2. 支持 provider 根据自身要求动态展示：
   - 部门树选择框
   - 手工范围输入框
3. 保持 `business_config.root_department_id` 作为统一范围字段，不拆分成多套配置键
4. 对飞书等现有部门树 provider 保持兼容，不改变现有保存、预览、同步路径
5. 为 AD 等 provider 提供手工输入范围的最小接入路径

## 非目标

- 不在本次设计中处理企业微信私域地址
- 不重做集成中心 provider 框架
- 不引入全新的远端资源选择器框架
- 不在第一阶段引入复杂的 AD DN 语法解析器
- 不改造 `user_sync` 之外的 `login_auth`、`im_notification` 能力

## 现状

当前关键实现位于：

- 前端
  - `web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx`
  - `web/src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx`
  - `web/src/app/system-manager/utils/userSyncUtils.ts`
- 后端
  - `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
  - `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
  - `server/apps/system_mgmt/services/user_sync_service.py`
  - `server/apps/system_mgmt/providers/adapters/base.py`
  - `server/apps/system_mgmt/providers/adapters/feishu.py`

当前行为为：

1. `root_department_id` 在前端被固定渲染为 `TreeSelect`
2. 页面通过 `department_options` 接口调用 `list_departments`
3. 创建页切换实例时，默认写入 `root_department_id="__all__"`
4. serializer 在保存时强制调用 `list_departments` 校验所选范围是否合法
5. `sync_users` 最终消费 `business_config.root_department_id`

因此现状的问题不是单纯前端控件类型问题，而是“前端渲染 + 后端校验”都绑定在“部门树可枚举”模型上。

## 设计原则

### 1. 范围输入方式属于字段自身元数据

“这个范围字段是选择还是手输”应归属于 `root_department_id` 字段本身，而不是页面级硬编码分支。新 provider 应只通过 manifest 声明行为，不要求前端新增 provider 特判。

### 2. 统一配置键，分离输入方式

无论 provider 采用部门树还是手输范围，最终仍统一写入 `business_config.root_department_id`。输入方式变化不应导致配置模型分裂。

### 3. 前后端按同一模式决策

前端渲染方式与后端校验方式必须来自同一份 manifest 元数据，避免出现“页面可填但保存失败”或“页面限制与后端校验不一致”的情况。

### 4. 兼容现有 provider，默认保守

未声明新元数据的旧 provider 默认按现有 `department_select` 语义处理，避免飞书等已接入能力被破坏。

## 推荐方案

采用“字段级范围输入模式”方案。

在 `user_sync` 对应 `business_template` 中，为 `root_department_id` 字段增加扩展元数据：

- `input_mode: "department_select" | "manual_input"`

语义定义：

- `department_select`
  - 表示该 provider 支持列举范围选项
  - 前端展示部门树选择器
  - 后端通过 `list_departments` 校验
- `manual_input`
  - 表示该 provider 需要用户手工输入范围
  - 前端展示普通文本输入框
  - 后端不再依赖 `list_departments` 校验

## 方案对比

### 方案 A：字段级 `input_mode`，推荐

- 优点
  - 保持 provider manifest 驱动模型完整
  - 新 provider 接入只需声明模式并实现自身 adapter
  - 前后端都可复用统一配置键
- 缺点
  - 需要扩展模板字段 schema
  - 需要前后端同步识别新元数据

### 方案 B：前端按 provider_key 特判

- 优点
  - 开发速度快
- 缺点
  - 页面逻辑会持续膨胀
  - 后端仍然需要补同等规模特判
  - 长期难维护

### 方案 C：重构成通用资源选择框架

- 优点
  - 长期抽象更完整
- 缺点
  - 明显超出当前需求
  - 投入与风险不成比例

结论：采用方案 A。

## 详细设计

### 一、数据模型

扩展 provider manifest 的字段元数据模型，使 `TemplateFieldManifest` 支持附加输入模式信息。

建议新增字段：

- `input_mode`
  - 取值：`department_select`、`manual_input`
  - 默认值：空；运行时按 `department_select` 兼容处理

对于 `user_sync` 业务模板：

- 飞书 provider 的 `root_department_id` 声明 `input_mode=department_select`
- AD provider 的 `root_department_id` 声明 `input_mode=manual_input`
- `manual_input` provider 不应在同一模板中声明 `department_id_type` 字段；该字段仅属于部门树模式

最终数据存储不变，仍保存在：

- `business_config.root_department_id`

### 二、前端渲染

前端重点改造 `UserSyncConfigFields.tsx`。

当前逻辑是：

- 只要 `field.key === "root_department_id"`，就固定渲染为 `TreeSelect`

目标逻辑是：

1. 读取 `root_department_id` 字段的 `input_mode`
2. 根据模式选择控件：
   - `department_select` -> `TreeSelect`
   - `manual_input` -> `Input` 或 `TextArea`

具体要求：

- `department_select`
  - 保持当前部门树加载逻辑
  - 保持加载失败、失效选择等提示
  - 继续使用 `department_options`
- `manual_input`
  - 不请求 `department_options`
  - 不展示部门树相关提示
  - 继续复用字段原生 `placeholder` 和 `help_text`
  - 表单校验仅保留必填与通用字符串校验

同步调整点：

- `UserSyncOperateModal.tsx`
  - 当前在切换实例时默认写入 `root_department_id="__all__"`
  - 调整为仅 `department_select` 模式下才写入该默认值
- `userSyncUtils.ts`
  - `getDefaultDepartmentIdType()` 仅在 `department_select` 模式下生效
  - `manual_input` 模式不自动注入 `department_id_type`
  - 当 provider 为 `manual_input` 时，前端忽略历史残留的 `department_id_type` 值，不参与提交构造

### 三、后端校验

后端重点改造 `UserSyncSourceSerializer.validate()`。

当前逻辑：

- 固定要求 `root_department_id` 存在
- 固定调用 `list_departments`
- 固定校验 `root_department_id` 必须存在于部门树返回值中

目标逻辑：

1. 根据 `integration_instance.provider_key` 找到 provider manifest
2. 定位 `user_sync` 对应 `business_template`
3. 读取 `root_department_id.input_mode`
4. 按模式决定校验方式

校验规则：

- `department_select`
  - 保持现有逻辑
  - 调用 `list_departments`
  - 做 `__all__` 归一化
  - 校验选中值必须在合法范围内
- `manual_input`
  - 校验 `root_department_id` 非空
  - 不调用 `list_departments`
  - 保存前忽略 `department_id_type` 等部门树模式遗留字段
  - 原样保留输入值写入 `business_config`

默认兼容策略：

- 当 manifest 未声明 `input_mode` 时，后端按 `department_select` 处理
- 当 provider 声明 `manual_input` 时，serializer 应主动剔除或忽略传入的 `department_id_type`

### 四、provider 与 adapter 职责

provider 的职责：

- 通过 manifest 声明 `root_department_id` 的输入方式
- 通过 adapter 消费 `business_config.root_department_id`

adapter 的职责：

- `department_select` provider
  - 实现 `list_departments`
  - `sync_users` 继续使用选择结果作为范围
- `manual_input` provider
  - 可不依赖 `list_departments`
  - `sync_users` 直接将 `root_department_id` 作为范围参数使用

说明：

- 不应依赖 `BaseUserSyncAdapter.list_departments()` 的默认“全部部门”虚拟节点来兼容 `manual_input`
- 因为当前问题不在“有没有默认返回值”，而在“是否应调用部门树校验”

### 五、AD 接入方式

本设计下，AD provider 的最小接入路径为：

1. 在 `user_sync` 的 `business_template` 中声明：
   - `root_department_id.input_mode = manual_input`
2. 在前端显示普通范围输入框
3. 在保存时后端仅做非空校验
4. 在 `sync_users` 中将 `business_config.root_department_id` 直接作为 AD 查询范围

这允许用户输入：

- `ou=paas,dc=bktest,dc=com`

而不需要平台先具备“枚举 AD OU 树”的能力。

### 六、历史数据兼容

本次改造默认不支持“同一个已上线 provider 从部门树模式切换为手工输入模式”的在线平滑迁移。

兼容约束如下：

- 已存在的飞书等 `department_select` provider 保持原模式，不变更为 `manual_input`
- `manual_input` 主要面向新接入 provider，例如 AD
- 若未来确实需要将既有 provider 从 `department_select` 切换为 `manual_input`，必须单独设计迁移方案，不纳入本次改造范围

原因：

- 已保存的 `root_department_id` 可能是 `__all__`、真实部门 ID 或历史部门树节点值
- 这些值对 `manual_input` provider 没有通用可解释语义
- 若直接透传到新 adapter，预览和正式同步可能误将历史树模式值当作原始范围字符串使用

因此本次实现采用保守策略：

- 不做自动迁移
- 不承诺跨模式复用旧数据
- 仅保证新增 `manual_input` provider 的数据模型与运行时链路成立

## 错误处理

### `department_select`

- 保持当前策略
- 部门加载失败时前端展示错误提示
- 已选部门失效时提示重新选择
- 保存时后端返回“所选范围无效”

### `manual_input`

- 第一阶段仅处理非空错误
- 若后续需要更严格规则，可在第二阶段增加：
  - manifest 声明正则 pattern
  - provider 自定义 `validate_scope`
  - serializer 调用 provider 级格式校验

本次设计不强制第一阶段实现 AD DN 语法校验，以降低落地复杂度。

### `department_options` 运行时行为

`department_options` 是公开运行时接口，本次需要明确其在 `manual_input` provider 下的合同：

- 前端不应主动请求 `manual_input` provider 的 `department_options`
- 后端收到这类请求时，应直接返回 `400`
- 返回信息应明确指出当前 provider 的范围输入模式不支持部门树选项加载

这样可以避免未来出现：

- 页面误调用后端接口却收到貌似可用的默认树数据
- 测试或外部调用方误以为 `manual_input` provider 仍支持部门树模式

## 测试策略

### 1. 飞书回归

- 创建用户同步源仍显示部门树
- 切换实例后仍可默认选择全部部门
- `department_options` 仍会按 `department_id_type` 刷新
- 无效部门值仍会被拒绝

### 2. `manual_input` 新模式

- 创建页展示输入框而不是部门树
- 不再请求 `department_options`
- 手工调用 `department_options` 时后端返回 `400`
- 可以输入 `ou=paas,dc=bktest,dc=com`
- 保存、预览、正式同步均可透传该值

### 3. 模式切换

- 从 `department_select` 切到 `manual_input` 时不残留 `__all__`
- 从 `manual_input` 切回 `department_select` 时恢复部门树逻辑
- 编辑已有 source 时回填值与控件类型一致

### 4. 兼容性

- 未声明 `input_mode` 的旧 provider 继续按部门树模式工作
- `manual_input` provider 的模板中不再声明 `department_id_type`
- serializer 对 `manual_input` 输入主动忽略遗留的 `department_id_type`

## 风险与缓解

### 风险 1：前端默认值污染

当前创建页默认写入 `root_department_id="__all__"`，若未按模式隔离，可能污染 `manual_input` provider 的真实输入。

缓解：

- 仅在 `department_select` 模式下注入该默认值

### 风险 2：后端仍隐式依赖部门树校验

若 preview、save 或 update 路径中仍保留固定 `list_departments` 依赖，会出现“页面能输入、保存时报错”。

缓解：

- 将校验入口统一收敛到 serializer 的模式分支

### 风险 3：字段 schema 前后端不同步

如果前端识别了 `input_mode` 但后端未识别，或反之，会造成行为不一致。

缓解：

- 同步扩展前后端字段 schema
- 为 `input_mode` 默认值补兼容测试

### 风险 4：既有 provider 被误改成 `manual_input`

如果后续把已有 `department_select` provider 直接改成 `manual_input`，历史保存值可能无法被新语义正确解释。

缓解：

- 将该场景明确视为单独迁移项目
- 本次范围内仅支持新增 `manual_input` provider，不支持既有 provider 在线切换语义

## 实施建议

按以下顺序落地：

1. 扩展 provider manifest 字段 schema，支持 `input_mode`
2. 前端将 `root_department_id` 渲染逻辑改为按模式分支
3. 后端 serializer 将范围校验改为按模式分支
4. 为飞书补回归测试
5. 为 `manual_input` 模式补新增测试

## 结论

推荐以 `root_department_id` 字段级 `input_mode` 为核心，将“部门选择”和“手工范围输入”统一纳入现有 provider manifest 体系：

- 前端按模式渲染
- 后端按模式校验
- provider 只声明模式并消费统一范围值

该方案可以在不推翻现有架构的前提下，为飞书等部门树 provider 保持兼容，同时为 AD 等手工范围 provider 提供清晰、低风险的接入路径。
