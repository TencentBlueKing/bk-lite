# Historical Superpowers change: 2026-06-29-system-manager-ad-provider

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-29-system-manager-ad-provider.md

> **For agentic workers:** REQUIRED EXECUTION STYLE: Use `superpowers:executing-plans` to implement this plan in a single mainline sequence. Follow the task order in this document, use lightweight validation between tasks, and perform full verification/review only after all planned tasks are complete. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a directory-style `ad` provider to system-manager so BK-Lite supports AD-backed login auth and user sync with the existing integration-center, binding, and sync-source models.

**Architecture:** Introduce a new built-in `ad` provider on top of a shared LDAP utility layer. The backend keeps AD as a first-class provider with `login_auth` and `user_sync` capabilities, while the frontend reuses manifest-driven rendering and updates the signin shell so each AD binding is an independent login source with its own username/password form state.

**Tech Stack:** Django 4.2, Pydantic provider manifests, Next.js App Router, React 19, TypeScript, existing public login-auth APIs, existing system-manager user-sync flows

## Global Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If login semantics, AD field contracts, username mapping behavior, or signin state transitions become unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to the AD provider delivery; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- `ad` is a directory-style provider over `LDAP/LDAPS`, not a redirect-style `OIDC / SAML / ADFS / Entra ID` provider.
- `ad` supports only `login_auth` and `user_sync` in this plan.
- `login_auth` uses the BK-Lite signin page username/password form and backend AD bind validation; it is not a browser redirect SSO flow.
- `user_sync` uses the integration instance service account to pull AD directory data.
- `login_auth_identity_field` must be configurable, support at least `sAMAccountName` and `userPrincipalName`, and default to `sAMAccountName`.
- `user_sync` must keep the current platform identity model centered on `username`; do not replace it with `objectGUID` as the primary sync key.
- `field_mapping` default auto-fill must not be implemented as an AD-only behavior; if defaults are ever added, they must be a provider-agnostic user-sync feature.
- `base_dn` belongs to `integration_instance.config`; `root_dn` belongs to `user_sync_source.business_config`.
- `root_dn` is single-value, required, and uses `manual_input`.
- One AD integration instance may be reused by multiple user sync sources with different `root_dn` values.
- Use the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.

---

## File Structure

### Existing files to modify

- `server/apps/system_mgmt/providers/loader.py`
  Register the new built-in AD provider manifest module.
- `server/apps/system_mgmt/providers/manifests/__init__.py`
  Export the AD manifest module if this package keeps explicit imports.
- `server/apps/system_mgmt/providers/runtime.py`
  Only touch if AD-specific runtime result normalization or adapter invocation shape needs a small shared extension.
- `server/apps/system_mgmt/services/user_sync_service.py`
  Keep AD user-sync behavior aligned with the current `username`-centric mapping model and ensure manual-input `root_dn` semantics work through existing flow.
- `server/apps/system_mgmt/tests/test_provider_manifest.py`
  Extend provider-manifest coverage for AD manifest structure and field declarations.
- `server/apps/system_mgmt/tests/test_runtime_service.py`
  Add runtime/adapter-level AD login auth behavior coverage.
- `server/apps/system_mgmt/tests/test_integration_instance_viewset.py`
  Ensure AD appears in provider listing and available instances for `login_auth` / `user_sync`.
- `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py`
  Cover AD `root_dn` manual-input behavior.
- `server/apps/system_mgmt/tests/test_login_auth_binding_viewset.py`
  Extend binding-facing AD contract coverage if needed.
- `server/apps/core/views/index_view.py`
  Adjust public login-auth API glue only if AD payload shape needs small frontend/backend contract extensions.
- `server/apps/core/tests/views/test_login_auth_bindings.py`
  Add public login-auth contract tests for AD binding flow if the start/status/login APIs need AD-specific assertions.
- `web/src/app/(core)/auth/signin/SigninClient.tsx`
  Split builtin password signin and binding-driven AD signin into distinct form states inside the same shell.
- `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
  Expand the shared binding state machine so account/password bindings like AD can drive a distinct form-state selection flow.
- `web/src/app/(core)/auth/signin/login-auth/types.ts`
  Extend login-auth types for AD binding presentation and form-state semantics.
- `web/src/app/system-manager/utils/intergrationCenter.ts`
  Add AD provider icon/label resolution.
- `web/src/app/system-manager/locales/zh.json`
  Add AD provider/login-source related copy.
- `web/src/app/system-manager/locales/en.json`
  Add AD provider/login-source related copy.
- `web/src/app/system-manager/utils/userSyncPageUtils.ts`
  Keep current field-mapping semantics explicit in UI copy if AD adds new external field examples.

### New files to create

- `server/apps/system_mgmt/providers/manifests/ad.py`
  Define the AD provider manifest, instance templates, business templates, and capability declarations.
- `server/apps/system_mgmt/providers/adapters/ad.py`
  Implement `ADLoginAuthAdapter` and `ADUserSyncAdapter`.
- `server/apps/system_mgmt/providers/adapters/common/ldap.py`
  Add the shared LDAP utility layer for connection setup, search, bind validation, pagination, and response normalization.
- `server/apps/system_mgmt/tests/test_ad_provider.py`
  Add focused AD adapter unit tests if keeping them separate from generic runtime tests is clearer.
- `web/scripts/signin-ad-binding-behavior-test.ts`
  Lightweight regression script for AD binding state transitions if repo style favors script-based auth UI checks.

### Reference files to read during implementation

- `docs/superpowers/specs/2026-06-29-system-manager-ad-provider-design.md`
- `server/apps/system_mgmt/providers/manifests/feishu.py`
- `server/apps/system_mgmt/providers/manifests/wechat.py`
- `server/apps/system_mgmt/providers/adapters/feishu.py`
- `server/apps/system_mgmt/providers/adapters/wechat.py`
- `server/apps/system_mgmt/providers/adapters/base.py`
- `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
- `server/apps/system_mgmt/services/login_auth_binding_service.py`
- `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
- `web/src/app/(core)/auth/signin/login-auth/LoginAuthBindingContent.tsx`
- `web/src/app/(core)/auth/signin/login-auth/BuiltinSigninContent.tsx`

### Files likely to stay unchanged

- `server/apps/system_mgmt/models/integration_instance.py`
  Existing generic config storage is already sufficient.
- `server/apps/system_mgmt/models/user_sync_source.py`
  Existing `business_config` and `field_mapping` storage is already sufficient.
- `web/src/app/system-manager/api/integration-center/index.ts`
  Provider listing API shape should remain manifest-driven.

## Task 1: Add the AD provider manifest and LDAP shared utility

**Files:**
- Create: `server/apps/system_mgmt/providers/manifests/ad.py`
- Create: `server/apps/system_mgmt/providers/adapters/common/ldap.py`
- Modify: `server/apps/system_mgmt/providers/loader.py`
- Modify: `server/apps/system_mgmt/providers/manifests/__init__.py`
- Test: `server/apps/system_mgmt/tests/test_provider_manifest.py`

**Interfaces:**
- Consumes: `ProviderManifest`, `TemplateFieldManifest`, `BusinessTemplateManifest`, `CapabilityManifest`
- Produces:
  - provider key: `"ad"`
  - capability keys: `"login_auth"`, `"user_sync"`
  - shared helpers such as `LDAPConnectionConfig`, `search_single_user(config, identity_field, identity_value)`, `bind_user_dn(connection_url, dn, password, use_ssl, timeout)`

- [ ] **Step 1: Write failing manifest tests for AD provider registration and field declarations**

Add tests that assert:

```python
def test_ad_manifest_declares_login_auth_and_user_sync():
    from apps.system_mgmt.providers.manifests.ad import PROVIDER_MANIFEST

    assert PROVIDER_MANIFEST.key == "ad"
    assert [cap.key for cap in PROVIDER_MANIFEST.capabilities] == ["login_auth", "user_sync"]


def test_ad_user_sync_root_dn_is_manual_input():
    from apps.system_mgmt.providers.manifests.ad import PROVIDER_MANIFEST

    template = PROVIDER_MANIFEST.business_templates["user_sync_form"]
    root_field = next(field for group in template.groups for field in group.fields if field.key == "root_dn")
    assert root_field.input_mode == "manual_input"
```

- [ ] **Step 2: Run the targeted manifest tests to verify they fail**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_provider_manifest.py -k ad -v
```

Expected:
- FAIL because `ad` manifest module does not exist yet

- [ ] **Step 3: Implement `ad.py` manifest and register it in the built-in loader**

Define the manifest with:

```python
PROVIDER_MANIFEST = ProviderManifest.model_validate({
    "key": "ad",
    "name": "Active Directory",
    "instance_templates": {
        "base_connection": {
            "title": "基础连接",
            "groups": [
                {
                    "key": "connection",
                    "title": "连接配置",
                    "fields": [
                        {"key": "connection_url", "label": "连接地址", "field_type": "string", "required": True},
                        {"key": "ssl_encryption", "label": "SSL加密方式", "field_type": "select", "required": True},
                        {"key": "timeout", "label": "超时时间", "field_type": "number", "required": True, "default": 10},
                        {"key": "bind_dn", "label": "Bind DN", "field_type": "string", "required": True},
                        {"key": "bind_password", "label": "Bind Password", "field_type": "password", "required": True, "secret": True},
                        {"key": "base_dn", "label": "Base DN", "field_type": "string", "required": True},
                        {
                            "key": "login_auth_identity_field",
                            "label": "登录标识字段",
                            "field_type": "select",
                            "required": True,
                            "default": "sAMAccountName",
                            "options": [
                                {"value": "sAMAccountName", "label": "sAMAccountName"},
                                {"value": "userPrincipalName", "label": "userPrincipalName"},
                            ],
                        },
                    ],
                }
            ],
        }
    },
    "business_templates": {
        "login_auth_form": {...},
        "user_sync_form": {
            "title": "用户同步配置",
            "groups": [
                {
                    "key": "scope",
                    "title": "同步范围",
                    "fields": [
                        {"key": "root_dn", "label": "Root DN", "field_type": "string", "required": True, "input_mode": "manual_input"},
                    ],
                }
            ],
            "available_external_fields": ["sAMAccountName", "displayName", "mail", "telephoneNumber", "distinguishedName"],
        },
    },
    "capabilities": [...],
})
```

Also update:

```python
BUILTIN_PROVIDER_MODULES = (
    "apps.system_mgmt.providers.manifests.feishu",
    "apps.system_mgmt.providers.manifests.wechat",
    "apps.system_mgmt.providers.manifests.ad",
)
```

- [ ] **Step 4: Add the minimal shared LDAP utility layer**

Implement focused helpers such as:

```python
@dataclass
class LDAPConnectionConfig:
    connection_url: str
    use_ssl: bool
    timeout: int
    bind_dn: str
    bind_password: str
    base_dn: str


def build_connection_config(config: dict) -> LDAPConnectionConfig: ...
def search_entries(connection_config: LDAPConnectionConfig, search_base: str, search_filter: str, attributes: list[str]) -> list[dict]: ...
def bind_user_dn(connection_config: LDAPConnectionConfig, user_dn: str, password: str) -> None: ...
```

Requirements:
- keep this layer AD-oriented but reusable
- do not introduce a generic abstraction beyond what AD uses now

- [ ] **Step 5: Re-run the manifest tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_provider_manifest.py -k ad -v
```

Expected:
- PASS for the new AD manifest assertions

## Task 2: Implement AD login-auth behavior on top of the shared LDAP utility

**Files:**
- Create: `server/apps/system_mgmt/providers/adapters/ad.py`
- Modify: `server/apps/system_mgmt/providers/adapters/base.py`
- Modify: `server/apps/system_mgmt/tests/test_runtime_service.py`
- Modify: `server/apps/core/tests/views/test_login_auth_bindings.py`
- Reference: `server/apps/system_mgmt/services/login_auth_binding_service.py`

**Interfaces:**
- Consumes:
  - `build_connection_config(config: dict) -> LDAPConnectionConfig`
  - `search_entries(...) -> list[dict]`
  - `bind_user_dn(...) -> None`
- Produces:
  - `ADLoginAuthAdapter.test_connection(config, provider_key, capability_key, **kwargs) -> CapabilityExecutionResult`
  - `ADLoginAuthAdapter.authenticate(config, provider_key, capability_key, auth_code="", username="", password="", **kwargs) -> CapabilityExecutionResult`
  - login payload shape:

```python
{
    "external_user": {
        "sAMAccountName": "...",
        "displayName": "...",
        "mail": "...",
        "telephoneNumber": "...",
        "distinguishedName": "...",
    }
}
```

- [ ] **Step 1: Write failing runtime tests for AD login-auth success and failure paths**

Add focused tests such as:

```python
def test_ad_login_auth_searches_single_user_and_binds_password():
    ...
    result = service.execute(
        provider_key="ad",
        capability_key="login_auth",
        operation="authenticate",
        config=runtime_config,
        username="alice",
        password="secret",
    )
    assert result.success is True
    assert result.payload["external_user"]["sAMAccountName"] == "alice"


def test_ad_login_auth_fails_when_search_returns_multiple_users():
    ...
    assert result.success is False
    assert result.errors[0].code == "provider.auth_failed"
```

- [ ] **Step 2: Run the targeted AD runtime tests to verify they fail**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_runtime_service.py -k "ad and login_auth" -v
```

Expected:
- FAIL because AD adapter is not implemented yet

- [ ] **Step 3: Implement `ADLoginAuthAdapter` with test-connection and authenticate**

Implement the core flow:

```python
class ADLoginAuthAdapter(BaseLoginAuthAdapter):
    capability_key = "login_auth"

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        connection_config = build_connection_config(config)
        search_entries(connection_config, connection_config.base_dn, "(objectClass=*)", ["distinguishedName"])
        return CapabilityExecutionResult.success_result("AD login capability is ready")

    @classmethod
    def authenticate(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        username = kwargs.get("username", "")
        password = kwargs.get("password", "")
        identity_field = (config or {}).get("login_auth_identity_field") or "sAMAccountName"
        ...
```

Requirements:
- reject missing `username` / `password`
- use service-account search first
- require exactly one matched user
- bind with matched `distinguishedName`
- return normalized `external_user` payload for existing binding mapping logic

- [ ] **Step 4: Extend public login-auth endpoint tests only if AD payload/contract needs coverage**

If the `/api/v1/core/api/login/` path for binding login now accepts AD credential submissions, add tests like:

```python
def test_login_with_binding_for_ad_credentials_sets_cookie_and_redirect():
    ...
```

If public API shape does not change yet, keep this step to contract assertions around returned binding payload/provider metadata only.

- [ ] **Step 5: Re-run the targeted runtime/login-auth tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_runtime_service.py -k "ad and login_auth" -v
uv run pytest apps/core/tests/views/test_login_auth_bindings.py -k ad -v
```

Expected:
- PASS for the new AD login-auth behavior

## Task 3: Implement AD user-sync behavior with manual `root_dn` and existing `field_mapping`

**Files:**
- Modify: `server/apps/system_mgmt/providers/adapters/ad.py`
- Modify: `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
- Modify: `server/apps/system_mgmt/services/user_sync_service.py`
- Modify: `server/apps/system_mgmt/tests/test_user_sync_source_input_mode.py`
- Create or Modify: `server/apps/system_mgmt/tests/test_ad_provider.py`

**Interfaces:**
- Consumes:
  - `source.business_config["root_dn"]`
  - `source.field_mapping`
  - current `DEFAULT_FIELD_MAPPING`
- Produces:
  - `ADUserSyncAdapter.sync_users(...) -> CapabilityExecutionResult`
  - user payload entries that existing `_mapped_value` can consume, for example:

```python
{
    "sAMAccountName": "alice",
    "displayName": "Alice",
    "mail": "alice@example.com",
    "telephoneNumber": "13800000000",
    "distinguishedName": "CN=Alice,OU=Shanghai,DC=corp,DC=example,DC=com",
    "department_ids": ["OU=Shanghai,DC=corp,DC=example,DC=com"],
}
```

- [ ] **Step 1: Write failing tests for AD manual-input `root_dn` and sync payload shape**

Add tests such as:

```python
def test_ad_root_dn_uses_manual_input_mode():
    assert get_user_sync_root_department_input_mode("ad") == "manual_input"


def test_ad_sync_users_returns_payload_compatible_with_existing_field_mapping():
    ...
    assert result.payload["user_list"][0]["sAMAccountName"] == "alice"
```

- [ ] **Step 2: Run targeted AD user-sync tests to verify they fail**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_source_input_mode.py -k ad -v
uv run pytest apps/system_mgmt/tests/test_ad_provider.py -k user_sync -v
```

Expected:
- FAIL because AD user-sync adapter path is not implemented yet

- [ ] **Step 3: Implement `ADUserSyncAdapter.sync_users` using `root_dn` and current mapping semantics**

Implement the behavior so:

```python
class ADUserSyncAdapter(BaseUserSyncAdapter):
    capability_key = "user_sync"

    @classmethod
    def sync_users(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        source = kwargs["source"]
        root_dn = str((source.business_config or {}).get("root_dn") or "").strip()
        ...
        return CapabilityExecutionResult.success_result(
            "AD user sync payload prepared",
            payload={"group_list": group_list, "user_list": user_list},
        )
```

Requirements:
- use `root_dn` as the single search root
- do not introduce AD-only field-mapping auto-fill
- keep payload compatible with existing `field_mapping` resolution
- if a record cannot produce a mapped `username`, let existing sync service treat it according to current skip/conflict behavior

- [ ] **Step 4: Keep `user_sync_service.py` aligned with current `username`-centric model**

Only make direct changes if AD payload shape needs tiny compatibility adjustments, for example:

```python
DEFAULT_FIELD_MAPPING = {
    "username": "user_id",
    ...
}
```

Requirements:
- do not switch the sync core to `objectGUID`
- do not add AD-only mapping defaults here unless they are generic

- [ ] **Step 5: Re-run targeted AD user-sync tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_source_input_mode.py -k ad -v
uv run pytest apps/system_mgmt/tests/test_ad_provider.py -k user_sync -v
```

Expected:
- PASS for AD `root_dn` manual-input and payload compatibility

## Task 4: Wire AD into signin UI and integration-center presentation

**Files:**
- Modify: `web/src/app/(core)/auth/signin/SigninClient.tsx`
- Modify: `web/src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts`
- Modify: `web/src/app/(core)/auth/signin/login-auth/types.ts`
- Modify: `web/src/app/system-manager/utils/intergrationCenter.ts`
- Modify: `web/src/app/system-manager/locales/zh.json`
- Modify: `web/src/app/system-manager/locales/en.json`
- Test: `web/scripts/signin-ad-binding-behavior-test.ts`

**Interfaces:**
- Consumes:
  - binding items with `provider_key: "ad"`
  - existing builtin password signin flow
- Produces:
  - independent AD login-source selection state
  - separate AD credentials form state from builtin password form state

- [ ] **Step 1: Write a failing lightweight frontend regression for AD binding selection behavior**

Add a script or small test that asserts:

```ts
assert.equal(resolveSigninMode("bk_lite_builtin"), "builtin");
assert.equal(resolveSigninMode("ad"), "binding-password");
assert.equal(lockProviderSwitch("waiting"), true);
```

or equivalent helpers if the file exposes named state resolvers.

- [ ] **Step 2: Run the targeted frontend auth behavior check to verify it fails**

Run:

```bash
cd web
pnpm exec tsx scripts/signin-ad-binding-behavior-test.ts
```

Expected:
- FAIL because AD-specific signin state is not represented yet

- [ ] **Step 3: Update signin shell state so builtin password and AD binding forms are distinct**

Implement state semantics like:

```ts
type SigninSurface = "builtin-password" | "binding-password";

interface BindingPasswordState {
  bindingId: number;
  providerKey: string;
  bindingName: string;
}
```

Requirements:
- selecting an AD binding enters a distinct credentials form state
- builtin password signin remains available as its own entry
- switching away from an AD binding resets only the AD form-local state
- provider switching is disabled in `starting`, `waiting`, and `syncing-session`

- [ ] **Step 4: Add AD provider display name/icon support in integration-center presentation**

Update helpers so:

```ts
const providerIconMap: Record<string, string> = {
  feishu: "feishu",
  wechat: "wechat",
  ad: "LDAP",
};
```

and add localized labels:

```json
"system": {
  "integrationCenter": {
    "provider": {
      "ad": "Active Directory"
    }
  }
}
```

- [ ] **Step 5: Re-run the targeted frontend auth and type checks**

Run:

```bash
cd web
pnpm exec tsx scripts/signin-ad-binding-behavior-test.ts
pnpm exec eslint 'src/app/(core)/auth/signin/SigninClient.tsx' 'src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts' 'src/app/(core)/auth/signin/login-auth/types.ts' 'src/app/system-manager/utils/intergrationCenter.ts'
```

Expected:
- behavior script passes
- no new lint errors in touched files

## Task 5: Final contract coverage and end-to-end verification

**Files:**
- Modify as needed from previous tasks only
- Reference: `docs/superpowers/specs/2026-06-29-system-manager-ad-provider-design.md`

**Interfaces:**
- Consumes:
  - AD provider manifest
  - AD login-auth adapter
  - AD user-sync adapter
  - signin AD binding state
- Produces:
  - verified end-to-end behavior against the spec

- [ ] **Step 1: Add any missing contract tests discovered during task execution**

Focus only on direct spec coverage gaps such as:

```python
def test_available_instances_includes_ready_ad_for_login_auth(): ...
def test_available_instances_includes_ready_ad_for_user_sync(): ...
```

and any direct frontend helper assertions still missing after Tasks 1-4.

- [ ] **Step 2: Run the full relevant backend verification suite**

Run:

```bash
cd server
uv run pytest \
  apps/system_mgmt/tests/test_provider_manifest.py \
  apps/system_mgmt/tests/test_runtime_service.py \
  apps/system_mgmt/tests/test_integration_instance_viewset.py \
  apps/system_mgmt/tests/test_user_sync_source_input_mode.py \
  apps/core/tests/views/test_login_auth_bindings.py -v
```

Expected:
- PASS for all touched AD-related backend behaviors

- [ ] **Step 3: Run the full relevant frontend verification suite**

Run:

```bash
cd web
pnpm exec eslint \
  'src/app/(core)/auth/signin/SigninClient.tsx' \
  'src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts' \
  'src/app/(core)/auth/signin/login-auth/types.ts' \
  'src/app/system-manager/utils/intergrationCenter.ts'
pnpm exec tsx scripts/signin-ad-binding-behavior-test.ts
```

Expected:
- no new lint errors
- signin AD binding behavior script passes

- [ ] **Step 4: Perform a spec-to-plan review before closeout**

Verify against `docs/superpowers/specs/2026-06-29-system-manager-ad-provider-design.md`:

- AD remains a directory-style `LDAP/LDAPS` provider
- only `login_auth` and `user_sync` were added
- login auth remains a username/password flow, not redirect SSO
- `root_dn` remains manual-input and single-value
- `field_mapping` default auto-fill was not implemented as an AD-only behavior
- login page shows each AD binding as a separate source

- [ ] **Step 5: Commit the finished implementation**

```bash
git add server/apps/system_mgmt/providers server/apps/system_mgmt/tests server/apps/core/tests/views/test_login_auth_bindings.py web/src/app/\(core\)/auth/signin web/src/app/system-manager/utils/intergrationCenter.ts web/src/app/system-manager/locales/zh.json web/src/app/system-manager/locales/en.json web/scripts/signin-ad-binding-behavior-test.ts
git commit -m "feat: add AD provider for login auth and user sync"
```

## Plan Self-Review

### Spec coverage

- Provider form and capability scope: covered by Task 1.
- LDAP shared base and AD login behavior: covered by Task 2.
- `root_dn` manual-input and current `username`-centric sync model: covered by Task 3.
- login-source selection and per-binding AD signin state: covered by Task 4.
- final behavior-level verification against the design: covered by Task 5.

### Placeholder scan

- No `TODO`, `TBD`, or deferred “implement later” markers remain in tasks.
- Each task names exact files, commands, expected outcomes, and interface contracts.

### Type consistency

- `login_auth_identity_field`, `root_dn`, `binding-password` signin state, and AD capability keys are named consistently across tasks.
- The plan keeps `username` as the sync identity anchor and does not introduce a conflicting `objectGUID`-primary model.

## specs: 2026-06-29-system-manager-ad-provider-design.md

## 背景

系统管理集成中心当前已经支持以 provider manifest 驱动的第三方集成实例管理，并已接入：

- `feishu`：支持 `login_auth`、`user_sync`、`im_notification`
- `wechat`：支持 `login_auth`

当前需要新增一个独立的 `ad` provider，用于在 BK-Lite 中接入企业 Active Directory。

在需求澄清过程中，已经确认以下产品语义：

1. 本次新增的是“目录型 AD provider”，不是跳转式企业 SSO provider。
2. `ad` 底层协议为 `LDAP/LDAPS` 直连 Active Directory。
3. `login_auth` 语义为：用户在 BK-Lite 登录页输入账号密码，后端直连 AD 做认证。
4. `user_sync` 语义为：系统使用配置好的服务账号从 AD 拉取用户、组织等目录数据。
5. 本次不做 `OIDC / SAML / ADFS / Entra ID` 跳转式登录。

同时，参考仓库 `/Users/lanyu/Work/bk-user` 中 `weops-4.x` 分支的 `mad` 实现，可以确认 BlueKing 既有 AD 方案也是：

- AD 作为独立目录源类型
- 登录使用本地账号密码表单
- 后端通过 LDAP 查询用户并对目标用户 DN 执行 bind 校验
- 同步使用服务账号拉取目录数据

因此，本次设计目标不是抽象一个泛化 SSO 系统，而是在 BK-Lite 现有集成中心与登录认证框架上，新增一个与当前平台模型兼容的 AD provider。

## 设计目标

1. 在集成中心中新增独立 `ad` provider，而不是把 AD 伪装成现有 provider 变体。
2. 支持 `login_auth + user_sync` 两个 capability。
3. 保持与 BK-Lite 当前 provider manifest、runtime service、binding、user sync source 的模型一致。
4. 登录页支持将每个启用中的 AD 登录绑定作为独立登录入口展示。
5. 同步侧复用当前 `field_mapping` 机制，不为 AD 单独发明一套用户字段映射模型。
6. 为未来可能的 `ldap` provider 预留共享 LDAP 基础能力，避免把 LDAP 逻辑写死在 AD adapter 中。

## 非目标

- 不在本次设计中实现跳转式 AD/ADFS/OIDC/SAML 登录。
- 不在本次设计中新增 `im_notification` capability。
- 不在本次设计中为 AD 做远程组织树浏览器或多根节点同步。
- 不在本次设计中重构整套登录页视觉布局，只处理与 AD 登录源相关的状态流与交互语义。
- 不在本次设计中引入一套仅对 AD 生效的 `user_sync.field_mapping` 默认自动填充逻辑。

## 方案选型

存在三种可行路径：

1. AD 专有实现
- 新增 `ad` provider
- 单独写 `ADLoginAuthAdapter`、`ADUserSyncAdapter`
- LDAP 连接、bind、search、分页逻辑都写在 AD 代码里

2. 通用 LDAP provider，AD 只是预置配置
- 后端只做 `ldap` provider
- 前端把一套默认字段映射包装成 “AD”

3. AD provider + LDAP 共享基座
- 对外新增独立 `ad` provider
- 对内抽一层共享 LDAP 能力
- `ad` 只承载 AD 默认字段、默认 filter、能力编排

本次选择方案 `3`。

选择原因：

- 产品层明确要求“增加一个 AD provider”，而不是“增加一个通用 LDAP provider”。
- 工程层不应把 LDAP 协议细节直接散落在 AD adapter 中。
- 后续若新增 `ldap` provider，可最大限度复用共享 LDAP 基座。

## 设计第 1 节：架构与数据模型

### 总体结构

新增独立 `ad` provider，与现有 `feishu`、`wechat` 同层。

对外 capability 只声明：

- `login_auth`
- `user_sync`

对内新增共享 LDAP 基座，负责：

- 初始化 `LDAP/LDAPS` 连接
- 使用服务账号执行搜索
- 按指定登录标识字段搜索目标用户
- 获取目标用户 `DN`
- 使用 `DN + 用户输入密码` 做 bind 校验
- 执行分页目录搜索
- 做 LDAP 异常到平台能力错误的归一化

### 配置与数据落点

#### `integration_instance.config`

存放连接级配置：

- `connection_url`
- `ssl_encryption`
- `timeout`
- `bind_dn`
- `bind_password`
- `base_dn`
- `login_auth_identity_field`

其中：

- `login_auth_identity_field` 默认 `sAMAccountName`
- 至少支持：
  - `sAMAccountName`
  - `userPrincipalName`

#### `login_auth binding`

继续沿用现有 binding 语义，负责定义：

- 认证成功后如何把外部用户字段映射到平台字段
- 默认推荐映射：
  - `platform.username <- AD.sAMAccountName`

这里需要明确区分两个概念：

- “用户输入什么账号去认证” 是 `login_auth_identity_field`
- “认证成功后拿什么字段匹配平台用户” 是 `binding.external_field -> binding.platform_field`

两者可以相同，也可以不同。

#### `user_sync_source.business_config`

存放同步实例自己的业务范围配置：

- `root_dn`

设计约束：

- `root_dn` 单值必填
- 一个 `integration_instance` 可被多个 `user_sync_source` 复用
- 多个同步源通过不同的 `root_dn` 表达不同同步范围

### `base_dn` 与 `root_dn` 的边界

- `base_dn`：连接的大边界，属于 `integration_instance.config`
- `root_dn`：单个同步源的业务边界，属于 `user_sync_source.business_config`

这样拆分的原因：

- 连接配置复用
- 同步范围独立
- 不需要在 provider 连接层引入多根节点搜索逻辑

### 凭据策略

v1 采用单套凭据策略：

- 同一套 `bind_dn / bind_password` 同时服务于：
  - `login_auth` 阶段的用户搜索
  - `user_sync` 阶段的目录拉取

后续如有必要，再扩展为登录查询账号与同步账号分离。

## 设计第 2 节：登录页交互与登录链路

### 登录页交互语义

AD 登录虽然也是账号密码表单，但不能与平台账号密码登录混成同一个表单态。

本次确定采用：

- 先选登录源
- 再进入对应独立表单态

具体规则：

- 平台账号密码登录是一个独立入口
- 每个启用中的 AD `login_auth binding` 都是一个独立入口
- 若系统中存在多个 AD 绑定，则分别展示为多个独立登录方式
- 用户点击某一个 AD 登录方式后，进入该绑定对应的独立账号密码表单态

### AD 表单态要求

AD 表单态虽然仍展示“账号 + 密码”，但其以下内容必须绑定到具体 AD 登录源：

- 表单标题
- 占位提示
- 提交目标
- 错误提示
- 成功后的登录链路

不能与平台密码登录混用同一状态容器，否则会造成以下认知混淆：

- 用户误以为平台密码可以直接登录 AD
- 多个 AD 登录源无法稳定区分
- 后续无法自然承载实例级差异化文案

### 登录链路

1. 用户选择某个 AD 登录绑定。
2. 前端进入该绑定对应的独立账号密码表单态。
3. 用户输入账号密码。
4. 前端将凭据提交给该绑定对应的 `login_auth` 链路。
5. 后端根据 binding 找到对应 `integration_instance`。
6. 后端用服务账号连接 AD。
7. 后端按 `login_auth_identity_field` 搜索目标用户。
8. 若找到唯一用户，取其 `DN`。
9. 使用 `DN + 用户输入密码` 对 AD 做 bind 校验。
10. 认证成功后，取 AD 外部用户属性，交给现有 login auth binding 匹配逻辑。
11. 根据 binding 的映射规则与未匹配策略决定：
- 匹配现有用户直接登录
- 或按既有策略处理未匹配用户

### 多 AD 绑定展示策略

如果系统中存在多个启用中的 AD 登录绑定：

- 每个 binding 单独展示为一个登录入口
- 不合并成一个统一 “AD 登录” 后再二次选择实例

原因：

- 与当前 `login_auth_binding` 模型最一致
- 减少额外一步选择
- 更容易让每个绑定拥有独立文案与表单状态

## 设计第 3 节：AD 配置模型与默认字段策略

### 连接级配置

`ad` provider 在 `integration_instance.config` 中至少需要以下字段：

- `connection_url`
- `ssl_encryption`
- `timeout`
- `bind_dn`
- `bind_password`
- `base_dn`
- `login_auth_identity_field`

建议的默认值与约束：

- `login_auth_identity_field = sAMAccountName`
- 允许值：
  - `sAMAccountName`
  - `userPrincipalName`

### 可选扩展字段

v1 可预留但不必全部强制暴露复杂 UI：

- `user_object_class`
- `organization_class`
- `user_search_filter`
- `department_search_filter`

### `user_sync` 配置模型

`user_sync_source.business_config` 中：

- `root_dn` 必填
- 输入模式为 `manual_input`

本次明确不做：

- AD 远程部门树选择器
- 多根节点输入

原因：

- DN 本身更适合直接手工输入
- 远程树组件会显著增加 v1 的复杂度与边界问题

### 字段映射策略

BK-Lite 当前用户同步能力已经提供统一的 `field_mapping` 机制，界面允许管理员把平台字段映射到外部字段。

当前平台事实：

- 平台用户唯一字段语义仍以 `username` 为核心
- 用户同步落库与冲突识别的主锚点仍是 `username`
- 当前 `field_mapping` 在界面中没有默认自动填充行为

因此，本次 AD 设计必须遵守以下约束：

1. `ad` provider 不单独实现一套 `field_mapping` 默认自动填充逻辑。
2. 如果未来要做字段映射默认填充，应作为所有支持 `user_sync` 的 provider 的统一能力实现。
3. `ad` provider 在 v1 只负责提供：
- `available_external_fields`
- 推荐外部字段集合
- 必要时可扩展推荐映射元数据

但真正的默认填充行为不在本次 AD 设计中落地。

### 推荐外部字段集合

AD `user_sync` business template 应至少声明以下外部字段供映射使用：

- `sAMAccountName`
- `displayName`
- `mail`
- `telephoneNumber`
- `distinguishedName`

同时，推荐但不强制的映射关系为：

- `platform.username <- AD.sAMAccountName`
- `platform.display_name <- AD.displayName`
- `platform.email <- AD.mail`
- `platform.phone <- AD.telephoneNumber`

## 设计第 4 节：用户同步行为与数据语义

### 同步入口

每个 `user_sync_source` 对应一次独立 AD 同步范围。

同步执行时：

- 通过 `integration_instance` 读取 AD 连接配置
- 通过 `business_config.root_dn` 确定当前同步源的具体范围

### 同步内容

v1 同步内容包括：

- 用户
- 组织 / OU
- 必要时的组信息
- 用户与组织关系

### 主身份锚点

按 BK-Lite 当前实现事实，`user_sync` 的主身份锚点仍是平台 `username`。

这意味着：

- AD 同步时，最关键的是把某个 AD 字段映射到平台 `username`
- 平台当前不是按一个新的“外部稳定 GUID 主键”来做用户落库与冲突判断

因此，本次 AD 设计不引入新的主身份模型，而是遵守当前平台语义：

- `field_mapping.username` 是同步时最关键的字段映射
- 推荐默认外部字段为 `sAMAccountName`

### 关于 `objectGUID`

虽然 `objectGUID` 在目录系统中更稳定，但在 BK-Lite 当前实现下：

- 它不应作为 v1 的平台主同步锚点
- 可以作为未来增强同步稳定性的扩展字段预留
- 不能在本次设计中替代 `username` 成为平台唯一身份核心

### 同步范围语义

本次同步范围约束如下：

- 单个同步源只支持单 `root_dn`
- 不支持一个同步源配置多个根节点
- 若用户要同步多个组织分支，则创建多个同步源，共用同一个 AD 集成实例

这个约束与当前产品确认一致：

- 用户同步可以引用同一个集成系统实例创建多个同步实例
- 只要各同步实例的根组织不同即可

### 输入方式

`root_dn` 采用：

- `manual_input`

v1 不做：

- 部门树下拉选择
- 远程组织树浏览

### 字段映射默认填充的统一原则

由于当前 `user_sync.field_mapping` 在界面中没有统一默认填充行为，本次设计明确：

- AD v1 不增加 provider 特有的默认映射自动填值
- 未来如果要做默认回填，应作为所有 provider 共享的统一表单能力实现

## 设计第 5 节：错误处理、校验与最小测试面

### 后端校验

创建或更新 AD 集成实例时，至少校验：

- `provider_key == ad`
- 必填连接字段存在：
  - `connection_url`
  - `bind_dn`
  - `bind_password`
  - `base_dn`
- `login_auth_identity_field` 必须在允许集合中

创建或更新 AD 用户同步源时，至少校验：

- `business_config.root_dn` 必填
- `root_dn` 走 `manual_input`
- `field_mapping` 继续沿用当前通用结构，不做 AD 特判

### 错误归一化

LDAP/AD 侧错误应统一归一为平台 capability 错误，而不是把底层协议细节直接暴露给前端。

至少需要覆盖：

- 连接失败
- 服务账号 bind 失败
- 用户搜索失败
- 用户未找到
- 用户搜索结果不唯一
- 用户密码 bind 失败
- 同步结果为空
- 同步字段缺失，无法映射到平台 `username`

### 登录错误语义

用户输入错误账号或密码时：

- 前端只拿到统一失败摘要
- 不直接暴露过细目录结构细节

日志中保留：

- `request_id`
- `provider_key`
- `capability_key`
- 关键错误码

### 同步错误语义

对于 `user_sync`：

- 若某条用户记录映射后拿不到平台 `username`，该记录应被跳过并计入摘要
- 若用户与现有其他同步源产生冲突，沿用当前部分成功 / 冲突用户名逻辑
- 除连接级失败外，不因为单个用户异常导致整次同步立即失败

### 最小测试面

#### 后端 manifest / serializer / viewset

- `ad` manifest 正确注册并暴露 `login_auth`、`user_sync`
- `providers()` 接口返回 `ad` 的 public manifest
- `login_auth_identity_field` 白名单校验
- `root_dn` 的 `manual_input` 模式校验
- `available_instances(capability=login_auth)` / `available_instances(capability=user_sync)` 能正确返回 AD 实例

#### runtime / adapter

- `test_connection` 成功
- `test_connection` 失败
- `login_auth` 搜索到唯一用户并 bind 成功
- `login_auth` 搜索为空
- `login_auth` 搜索出多个用户
- `login_auth` bind 失败
- `user_sync` 能返回标准 `group_list / user_list`
- `user_sync` 字段缺失时的容错行为

#### 现有服务链路

- login auth binding 能消费 AD 返回的外部用户 payload
- user sync service 能按现有 `field_mapping` 逻辑将 AD 用户映射到平台 `username`
- 同一 AD 集成实例下多个 `user_sync_source` 使用不同 `root_dn` 时可独立运行

#### 前端最小面

- 登录页能展示多个 AD 登录绑定入口
- 选择某个 AD 登录入口后进入独立表单态
- 从 AD 表单切换回其他登录源时状态正确重置
- 集成中心 provider 列表能显示 AD
- 用户同步配置页能渲染 AD 的 `root_dn` 手工输入项

## 影响范围

### 后端

- `server/apps/system_mgmt/providers/manifests/ad.py`
- `server/apps/system_mgmt/providers/adapters/ad.py`
- `server/apps/system_mgmt/providers/adapters/common/*` 或等价 LDAP 共享基座
- `server/apps/system_mgmt/providers/loader.py`
- `server/apps/system_mgmt/tests/*` 中与 provider manifest、runtime、integration instance、user sync、login auth binding 相关测试

### 前端

- `web/src/app/system-manager/utils/intergrationCenter.ts`
- `web/src/app/system-manager/locales/*.json`
- 登录页相关实现
- 用户同步配置页 manifest 驱动表单逻辑

## 风险与后续

### 风险

- AD 登录与平台密码登录都使用账号密码表单，若表单态处理不清晰，极易引起用户混淆。
- AD 目录结构差异较大，`manual_input root_dn` 在 v1 更稳，但需要文档引导。
- 如果未来很快要做 `ldap` provider，本次 LDAP 共享基座的边界必须从一开始就控制好，避免只服务 AD 的伪抽象。

### 后续扩展

- 新增统一的 `field_mapping` 推荐填充能力，供所有 `user_sync` provider 复用
- 抽象出独立 `ldap` provider
- 追加跳转式 `adfs` / `oidc` / `saml` provider
- 视需求决定是否增加 AD 远程组织树选择器
