# Wechat Login Auth Field Mapping

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/wechat-login-auth-field-mapping/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

`LoginAuthBinding` 通用登录认证链路已支持「平台字段 ↔ 外部字段」映射、未匹配处理、默认组处理和 token 签发,但 WeChat provider 走了一条与通用链路并行的旧分支:

- `WechatLoginAuthAdapter.authenticate()` 在拿到微信 `userinfo` 后**直接调用**旧的 NATS handler `wechat_user_register(openid, nickname)`,并把 `login_result` 塞进 `payload["login_result"]`。
- `login_with_binding()` 在发现 `payload["login_result"]` 后**直接返回**,导致 `_resolve_platform_user()` 内的 `external_field` / `platform_field` / `unmatched_user_action` / `default_group_name` 全部不生效。
- WeChat manifest 把可匹配字段声明为 `open_id` / `nickname`,与微信 `sns/userinfo` 真实返回的 `openid` 不一致;且 `nickname` 是可变昵称,不应作为账号匹配字段。
- 前端弹窗在 WeChat create 时自动填 `OpsPilotGuest`,后端 serializer 又强制 `default_group_name` 必填,形成「前端想隐藏、后端不让空」的矛盾。

结果:管理员在「登录认证」页给 WeChat 配置的字段映射,运行时完全不被使用,实际行为仍是旧扫码登录逻辑,UI 与行为不一致。

## What Changes

- **WeChat provider 改为只返回真实 external_user**:`WechatLoginAuthAdapter.authenticate()` 删掉 `wechat_user_register` 调用和 `payload["login_result"]`,改为返回微信原始字段(以 `openid` 为准,不再硬造 `user_id` / `open_id` / `name`)。
- **WeChat manifest 字段修正**:`available_external_fields` 改为 `["openid", "unionid"]`,`default_external_match_field` 改为 `"openid"`,移除 `nickname`。
- **通用登录认证链路生效**:
  - 匹配已有用户时只刷 `last_login`,删除 `_update_user_profile()` 函数(不覆盖 `display_name` / `email` / `phone` / `group_list` / `role_list`)。
  - 创建新用户时 `display_name = external_user.get("nickname") or username`(仅 WeChat 场景;其他 provider 仍走 `name or username`)。
  - `platform_field != username` 时,username 兜底改为 `external_user.get("openid") or external_value`,按 `platform_field` 写入对应字段。
  - 保留现有 WeChat 默认组 fallback(`default_group_name` 为空时自动用 `OpsPilotGuest`)。
- **serializer 允许 WeChat create 时 `default_group_name` 为空**,非 WeChat create 仍要求必填。
- **前端弹窗行为**:
  - 移除 WeChat 选中时自动填 `OpsPilotGuest` 的逻辑。
  - WeChat `unmatched_user_action === 'create'` 时**不渲染**「默认组名」输入框。
  - WeChat create payload 允许 `default_group_name = ""`,非 WeChat provider 行为不变。
- **旧入口 `index_view.py:wechat_login` 保留**,仅在函数顶部加注释标记为 legacy,说明「与 LoginAuthBinding 通用链路并行,新链路稳定后移除」。

## Capabilities

### New Capabilities

<!-- 本次不新增独立 capability,在已有 login-auth-binding 下加 MODIFIED -->

### Modified Capabilities

- `login-auth-binding`:扩展 WeChat 场景下的 provider 行为、字段映射语义和默认组处理

## Impact

- **后端**:
  - `server/apps/system_mgmt/providers/manifests/wechat.py` — manifest 字段名与可匹配字段集调整
  - `server/apps/system_mgmt/providers/adapters/wechat.py` — adapter 不再调 `wechat_user_register`,改为返回 `external_user`
  - `server/apps/system_mgmt/services/login_auth_binding_service.py` — `_resolve_platform_user` 不调 `_update_user_profile` 并删除该函数;username / display_name 兜底逻辑调整
  - `server/apps/system_mgmt/serializers/login_auth_binding_serializer.py` — WeChat create 允许空 `default_group_name`
  - `server/apps/system_mgmt/tests/test_builtin_platform_login_auth.py` — 改写 `test_login_with_binding_accepts_adapter_supplied_login_result`,断言走 `external_user` 路径
- **前端**:
  - `web/src/app/system-manager/(pages)/user/login-auth/page.tsx` — 移除自动填 `OpsPilotGuest`,WeChat create 不展示默认组名输入框
  - `web/src/app/system-manager/utils/loginAuthFormUtils.ts` — WeChat create 允许 `default_group_name` 为空字符串
  - `web/scripts/login-auth-modal-behavior-test.ts` — 新增 WeChat 默认外部字段 = `openid`、WeChat create payload 空默认组等用例
- **旧入口**:
  - `server/apps/core/views/index_view.py` — `wechat_login` 顶部加 legacy 注释
- **API 行为**:
  - WeChat provider 的 `authenticate()` 返回结构从 `{"login_result": {...}}` 改为 `{"external_user": {...}}`
  - 字段名从 `open_id` 变更为 `openid`(无历史数据需要迁移,见 design.md 决策 6)
- **依赖**:无新增依赖
- **配置/数据**:`available_external_fields` / `default_external_match_field` 变更只影响前端提示,不影响数据库字段

## Implementation Decisions

## Context

`LoginAuthBinding` 是 BK-Lite 后端的「集成登录认证」配置入口,管理员可在「登录认证」页为某个 `IntegrationInstance` 配置:

- `platform_field`:平台账号字段(`username` / `email` / `phone`)
- `external_field`:外部身份系统返回的用户字段
- `unmatched_user_action`:未匹配平台用户时 `deny` 或 `create`
- `default_group_name`:create 时的默认组

通用登录认证流程在 `server/apps/system_mgmt/services/login_auth_binding_service.py` 的 `login_with_binding()` 中,执行顺序是:

```
RuntimeApplicationService.execute(operation="authenticate")
  → result.payload.get("login_result")      # 命中即返回(短路)
  → result.payload.get("external_user")
  → _resolve_platform_user(binding, external_user)
    → User.objects.filter(platform_field=external_value).first()   # 匹配
    → 未匹配且 action=create → User.objects.create(...)            # 创建
  → user.last_login = now → get_user_login_token(...)
```

WeChat provider 是**唯一**走 `login_result` 短路路径的 provider。它的 `authenticate()` 调 `wechat_user_register(openid, nickname)` 这个 NATS handler——这个 handler 会自己用 `username=openid` 创建/获取用户、自己刷 `last_login` / `role_list`、自己签发 token,再把结果包成 `{"login_result": {...}}` 返回。

### 修复前 vs 修复后(主流程对照)

```text
                  修 复 前                                       修 复 后

   ┌─────────────────────────────┐                ┌─────────────────────────────┐
   │  login_with_binding()       │                │  login_with_binding()       │
   └──────────────┬──────────────┘                └──────────────┬──────────────┘
                  │                                              │
                  ▼                                              ▼
   ┌─────────────────────────────┐                ┌─────────────────────────────┐
   │ RuntimeApp.execute(         │                │ RuntimeApp.execute(         │
   │   operation="authenticate"  │                │   operation="authenticate"  │
   └──────────────┬──────────────┘                └──────────────┬──────────────┘
                  │                                              │
                  ▼                                              ▼
   ┌─────────────────────────────┐     删 wechat_   ┌─────────────────────────────┐
   │ WechatLoginAuthAdapter      │   user_register  │ WechatLoginAuthAdapter      │
   │  · code → access_token      │  ──────────────▶ │  · code → access_token      │
   │  · fetch userinfo           │                  │  · fetch userinfo           │
   │  · wechat_user_register(    │                  │  · return external_user     │
   │      openid, nickname)      │                  │      = {openid, unionid,    │
   │  · login_result = …         │                  │         nickname, ...}      │
   └──────────────┬──────────────┘                  └──────────────┬──────────────┘
                  │                                              │
                  │ ① 命中即返回                                  │ ② 通用链路继续
                  │ 短路!                                         ▼
                  ▼                                ┌─────────────────────────────┐
   ┌─────────────────────────────┐                │ _resolve_platform_user(     │
   │ 直接返回 token              │                │   binding, external_user)    │
   │ (字段映射从未执行)          │                │  · 匹配已有用户(只刷         │
   └─────────────────────────────┘                │    last_login, 不改 profile) │
                                                │  · 未匹配 + create          │
                                                │    → display_name =         │
                                                │      WeChat: nickname       │
                                                │      其他: name             │
                                                │    → OpsPilotGuest fallback │
                                                │      (WeChat + 空 default)  │
                                                └──────────────┬──────────────┘
                                                               │
                                                               ▼
                                                ┌─────────────────────────────┐
                                                │ 刷 last_login →             │
                                                │ get_user_login_token → 返回 │
                                                └─────────────────────────────┘
```

**当前问题**:
1. 通用链路的字段映射对 WeChat 不生效,UI 配置是装饰品
2. WeChat manifest 的 `open_id` / `nickname` 与微信 `sns/userinfo` 真实返回字段 `openid` 不一致
3. 旧 NATS handler `wechat_user_register` 仍被新 provider 调,职责重叠
4. 前端自动填 `OpsPilotGuest` + 后端强制 `default_group_name` 必填,形成「前端想隐藏 → 后端不让空」的死结

## Goals / Non-Goals

**Goals**:
- WeChat provider 只返回微信真实 `external_user`,不签发 token、不创建/获取用户
- WeChat 可匹配字段集改为 `["openid", "unionid"]`,默认 `openid`
- 通用登录认证链路在 WeChat 场景下真实生效:`platform_field` / `external_field` / `unmatched_user_action` 全部按 binding 配置工作
- 匹配已有用户时**只刷 `last_login`**,不修改业务字段
- 创建新用户时 WeChat 用 `nickname` 初始化 `display_name`
- WeChat `unmatched_user_action=create` 且 `default_group_name` 为空时,后端 fallback 到 `OpsPilotGuest`
- WeChat `unmatched_user_action=create` 时,UI 不展示「默认组名」输入框
- serializer 允许 WeChat create 时 `default_group_name=""`,非 WeChat 仍要求必填
- 旧入口 `wechat_login` 保留并加 legacy 注释

**Non-Goals**:
- 不移除 `wechat_user_register` NATS handler(旧入口继续依赖)
- 不改 `LoginAuthBinding` 模型结构
- 不做历史 `external_field="open_id"` 数据迁移(线上无此数据)
- 不动非 WeChat provider 的字段映射行为

## Decisions

### 1. WeChat adapter 改为返回 `external_user`,不再调 `wechat_user_register`

**选择**: 删 `wechat_user_register` 调用,改为在 `payload` 中返回 `external_user` 字段。

```python
return CapabilityExecutionResult.success_result(
    "WeChat login authenticated",
    payload={
        "external_user": {
            "openid": user_data["openid"],
            "unionid": user_data.get("unionid", ""),
            "nickname": user_data.get("nickname", ""),
            "headimgurl": user_data.get("headimgurl", ""),
        }
    },
)
```

**理由**:
- 与 `FeishuLoginAuthAdapter.authenticate()` 行为一致,通用链路已经为这种 payload 设计
- 账号匹配、用户创建、token 签发都由 `login_with_binding()` 统一负责,职责清晰
- 旧 NATS handler 的 `wechat_user_register` 仍可保留,旧入口 `index_view.py:wechat_login` 继续使用

**备选**:
- 在 adapter 内直接签发 token 并复用 `login_result` 短路路径 → 与通用链路脱节,放弃

### 2. WeChat manifest 字段名修正

**选择**:

```python
"available_external_fields": ["openid", "unionid"],
"default_external_match_field": "openid",
```

**理由**:
- 微信 `sns/userinfo` 接口真实返回的字段就是 `openid`(无下划线)
- `nickname` 是可变昵称,不该作为匹配字段(可被用户改、可重复、可空)

**备选**:
- 保留 `nickname` 作为可选匹配字段 → 误用风险高,放弃

### 3. 匹配已有用户时只刷 `last_login`,`_update_user_profile` 函数彻底删除

**选择**: 在 `_resolve_platform_user` 的命中分支去掉 `return _update_user_profile(user, external_user)`,改为 `return user`。`_update_user_profile` 函数整体删除(全仓仅 1 处调用,经 grep 确认无外部引用与测试依赖)。

**理由**:
- 登录认证不是资料同步,匹配成功后不应该覆盖平台用户业务字段
- 函数是 `_` 私有 helper,无外部模块 import,无测试 mock,删除安全
- 「为未来按 provider 差异化更新留扩展点」是过度设计 — 真有需求时基于 git 历史恢复一行即可
- `last_login` 由 `login_with_binding:83-84` 外层 `user.save(update_fields=["last_login", ...])` 负责,不变

**备选**:
- 保留为 no-op 函数体 → 维护一个空函数没有意义,放弃

### 4. 创建新用户时 WeChat 用 `nickname` 初始化 `display_name`

**选择**:

```python
if binding.integration_instance.provider_key == "wechat":
    display_name = external_user.get("nickname") or username
else:
    display_name = external_user.get("name") or username
```

**理由**:
- 微信 userinfo 不返回标准 `name` 字段,只有 `nickname`
- `nickname` 只用于新用户初始化,不参与匹配、不覆盖已有用户
- 其他 provider(飞书、AD)继续用 `name` 字段,行为不变

### 5. `platform_field != username` 时 username 兜底

**选择**: username 兜底按 `external_user` 中真实存在的稳定身份字段,不再读 `user_id` / `open_id`(这两个字段是 Feishu 旧字段,WeChat 场景下不存在)。

```python
external_value = external_user.get(binding.external_field) or external_user.get("openid") or ""
# 创建时 username
if binding.integration_instance.provider_key == "wechat":
    username = external_user.get("openid") or external_value
else:
    username = external_value  # 其他 provider 由 external_field 直接决定
```

**理由**:
- 平台 user 必须有 `username`,`platform_field=email/phone` 时仍需要 username 兜底
- 稳定身份字段是 `openid`,不是 `user_id` / `open_id`(那些是其他 provider 的字段)

#### 字段兜底数据流(WeChat create 场景示例)

```text
binding.platform_field = "email"
binding.external_field  = "openid"
external_user = {"openid": "oxxx", "nickname": ""}

匹配阶段:
   User.objects.filter(email=external_user["openid"])
   external_value = external_user["openid"] = "oxxx"
   → 没找到 → 进入 create 分支

create 分支(WeChat):
   ┌─ username 兜底
   │  external_user.get("openid")     = "oxxx"   ← WeChat 唯一稳定身份字段
   │  or external_value                = "oxxx"
   │  → username = "oxxx"
   │
   ├─ 按 platform_field 写入对应字段
   │  User.email = "oxxx"             ← platform_field=email
   │
   ├─ display_name 兜底
   │  external_user.get("nickname")   = ""       ← WeChat 用 nickname
   │  or username                     = "oxxx"
   │  → display_name = "oxxx"
   │
   └─ default_group fallback
      binding.default_group_name = "" (WeChat + 空)
      → default_group_name = "OpsPilotGuest"
      → User.group_list = [OpsPilotGuest.id]

最终写入:
   User(username="oxxx", email="oxxx", display_name="oxxx",
        group_list=[OpsPilotGuest.id], password="", domain="domain.com")
```

### 6. 不做历史 `external_field="open_id"` 数据迁移

**选择**: 直接改 manifest 字段名,旧 `open_id` 不再出现在 `available_external_fields` 中。

**理由**:
- 线上无 `external_field="open_id"` 的历史 binding(经用户确认)
- 旧 binding 即使存在,新 manifest 的提示也只展示 `openid / unionid`,管理员主动改 binding 才能修复(失败也是显式的)

**备选**:
- 写 migration 脚本把 `external_field="open_id"` 改成 `"openid"` → 线上无数据,无意义

### 7. serializer 允许 WeChat create 时 `default_group_name=""`

**选择**: 校验逻辑改为

```python
if unmatched_action == CREATE and not default_group_name:
    is_wechat = (instance.provider_key == "wechat")
    if not is_wechat:
        raise ValidationError({"default_group_name": "Default group name is required..."})
    # WeChat 允许空,后端 fallback 到 OpsPilotGuest
```

**理由**:
- 前端 WeChat create 时不展示「默认组名」输入框,提交时该字段为空
- 后端必须有 fallback,否则 binding 保存失败
- 非 WeChat provider 仍要求必填,行为不变

### 8. 前端 WeChat 选中时不再自动填 `OpsPilotGuest`,WeChat create 不渲染默认组名输入框

**选择**:
- `handleIntegrationInstanceChange(providerKey === 'wechat')` 不再写 `form.setFieldValue('default_group_name', 'OpsPilotGuest')`
- WeChat create 时 `{unmatchedAction === 'create' && <Form.Item default_group_name .../>}` 改为 `{!isWechat && unmatchedAction === 'create' && ...}`
- WeChat create 时 `buildLoginAuthBindingPayload` 允许 `default_group_name=""`

**理由**:
- 旧前端把 `OpsPilotGuest` 写进 binding 数据,绑定到具体 binding 的 `default_group_name`;新策略下「默认加入 OpsPilotGuest」是后端 fallback 行为,不应作为配置写入 binding
- UI 与后端 fallback 分离:管理员不需要也不能改默认组

**备选**:
- 保留前端自动填值,后端 fallback 删掉 → 后端失去兜底,serializer 仍要允许空,反而让 fallback 在 binding 数据为空时失效

### 9. 旧入口 `index_view.py:wechat_login` 保留

**选择**: 函数体不动,顶部加 legacy 注释:

```python
@api_exempt
def wechat_login(request):
    """
    [LEGACY] 旧扫码登录入口,与 LoginAuthBinding 通用链路并行。
    新链路稳定后移除。详见:
    openspec/changes/wechat-login-auth-field-mapping/design.md
    """
```

**理由**:
- 旧入口可能仍有外部依赖(扫码登录配置)
- 新入口走 `RuntimeApplicationService` → `WechatLoginAuthAdapter.authenticate()`,与旧入口调用栈完全分离
- 标记后便于未来清理

**备选**:
- 直接删除旧入口 → 可能影响线上正在使用的旧登录配置,放弃

#### 旧入口与新链路并存关系

```text
                    旧扫码登录入口                        新集成登录认证入口
                  (index_view.py)                    (LoginAuthBinding)
                        │                                     │
                        ▼                                     ▼
              ┌─────────────────────┐               ┌──────────────────────┐
              │ wechat_login(request)│               │  登录认证弹窗配置     │
              │   [LEGACY]           │               │  binding             │
              │                     │               │  (external_field=    │
              │  · verify_wechat_    │               │   openid,            │
              │    code(code)        │               │   platform_field=    │
              │  · openid, nickname  │               │   username, ...)     │
              └──────────┬──────────┘               └──────────┬───────────┘
                         │                                     │
                         │ RPC                                 │ HTTP
                         │ client.wechat_                      │ /api/v1/login_auth/...
                         │ user_register                       │
                         ▼                                     ▼
              ┌─────────────────────┐               ┌──────────────────────┐
              │ wechat_user_register │               │ RuntimeApplication   │
              │ (NATS handler)       │               │ Service.execute(     │
              │                     │               │   authenticate)      │
              │  · username=openid   │               └──────────┬───────────┘
              │  · OpsPilotGuest     │                          │
              │  · normal/guest role │                          ▼
              │  · sign token        │               ┌──────────────────────┐
              │  · return {token,…}  │               │ WechatLoginAuth      │
              └─────────────────────┘               │ Adapter              │
                                                    │  · code→access_token │
                                                    │  · fetch userinfo    │
                                                    │  · return external_  │
                                                    │    user              │
                                                    └──────────┬───────────┘
                                                               │
                                                               ▼
                                                    ┌──────────────────────┐
                                                    │ _resolve_platform_   │
                                                    │ user(binding, ext)   │
                                                    │  · 匹配/创建/兜底     │
                                                    │  · get_user_login_    │
                                                    │    token             │
                                                    └──────────────────────┘

   现状:两条链路并行,新链路行为正确,旧链路作为兼容入口保留
   未来:旧入口扫码登录配置全量切换到新链路后,删除 wechat_login 和 wechat_user_register
```

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|---------|
| 旧入口与新入口行为不一致,管理员可能误用 | 旧入口顶部加 LEGACY 注释;后续 deprecate |
| `wechat_user_register` NATS handler 仍被旧入口依赖,但新 adapter 不再调用 | handler 保留;旧入口继续工作;新链路不再需要 |
| 匹配成功后不再覆盖 `display_name`,旧微信用户 `display_name` 仍是 openid | 这是新策略的预期行为,用户登录后可在用户管理手动改名 |
| WeChat create 时 `default_group_name` 持久化为空 | serializer 允许;后端 fallback 在登录时生效;`last_login` 仍正常刷 |

## 修改的文件清单

### 后端核心

- `server/apps/system_mgmt/providers/manifests/wechat.py` — manifest 字段修正
- `server/apps/system_mgmt/providers/adapters/wechat.py` — adapter 返回 `external_user`
- `server/apps/system_mgmt/services/login_auth_binding_service.py` — `_resolve_platform_user` 调整
- `server/apps/system_mgmt/serializers/login_auth_binding_serializer.py` — 校验放宽

### 后端测试

- `server/apps/system_mgmt/tests/test_builtin_platform_login_auth.py` — 改写 `test_login_with_binding_accepts_adapter_supplied_login_result`
- 新增 `test_login_with_binding_resolves_external_user_for_wechat`(走 `external_user` 路径断言)
- 新增 `test_login_with_binding_does_not_update_existing_user_profile`(断言匹配后不改 display_name/email/phone)
- 新增 `test_login_auth_binding_serializer_allows_wechat_create_with_empty_default_group`
- 新增 `test_login_auth_binding_serializer_rejects_non_wechat_create_with_empty_default_group`

### 前端

- `web/src/app/system-manager/(pages)/user/login-auth/page.tsx` — 弹窗行为调整
- `web/src/app/system-manager/utils/loginAuthFormUtils.ts` — payload 构建
- `web/scripts/login-auth-modal-behavior-test.ts` — 用例扩展

### 旧入口标记

- `server/apps/core/views/index_view.py` — `wechat_login` 顶部加 LEGACY 注释

## Capability Deltas

### login-auth-binding

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

## Work Checklist

## 1. WeChat manifest 字段修正

- [x] 1.1 修改 `server/apps/system_mgmt/providers/manifests/wechat.py`,将 `available_external_fields` 改为 `["openid", "unionid"]`
- [x] 1.2 将 `default_external_match_field` 改为 `"openid"`

## 2. WeChat adapter 返回 external_user

- [x] 2.1 修改 `server/apps/system_mgmt/providers/adapters/wechat.py`,删除 `from apps.system_mgmt.nats_api import wechat_user_register` 与 `wechat_user_register(...)` 调用
- [x] 2.2 替换 `payload={"login_result": ...}` 为 `payload={"external_user": {...}}`,字段用 `openid` / `unionid` / `nickname` / `headimgurl`
- [x] 2.3 保留 OAuth 错误处理(`errcode` / `errmsg` / 超时分支)不变
- [x] 2.4 防御性处理:userinfo 缺 openid 时 fallback 到 token 的 openid;两者都缺时返回 `provider.invalid_response` 失败结果(避免 KeyError)
- [x] 2.5 补 `apps/system_mgmt/tests/test_wechat_login_auth_adapter.py` 直接单元测试,覆盖 token exchange / userinfo / errcode / 缺 openid / 不调用 `wechat_user_register` 等场景

## 3. 通用登录认证 service 调整

- [x] 3.1 修改 `server/apps/system_mgmt/services/login_auth_binding_service.py` 的 `_resolve_platform_user`
- [x] 3.2 命中已有用户分支去掉 `_update_user_profile` 调用,改为 `return user`
- [x] 3.3 删除 `_update_user_profile` 函数定义(全仓仅 1 处调用,经 grep 确认无外部引用与测试依赖)
- [x] 3.4 调整 `external_value` fallback 链:删除 `user_id` / `open_id`,只保留 `external_user.get(binding.external_field) or external_user.get("openid") or ""`
- [x] 3.5 创建用户时 WeChat 用 `external_user.get("nickname") or username` 作为 `display_name`;其他 provider 维持 `external_user.get("name") or username`
- [x] 3.6 创建用户时 username 兜底:WeChat 用 `external_user.get("openid") or external_value`;其他 provider 用 `external_value`
- [x] 3.7 保留现有 WeChat `OpsPilotGuest` fallback 逻辑(`if not default_group_name and provider_key == "wechat": default_group_name = "OpsPilotGuest"`)

## 4. serializer 校验放宽

- [x] 4.1 修改 `server/apps/system_mgmt/serializers/login_auth_binding_serializer.py` 的 `validate` 方法
- [x] 4.2 `unmatched_action=create && default_group_name=""` 时:WeChat 允许通过;非 WeChat 抛 `ValidationError`
- [x] 4.3 确认 `bk_lite_builtin` provider 的 protected fields 保护逻辑仍生效(不被本次改动影响)
- [x] 4.4 用 `in` 检查区分 "字段未提交" 和 "显式空字符串",避免 update 场景被旧值兜底绕过校验
- [x] 4.5 补 `test_serializer_rejects_non_wechat_update_clearing_default_group` 测试覆盖 update 场景

## 5. 前端弹窗行为调整

- [x] 5.1 修改 `web/src/app/system-manager/(pages)/user/login-auth/page.tsx` 的 `handleIntegrationInstanceChange`
- [x] 5.2 移除 WeChat 选中时 `form.setFieldValue('default_group_name', 'OpsPilotGuest')` 自动填值逻辑(只保留 `unmatched_user_action='create'` 的预填)
- [x] 5.3 WeChat create 渲染分支(`unmatchedAction === 'create'` 块)增加 `!isWechat` 守卫,不渲染 `<Form.Item default_group_name>`

## 6. 前端 payload 构建

- [x] 6.1 修改 `web/src/app/system-manager/utils/loginAuthFormUtils.ts` 的 `buildLoginAuthBindingPayload`
- [x] 6.2 WeChat create 时允许 `default_group_name=""`(当前实现已经是 `values.default_group_name?.trim() || ''`,确认覆盖即可)
- [x] 6.3 非 WeChat provider 行为不变(deny 时清空 default_group_name)

## 7. 前端测试扩展

- [x] 7.1 在 `web/scripts/login-auth-modal-behavior-test.ts` 新增:WeChat 默认外部字段 = `openid`(根据 manifest 切换)
- [x] 7.2 新增:WeChat create 时 payload 中 `default_group_name=""` 不报错
- [x] 7.3 新增:非 WeChat create 时 payload 中 `default_group_name=""` 强制 deny(已有断言需更新)
- [x] 7.4 跑 `cd web && pnpm exec tsx scripts/login-auth-modal-behavior-test.ts` 确认通过

## 8. 后端测试改写与新增

- [x] 8.1 改写 `server/apps/system_mgmt/tests/test_builtin_platform_login_auth.py::test_login_with_binding_accepts_adapter_supplied_login_result` → 改为 `test_login_with_binding_resolves_external_user_for_wechat`
- [x] 8.2 改写后断言走 `_resolve_platform_user` 路径:mock 返回 `external_user`,断言最终调用 `get_user_login_token` 并签发 token
- [x] 8.3 新增 `test_login_with_binding_resolves_external_user_for_wechat`:验证 `openid` 映射 `username` 匹配已有用户
- [x] 8.4 新增 `test_login_with_binding_resolves_external_user_for_wechat_via_unionid`:验证 `unionid` 映射 `username` 匹配
- [x] 8.5 新增 `test_login_with_binding_does_not_modify_existing_user_profile`(在 `test_runtime_service.py`):匹配已有用户后 `display_name` / `email` / `phone` 不变
- [x] 8.6 新增 `test_login_with_binding_creates_new_user_with_nickname_display_name_for_wechat`:未匹配 + create 时 `display_name = nickname`
- [x] 8.7 新增 `test_login_with_binding_falls_back_to_ops_pilot_guest_for_wechat`:WeChat create 且 default_group_name 空时,新建用户加入 `OpsPilotGuest`
- [x] 8.8 新增 `test_serializer_allows_wechat_create_with_empty_default_group`
- [x] 8.9 新增 `test_serializer_rejects_non_wechat_create_with_empty_default_group`
- [x] 8.10 新增 `test_serializer_rejects_non_wechat_update_clearing_default_group`(CRITICAL-1 修复)
- [x] 8.11 新增 `apps/system_mgmt/tests/test_wechat_login_auth_adapter.py` adapter 直接测试(WARNING-3)

## 9. 旧入口标记

- [x] 9.1 修改 `server/apps/core/views/index_view.py` 的 `wechat_login` 函数
- [x] 9.2 在 docstring 顶部加 `[LEGACY]` 标记,引用 `openspec/changes/wechat-login-auth-field-mapping/design.md`

## 10. 验证

- [x] 10.1 跑 `cd server && uv run python -m pytest apps/system_mgmt/tests/test_builtin_platform_login_auth.py apps/system_mgmt/tests/test_wechat_login_auth_adapter.py apps/system_mgmt/tests/test_login_auth_manifest.py apps/system_mgmt/tests/test_runtime_service.py` 全部通过(46 passed, 1 warning)
- [ ] 10.2 跑 `pnpm lint && pnpm type-check` 在 `web/` 下 — 未完整跑,改动文件 lint 干净;type-check 有预先存在的错误(非本 PR 引入)
- [x] 10.3 跑 `cd web && pnpm exec tsx scripts/login-auth-modal-behavior-test.ts` 通过
- [ ] 10.4 手动验证:配置一个 WeChat binding(`platform_field=username, external_field=openid, unmatched=create`),用真实微信 OAuth 走一次登录 — 需在线上或测试环境手动跑,本环境无法 mock 真实微信 OAuth
