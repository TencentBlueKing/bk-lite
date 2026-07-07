## ADDED Requirements

### Requirement: WeChat provider returns external user from real WeChat OAuth response

WeChat login authentication provider SHALL return `external_user` payload containing the real fields returned by WeChat `sns/userinfo` API, and SHALL NOT directly create platform users, refresh user profile, or sign login tokens.

The adapter payload SHALL include:

- `openid` (string, required) — WeChat user's openid, used as the primary match key
- `unionid` (string, optional, defaults to empty string) — WeChat user's unionid, used as alternate match key
- `nickname` (string, optional, defaults to empty string) — WeChat user's nickname, used only when creating a new platform user
- `headimgurl` (string, optional, defaults to empty string) — WeChat user's avatar URL, reserved for future use

The adapter SHALL NOT return `payload["login_result"]`. The adapter SHALL NOT invoke `wechat_user_register` NATS handler.

#### Scenario: WeChat authenticate returns external_user with openid

- **WHEN** WeChat adapter calls `sns/userinfo` and receives `{openid: "oxxx", unionid: "uxxx", nickname: "Alice"}`
- **THEN** adapter returns `CapabilityExecutionResult.success_result` with `payload["external_user"] = {"openid": "oxxx", "unionid": "uxxx", "nickname": "Alice", "headimgurl": ""}`
- **AND** adapter does NOT invoke `wechat_user_register`

#### Scenario: WeChat authenticate handles sns/userinfo error

- **WHEN** WeChat `sns/userinfo` returns `errcode != 0`
- **THEN** adapter returns `CapabilityExecutionResult.failed_result` with `code="provider.auth_failed"` and the original `errmsg`
- **AND** `login_with_binding()` returns `{"result": false, "message": "..."}` to the caller

#### Scenario: WeChat authenticate handles unionid absent

- **WHEN** WeChat `sns/userinfo` returns `{openid: "oxxx"}` without `unionid`
- **THEN** adapter returns `payload["external_user"]["unionid"] = ""` (empty string, not None)
- **AND** `_resolve_platform_user` treats empty `unionid` as unable to match on unionid

### Requirement: WeChat login authentication manifest exposes openid and unionid as matchable fields

The WeChat provider manifest SHALL declare `available_external_fields = ["openid", "unionid"]` and `default_external_match_field = "openid"`. The manifest SHALL NOT include `nickname` or `open_id` in matchable fields.

#### Scenario: WeChat manifest advertises real WeChat API field names

- **WHEN** administrator opens the login authentication modal for a WeChat integration instance
- **THEN** the external field hint displays `openid / unionid`
- **AND** the default value of `external_field` is `openid`

#### Scenario: WeChat manifest does not expose nickname as matchable

- **WHEN** administrator opens the login authentication modal for a WeChat integration instance
- **THEN** the external field hint does NOT include `nickname`
- **AND** the external field hint does NOT include `open_id` (with underscore)

### Requirement: Generic login authentication binding resolves platform user via field mapping for all providers including WeChat

The generic `login_with_binding()` flow SHALL resolve platform users for WeChat bindings the same way it does for Feishu / AD / built-in providers — through `_resolve_platform_user(binding, external_user)` using `binding.platform_field`, `binding.external_field`, and `binding.unmatched_user_action`. WeChat adapter SHALL NOT short-circuit the flow by returning `payload["login_result"]`.

#### Scenario: WeChat external_user flows through _resolve_platform_user

- **WHEN** WeChat adapter returns `payload["external_user"] = {"openid": "oxxx", ...}` and binding has `external_field="openid"`, `platform_field="username"`
- **THEN** `login_with_binding()` calls `_resolve_platform_user(binding, external_user)`
- **AND** `_resolve_platform_user` matches `User.objects.filter(username="oxxx").first()`

#### Scenario: WeChat binding with create action and no matched user creates a new platform user

- **WHEN** `_resolve_platform_user` finds no user matching `platform_field=external_value` and `binding.unmatched_user_action="create"`
- **THEN** a new `User` row is created with `username=external_value` (or fallback per WeChat rules)
- **AND** the new user is associated with the resolved default group

#### Scenario: WeChat binding with deny action and no matched user rejects login

- **WHEN** `_resolve_platform_user` finds no user matching `platform_field=external_value` and `binding.unmatched_user_action="deny"`
- **THEN** `_resolve_platform_user` returns `None`
- **AND** `login_with_binding()` returns `{"result": false, "message": "No matching platform user found"}`

### Requirement: Matching an existing platform user only refreshes last_login and does not modify profile

When `_resolve_platform_user` finds an existing platform user, the system SHALL return that user unchanged (no updates to `display_name`, `email`, `phone`, `group_list`, or `role_list`). The system SHALL refresh `last_login` to the current time as part of the `login_with_binding()` post-processing step, not as part of profile sync.

#### Scenario: Matched user profile fields are preserved

- **WHEN** `_resolve_platform_user` finds an existing user with `display_name="Old Name"`, `email="old@example.com"`, `phone="13800000000"`
- **AND** `external_user` contains `{"openid": "...", "nickname": "New Name", "email": "new@example.com"}`
- **THEN** the returned user still has `display_name="Old Name"`, `email="old@example.com"`, `phone="13800000000"`
- **AND** only `last_login` is updated to the current time

#### Scenario: Matched user last_login is refreshed

- **WHEN** `login_with_binding()` returns a token for an existing user
- **THEN** that user's `last_login` field is set to the current time and saved
- **AND** no other fields of the user record are modified by the login authentication flow

### Requirement: WeChat new user display_name initialization uses nickname

When `_resolve_platform_user` creates a new platform user for a WeChat binding, the new user's `display_name` SHALL be initialized from `external_user["nickname"]` if non-empty, otherwise from the resolved `username`. The system SHALL NOT overwrite `display_name` of an already-matched user.

#### Scenario: WeChat create new user with nickname

- **WHEN** WeChat binding has `unmatched_user_action="create"` and `external_user["nickname"]="Alice"`
- **AND** no platform user matches the external value
- **THEN** the new user's `display_name` is `"Alice"`

#### Scenario: WeChat create new user with empty nickname falls back to username

- **WHEN** WeChat binding has `unmatched_user_action="create"` and `external_user["nickname"]=""`
- **AND** the resolved `username` is `"oxxx"`
- **THEN** the new user's `display_name` is `"oxxx"`

#### Scenario: Non-WeChat create new user uses name field

- **WHEN** non-WeChat binding (e.g. Feishu) has `unmatched_user_action="create"` and `external_user["name"]="Bob"`
- **AND** no platform user matches the external value
- **THEN** the new user's `display_name` is `"Bob"` (using `name`, not `nickname`)

### Requirement: WeChat default group fallback to OpsPilotGuest when default_group_name is empty

When a WeChat binding has `unmatched_user_action="create"` and `default_group_name` is empty, the system SHALL fall back to using `OpsPilotGuest` as the default group for newly created platform users.

#### Scenario: WeChat create with empty default_group_name uses OpsPilotGuest

- **WHEN** WeChat binding has `unmatched_user_action="create"` and `default_group_name=""`
- **AND** no platform user matches the external value
- **THEN** a new `User` row is created
- **AND** the new user is added to the `OpsPilotGuest` group (auto-created with `parent_id=0` if absent)

#### Scenario: WeChat create with explicit default_group_name uses configured group

- **WHEN** WeChat binding has `unmatched_user_action="create"` and `default_group_name="CustomGroup"`
- **THEN** a new `User` row is created and added to the `CustomGroup` group
- **AND** `OpsPilotGuest` fallback is NOT applied

#### Scenario: Non-WeChat create with empty default_group_name still rejected

- **WHEN** non-WeChat binding has `unmatched_user_action="create"` and `default_group_name=""`
- **THEN** the system falls back to the existing behavior (no OpsPilotGuest fallback)

### Requirement: Serializer allows WeChat create with empty default_group_name but rejects non-WeChat create

The `LoginAuthBindingSerializer.validate()` method SHALL permit `default_group_name=""` when `unmatched_user_action="create"` only for WeChat provider bindings. For all other providers (including built-in), `default_group_name` remains required when `unmatched_user_action="create"`.

#### Scenario: WeChat create with empty default_group_name passes serializer validation

- **WHEN** serializer receives `unmatched_user_action="create"`, `default_group_name=""`, and `instance.provider_key="wechat"`
- **THEN** validation passes
- **AND** the binding is saved with empty `default_group_name`

#### Scenario: Non-WeChat create with empty default_group_name fails serializer validation

- **WHEN** serializer receives `unmatched_user_action="create"`, `default_group_name=""`, and `instance.provider_key` is not `wechat`
- **THEN** validation raises `ValidationError({"default_group_name": "Default group name is required when unmatched user action is create"})`

### Requirement: WeChat login authentication modal hides default_group_name input when create is selected

The WeChat login authentication modal SHALL NOT render the `default_group_name` input field when the binding has `unmatched_user_action="create"`. The system SHALL NOT auto-fill `OpsPilotGuest` as the default group value in the modal. The serializer-level fallback handles `OpsPilotGuest` at runtime.

#### Scenario: WeChat create modal does not render default_group_name input

- **WHEN** administrator selects a WeChat integration instance and `unmatched_user_action="create"`
- **THEN** the modal does NOT display a "默认组名" input field
- **AND** submitting the form sends `default_group_name=""` in the payload

#### Scenario: WeChat modal does not auto-fill OpsPilotGuest

- **WHEN** administrator selects a WeChat integration instance
- **THEN** the modal does NOT pre-populate `default_group_name="OpsPilotGuest"`
- **AND** `OpsPilotGuest` is resolved at runtime by the backend fallback

#### Scenario: Non-WeChat create modal still renders default_group_name input

- **WHEN** administrator selects a non-WeChat integration instance (e.g. Feishu) and `unmatched_user_action="create"`
- **THEN** the modal displays the "默认组名" input field
- **AND** the field is required for the form to pass validation

### Requirement: Legacy WeChat login endpoint retained with deprecation marker

The `wechat_login` view in `server/apps/core/views/index_view.py` SHALL be retained for backward compatibility with existing WeChat scan-code login integrations. The view SHALL be marked with a `[LEGACY]` docstring indicating it runs in parallel with the new `LoginAuthBinding` generic flow and is scheduled for removal after the new flow is stable.

#### Scenario: Legacy wechat_login endpoint continues to work

- **WHEN** a client calls `POST /api/v1/wechat_login/` with a valid WeChat auth code
- **THEN** the endpoint still invokes `wechat_user_register` NATS handler and returns a token
- **AND** the function body is unchanged from its current implementation

#### Scenario: Legacy endpoint carries deprecation marker

- **WHEN** developer reads the `wechat_login` function source
- **THEN** the docstring starts with `[LEGACY]`
- **AND** the docstring references `openspec/changes/wechat-login-auth-field-mapping/design.md` as the rationale

## MODIFIED Requirements

<!-- The following existing requirements are extended. The original requirement text is preserved and the extension clarifies the new WeChat behavior. -->

### Requirement: Login authentication provider adapter generic interface

The login authentication provider adapter interface (`BaseLoginAuthAdapter.authenticate`) SHALL return a `CapabilityExecutionResult` whose `payload` is interpreted by `login_with_binding()` according to the following contract (extended to cover WeChat):

- **`login_result`** (deprecated, WeChat-specific legacy contract): if present and non-empty, `login_with_binding()` returns it directly to the caller, skipping the generic user resolution flow. This contract is retained ONLY for backward compatibility; new provider adapters SHALL NOT use it.
- **`external_user`** (generic contract): if present, `login_with_binding()` passes it to `_resolve_platform_user()` to perform platform user matching and creation per the binding's `platform_field`, `external_field`, `unmatched_user_action`, and `default_group_name` configuration.

The WeChat login authentication adapter SHALL use the `external_user` contract and SHALL NOT use the `login_result` contract.

#### Scenario: WeChat adapter uses external_user contract

- **WHEN** WeChat `authenticate()` returns a `CapabilityExecutionResult` with `payload["external_user"]` set
- **THEN** `login_with_binding()` extracts `external_user` and calls `_resolve_platform_user(binding, external_user)`
- **AND** `login_with_binding()` does NOT short-circuit on `payload["login_result"]`

#### Scenario: Non-WeChat adapters continue to use external_user contract

- **WHEN** any non-WeChat adapter (Feishu / AD / built-in) returns `payload["external_user"]`
- **THEN** `login_with_binding()` continues to resolve the user through `_resolve_platform_user`
- **AND** behavior is unchanged from previous versions
