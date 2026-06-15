# 模块 ARD：Console Management（控制台）

> 路径 `server/apps/console_mgmt` ｜ API 前缀 `api/v1/console_mgmt/`

## 1. 职责【已实现/已存在】
用户首登初始化、站内通知、用户应用偏好；作为控制台 UI 的网关，对接 system_mgmt 获取角色/组/权限。

## 2. 数据模型与存储【已实现/已存在 / PostgreSQL】
| 模型 | 文件 | 说明 |
|------|------|------|
| Notification | `models/notification.py` | 站内消息（时间/模块/内容/来源） |
| NotificationRead | `models/notification.py` | 每用户已读状态（unique notification+user） |
| UserAppSet | `models/user_app_set.py` | 用户应用看板配置（app_config_list JSON） |

## 3. 接口【已实现/已存在】
`init_user_set/`、`update_user_base_info/`、`validate_pwd/`、`validate_email_code/`、`send_email_code/`、`reset_pwd/`、`get_user_info/`、`notifications`（ViewSet）、`user_app_sets`（ViewSet）。

## 4. 依赖与通信【已实现/已存在】
- `apps.rpc.system_mgmt.SystemMgmt`：首登同步用户/组/角色。
- NATS：`nats_api.py:create_notification(app, message)` —— 任意 app 经白名单（monitor/cmdb/node_mgmt/job_mgmt/alerts/log/opspilot/system_mgmt/console_mgmt/mlops/operation_analysis）创建通知，内容上限 2000 字。

## 5. 风险 / 待确认
- 通知的实时推送通道（WebSocket/SSE）是否存在【待确认】——当前仅见 ORM 落库。

## 6. 证据来源
`server/apps/console_mgmt/{urls.py,models/*,views.py,nats_api.py}`、`apps/rpc/system_mgmt.py`。
