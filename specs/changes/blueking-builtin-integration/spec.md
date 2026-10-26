# 内置蓝鲸集成：登录认证与用户同步

Status: proposed

## Problem Statement

旧的蓝鲸单点登录还挂在 `get_bk_settings` 上：页面启动读取 cookie `bk_token`，`verify_bk_token` 用已启用的 `LoginModule(source_type=bk_login)` 向蓝鲸核对身份，并在根组织下创建或更新本地用户。认证源管理页和 `LoginModule` 路由已经关闭，启动写入的「蓝鲸平台」默认不启用。现网响应里的 `bk_login_open: false` 就是这条关闭状态。

集成中心已经用 Provider 承接企微、飞书、微信和 AD 的登录认证与用户同步。蓝鲸需要回到这条链路，同时保留「同一父域名下打开 BK-Lite 就带上 `bk_token`」的单点方式。

## Solution

新增社区内置 Provider `blueking`，只声明 `login_auth` 和 `user_sync`。管理员在集成中心配置蓝鲸地址、应用 ID、应用 Token，再启用登录认证并创建用户同步源。

浏览器入口不变。`get_bk_settings` 继续在启动时被调用，并继续返回门户品牌。只有蓝鲸登录认证就绪时，服务端才用 `bk_token` 向蓝鲸核对用户名，再按登录绑定匹配已同步的本地用户。匹配成功则签发本平台 JWT 并写入 `bklite_token`。登录页的 binding 列表不展示蓝鲸。

## User Stories

1. As a 系统管理员, I want 在集成中心创建蓝鲸实例并填写地址与应用凭证, so that 不用再打开已关闭的认证源页面。
2. As a 系统管理员, I want 用户同步源可以选择「全部」或一个根部门，并默认包含下级, so that 拉取范围和企微、飞书一样由同步源决定。
3. As a 已在蓝鲸登录的用户, I want 打开同一父域名下的 BK-Lite 时直接进入已同步账号, so that 不必在登录页再点一次蓝鲸。
4. As a 尚未被该蓝鲸同步源同步的用户, I want 绑定保持默认拒绝时携带 `bk_token` 打开 BK-Lite 停在本平台登录页, so that 未改配置不会临时创建账号。管理员若把该绑定改成创建，则按 `specs/changes/login-auth-unmatched-create/spec.md` 建号。
5. As a 只使用本平台账号的用户, I want 蓝鲸登录未启用时启动请求不再向蓝鲸核验 cookie, so that 门户品牌照常返回，身份保持本平台会话。

## Implementation Decisions

- Provider 键为 `blueking`，放在 `server/apps/system_mgmt/providers/builtin/blueking/`。loader 按目录自动发现。必填文件沿用现有包：`__init__.py`、`manifest.py`、`adapters/client.py`、`adapters/base_connection.py`，外加 `adapters/login_auth.py`、`adapters/user_sync.py` 和中英文 `language/*.yaml`。
- 能力只有 `login_auth` 与 `user_sync`。不声明 IM 通知或群协作。
- 基础连接字段：`bk_url`（蓝鲸地址）、`app_id`（应用 ID）、`app_token`（应用 Token，密钥，加密存储，回显脱敏）。三者变更时重置 `login_auth` 与 `user_sync`。不提供调用用户名表单字段。不把 ESB 路径做成表单字段；路径使用下面的固定后缀。
- 登录认证业务模板只提供用户名这一个外部身份字段，默认且唯一的外部字段是 `username`，平台字段锁定为 `username`。未匹配动作默认 `deny`。管理员可以改成创建，规则见 `specs/changes/login-auth-unmatched-create/spec.md`。登录不改已有用户的显示名、邮箱、手机、组织和角色。
- 用户同步拉取设置与企微相同：`root_department_id` 使用 `department_select`，必填；`include_child_departments` 默认 `true`。部门选择器顶部有一个可选节点「全部」。选中「全部」时拉取蓝鲸用户管理返回的全部部门和这些部门中的用户，本地目录与 LDAP 目录的部门都在这棵树下，不先选目录。选中具体部门时只拉该部门；关闭「包含子部门」时只留该部门本身及其直属用户。空值、`__all__`、`**all**` 继续视为无效，不作为可保存根。
- 「全部」使用本 Provider 在 `list_departments` 里返回的稳定节点 id `bk_all`，名称由语言包给出。`sync_users` 只在 `root_department_id == bk_all` 时拉全量。该 id 不是蓝鲸部门 id，也不会交给 ESB。此时父部门不在本次拉取结果中的节点，`group_list.parent_id` 写 `bk_all`，现有引擎才能把这些顶级部门建到同步源根组下。更下层仍用返回的 `parent`。选具体部门时不改 `parent`。
- 用户同步载荷沿用现有引擎：`group_list` 为 `{id, parent_id, name}`，`user_list` 至少含 `username`、`display_name`、`email`、`mobile`、`department_ids`。蓝鲸字段对应关系：`username`、`display_name`、`email`、`telephone`、部门 `id`。本地根组织名仍用同步源已有的 `root_group_name`。失效清理只作用于该同步源。
- 目录接口按页拉取，`page_size` 为 2000。某一页没有结果，或累计条数达到返回的 `count` 时停止。满 100 页仍可能有下一页时返回 `provider.invalid_response`。部门用返回的 `parent` 在本地组成树。请求只带分页和用户字段，不把根部门传给 ESB 再由蓝鲸过滤。
- ESB 路径固定为：
  - 校验登录：`GET {bk_url}/api/c/compapi/v2/bk_login/get_user/`
  - 部门：`GET {bk_url}/api/c/compapi/v2/usermanage/list_departments/`
  - 用户：`GET {bk_url}/api/c/compapi/v2/usermanage/list_users/`
  - 查询参数使用 `bk_app_code`、`bk_app_secret`。连接测试、部门列表和用户列表没有登录 Cookie，固定再带 `bk_username=admin`。校验登录只加浏览器带来的 `bk_token`，不带 `bk_username`。日志不记录这些参数、token 或响应正文。
- `login_auth.authenticate` 接收 `bk_token`。成功时 `external_user` 只有核对到的 `username`。`build_login_url` 保持未实现，登录页不发起跳转。
- `get_active_login_auth_bindings` 的公开结果排除 `provider_key=blueking`。绑定记录仍可创建，供 `get_bk_settings` 使用。
- `get_bk_settings` 继续合并门户品牌。蓝鲸登录认证未就绪时返回 `bk_login_open: false`，不读取 cookie 去调用蓝鲸。就绪时读取 `bk_token`：没有 cookie、蓝鲸判定无效、或绑定拒绝创建且本地没有同名用户时，返回 `bk_login_open: true` 且 `user` 为空。绑定选择创建且本地没有同名用户时，由 `login_with_binding` 建号并返回 `user.token`。匹配成功时返回与现在自动登录相同的 `user.token` 结构，并用 `_set_auth_cookie_on_response` 写入 `bklite_token`。
- 就绪的判定是：存在启用的蓝鲸 `LoginAuthBinding`，且其实例的 `login_auth` 能力可用。多个这样的绑定时，按现有 `order, id` 取第一条，只用它的应用凭证核验这张 cookie。
- 兑换复用 `login_with_binding` 的匹配和发 token，不在 `verify_bk_token` 里 `get_or_create`。调用时传入该绑定 id 和 `bk_token`。`login_with_binding` 需要能把 `bk_token` 传给 `authenticate`，企微、飞书、微信、AD 的现有参数保持不变。
- 旧 `LoginModule`、`init_bk_login_settings` 和认证源页面保留，但 `get_bk_settings` 不再调用旧的 `verify_bk_token` 建用户。已启用的旧认证源不会再把未同步用户自动建进「蓝鲸」根组织。

## Testing Decisions

- Provider 包测试：manifest 只有登录认证和用户同步；`app_token` 为密钥；登录绑定锁定 `username` 字段；公开 binding 列表不含 `blueking`。未匹配创建的保存与登录行为由 `login-auth-unmatched-create` 覆盖。
- 登录适配器对 HTTP 打桩：有效 `bk_token` 返回 `username`；蓝鲸 `result: false`、超时、缺 token 返回稳定错误码，日志不含 `bk_token`、`app_token` 和响应正文。
- 用户同步适配器对 HTTP 打桩：分页拉完部门和用户；`bk_all` 包含全部部门；指定根且包含子部门时只含该子树；关闭子部门时只含该部门；`parent` 组成 `group_list`。
- `get_bk_settings`：未就绪时与现在一样返回 `bk_login_open: false` 和品牌字段，且不发起蓝鲸请求。就绪但无 cookie，或绑定拒绝创建且本地没有同名用户时，不写 `bklite_token`。绑定选择创建时的建号与写 cookie 由 `login-auth-unmatched-create` 覆盖。匹配成功时响应含 `user.token` 且 `Set-Cookie` 为 `bklite_token`。断言不再调用 `User.objects.get_or_create`。
- 前端不新增登录按钮。若有 binding 列表契约测试，补一条蓝鲸绑定不出现。集成中心表单靠 manifest 和语言包出现，不新做页面。

## Out of Scope

- 登录页上的蓝鲸按钮、跳转蓝鲸、蓝鲸回调 BK-Lite。
- 重开认证源管理页或给 `LoginModule` 增加行为。
- 蓝鲸用户目录作为单独的同步步骤、密码有效期、ITSM 角色、业务权限、用户锁定状态。
- IM 通知。
- 一次 cookie 依次尝试多个蓝鲸实例的应用凭证。

## Further Notes

现状入口：

- `web/src/context/auth.tsx` 启动时请求 `get_bk_settings`。
- `web/src/hooks/usePortalBranding.ts` 用同一接口取品牌，登录未启用时也要成功。
- `server/apps/core/views/index_view.py` 的 `get_bk_settings` 读取 cookie `bk_token`。
- `server/apps/system_mgmt/nats/settings.py` 的 `verify_bk_token` 和 `server/apps/system_mgmt/utils/bk_user_utils.py` 是旧核对与建用户实现。
- 企微同步表单在 `providers/builtin/wecom/manifest.py`。登录未匹配策略见 `specs/changes/login-auth-unmatched-create/spec.md`。

WeOps 的 `UserUtils.sys_pull_mian` 只说明 ESB 的分页字段和 `parent` 树。BK-Lite 不按它删除全部本地用户，也不拉目录对象。
