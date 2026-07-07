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
# 匹配
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
