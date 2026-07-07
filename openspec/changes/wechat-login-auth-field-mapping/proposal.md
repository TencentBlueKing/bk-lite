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
