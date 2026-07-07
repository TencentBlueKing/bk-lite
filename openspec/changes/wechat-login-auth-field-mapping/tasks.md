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
