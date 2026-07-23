# 模块 ARD：公共基座（base / core / rpc）

> Migrated from `spec/ARD/modules/base_core_rpc.md` as legacy capability evidence.

> 路径 `server/apps/{base,core,rpc}` ｜ 常驻 INSTALLED_APPS

## base —— 用户模型与 API 密钥【已实现/已存在】
- `models/user.py`：`User`（继承 `AbstractUser`，`unique_together=(username, domain)`，`AUTH_USER_MODEL=base.User`）、`UserAPISecret`（一次性返回 64 位明文 token；数据库字段保存 `sha256$` 摘要，`max_length=80`，unique username+domain+team；迁移保留旧明文兼容查找）。
- `User` 除 username/domain 外还含运行/持久字段：`group_list`（JSONField，默认 `list`）、`roles`（JSONField，默认 `list`）、`locale`（默认 `zh-CN`）、`domain`（默认 `domain.com`）；这些字段由认证后端读写：`set_user_info` 写 `group_list`/`roles`/`locale`（`backends.py:319-321`），`APISecretAuthBackend.authenticate` 以 team 重写 `group_list`（`backends.py:42`）。【已实现，证据 `models/user.py:38-41`、`core/backends.py:42,319-321`】
- 接口：`user_api_secret`（ViewSet）。

## core —— Celery / 认证 / 中间件 / 工具【已实现/已存在】
- **Celery**（`celery.py`）：app=`bklite`，自动发现各 app 任务；与 `django_celery_beat` 同步周期任务（从各 app `CELERY_BEAT_SCHEDULE` 聚合）。
- **认证后端**（`backends.py`，`AUTHENTICATION_BACKENDS` 顺序：`AuthBackend` → `APISecretAuthBackend` → `ModelBackend`，见 `config/components/app.py:61-64`）：
  - `AuthBackend`（默认优先）：Token 经 system_mgmt RPC 校验，填充 locale/timezone/groups/roles。
  - `APISecretAuthBackend`：按 api_secret 查用户，填充角色/权限，权限缓存 TTL 60s。
- **中间件**（`middlewares/`）：auth、api、app_exception、request_timing、drf、dameng_connection。
- **加密**（`mixinx.py:EncryptMixin`）：基于 `cryptography.fernet.Fernet`，密钥由 `SECRET_KEY` 经 sha256 + urlsafe_b64 派生；`encrypt_field`/`decrypt_field` 按字段加解密，解密遇 `InvalidToken` 视为明文静默跳过（`mixinx.py:6,17-35,37-58,60-85`）。【已实现】密文形如标准 Fernet token（以 `gAAAAA` 开头）系 Fernet 编码格式，代码中无对该前缀的引用或校验逻辑（grep 无命中）【推断】。
- **公共模型**（`models/`）：`TimeInfo`、`MaintainerInfo`、`Groups`、`VtypeMixin`（均为 `abstract=True` Mixin）。`core/models/__init__.py` 为空文件，未 re-export 任何模型，各模型需从子文件直接导入（如 `from apps.core.models.time_info import TimeInfo`，见 `base/models/user.py:9`）。【已实现，证据 `models/group_info.py:10`、`models/vtype_mixin.py:16`、`models/time_info.py:5`、`models/maintainer_info.py:5`、`models/__init__.py`（空）】
- **工具**：permission_cache、custom_error、loader（i18n）、web_utils、logger（分模块）。
- **Celery 任务**（`tasks/auditlog_flush_task.py`）：`@shared_task def clear_audit_logs`（清理 30 天前 AuditLog，内部 `call_command("auditlogflush", ...)`）。仅定义，未见于任何 `CELERY_BEAT_SCHEDULE`（grep `config/` 无命中），为「仅定义未排程」。【已实现，证据 `tasks/auditlog_flush_task.py:8-9`】
- **登录路由**（`urls.py:11-32`）：`api/login`、`api/verify_otp_login`、`api/wechat_login`、`api/get_domain_list`、`api/get_wechat_settings`、`api/get_bk_settings`、`api/generate_qr_code`、`api/verify_otp_code`、`api/reset_pwd`、`api/login_info`、`api/get_client`、`api/get_my_client`、`api/get_client_detail`、`api/get_user_menus`、`api/get_all_groups`、`api/logout`，外加 router 注册的 `api/user_group`（`UserGroupViewSet`）。

## rpc —— NATS RPC 网关【已实现/已存在】
- `base.py`：
  - `RpcClient(namespace=bklite)`：`run()` → `nats_client.request(namespace, method, ...)`，超时优先级 调用参数 `_timeout` > `settings.NATS_REQUEST_TIMEOUT` > 默认常量 60s（`base.py:8,21`）。
  - `AppClient`：本进程模块导入回退（`__import__(path)` → `getattr(method)`）。
  - `OperationAnalysisRpc`：独立 server/namespace，支持 request_v2。
- `jetstream.py:JetStreamService`：NATS 对象存储封装（put/get/delete/list/watch/streaming）。
- RPC 客户端（均为客户端封装）：`executor.py`（local/ssh execute、download/upload、unzip、health）、`ansible.py`、`cmdb.py`、`monitor.py`、`log.py`、`node_mgmt.py`、`system_mgmt.py`、`opspilot.py`、`alerts.py`、`job_mgmt.py`、`mlops.py`、`console_mgmt.py`（`ConsoleMgmt`，创建通知）、`stargazer.py`（`StargazerRpcClient`/`Stargazer`，独立 namespace + health_check）、`operation_analysis.py`。【已实现，证据 `rpc/console_mgmt.py:4`、`rpc/stargazer.py:6,11`】其中 `system_mgmt.py` 始终使用 `AppClient` 本进程导入 `apps.system_mgmt.nats_api`，不读取 `IS_LOCAL_RPC`。
- `sensitive.py`：RPC 可观测面敏感字段脱敏工具，`MASKED_VALUE='***'`，对 `password`/`private_key`/`passphrase`/`inventory_content`/`ansible_*` 等键直接掩码，并用正则掩码字符串内的赋值片段与私钥块。【已实现，证据 `rpc/sensitive.py:1-30`】
- 处理函数（`@nats_client.register`）不在 `apps/rpc/` 内——`apps/rpc/` 全为客户端封装，grep `@nats_client` 无命中；`register` 处理函数位于各业务 app 的 `nats_api.py`/`nats/` 模块（如 `system_mgmt/nats_api.py:63` 的 `get_user_all_roles` 等），由各 app 启动时自动发现。【已实现，证据 `apps/rpc/` grep `@nats_client` 无命中、`system_mgmt/nats_api.py:63`】

## 风险 / 待确认
- 两套权限解析逻辑（`core.backends._get_user_all_roles`（`backends.py:131`）与 `system_mgmt.nats_api.get_user_all_roles`（`nats_api.py:63`）函数名不同但职责重叠）需保持一致【已实现，技术债】。
- `AppClient` 本进程回退与 NATS 远程调用的切换条件 `IS_LOCAL_RPC` 为已实现的明确开关：`cmdb`、`monitor`、`opspilot` 等客户端读 env `IS_LOCAL_RPC`（默认 `'0'`），`=='1'` 时用 `AppClient` 本进程导入对应 app 的 nats handler 模块，否则用 `RpcClient` 走 NATS；构造函数另留 `is_local_client` 参数可强制本进程。例外：`system_mgmt.py` 固定走 `AppClient` 本进程导入 `apps.system_mgmt.nats_api`。【已实现，证据 `rpc/cmdb.py:8-10`、`rpc/monitor.py:8-9`、`rpc/opspilot.py:8-10`、`rpc/system_mgmt.py:1,4,6`】

## 2026-07-01 Code-ARD 校准
- `[base_core_rpc#20260701-027]` 修正 UserAPISecret：ARD 区分一次性返回 64 位明文 token、数据库 `sha256$` 摘要存储、旧明文兼容查找与 `max_length=80` 字段事实。
- `[base_core_rpc#20260701-028]` 补录 core 管理命令：`batch_init` 按 `INSTALL_APPS`/`--apps` 批量初始化并预热语言缓存；`cleanup_orphan_snapshot_objects` 扫描快照孤儿对象，`--delete` 才执行删除，默认 dry-run，依赖 monitor/log 快照对象。
- `[base_core_rpc#20260701-029]` 修正 `IS_LOCAL_RPC` 适用范围：`cmdb`/`monitor`/`opspilot` 等可切换，`system_mgmt.py` 固定本进程 AppClient。

## 证据来源
`server/apps/base/models/user.py:9,13,18,26,38-41`、`server/apps/base/user_api_secret_mgmt/views.py:89,92`、`server/apps/base/migrations/0010_hash_user_api_secret.py:24`、`server/apps/core/{celery.py,backends.py:42,319-321,mixinx.py:6,17-85,middlewares/*,utils/*,urls.py:11-32,models/{__init__.py,time_info.py:5,maintainer_info.py:5,group_info.py:10,vtype_mixin.py:16},tasks/auditlog_flush_task.py:8-9,management/commands/batch_init.py:14,31,80,management/commands/cleanup_orphan_snapshot_objects.py:8,31,43}`、`server/config/components/app.py:61-64`、`server/apps/rpc/{base,jetstream,executor,console_mgmt.py:4,stargazer.py:6,11,sensitive.py:1-30,cmdb.py:8-10,monitor.py:8-9,opspilot.py:8-10,system_mgmt.py:1,4,6,...}.py`、`server/apps/system_mgmt/nats_api.py:63`。
