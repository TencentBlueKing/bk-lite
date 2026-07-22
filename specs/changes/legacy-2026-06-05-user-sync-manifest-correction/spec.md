# Historical Superpowers change: 2026-06-05-user-sync-manifest-correction

Status: done

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-05-user-sync-manifest-correction.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the current user-sync implementation so the second-step business parameter area is driven by the selected instance's provider manifest, field mapping remains a fixed editable area, and user-sync "test connection" performs a dry-run against real provider APIs and returns estimated sync counts.

**Architecture:** Keep `IntegrationInstance` responsible only for connection facts and capability readiness. Move provider-specific user-sync parameters into `UserSyncSource.business_config`, render those parameters from `provider.business_templates`, keep `field_mapping`/`schedule_config` as fixed user-sync page concerns, and add a dry-run path that reuses real provider sync fetch logic without persistence.

**Tech Stack:** Django REST Framework, Pydantic provider manifests, Next.js 16 + React 19 + TypeScript + Ant Design, existing node assert helper scripts, pytest

> **Status:** Completed on 2026-06-08.
>
> **Implementation notes:**
> - Task 1–Task 4 are complete.
> - Frontend preview was intentionally simplified to a `message`-based result prompt inside system-manager instead of adding an inline result card.
> - Shared/common frontend modules were not extended for this task; preview-specific handling stayed within system-manager code.
> - No new frontend helper test script was introduced; frontend validation stayed on touched system-manager files via existing TypeScript checks, with unrelated pre-existing `alarm` errors documented separately.
> - The current user-sync page exposes a page-level records entry and does not rely on shared/common component expansion for this task.

---

### Task 1: Refactor provider manifest structure to match the design plan

**Files:**
- Modify: `server/apps/system_mgmt/providers/schemas.py`
- Modify: `server/apps/system_mgmt/providers/manifests/feishu.py`
- Modify: `server/apps/system_mgmt/serializers/integration_instance_serializer.py`
- Modify: `web/src/app/system-manager/(pages)/integration-center/detail/page.tsx`
- Modify: `web/src/app/system-manager/types/integration-center.ts`
- Test: `server/apps/system_mgmt/tests/test_provider_manifest.py`

- [x] **Step 1: Write the failing manifest tests**

```python
def test_provider_manifest_public_dict_includes_business_templates():
    manifest = ProviderManifest.model_validate(
        {
            "key": "demo",
            "name": "Demo",
            "instance_templates": {"base_connection": {"title": "Base", "groups": []}},
            "business_templates": {
                "user_sync_form": {
                    "title": "User Sync",
                    "groups": [
                        {
                            "key": "pull",
                            "title": "拉取配置",
                            "fields": [{"key": "root_department_id", "label": "根部门 ID", "required": True}],
                        }
                    ],
                    "available_external_fields": ["user_id", "name"],
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
    assert public_dict["business_templates"]["user_sync_form"]["available_external_fields"] == ["user_id", "name"]
    assert public_dict["capabilities"][0]["business_template"] == "user_sync_form"
```

- [x] **Step 2: Run the provider manifest tests to verify they fail**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_provider_manifest.py -v`
Expected: FAIL because `ProviderManifest` still expects `business_template` to be a flat field list and has no `business_templates`.

- [x] **Step 3: Implement the minimal schema + manifest changes**

```python
class TemplateGroupManifest(BaseModel):
    key: str
    title: str
    description: str = ""
    fields: list[TemplateFieldManifest] = Field(default_factory=list)


class BusinessTemplateManifest(BaseModel):
    title: str
    groups: list[TemplateGroupManifest] = Field(default_factory=list)
    available_external_fields: list[str] = Field(default_factory=list)


class CapabilityManifest(BaseModel):
    ...
    business_template: str = Field(default="")


class ProviderManifest(BaseModel):
    instance_templates: dict[str, BusinessTemplateManifest] = Field(default_factory=dict)
    business_templates: dict[str, BusinessTemplateManifest] = Field(default_factory=dict)
```

In `feishu.py`, replace the flat `user_sync.business_template` field array with a `business_templates["user_sync_form"]` entry whose group contains:
- `root_department_id`
- `department_id_type`
- `user_id_type`
- `fetch_child`
- `status`

and set `available_external_fields` to the Feishu common field examples (for example `["user_id", "open_id", "name", "email", "mobile", "department_ids"]`).

Update existing manifest consumers so the current integration-center flow keeps working while user-sync moves to template-key lookup:
- `integration_instance_serializer.py` must continue validating instance-level connection templates and stop assuming business fields are inline capability arrays
- `integration-center/detail/page.tsx` and `types/integration-center.ts` must read `business_templates` without breaking the existing detail page rendering path

- [x] **Step 4: Re-run the provider manifest tests**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_provider_manifest.py -v`
Expected: PASS

> Completed: provider manifests now use `instance_templates + business_templates`, Feishu `user_sync` business fields are template-driven, and integration-center detail rendering remains backward compatible.

### Task 2: Move user-sync provider parameters into business_config and add dry-run preview behavior

**Files:**
- Modify: `server/apps/system_mgmt/models/user_sync_source.py`
- Modify: `server/apps/system_mgmt/migrations/0037_usersyncsource_business_fields.py` or create the next sequential migration after the current highest migration number
- Modify: `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
- Modify: `server/apps/system_mgmt/services/user_sync_service.py`
- Modify: `server/apps/system_mgmt/providers/adapters/feishu.py`
- Modify: `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
- Test: `server/apps/system_mgmt/tests/test_user_sync_service.py`
- Test: `server/apps/system_mgmt/tests/test_runtime_service.py`

- [x] **Step 1: Write failing backend tests for business_config and preview**

```python
def test_user_sync_source_serializer_accepts_business_config_for_ready_instance(...):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "source-a",
            "integration_instance": ready_instance.id,
            "root_group_name": "Feishu Root",
            "business_config": {
                "sync_scope": "department",
                "root_department_id": "0",
                "department_id_type": "department_id",
                "user_id_type": "user_id",
                "fetch_child": True,
                "status": "active",
            },
            "field_mapping": {"username": "user_id"},
            "schedule_config": {},
        }
    )
    assert serializer.is_valid(), serializer.errors


def test_preview_user_sync_returns_estimated_counts_without_creating_run(...):
    result = preview_user_sync(source_payload)
    assert result["result"] is True
    assert result["data"]["estimated_user_count"] == 2
    assert UserSyncRun.objects.count() == 0
```

- [x] **Step 2: Run the targeted backend tests to verify they fail**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_user_sync_service.py apps/system_mgmt/tests/test_runtime_service.py -v`
Expected: FAIL because `UserSyncSource` has no `business_config` field and there is no preview behavior.

- [x] **Step 3: Implement minimal backend changes**

```python
class UserSyncSource(...):
    business_config = models.JSONField(default=dict, blank=True)
    field_mapping = models.JSONField(default=dict, blank=True)
    schedule_config = models.JSONField(default=dict, blank=True)
```

Remove the accidental structured columns introduced during UI-only exploration:
- `address_book_app`
- `user_filter_rule`
- `organization_sync_mode`
- but **do not** remove `sync_scope` or `root_department_id` in this correction pass; keep them as compatibility fields until the new `business_config` shape is fully wired through runtime and existing rows are safely migrated

Add a data migration that copies current values into `business_config` for compatibility. At minimum, preserve existing values for:
- `root_department_id`
- `sync_scope`
- any accidental structured exploration fields already written to local rows

Make the runtime access pattern explicit and consistent in serializer/service/adapter code:

```python
def get_user_sync_business_value(source: UserSyncSource, key: str, default=None):
    if key in (source.business_config or {}):
        return source.business_config[key]
    return getattr(source, key, default)
```

Use that helper (or equivalent inline logic) everywhere user-sync parameters are consumed so preview and real sync both read:
- `business_config` first
- legacy top-level columns second

Treat `sync_scope` as an explicit user-sync business parameter throughout this task:
- keep it visible in the UI
- store it in `business_config["sync_scope"]`
- validate it in the serializer
- use it in preview/real sync to decide whether `root_department_id` is required

Add a preview path that reuses the real provider fetch logic but stops before persistence:

```python
def preview_user_sync(instance, source_payload):
    result = runtime_service.execute(
        provider_key=instance.provider_key,
        capability_key="user_sync",
        operation="sync_users",
        config=instance.get_runtime_config(),
        source=TransientUserSyncSource(source_payload),
        dry_run=True,
    )
    return {
        "result": result.success,
        "data": {
            "estimated_user_count": len(result.payload.get("user_list") or []),
            "estimated_group_count": len(result.payload.get("group_list") or []),
        },
    }
```

Expose `POST /system_mgmt/user_sync_source/preview/` on `UserSyncSourceViewSet`.

- [x] **Step 4: Re-run the targeted backend tests**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_user_sync_service.py apps/system_mgmt/tests/test_runtime_service.py -v`
Expected: PASS

> Completed: `UserSyncSource.business_config`, migration backfill, serializer compatibility logic, preview endpoint, and Feishu adapter business-config-first reads are all in place.

### Task 3: Rebuild the user-sync modal around provider business templates

**Files:**
- Modify: `web/src/app/system-manager/types/integration-center.ts`
- Modify: `web/src/app/system-manager/types/user-sync.ts`
- Modify: `web/src/app/system-manager/api/integration-center/index.ts`
- Modify: `web/src/app/system-manager/api/user-sync/index.ts`
- Modify: `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
- Modify: `web/src/app/system-manager/utils/userSyncUtils.ts`
- Test: existing TypeScript validation on touched user-sync / integration-center files

- [x] **Step 1: Write the failing frontend helper tests**

```ts
import assert from 'node:assert/strict';
import { buildUserSyncBusinessFields, invalidatePreviewResult } from '../src/app/system-manager/utils/userSyncUtils.ts';

assert.equal(
  buildUserSyncBusinessFields(provider, 'user_sync').groups[0].fields[0].key,
  'root_department_id'
);
assert.equal(invalidatePreviewResult({ dirty: false }, ['status']).dirty, true);
```

- [x] **Step 2: Run the helper tests to verify they fail**

Run: `cd web && pnpm exec tsx scripts/user-sync-helpers-test.ts`
Expected: FAIL because the helper utilities do not exist and the page still hard-codes `sync_scope`.

- [x] **Step 3: Implement the minimal frontend changes**

```ts
export interface BusinessTemplateGroup {
  key: string;
  title: string;
  description: string;
  fields: TemplateField[];
}

export interface ProviderCapability {
  ...
  business_template: string;
}

export interface ProviderManifest {
  ...
  business_templates: Record<string, { title: string; groups: BusinessTemplateGroup[]; available_external_fields: string[] }>;
}
```

In `page.tsx`:
- fetch the selected instance's provider manifest
- keep `sync_scope` visible as a first-class business parameter sourced from `business_config`
- render `user_sync` groups from `provider.business_templates[capability.business_template]`
- keep field mapping as a fixed editable area below the provider-driven groups
- render the `available_external_fields` hint under the mapping UI
- add a `测试连接` button in step 2 that calls the new preview API

- [x] **Step 4: Re-run the helper tests and TypeScript checks**

Run:
- `cd web && pnpm exec tsx scripts/user-sync-helpers-test.ts`
- `cd web && pnpm exec tsc -p tsconfig.lint.json --noEmit`

Expected:
- helper tests PASS
- `tsc` reports no new errors from touched user-sync/integration-center files (document any unrelated pre-existing repository errors if they persist outside touched files)

> Completed with adjustment: no new frontend helper test script was added; the user-sync modal was rebuilt around provider business templates, field mapping stayed fixed/editable, and validation used existing TypeScript checks. The remaining `alarm` errors are unrelated pre-existing issues.

### Task 4: Wire dry-run results into user-sync UX and protect regression edges

**Files:**
- Modify: `server/apps/system_mgmt/tests/test_user_sync_service.py`
- Modify: `server/apps/system_mgmt/tests/test_runtime_service.py`
- Modify: `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
- Modify: `web/src/app/system-manager/locales/zh.json`
- Modify: `web/src/app/system-manager/locales/en.json`
- Test: existing TypeScript validation on touched user-sync files

- [x] **Step 1: Write failing regression tests for preview/result invalidation**

```python
def test_preview_user_sync_uses_real_runtime_execute(...):
    result = preview_user_sync(...)
    assert result["data"]["estimated_user_count"] == 3
```

```ts
assert.equal(
  formatUserSyncPreview({ estimated_user_count: 10, estimated_group_count: 2 }),
  '预计同步用户 10，预计同步组织 2'
);
```

- [x] **Step 2: Run the tests to verify they fail**

Run:
- `cd server && uv run pytest apps/system_mgmt/tests/test_user_sync_service.py apps/system_mgmt/tests/test_runtime_service.py -v`
- `cd web && pnpm exec tsx scripts/user-sync-helpers-test.ts`

Expected: FAIL because preview formatting and regression coverage are missing.

- [x] **Step 3: Implement minimal UX and locale support**

Preview UX was intentionally simplified during implementation:
- keep a `测试连接` button in step 2
- show preview results through `message.success` / `message.error`
- do not add an inline result card or extra locale-driven preview state UI
- keep all preview-specific behavior inside system-manager modules only

- [x] **Step 4: Run the final targeted checks**

Run:
- `cd server && uv run pytest apps/system_mgmt/tests/test_provider_manifest.py apps/system_mgmt/tests/test_user_sync_service.py apps/system_mgmt/tests/test_runtime_service.py -v`
- `cd web && pnpm exec tsx scripts/user-sync-helpers-test.ts`
- `cd web && pnpm exec tsc -p tsconfig.lint.json --noEmit`

Expected: PASS

> Completed with adjustment: backend targeted tests passed; frontend `tsc -p tsconfig.lint.json --noEmit` confirmed no new errors in touched system-manager files, with unrelated pre-existing `alarm` errors still present outside this task's boundary.
