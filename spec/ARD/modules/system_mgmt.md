# 模块 ARD：System Management（系统管理）

> 路径 `server/apps/system_mgmt` ｜ API 前缀 `api/v1/system_mgmt/`

## 1. 职责【已实现/已存在】
多租户用户/组/角色/权限管理、登录流程（密码/OTP/外部认证）、权限矩阵、审计日志、系统设置与通知渠道。

## 2. 数据模型与存储【已实现/已存在 / PostgreSQL】
| 模型 | 文件 | 说明 |
|------|------|------|
| User | `models/user.py` | 用户（username+domain 唯一、OTP、锁定、密码策略） |
| Group | `models/user.py` | 层级组（parent_id、allow_inherit_roles、M2M Role） |
| Role | `models/role.py` | 角色（app、menu_list） |
| GroupDataRule / UserRule | `models/group_data_rule.py` | 数据级访问规则 |
| Menu / LoginModule / SystemSettings | `models/*.py` | 菜单、登录提供方、系统配置 |
| OperationLog / UserLoginLog / ErrorLog | `models/*.py` | 审计追踪 |

## 3. 接口【已实现/已存在】
`group`/`user`/`role`/`channel`/`group_data_rule`/`system_settings`/`login_module`/`custom_menu_group`/`user_login_log`/`operation_log`/`error_log`。

## 4. 认证与权限【已实现/已存在】
- `nats_api.py`：`bk_lite_user_login`、`verify_otp_login`、`reset_pwd`、`login_info`、`get_all_groups`、`get_authorized_groups_scoped`、`create_guest_role` 等。
- JWT（含 jti/exp）、OTP（二维码/挑战/限频）、token 黑名单。
- 角色继承：`get_user_all_roles` 沿 `parent_id`+`allow_inherit_roles` 递归汇总；权限缓存 TTL 60s。
- 密码策略：`utils/password_validator.py`（失败锁定）。

## 5. 通知渠道【已实现/已存在】
`utils/channel_utils.py`：邮件、钉钉、企微、飞书、NATS 消息；BK 用户对接 `utils/bk_user_utils.py`。

## 6. 风险 / 待确认
- domain 多租户隔离在所有 ViewSet 是否强制【待确认】。
- 外部登录模块（LDAP/WeChat/BK）配置与回退【推断，需确认覆盖范围】。

## 7. 证据来源
`server/apps/system_mgmt/{urls.py,models/*,nats_api.py,services/role_manage.py,utils/*}`。
