# 模块 ARD：公共基座（base / core / rpc）

> 路径 `server/apps/{base,core,rpc}` ｜ 常驻 INSTALLED_APPS

## base —— 用户模型与 API 密钥【已实现/已存在】
- `models/user.py`：`User`（继承 `AbstractUser`，username+domain 唯一，`AUTH_USER_MODEL=base.User`）、`UserAPISecret`（64 位 hex 密钥，`generate_api_secret()`，unique username+domain+team）。
- 接口：`user_api_secret`（ViewSet）。

## core —— Celery / 认证 / 中间件 / 工具【已实现/已存在】
- **Celery**（`celery.py`）：app=`bklite`，自动发现各 app 任务；与 `django_celery_beat` 同步周期任务（从各 app `CELERY_BEAT_SCHEDULE` 聚合）。
- **认证后端**（`backends.py`，`AUTHENTICATION_BACKENDS` 顺序：`AuthBackend` → `APISecretAuthBackend` → `ModelBackend`，见 `config/components/app.py:61-65`）：
  - `AuthBackend`（默认优先）：Token 经 system_mgmt RPC 校验，填充 locale/timezone/groups/roles。
  - `APISecretAuthBackend`：按 api_secret 查用户，填充角色/权限，权限缓存 TTL 60s。
- **中间件**（`middlewares/`）：auth、api、app_exception、request_timing、drf、dameng_connection。
- **加密**（`mixinx.py:EncryptMixin`）：Fernet，密文前缀 `gAAAAA`。
- **公共模型**（`models/`）：TimeInfo、MaintainerInfo、GroupInfo、VTypeMixin。
- **工具**：permission_cache、custom_error、loader（i18n）、web_utils、logger（分模块）。
- **登录路由**（`urls.py`）：`api/login`、`api/verify_otp_login`、`api/wechat_login`、`api/generate_qr_code`、`api/reset_pwd`、`api/get_user_menus`、`api/user_group`。

## rpc —— NATS RPC 网关【已实现/已存在】
- `base.py`：
  - `RpcClient(namespace=bklite)`：`run()` → `nats_client.request(namespace, method, ...)`，超时优先级 调用参数 `_timeout` > `settings.NATS_REQUEST_TIMEOUT` > 默认常量 60s（`base.py:8,21`）。
  - `AppClient`：本进程模块导入回退（`__import__(path)` → `getattr(method)`）。
  - `OperationAnalysisRpc`：独立 server/namespace，支持 request_v2。
- `jetstream.py:JetStreamService`：NATS 对象存储封装（put/get/delete/list/watch/streaming）。
- RPC 客户端：`executor.py`（local/ssh execute、download/upload、unzip、health）、`ansible.py`、`cmdb.py`、`monitor.py`、`log.py`、`node_mgmt.py`、`system_mgmt.py`、`opspilot.py`、`alerts.py`、`job_mgmt.py`、`mlops.py`。
- 处理函数经 `@nats_client.register` 暴露，启动自动发现。

## 风险 / 待确认
- 两套权限解析逻辑（core.backends 与 system_mgmt.nats_api 各有 `_get_user_all_roles`）需保持一致【已实现，技术债】。
- `AppClient` 本进程回退与 NATS 远程调用的切换条件（`IS_LOCAL_RPC`）【已实现，需文档化】。

## 证据来源
`server/apps/base/models/user.py`、`server/apps/core/{celery.py,backends.py,mixinx.py,middlewares/*,utils/*,urls.py}`、`server/apps/rpc/{base,jetstream,executor,...}.py`。
