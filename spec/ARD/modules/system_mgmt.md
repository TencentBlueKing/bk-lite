# 模块 ARD：System Management（系统管理）

> 路径 `server/apps/system_mgmt` ｜ API 前缀 `api/v1/system_mgmt/`

## 1. 职责【已实现/已存在】
多租户用户/组/角色/权限管理、登录流程（密码/OTP/外部认证）、权限矩阵、审计日志、系统设置与通知渠道。

## 2. 数据模型与存储【已实现/已存在 / PostgreSQL】
| 模型 | 文件 | 说明 |
|------|------|------|
| User | `models/user.py` | 用户（username+domain 唯一）。除基础字段外含 `phone`、`last_login`、`password_last_modified`、`password_error_count`、`account_locked_until`、`otp_secret`；`save()` 重写：改密时自动 `password_last_modified=now`、重置 `password_error_count=0`、清空 `account_locked_until`，并清除该用户权限缓存 |
| Group | `models/user.py` | 层级组（parent_id、allow_inherit_roles、M2M Role） |
| Role | `models/role.py` | 角色（app、menu_list） |
| GroupDataRule / UserRule | `models/group_data_rule.py` | 数据级访问规则 |
| Menu / LoginModule / SystemSettings | `models/*.py` | 菜单、登录提供方、系统配置 |
| NetworkWhiteList | `models/network_white_list.py` | SSRF 内网白名单（CIDR、备注、启停），用于放行特定私网网段 |
| SensitiveInfoAuthorization | `models/sensitive_info_authorization.py` | 敏感信息脱敏授权白名单（企业版）：`username`+`domain` 唯一，`sensitive_types`（JSON，限 email/phone）记录被授权可见的敏感字段类型 |
| OperationLog / UserLoginLog / ErrorLog | `models/*.py` | 审计追踪 |

## 3. 接口【已实现/已存在】
DRF Router 注册 13 个路由组：`group`/`user`/`role`/`channel`/`group_data_rule`/`system_settings`/`app`（AppViewSet，应用清单）/`login_module`/`custom_menu_group`/`user_login_log`/`operation_log`/`error_log`/`network_white_list`。企业版路由在 `enterprise/urls.py` 存在时追加合并。
- `network_white_list`【已实现/已存在】：提供内网白名单的 CRUD 接口，按 `network_white_list-View/Add/Edit/Delete` 权限控制；写操作会主动失效白名单缓存并写入操作日志（`viewset/network_white_list_viewset.py:10-55`）。

## 4. 认证与权限【已实现/已存在】
- 真实 NATS handler 分布在 `nats/auth.py`、`nats/login.py`、`nats/otp.py`、`nats/settings.py`、`nats/wechat.py`、`nats/users.py` 等子模块；`nats_api.py` 现为旧导入路径兼容导出层，会同步 `_verify_token`、`_build_jwt_payload`、`create_challenge` 等 legacy helper，再转发到真实 handler。
- JWT（含 jti/exp）、OTP（二维码/挑战/限频）、token 黑名单。
- 角色继承：`get_user_all_roles` 沿 `parent_id`+`allow_inherit_roles` 递归汇总；权限缓存 TTL 由 `PERMISSION_CACHE_TTL` 配置（默认 600s），token 信息缓存 TTL 由 `TOKEN_INFO_CACHE_TTL` 配置（默认 60s）。
- 密码策略：`utils/password_validator.py`（失败锁定）。

## 5. 通知渠道【已实现/已存在】
`models/channel.py` 的 `ChannelChoices` 定义 7 类渠道：`email`（邮件）、`enterprise_wechat`（企微）、`enterprise_wechat_bot`（企微机器人）、`nats`（NATS 消息）、`feishu_bot`（飞书机器人）、`dingtalk_bot`（钉钉机器人）、`custom_webhook`（自定义 Webhook）。发送实现见 `utils/channel_utils.py`；BK 用户对接 `utils/bk_user_utils.py`。

## 6. 核心数据流 / 任务【已实现/已存在】
`tasks.py` 定义 3 个 Celery 任务：
- `write_error_log_async`：异步写入错误日志到 `ErrorLog`（`bind=True, max_retries=3, default_retry_delay=60`，失败按重试机制重试，超限返回失败）。
- `sync_user_and_group_by_login_module`：按 `LoginModule`（须 enabled）经 `RpcClient` 调用对应 namespace 的 `sync_data`，将外部用户/组同步入库（递归建组、external_id 映射、批量增改删）。
- `check_password_expiry_and_notify`：定时检查密码即将/已过期用户，读取 `pwd_set_validity_period`/`pwd_set_expiry_reminder_days` 系统设置，经 email 渠道发送提醒邮件（validity_days<=0 视为永不过期则跳过）。
- SSRF 白名单缓存【已实现/已存在】：`utils/network_whitelist_cache.py` 以 300 秒 TTL 缓存启用中的规范化 CIDR 列表，白名单 CRUD 成功后主动清除缓存；任何异常返回空列表以保持 fail-closed（`network_whitelist_cache.py:9-32`）。

## 7. 风险 / 待确认
- domain 多租户隔离在所有 ViewSet 是否强制【待确认】。
- 外部登录模块（LDAP/WeChat/BK）配置与回退【推断，需确认覆盖范围】。

## 8. 证据来源
- 路由：`server/apps/system_mgmt/urls.py:19-39`（含 `app` 路由 `urls.py:26`、`network_white_list` 路由 `urls.py:32`、企业版合并 `urls.py:35-39`）。
- 模型：`server/apps/system_mgmt/models/user.py:7-62`（User 字段与 `save()` 重写）、`models/network_white_list.py:7-20`、`models/sensitive_info_authorization.py:33-42`、`models/channel.py:7-14`（ChannelChoices 7 类）、`models/role.py`、`models/group_data_rule.py`。
- 认证/权限：`server/apps/system_mgmt/nats_api.py:1-109`（兼容导出层）、`nats/auth.py:5-118`、`nats/login.py:5-220`、`nats/otp.py:5-186`、`nats/settings.py:21-79`、`nats/wechat.py:6-48`；缓存 TTL `server/apps/core/utils/permission_cache.py:22,25`。
- Celery 任务：`server/apps/system_mgmt/tasks.py:14`（write_error_log_async）、`tasks.py:42`（sync_user_and_group_by_login_module）、`tasks.py:251`（check_password_expiry_and_notify）。
- 白名单与缓存：`server/apps/system_mgmt/{viewset/network_white_list_viewset.py:10-55, serializers/network_white_list_serializer.py:11-35, utils/network_whitelist_cache.py:9-32}`。
- 其他：`server/apps/system_mgmt/{services/role_manage.py,utils/*}`。
