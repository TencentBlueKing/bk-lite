# System Manager AD Provider Implementation Plan

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
