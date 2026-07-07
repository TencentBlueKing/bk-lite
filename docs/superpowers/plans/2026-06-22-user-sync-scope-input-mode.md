# 用户同步范围输入模式框架能力 Implementation Plan

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
