# Historical Superpowers change: 2026-06-23-integration-center

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-23-integration-center.md

> **For agentic workers:** REQUIRED EXECUTION STYLE: Use `superpowers:executing-plans` to implement this plan in a single mainline sequence. Follow the task order in this document, use lightweight validation between tasks, and perform full verification/review only after all planned tasks are complete. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement capability-level enablement switches, unify the available integration instances API, converge card list capability tags, and standardize instance option display format across integration center and downstream modules.

**Architecture:** Add `capability_enabled` JSONField to `IntegrationInstance` by rebuilding migration `0034`. Expose a single `available_instances` action on `IntegrationInstanceViewSet` filtered by capability, and remove duplicated actions from login-auth, user-sync, and IM-notification ViewSets. Update the detail page to render per-capability enablement controls and an unsaved-change guard before testing. Update the card list to remove primary status tags and render provider-declared capability tags with green/gray binary coloring. Update downstream modals to consume the unified API and display `display_name`.

**Tech Stack:** Django 4.2, DRF, Next.js 16, React 19, TypeScript, Ant Design, Tailwind CSS

## Execution Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If design intent, capability semantics, filter rules, or frontend behavior becomes unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to the integration-center issues covered by the spec; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- Prefer no temporary compatibility layer unless explicitly required.
- Execute this plan in `executing-plans` style: follow the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.

---

## File Structure

### Backend files to modify

- `server/apps/system_mgmt/models/integration_instance.py`
  Add `capability_enabled` JSONField to `IntegrationInstance`.

- `server/apps/system_mgmt/migrations/0034_integrationinstance.py`
  Rebuild the migration to include `capability_enabled`. No new migration file should be added.

- `server/apps/system_mgmt/serializers/integration_instance_serializer.py`
  Add `display_name` SerializerMethodField, allow reading/writing `capability_enabled`, and validate capability keys against the provider manifest.

- `server/apps/system_mgmt/viewset/integration_instance_viewset.py`
  Add a unified `available_instances` action that filters by capability and returns `display_name`; keep existing list/retrieve/create/update/destroy/test_connection behavior intact.

- `server/apps/system_mgmt/viewset/login_auth_binding_viewset.py`
  Remove the `available_instances` action; the frontend will call the integration-center endpoint instead.

- `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
  Remove the `available_instances` action; the frontend will call the integration-center endpoint instead.

- `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
  Remove the `available_instances` action; the frontend will call the integration-center endpoint instead.

- `server/apps/system_mgmt/tests/test_integration_instance_serializer.py`
  Add coverage for `capability_enabled` default values, validation, and `display_name`.

- `server/apps/system_mgmt/tests/test_integration_instance_viewset.py`
  Add coverage for the unified `available_instances` action, including filtering by capability, excluding builtin provider, and respecting `enabled`/`status`/`capability_enabled`/`capability_status`.

- `server/apps/system_mgmt/tests/test_builtin_platform_login_auth.py`
  Update or add assertions confirming the builtin provider is not returned by the unified `available_instances` endpoint.

### Frontend files to modify

- `web/src/app/system-manager/types/integration-center.ts`
  Extend `IntegrationInstance` with `capability_enabled`; add `AvailableInstance` type if needed.

- `web/src/app/system-manager/api/integration-center/index.ts`
  Add `getAvailableInstances(capability: string)` calling the unified endpoint.

- `web/src/app/system-manager/utils/intergrationCenter.ts`
  Update `buildIntegrationInstanceCardItem`, `isIntegrationInstanceStarted`, and add helpers for capability enablement / tag color.

- `web/src/app/system-manager/(pages)/integration-center/detail/page.tsx`
  Render per-capability platform-state label and enable/disable button; guard test connection when the form is dirty.

- `web/src/app/system-manager/(pages)/integration-center/page.tsx`
  Remove primary status tag from cards; render capability tags only for provider-declared capabilities using green/gray binary coloring.

- Login-auth / user-sync / IM-notification modal pages
  Replace calls to the old per-module `available_instances` endpoints with the unified integration-center endpoint, and use `display_name` for option labels.

---

## Task 1: Update the data model and migration

**Files:**
- Modify: `server/apps/system_mgmt/models/integration_instance.py`
- Modify: `server/apps/system_mgmt/migrations/0034_integrationinstance.py`

- [ ] **Step 1: Add `capability_enabled` to the model**

In `server/apps/system_mgmt/models/integration_instance.py`, add the new field after `capability_status`:

```python
    capability_status = models.JSONField(default=dict)
    capability_enabled = models.JSONField(default=dict)
```

- [ ] **Step 2: Rebuild migration 0034**

In `server/apps/system_mgmt/migrations/0034_integrationinstance.py`, add the corresponding field inside the `IntegrationInstance` `fields` list:

```python
                (
                    "capability_enabled",
                    models.JSONField(default=dict),
                ),
```

Keep it adjacent to `capability_status` for readability.

- [ ] **Step 3: Validate the migration locally**

Run:

```bash
cd server
uv run python manage.py migrate system_mgmt 0033
uv run python manage.py migrate
```

Expected:
- Migration applies without errors.
- The `system_mgmt_integrationinstance` table includes the `capability_enabled` column.

---

## Task 2: Update the serializer

**Files:**
- Modify: `server/apps/system_mgmt/serializers/integration_instance_serializer.py`

- [ ] **Step 1: Add `display_name` and allow `capability_enabled` serialization**

At the top of `IntegrationInstanceSerializer`, add:

```python
    display_name = serializers.SerializerMethodField()
```

Add the method:

```python
    def get_display_name(self, obj):
        manifest = get_provider_registry().get(obj.provider_key)
        provider_name = manifest.name if manifest else obj.provider_key
        return f"{obj.name}({provider_name})"
```

Because `Meta.fields = "__all__"`, `capability_enabled` is already included in serialization. We only need to validate it.

- [ ] **Step 2: Validate `capability_enabled` keys against the provider manifest**

Inside `validate(self, attrs)`, after the existing provider_key/manifest checks, add:

```python
        capability_enabled = attrs.get("capability_enabled")
        if capability_enabled is not None and manifest is not None:
            allowed_capabilities = {capability.key for capability in manifest.capabilities}
            invalid_keys = set(capability_enabled.keys()) - allowed_capabilities
            if invalid_keys:
                raise serializers.ValidationError(
                    {"capability_enabled": f"Invalid capability keys: {', '.join(sorted(invalid_keys))}"}
                )
```

- [ ] **Step 3: Set default `capability_enabled` on create**

In `create(self, validated_data)`, after getting the manifest, add:

```python
        validated_data["capability_enabled"] = {
            capability.key: True for capability in manifest.capabilities
        }
```

Place it before the existing `capability_status` initialization so the two blocks are adjacent.

- [ ] **Step 4: Run backend lint / import checks**

Run:

```bash
cd server
uv run python -m py_compile apps/system_mgmt/serializers/integration_instance_serializer.py
```

Expected:
- No syntax or import errors.

---

## Task 3: Add the unified `available_instances` action

**Files:**
- Modify: `server/apps/system_mgmt/viewset/integration_instance_viewset.py`

- [ ] **Step 1: Add the action**

Add the following action to `IntegrationInstanceViewSet`, after the existing `test_connection` action or near the other actions:

```python
    builtin_provider_key = "bk_lite_builtin"

    @action(methods=["GET"], detail=False)
    @HasPermission("integration_center-View")
    def available_instances(self, request):
        capability = request.query_params.get("capability")
        if not capability:
            return Response({"result": False, "message": "capability is required"}, status=400)

        queryset = IntegrationInstance.objects.filter(
            enabled=True,
            status=IntegrationInstanceStatusChoices.READY,
        ).exclude(provider_key=self.builtin_provider_key)

        instances = []
        for item in queryset.order_by("name", "id"):
            if (
                item.capability_enabled.get(capability) is True
                and item.capability_status.get(capability) == IntegrationInstanceStatusChoices.READY
            ):
                manifest = get_provider_registry().get(item.provider_key)
                provider_name = manifest.name if manifest else item.provider_key
                instances.append({
                    "id": item.id,
                    "name": item.name,
                    "provider_key": item.provider_key,
                    "display_name": f"{item.name}({provider_name})",
                })
        return Response(instances)
```

Note: `get_provider_registry()` is already imported in this viewset. If not, add `from apps.system_mgmt.providers import get_provider_registry` alongside the existing provider imports.

- [ ] **Step 2: Run a lightweight endpoint smoke test**

Start the dev server (or use Django shell) and call:

```bash
curl -u admin:password "http://127.0.0.1:8011/system_mgmt/integration_instance/available_instances/?capability=login_auth"
```

Expected:
- Returns a list (possibly empty if no instances match).
- Builtin provider is never in the list.
- Response items include `id`, `name`, `provider_key`, and `display_name`.

---

## Task 4: Remove duplicated `available_instances` actions

**Files:**
- Modify: `server/apps/system_mgmt/viewset/login_auth_binding_viewset.py`
- Modify: `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
- Modify: `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`

- [ ] **Step 1: Remove the action from `LoginAuthBindingViewSet`**

Delete the `available_instances` method and its `@action` decorator from `server/apps/system_mgmt/viewset/login_auth_binding_viewset.py`.

Remove the `IntegrationInstance` and `IntegrationInstanceStatusChoices` imports if they are no longer used in that file.

- [ ] **Step 2: Remove the action from `UserSyncSourceViewSet`**

Delete the `available_instances` method and its `@action` decorator from `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`.

Remove the `IntegrationInstance` and `IntegrationInstanceStatusChoices` imports if they are no longer used.

- [ ] **Step 3: Remove the action from `IMNotificationChannelViewSet`**

Delete the `available_instances` method and its `@action` decorator from `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`.

Remove the `IntegrationInstance` and `IntegrationInstanceStatusChoices` imports if they are no longer used.

- [ ] **Step 4: Verify the old endpoints are gone**

Run:

```bash
cd server
uv run python manage.py show_urls | grep available_instances
```

Expected:
- Only one result: `/system_mgmt/integration_instance/available_instances/`

---

## Task 5: Add backend tests

**Files:**
- Modify: `server/apps/system_mgmt/tests/test_integration_instance_serializer.py`
- Modify: `server/apps/system_mgmt/tests/test_integration_instance_viewset.py`
- Modify: `server/apps/system_mgmt/tests/test_builtin_platform_login_auth.py`

- [ ] **Step 1: Test `capability_enabled` defaults and validation in the serializer**

In `test_integration_instance_serializer.py`, add:

```python
import pytest
from apps.system_mgmt.models import IntegrationInstance


@pytest.mark.django_db
class TestIntegrationInstanceSerializerCapabilityEnabled:
    def test_create_sets_default_capability_enabled(self, feishu_provider):
        # Assumes a factory or fixture that creates an IntegrationInstance
        instance = IntegrationInstance.objects.create(
            name="Test",
            provider_key="feishu",
            config={},
            capability_status={},
            capability_enabled={},
        )
        assert instance.capability_enabled == {
            "login_auth": True,
            "user_sync": True,
            "im_notification": True,
        }

    def test_update_rejects_invalid_capability_enabled_keys(self, feishu_instance, api_client):
        url = f"/system_mgmt/integration_instance/{feishu_instance.id}/"
        response = api_client.put(url, {
            "name": feishu_instance.name,
            "provider_key": feishu_instance.provider_key,
            "capability_enabled": {"nonexistent": True},
        }, format="json")
        assert response.status_code == 400
        assert "capability_enabled" in response.data
```

Adjust fixtures/names to match the existing test conventions in the file.

- [ ] **Step 2: Test the unified `available_instances` action**

In `test_integration_instance_viewset.py`, add:

```python
import pytest
from apps.system_mgmt.models import IntegrationInstance, IntegrationInstanceStatusChoices


@pytest.mark.django_db
class TestIntegrationInstanceAvailableInstances:
    def test_filters_by_capability(self, ready_feishu_instance):
        ready_feishu_instance.capability_enabled = {"login_auth": True}
        ready_feishu_instance.capability_status = {"login_auth": IntegrationInstanceStatusChoices.READY}
        ready_feishu_instance.save()

        response = api_client.get("/system_mgmt/integration_instance/available_instances/?capability=login_auth")
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["display_name"] == "总部通讯录（飞书）"

    def test_excludes_disabled_capability(self, ready_feishu_instance):
        ready_feishu_instance.capability_enabled = {"login_auth": False}
        ready_feishu_instance.capability_status = {"login_auth": IntegrationInstanceStatusChoices.READY}
        ready_feishu_instance.save()

        response = api_client.get("/system_mgmt/integration_instance/available_instances/?capability=login_auth")
        assert response.status_code == 200
        assert len(response.data) == 0

    def test_excludes_builtin_provider(self, builtin_instance):
        builtin_instance.capability_enabled = {"login_auth": True}
        builtin_instance.capability_status = {"login_auth": IntegrationInstanceStatusChoices.READY}
        builtin_instance.save()

        response = api_client.get("/system_mgmt/integration_instance/available_instances/?capability=login_auth")
        assert response.status_code == 200
        assert not any(item["provider_key"] == "bk_lite_builtin" for item in response.data)
```

- [ ] **Step 3: Run the new backend tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_integration_instance_serializer.py apps/system_mgmt/tests/test_integration_instance_viewset.py apps/system_mgmt/tests/test_builtin_platform_login_auth.py -v
```

Expected:
- New tests pass.
- Existing tests in these files still pass.

---

## Task 6: Update frontend types and API

**Files:**
- Modify: `web/src/app/system-manager/types/integration-center.ts`
- Modify: `web/src/app/system-manager/api/integration-center/index.ts`

- [ ] **Step 1: Extend `IntegrationInstance` type**

In `web/src/app/system-manager/types/integration-center.ts`, add `capability_enabled` and `display_name` to `IntegrationInstance`:

```typescript
export interface IntegrationInstance {
  id: number;
  name: string;
  display_name?: string;
  provider_key: string;
  provider: { key: string; name: string };
  description: string;
  enabled: boolean;
  status: InstanceStatus;
  capability_status: Record<string, InstanceStatus>;
  capability_enabled: Record<string, boolean>;
  team: number[];
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: Add `AvailableInstance` type**

In the same file, add:

```typescript
export interface AvailableInstance {
  id: number;
  name: string;
  provider_key: string;
  display_name: string;
}
```

- [ ] **Step 3: Add `getAvailableInstances` API helper**

In `web/src/app/system-manager/api/integration-center/index.ts`, add:

```typescript
  async function getAvailableInstances(capability: string): Promise<AvailableInstance[]> {
    return await get('/system_mgmt/integration_instance/available_instances/', {
      params: { capability },
    });
  }
```

And export it in the returned object:

```typescript
  return {
    getProviders,
    getInstances,
    getInstance,
    createInstance,
    updateInstance,
    deleteInstance,
    testConnection,
    getAvailableInstances,
  };
```

- [ ] **Step 4: Run TypeScript check on touched files**

Run:

```bash
cd web
pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected:
- No new type errors introduced by these changes.

---

## Task 7: Add capability enablement controls to the detail page

**Files:**
- Modify: `web/src/app/system-manager/(pages)/integration-center/detail/page.tsx`

- [ ] **Step 1: Track form dirty state**

Add a `isFormDirty` state:

```typescript
  const [isFormDirty, setIsFormDirty] = useState(false);
```

In the existing `useEffect` that sets form values, also reset dirty state:

```typescript
  useEffect(() => {
    if (!instance) return;
    const configValues = activeFields.reduce<Record<string, unknown>>((acc, field) => {
      if (!field.write_only) {
        const savedValue = instance.config?.[field.key];
        acc[field.key] = savedValue ?? field.default;
      }
      return acc;
    }, {});
    form.setFieldsValue({ config: configValues });
    setIsFormDirty(false);
  }, [activeFields, form, instance]);
```

Add `onValuesChange` to the `Form` components in both the base and capability tab branches:

```tsx
<Form form={form} layout="vertical" onValuesChange={() => setIsFormDirty(true)}>
```

Apply this change to both `base` form (around line 283) and capability form (around line 322).

- [ ] **Step 2: Add enable/disable capability handler**

Add:

```typescript
  const handleToggleCapability = async (enabled: boolean) => {
    if (!id || Number.isNaN(numericId) || !instance || activeTab === 'base') {
      return;
    }

    const nextCapabilityEnabled = {
      ...instance.capability_enabled,
      [activeTab]: enabled,
    };

    setSaving(true);
    try {
      await updateInstance(numericId, {
        name: instance.name,
        provider_key: instance.provider_key,
        description: instance.description || '',
        capability_enabled: nextCapabilityEnabled,
      });
      message.success(enabled ? t('system.integrationCenter.capabilityEnabled') : t('system.integrationCenter.capabilityDisabled'));
      fetchDetailData();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };
```

- [ ] **Step 3: Guard test connection when form is dirty**

Ensure `Modal` is imported from `antd` at the top of the file:

```typescript
import { Button, Form, Input, InputNumber, Modal, Select, Spin, Switch, Tabs, message } from 'antd';
```

Modify `handleTestConnection`:

```typescript
  const handleTestConnection = async () => {
    if (!id || Number.isNaN(numericId)) {
      return;
    }

    if (isFormDirty) {
      Modal.confirm({
        title: t('system.integrationCenter.unsavedConfigTitle', '配置未保存'),
        content: t('system.integrationCenter.unsavedConfigContent', '当前配置有未保存的修改，请先保存后再测试。'),
        okText: t('common.save', '保存'),
        cancelText: t('common.cancel', '取消'),
        onOk: handleSave,
      });
      return;
    }

    setTesting(true);
    try {
      const result = await testConnection(numericId, activeTab === 'base' ? undefined : activeTab);
      if (result.result) {
        message.success(t('system.integrationCenter.testSuccess'));
      } else {
        message.error(t('system.integrationCenter.testFailed'));
      }
      fetchDetailData();
    } catch (error) {
      if (!isSilentRequestError(error)) {
        message.error(t('system.integrationCenter.testFailed'));
      }
    } finally {
      setTesting(false);
    }
  };
```

- [ ] **Step 4: Render platform-state label and enable/disable button**

In the footer rendering, replace the static capability status display with platform state + enable/disable button:

```tsx
            <div className="text-[14px] text-[var(--color-text-2)]">
              {t('system.integrationCenter.testStatus', '测试状态')}：
              <span className="ml-2 inline-flex items-center gap-2">
                <span className={`h-2.5 w-2.5 rounded-full ${
                  currentCapabilityStatus === 'ready'
                    ? 'bg-emerald-500'
                    : currentCapabilityStatus === 'verification_failed'
                      ? 'bg-red-500'
                      : 'bg-slate-400'
                }`} />
                <span className="text-[var(--color-text)]">
                  {activeTab === 'base'
                    ? getIntegrationTestStatusText(instance.status, t)
                    : getIntegrationCapabilityStatusText(currentCapabilityStatus || 'pending_verification', t)}
                </span>
              </span>
            </div>

            {activeTab !== 'base' && (
              <div className="text-[14px] text-[var(--color-text-2)]">
                {t('system.integrationCenter.platformStatus', '平台状态')}：
                <span className="ml-2 inline-flex items-center gap-2">
                  <span className={`h-2.5 w-2.5 rounded-full ${
                    instance.capability_enabled?.[activeTab] ? 'bg-emerald-500' : 'bg-slate-400'
                  }`} />
                  <span className="text-[var(--color-text)]">
                    {instance.capability_enabled?.[activeTab]
                      ? t('system.integrationCenter.enabled', '已启用')
                      : t('system.integrationCenter.disabled', '未启用')}
                  </span>
                </span>
              </div>
            )}

            {activeTab !== 'base' && (
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button
                  onClick={() => handleToggleCapability(!instance.capability_enabled?.[activeTab])}
                  loading={saving}
                >
                  {instance.capability_enabled?.[activeTab]
                    ? t('system.integrationCenter.disableCapability', '禁用能力')
                    : t('system.integrationCenter.enableCapability', '启用能力')}
                </Button>
              </PermissionWrapper>
            )}
```

Insert these blocks before or near the existing Save/Test buttons.

- [ ] **Step 5: Run lint on the detail page**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/\(pages\)/integration-center/detail/page.tsx
```

Expected:
- No new lint errors.

---

## Task 8: Converge card list capability tags

**Files:**
- Modify: `web/src/app/system-manager/utils/intergrationCenter.ts`
- Modify: `web/src/app/system-manager/(pages)/integration-center/page.tsx`

- [ ] **Step 1: Add capability tag helpers**

In `web/src/app/system-manager/utils/intergrationCenter.ts`, add:

```typescript
export function getIntegrationCapabilityEnabled(
  instance: Pick<IntegrationInstance, 'capability_enabled'>,
  capabilityKey: string,
): boolean {
  return Boolean(instance.capability_enabled?.[capabilityKey]);
}

export function getIntegrationCapabilityTagColor(
  instance: IntegrationInstance,
  capabilityKey: string,
): 'green' | 'default' {
  const enabled = getIntegrationCapabilityEnabled(instance, capabilityKey);
  const ready = instance.capability_status?.[capabilityKey] === 'ready';
  return enabled && ready ? 'green' : 'default';
}
```

- [ ] **Step 2: Remove primary status tag from card item**

Update `buildIntegrationInstanceCardItem` to return an empty `tagList`:

```typescript
export function buildIntegrationInstanceCardItem(
  instance: IntegrationInstance,
  t: (key: string, fallback?: string) => string,
) {
  return {
    id: instance.id,
    name: instance.name,
    icon: resolveIntegrationProviderIcon(instance.provider_key),
    description: instance.provider?.name || instance.provider_key,
    tagList: [],
    raw: instance,
  };
}
```

- [ ] **Step 3: Render provider-declared capability tags with binary coloring**

In `web/src/app/system-manager/(pages)/integration-center/page.tsx`, update `generateDescSlot` to use the provider's declared capabilities instead of `capability_status` keys:

```tsx
  const generateDescSlot = (data: { raw: IntegrationInstance }) => {
    const provider = providers.find((p) => p.key === data.raw.provider_key);
    const capabilityKeyMap: Record<string, string> = {
      user_sync: 'userSync',
      login_auth: 'loginAuth',
      im_notification: 'imNotification',
    };

    const capabilitiesTag = (provider?.capabilities || []).map((capability) => {
      const color = getIntegrationCapabilityTagColor(data.raw, capability.key);
      return (
        <Tag
          key={capability.key}
          bordered
          color={color}
          className={`mr-0 rounded-md font-mini ${
            color === 'green'
              ? 'border-[#b7eb8f] bg-[#f6ffed] text-[#389e0d]'
              : 'border-[#d9d9d9] bg-[#fafafa] text-[#8c8c8c]'
          }`}
        >
          <span className="flex items-center gap-1">
            <span className={`h-2 w-2 rounded-full ${color === 'green' ? 'bg-[#389e0d]' : 'bg-[#bfbfbf]'}`} />
            <span>{t(`system.integrationCenter.capability.${capabilityKeyMap[capability.key]}`)}</span>
          </span>
        </Tag>
      );
    });

    return (
      <div className='flex flex-wrap justify-end gap-1'>
        {capabilitiesTag}
      </div>
    );
  };
```

- [ ] **Step 4: Run lint on the card list page and utility file**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/\(pages\)/integration-center/page.tsx src/app/system-manager/utils/intergrationCenter.ts
```

Expected:
- No new lint errors.

---

## Task 9: Update downstream modals to use the unified API

**Files:**
- Modify: `web/src/app/system-manager/api/login-auth/index.ts`
- Modify: `web/src/app/system-manager/api/user-sync/index.ts`
- Modify: `web/src/app/system-manager/api/im-notification/index.ts`
- Modify: `web/src/app/system-manager/(pages)/user/login-auth/page.tsx`
- Modify: `web/src/app/system-manager/components/user/user-sync/UserSyncBasicModal.tsx`
- Modify: `web/src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx`
- Modify: `web/src/app/system-manager/components/user/user-sync/UserSyncConfigModal.tsx`
- Modify: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`

- [ ] **Step 1: Update the login-auth API helper**

In `web/src/app/system-manager/api/login-auth/index.ts`, replace the existing `getAvailableInstances` implementation with:

```typescript
  async function getAvailableInstances(): Promise<AvailableInstance[]> {
    return await get('/system_mgmt/integration_instance/available_instances/', {
      params: { capability: 'login_auth' },
    });
  }
```

- [ ] **Step 2: Update the login-auth modal option label**

In `web/src/app/system-manager/(pages)/user/login-auth/page.tsx` around line 450, change:

```tsx
options={availableInstances.map(i => ({ value: i.id, label: i.name }))}
```

to:

```tsx
options={availableInstances.map((i) => ({ value: i.id, label: i.display_name || i.name }))}
```

- [ ] **Step 3: Update the user-sync API helper**

In `web/src/app/system-manager/api/user-sync/index.ts`, replace the existing `getAvailableInstances` implementation with:

```typescript
  async function getAvailableInstances(): Promise<AvailableInstance[]> {
    return await get('/system_mgmt/integration_instance/available_instances/', {
      params: { capability: 'user_sync' },
    });
  }
```

- [ ] **Step 4: Update user-sync option labels**

In the following files, update any `availableInstances.map(...)` that builds Select options to use `display_name`:

- `web/src/app/system-manager/components/user/user-sync/UserSyncBasicModal.tsx`
- `web/src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx`
- `web/src/app/system-manager/components/user/user-sync/UserSyncConfigModal.tsx`

Change patterns like:

```tsx
instanceOptions = availableInstances.map((inst) => ({ value: inst.id, label: inst.name }))
```

to:

```tsx
instanceOptions = availableInstances.map((inst) => ({ value: inst.id, label: inst.display_name || inst.name }))
```

- [ ] **Step 5: Update the IM-notification API helper**

In `web/src/app/system-manager/api/im-notification/index.ts`, replace the existing `getAvailableInstances` implementation with:

```typescript
  async function getAvailableInstances(): Promise<AvailableInstance[]> {
    return await get('/system_mgmt/integration_instance/available_instances/', {
      params: { capability: 'im_notification' },
    });
  }
```

- [ ] **Step 6: Update the IM-notification modal option label**

In `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx` around line 867, change:

```tsx
options={availableInstances.map((instance) => ({ value: instance.id, label: instance.name }))}
```

to:

```tsx
options={availableInstances.map((instance) => ({ value: instance.id, label: instance.display_name || instance.name }))}
```

- [ ] **Step 7: Update the shared `AvailableInstance` type**

If `AvailableInstance` is defined locally in each of the above modules, update it to include `display_name`:

```typescript
interface AvailableInstance {
  id: number;
  name: string;
  display_name: string;
  provider_key: string;
}
```

Alternatively, import `AvailableInstance` from `web/src/app/system-manager/types/integration-center.ts` and remove the local duplicates.

- [ ] **Step 8: Run lint and type-check**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/api/login-auth/index.ts src/app/system-manager/api/user-sync/index.ts src/app/system-manager/api/im-notification/index.ts src/app/system-manager/\(pages\)/user/login-auth/page.tsx src/app/system-manager/components/user/user-sync/UserSyncBasicModal.tsx src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx src/app/system-manager/components/user/user-sync/UserSyncConfigModal.tsx src/app/system-manager/\(pages\)/channel/im-notification/page.tsx
pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected:
- No new lint or type errors.

---

## Task 10: Final verification and review

- [ ] **Step 1: Run full backend tests for touched apps**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_integration_instance_serializer.py apps/system_mgmt/tests/test_integration_instance_viewset.py apps/system_mgmt/tests/test_builtin_platform_login_auth.py apps/system_mgmt/tests/test_im_notification_viewset.py apps/system_mgmt/tests/test_user_sync_service.py -v
```

Expected:
- All tests pass.

- [ ] **Step 2: Run full frontend validation**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/\(pages\)/integration-center/ src/app/system-manager/\(pages\)/user/login-auth/ src/app/system-manager/\(pages\)/user/user-sync/ src/app/system-manager/\(pages\)/channel/im-notification/ src/app/system-manager/api/integration-center/ src/app/system-manager/utils/intergrationCenter.ts src/app/system-manager/types/integration-center.ts
pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected:
- No new lint or type errors.

- [ ] **Step 3: Manual end-state verification**

Checklist:
- Integration center detail page shows per-capability platform-state label and enable/disable button.
- Clicking test connection with unsaved changes shows a "save first" confirmation.
- Disabling a capability removes the instance from the corresponding downstream modal's integration-instance dropdown.
- Re-enabling a capability restores it to the dropdown (if the capability status is ready).
- Card list no longer shows the primary status tag.
- Card list shows capability tags only for provider-declared capabilities.
- Ready + enabled capabilities show green tags; others show gray tags.
- Downstream modal dropdown options display `名称（系统类型）` format.
- Builtin provider (`bk_lite_builtin`) is not shown in any dropdown.

- [ ] **Step 4: Review implementation against the spec**

Checklist:
- `capability_enabled` is added via rebuilt migration 0034.
- Unified `available_instances` action exists on `IntegrationInstanceViewSet` only.
- The three business ViewSets no longer have their own `available_instances` actions.
- `display_name` is generated by the backend.
- Frontend types include `capability_enabled`.
- Detail page guards test connection on dirty form state.
- Card list uses binary green/gray coloring for capability tags.
- No temporary compatibility layer was introduced.

---

## Spec Coverage

| Spec Section | Implementing Task |
| --- | --- |
| Data model: `capability_enabled` JSONField | Task 1 |
| Migration: rebuild 0034 | Task 1 |
| Serializer: `display_name` + validation | Task 2 |
| Unified `available_instances` API | Task 3 |
| Remove duplicated business APIs | Task 4 |
| Backend tests | Task 5 |
| Frontend types + API helper | Task 6 |
| Detail page enablement controls + dirty guard | Task 7 |
| Card list tag convergence | Task 8 |
| Downstream modal updates | Task 9 |
| Final verification | Task 10 |

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-23-integration-center.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach would you prefer?

## specs: 2026-06-23-integration-center-design.md

## 背景

集成中心（Integration Center）是 BK-Lite 系统管理模块中管理第三方集成系统实例的入口。当前存在以下体验与架构问题：

1. **能力缺少显式启停开关**：详情页各能力（登录认证 / 用户同步 / IM 通知）只能看到测试状态，无法单独启用或禁用。
2. **未保存配置直接测试会使用旧值**：详情页“保存”与“测试连接”是独立按钮，测试接口只接收 `capability_key`，不接收当前表单值。
3. **能力状态与操作流程不够闭环**：详情页缺少“配置 → 保存 → 启用/禁用 → 测试”的完整操作入口。
4. **卡片列表能力 Tag 表达冗余**：当前卡片同时显示实例级主状态 Tag 和能力 Tag，且能力 Tag 未按 provider manifest 声明的能力过滤。
5. **业务弹窗选项格式不统一**：登录认证、用户同步、IM 通知等页面引用集成实例时，下拉选项只显示 `name`，同名实例难以区分。
6. **可用实例接口重复且可见策略未统一**：三个业务模块各自实现了 `available_instances` 接口，都直接遍历 `IntegrationInstance.objects.all()`，未继承集成中心的访问控制逻辑。

## 设计目标

- 在集成实例上引入能力级启停控制，且不破坏业务模型自身的启用状态。
- 统一可用实例接口，由集成中心提供，业务模块只负责消费。
- 收敛卡片列表的视觉表达，去掉主状态 Tag，按 provider 能力渲染能力 Tag。
- 统一业务弹窗中的集成实例展示格式为 `名称（系统类型）`。
- 明确集成实例能力启停与业务实例启停的分层：
  - 集成实例能力启停 → 决定业务弹窗能否选到该实例
  - 业务实例启停 → 决定外部能否访问到该业务实例

## 关键决策

| 决策项 | 选择 | 原因 |
| --- | --- | --- |
| 能力启停存储方式 | 新增 `capability_enabled` JSONField，保留现有 `capability_status` | 能力数量少（最多 3 个），JSONField 足够；比统一 `capabilities` JSONField 改动小，比关系表更轻量 |
| Migration 策略 | 直接修改 `0034_integrationinstance.py`，不新增 migration | 线上共享数据库当前只到 `0033`，`0034` 尚未上线；本地开发者需回滚重建 |
| 可用实例接口 | 由 `IntegrationInstanceViewSet` 统一提供，业务模块删除重复实现 | 消除三处重复代码，统一过滤规则和展示字段 |
| 组织隔离 | `available_instances` 不过滤 `team` | 创建/编辑弹窗没有组织选择入口，原型也未体现；等入口明确后再补 |
| 内建 provider | 在 `available_instances` 中排除 `bk_lite_builtin` | 内建账户体系不应作为第三方集成系统被业务模块引用 |
| 未保存配置测试 | 弹窗提示“请先保存” | 不改变数据库状态，也不引入临时配置测试接口，实现最简单 |

## 数据模型

### IntegrationInstance 变更

在 `server/apps/system_mgmt/models/integration_instance.py` 中新增字段：

```python
class IntegrationInstance(MaintainerInfo, TimeInfo, EncryptMixin):
    name = models.CharField(max_length=100)
    provider_key = models.CharField(max_length=64, db_index=True)
    config = models.JSONField(default=dict)
    status = models.CharField(
        max_length=32,
        choices=IntegrationInstanceStatusChoices.choices,
        default=IntegrationInstanceStatusChoices.PENDING_VERIFICATION,
    )
    capability_status = models.JSONField(default=dict)
    capability_enabled = models.JSONField(default=dict)  # 新增
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")
    team = models.JSONField(default=list)
```

`capability_enabled` 结构示例：

```json
{
  "login_auth": true,
  "user_sync": false,
  "im_notification": true
}
```

约束：

- key 必须为 provider manifest 声明的能力。
- 创建实例时，声明的能力默认 `enabled=true`。
- 未声明的能力不会出现；不存在的 key 视为 `false`。

### Migration 说明

直接修改 `server/apps/system_mgmt/migrations/0034_integrationinstance.py`，将 `capability_enabled` 字段加入 `IntegrationInstance` 的 `fields` 列表。

> 注意：线上共享数据库当前仅应用至 `0033`，因此修改 `0034` 不会影响线上。本地已应用 `0034` 的环境需回滚后重建：
>
> ```bash
> cd server
> uv run python manage.py migrate system_mgmt 0033
> uv run python manage.py migrate
> ```

## API 设计

### 统一可用实例接口

在 `IntegrationInstanceViewSet` 中新增 `available_instances` action：

```python
@action(methods=["GET"], detail=False)
@HasPermission("integration_center-View")
def available_instances(self, request):
    capability = request.query_params.get("capability")
    if not capability:
        return Response({"result": False, "message": "capability is required"}, status=400)

    queryset = IntegrationInstance.objects.filter(
        enabled=True,
        status=IntegrationInstanceStatusChoices.READY,
    ).exclude(provider_key="bk_lite_builtin")

    instances = []
    for item in queryset.order_by("name", "id"):
        if (
            item.capability_enabled.get(capability) is True
            and item.capability_status.get(capability) == IntegrationInstanceStatusChoices.READY
        ):
            instances.append({
                "id": item.id,
                "name": item.name,
                "provider_key": item.provider_key,
                "display_name": f"{item.name}({item.provider.name})",
            })
    return Response(instances)
```

调用示例：

- `/system_mgmt/integration_instance/available_instances/?capability=login_auth`
- `/system_mgmt/integration_instance/available_instances/?capability=user_sync`
- `/system_mgmt/integration_instance/available_instances/?capability=im_notification`

### 删除业务端重复接口

从以下 ViewSet 中移除 `available_instances` action：

- `server/apps/system_mgmt/viewset/login_auth_binding_viewset.py`
- `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
- `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`

前端三个业务弹窗统一改调集成中心接口。

### 序列化器更新

在 `IntegrationInstanceSerializer` 中：

1. 新增 `display_name` 只读字段：

```python
display_name = serializers.SerializerMethodField()

def get_display_name(self, obj):
    return f"{obj.name}({obj.provider.name})"
```

2. 允许读写 `capability_enabled`，并在 `validate` 中校验 key 属于 provider manifest 声明的能力范围。

返回示例：

```json
{
  "id": 1,
  "name": "总部通讯录",
  "display_name": "总部通讯录（飞书）",
  "provider_key": "feishu",
  "provider": {"key": "feishu", "name": "飞书"},
  "status": "ready",
  "capability_status": {
    "login_auth": "ready",
    "user_sync": "ready",
    "im_notification": "pending_verification"
  },
  "capability_enabled": {
    "login_auth": true,
    "user_sync": true,
    "im_notification": false
  }
}
```

### 能力启停更新

复用现有的 `PUT /system_mgmt/integration_instance/{id}/` 接口。前端传：

```json
{
  "capability_enabled": {
    "login_auth": false,
    "user_sync": true,
    "im_notification": true
  }
}
```

后端行为：

- 校验 `capability_enabled` 的 key 必须在 provider manifest 声明的能力范围内。
- 切换 `enabled` 不影响 `capability_status`。
- 从 `false` 切回 `true` 时，保持禁用前的测试状态（ready 则立即可用）。

## 前端设计

### 详情页能力 Tab 底部操作区

参考原型布局：

```
测试状态：● 待测试    平台状态：● 未启用    [保存配置] [测试连接] [启用能力]
```

交互规则：

- **测试状态**：根据 `capability_status[capability]` 映射为“待测试 / 已就绪 / 测试失败”。
- **平台状态**：根据 `capability_enabled[capability]` 映射为“已启用 / 未启用”。
- **启用能力 / 禁用能力**：点击后调用 `updateInstance` 更新 `capability_enabled`。
- **测试连接**：点击前检测当前表单是否 dirty，若存在未保存修改则弹窗提示“请先保存配置”，不调用测试接口。

### 卡片列表

- 去掉 `buildIntegrationInstanceCardItem` 生成的主状态 Tag。
- 只渲染 provider manifest 声明的能力 Tag。
- Tag 颜色：
  - **绿色**：`capability_enabled == true` 且 `capability_status == ready`
  - **灰色**：其它任何状态
- 卡片主标题保持 `name`，副标题保持 `provider.name`；或考虑使用 `display_name` 替代主标题（待实现时确认）。

### 业务弹窗下拉选项

- 改调统一接口 `/system_mgmt/integration_instance/available_instances/?capability=xxx`。
- 选项文案使用 `display_name`，格式为 `名称（系统类型）`。
- 不展示 `bk_lite_builtin` 内建实例。

## 状态流转

| 场景 | 行为 |
| --- | --- |
| 创建实例 | 根据 provider manifest 创建 `capability_enabled=true`，`capability_status=pending_verification` |
| 禁用能力 | `capability_enabled=false`，`capability_status` 保持不变 |
| 重新启用能力 | `capability_enabled=true`，`capability_status` 保持禁用前状态 |
| 基础连接配置变化 | 所有能力 `capability_status=pending_verification` |
| 某能力配置变化 | 仅该能力 `capability_status=pending_verification` |

## 测试策略

### 后端

- `test_integration_instance_serializer.py`：覆盖 `capability_enabled` 的序列化/反序列化、key 校验、默认值。
- 新增/更新 `test_integration_instance_viewset.py`：覆盖 `available_instances` 过滤逻辑（`enabled`、`status`、`capability_enabled`、`capability_status`、排除内建 provider）。
- 更新 `test_builtin_platform_login_auth.py` 等相关测试：确认内建 provider 不在 `available_instances` 中。

### 前端

- 更新 `types/integration-center.ts` 中的 `IntegrationInstance` 类型，增加 `capability_enabled`。
- 运行 `pnpm type-check` 确保所有消费点类型正确。
- 更新详情页、卡片列表、业务弹窗的相关单元测试（如有）。

## 影响范围

### 后端文件

- `server/apps/system_mgmt/models/integration_instance.py`
- `server/apps/system_mgmt/migrations/0034_integrationinstance.py`
- `server/apps/system_mgmt/serializers/integration_instance_serializer.py`
- `server/apps/system_mgmt/viewset/integration_instance_viewset.py`
- `server/apps/system_mgmt/viewset/login_auth_binding_viewset.py`
- `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
- `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
- 相关测试文件

### 前端文件

- `web/src/app/system-manager/(pages)/integration-center/detail/page.tsx`
- `web/src/app/system-manager/(pages)/integration-center/page.tsx`
- `web/src/app/system-manager/api/integration-center/index.ts`
- `web/src/app/system-manager/types/integration-center.ts`
- `web/src/app/system-manager/utils/intergrationCenter.ts`
- 登录认证 / 用户同步 / IM 通知弹窗中引用集成实例下拉的相关文件

## 后续可扩展项

- 当产品原型给集成实例增加“组织归属”编辑入口后，再在 `available_instances` 中按 `team` 过滤。
- 当能力专属配置增多时，可考虑将能力配置从 `IntegrationInstance.config` 中拆出，迁移到独立模型。
- 当 provider 支持动态能力时，需要重新评估 `capability_enabled` 的 key 管理方式。

## 备注

- 本次设计不涉及登录认证、用户同步、IM 通知业务模型自身的启用状态变更。这些业务模型的 `enabled` 字段继续独立工作。
- 集成实例能力的禁用不会级联禁用下游已创建的业务实例，仅阻止新建业务实例时引用该能力。
