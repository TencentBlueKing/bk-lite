# 模块 ARD：Console Management（控制台）

> Migrated from `spec/ARD/modules/console_mgmt.md` as legacy capability evidence.

> 路径 `server/apps/console_mgmt` ｜ API 前缀 `api/v1/console_mgmt/`

## 1. 职责【已实现/已存在】
用户首登初始化、站内通知、用户应用偏好；作为控制台 UI 的网关，对接 system_mgmt 获取角色/组/权限。

## 2. 数据模型与存储【已实现/已存在 / PostgreSQL】
| 模型 | 文件 | 说明 |
|------|------|------|
| Notification | `models/notification.py` | 站内消息（时间/模块/内容/来源）；另保留 `is_read` 字段，verbose_name 标注「已废弃，保留兼容」并带 `db_index`，已读状态实际不再依赖此字段【已实现/已存在 `models/notification.py:12`】 |
| NotificationRead | `models/notification.py` | 每用户独立的通知状态（`unique_together` notification+user）；字段含 `is_read`、`read_at`（已读时间）、`is_deleted`（按用户软删除），同时承载按用户隔离的已读与删除状态，而非单纯已读标记【已实现/已存在 `models/notification.py:32-46`】 |
| UserAppSet | `models/user_app_set.py` | 用户应用看板配置（app_config_list JSON） |

## 3. 接口【已实现/已存在】

### 3.1 函数视图（views.py）
`init_user_set/`、`update_user_base_info/`、`validate_pwd/`、`validate_email_code/`、`send_email_code/`、`reset_pwd/`、`get_user_info/`。

其中 `send_email_code`/`validate_email_code` 采用**服务端 cache TTL + 一次性校验**机制【已实现/已存在 `views.py:184,205,214,222,240,282,285`】：`send_email_code` 生成 6 位随机数字码，经 `SystemMgmt.send_email_to_receiver` RPC 发往目标邮箱；验证码按用户+邮箱隔离写入服务端 cache，TTL 默认 600 秒，发送侧有 60 秒限流；响应不再向客户端返回 `hashed_code`。`validate_email_code` 校验 cache 中验证码，校验通过后删除 cache key，避免重复使用。

### 3.2 NotificationViewSet（`notifications`）
按用户隔离已读/删除状态，`http_method_names` 限定为 get/post/delete【`viewsets/notification.py:17`】，`create`/`update`/`partial_update` 被显式覆写禁用返回 405【已实现/已存在 `viewsets/notification.py:55-65`】。自定义 action：
- `mark_as_read`（detail post）：标记单条为当前用户已读【`notification.py:77-91`】。
- `mark_all_as_read`（detail=False post）：批量标记所有未读为已读【`notification.py:93-120`】。
- `mark_batch_as_read`（detail=False post）：按 `ids` 批量标记已读【`notification.py:122-146`】。
- `unread_count`（detail=False get）：返回当前用户未读数（排除已删除/已读）【`notification.py:148-164`】。
- `destroy`（delete）：软删除，仅按用户写 `NotificationRead.is_deleted=True`，非物理删除，不影响其他用户【`notification.py:67-75`】。

### 3.3 UserAppSetViewSet（`user_app_sets`）
`http_method_names` 限定为 get/post【`viewsets/user_app_set.py:16`】，标准的 list/create/retrieve/update/partial_update/destroy 均被显式覆写禁用，返回 405【已实现/已存在 `viewsets/user_app_set.py:18-64`】。对外仅暴露两个自定义 action：
- `current_user_apps`（detail=False get）：取当前用户应用配置【`user_app_set.py:82-120`】。
- `configure_user_apps`（detail=False post）：保存当前用户应用配置【`user_app_set.py:122-142`】。

## 4. 依赖与通信【已实现/已存在】
- `apps.rpc.system_mgmt.SystemMgmt`：本模块函数视图经其调用三个方法【已实现/已存在 `views.py:101,226,322`】——`init_user_default_attributes`（首登初始化用户默认属性/组/角色）、`send_email_to_receiver`（发送邮箱验证码邮件）、`reset_pwd`（重置密码）；另管理命令 `init_guest_role` 额外调用 `create_guest_role`/`create_default_rule`（见下）。
- `apps.rpc.opspilot.OpsPilot`：管理命令 `init_guest_role` 依赖 `SystemMgmt.create_guest_role`/`create_default_rule` 与 `OpsPilot.get_guest_provider`，用 Guest 角色对应的 LLM/OCR/embed/rerank 模型初始化默认规则【已实现/已存在 `management/commands/init_guest_role.py:4-30`】。
- NATS：`nats_api.py:create_notification(app, message)` 创建通知，内容上限 2000 字。app 校验为「白名单 OR App 表存在」二选一【已实现/已存在 `nats_api.py:33`】：app 命中 `BUILTIN_APP_MODULES`（monitor/cmdb/node_mgmt/job_mgmt/alerts/log/opspilot/system_mgmt/console_mgmt/mlops/operation_analysis）直接放行；未命中白名单时，只要 `App` 表存在同名 `name` 记录亦放行，二者皆不满足才拒绝。

## 5. 风险 / 待确认
- 通知的实时推送通道（WebSocket/SSE）是否存在【待确认】——当前仅见 ORM 落库。

## 2026-07-01 Code-ARD 校准
- `[console_mgmt#20260701-024]` 邮箱验证码描述从前端持有 `hashed_code` 的无状态校验，修正为服务端 cache TTL、按用户+邮箱隔离、验证通过删除、发送 60 秒限流且不返回 `hashed_code`。

## 6. 证据来源
`server/apps/console_mgmt/{urls.py,models/*,views.py:22,184,205,214,222,240,282,285,nats_api.py}`、`server/apps/console_mgmt/tests/test_email_code_views.py:5`、`server/apps/console_mgmt/viewsets/{notification.py,user_app_set.py}`、`server/apps/console_mgmt/management/commands/init_guest_role.py`、`apps/rpc/system_mgmt.py`、`apps/rpc/opspilot.py`。
