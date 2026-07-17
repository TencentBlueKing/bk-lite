# 系统管理用户同步-本地密码初始化方式设计

## Summary

在「系统管理 → 用户同步」中，新增对同步用户的**本地密码初始化方式配置能力**。每个 `UserSyncSource` 独立配置三种模式：

- **不设置密码**：同步用户不创建本地密码，仅允许通过外部身份源登录
- **设置统一密码**：为所有同步用户设置相同的初始密码，首次登录强制改密，密码通过邮件通道发送
- **设置随机密码**：为每个同步用户生成随机初始密码，首次登录强制改密，密码通过邮件通道发送

实现要点：
- **新增独立 `platform_config` JSONField**（不在 `business_config` 里），其中 `platform_config.password_init` 承载密码初始化策略；避开 provider manifest contract 校验（最初设计放在 `business_config` 里被飞书等 provider 拒绝；这是关键设计调整）
- 复用现有 `User.temporary_pwd` 机制（已存在，reset_pwd 后自动置 False）
- 邮件发送走 Celery 异步队列，独立可重试，不阻塞同步任务
- 统一密码在 `platform_config.password_init.uniform_password` 中以 AES 密文持久化；读取 API 脱敏为 `uniform_password_configured=true`，更新时留空表示保持原密文
- raw_password 经 AES 加密后存入 `UserSyncRun.payload.password_vault`（payload 内的新 key，不算新 model 字段），worker 端解密、发邮件、立即 pop
- 邮件状态回写到 `UserSyncRun.payload.email_status`（payload 内的新 key），前端按 `completed` 标志展示「邮件发送中 / 95/100 已送达」
- 邮件发送**走通用 `Channel` 表** + `channel_utils.send_email` 直接 SMTP（不走 `RuntimeApplicationService`，因为项目没有 email provider manifest）

## Goals

- 每个 `UserSyncSource` 独立配置三种密码初始化模式
- 同步用户**首次创建**时按模式初始化本地密码
- 后续周期同步**不重置**已有用户的本地密码
- 邮件发送失败**不阻塞**同步任务（Celery 异步 + 自动重试）
- 邮件发送是否全部成功 / 部分失败 / 失败用户名单**可追溯**
- 复用现有 `User.temporary_pwd` 机制
- 引入独立 `UserSyncSource.platform_config` JSONField（避开 provider contract 校验，并作为 BK-Lite 平台侧策略统一扩展入口）
- 邮件通知通道从**通用 `Channel` 表**的 `channel_type='email'` 通道选择
- 密码复杂度遵循系统安全策略
- **三种模式**：none 不发邮件；uniform / random 都必发邮件（统一密码告知所有用户；随机密码必须告知）

## Non-Goals

- 本轮不重做 IM 通知 / 集成中心 / 用户管理模块
- 本轮不新增 `UserSyncRecord` 单条记录模型
- 本轮不新增 `failure_reason` / `retry_count` 等 UserSyncRun 字段
- 本轮不新增重发邮件 REST 端点（Celery 自动重试 + 失败容忍）
- 本轮不做「统一密码」模式的二次确认拦截（产品侧允许，仅 UI 加风险提示）
- 本轮不对存量已同步用户执行密码初始化（重新创建 source 后单独处理）
- 本轮不处理多密码策略（统一用系统当前策略）
- 本轮不开通「OAuth 首登走改密页」路径（仅本地账号密码登录触发改密）

## Current State

### 已有机制（复用）

- `User.temporary_pwd` BooleanField，default=False（`server/apps/system_mgmt/models/user.py:18`）
- `User.password_last_modified` DateTimeField，密码变更自动更新（`save()` 方法）
- `reset_pwd` 成功后 `user.temporary_pwd = False`（`server/apps/system_mgmt/nats/login.py:143`）
- 登录响应 `temporary_pwd` 字段已暴露给前端（`nats/login.py:213, 244`）
- `_sync_users` 已实现「首次创建 vs 增量更新」分离（`server/apps/system_mgmt/services/user_sync_service.py:395-508`），更新时只覆盖 `display_name/email/phone/group_list/disabled/sync_source`，不重置 `password`
- `PasswordValidator.validate_password` 提供密码复杂度校验（`server/apps/system_mgmt/nats/login.py:138`）
- `PasswordCrypto`（AES-CBC + base64）已存在（`server/apps/core/utils/crypto/password_crypto.py`）
- `channel_utils.send_email`（直接 SMTP）已存在（`server/apps/system_mgmt/utils/channel_utils.py:91`）
- Celery 任务现有模式：args 只传 `id`，数据走 DB 读取（如 `execute_im_notification_sync_run_task(run_id)`，`server/apps/system_mgmt/tasks.py:335-339`）
- `UserSyncRun.payload` JSONField 已存在，可追加新 key 而不增加 model 字段

### 已有相关 issue / 决策

- `User.temporary_pwd` 改密机制已稳定，issue #0004 已修复 reset_password 弱密码 500→400
- OAuth 首登创建用户的 `role_list` 写入路径已修（issue #0007）

### 前端现状

- 用户同步配置弹窗：`web/src/app/system-manager/components/user/user-sync/UserSyncConfigModal.tsx`
- 字段通过 provider manifest 的 `business_template` 渲染，**但 password_init 不走 business_config**（改走 `platform_config.password_init`，避开 provider contract 拒绝）
- 同步记录抽屉：`web/src/app/system-manager/components/user/user-sync/UserSyncRecordsDrawer.tsx`，按 `UserSyncRun.status` 显示 success / partial / failed

---

## Design

### 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│ 前端 (web/src/app/system-manager/components/user/user-sync)     │
│   PasswordInitSection (新增)                                    │
│   └─ mode Select + email_channel_id Select + uniform 输入      │
└─────────────────────────────────────────────────────────────────┘
                            │ platform_config.password_init
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ UserSyncSource.platform_config (独立 JSONField)                 │
│   { password_init: {                                           │
│       mode: none|uniform|random,                               │
│       uniform_password: "...",                                 │
│       email_channel_id: 7,                                     │
│       email_template_key: "..." } }                            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ _sync_users (修改)                                              │
│   创建用户 → PasswordInitService.init_password_for_user()       │
│   uniform/random → enqueue Celery (via transaction.on_commit)   │
│   → 初始化 run.payload.password_vault + email_status            │
└─────────────────────────────────────────────────────────────────┘
                            │ (atomic commit 后)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Celery: send_initial_password_email(user_id, run_id)            │
│   1. 取 user + run                                              │
│   2. 解密 vault 拿 raw_password                                │
│   3. 调 channel_utils.send_email (直接 SMTP, 不走 provider)     │
│   4. pop vault 中该 username                                    │
│   5. update_email_status(run_id, username, ok, reason)          │
└─────────────────────────────────────────────────────────────────┘
```

### 文件改动清单

#### 后端

| 路径 | 类型 | 职责 |
|------|------|------|
| `server/apps/system_mgmt/models/user_sync_source.py` | **修改** | 加 `platform_config` JSONField |
| `server/apps/system_mgmt/migrations/0039_*.py` | **新增** | 字段迁移 migration |
| `server/apps/system_mgmt/services/password_init_service.py` | **新增** | 核心 service：`init_password_for_user(user, mode, password_init_policy, run)` |
| `server/apps/system_mgmt/services/password_init_email.py` | **新增** | `send_email_via_runtime(user, raw_password)` 调 `channel_utils.send_email` |
| `server/apps/system_mgmt/services/user_sync_service.py:_sync_users` | **修改** | 创建用户后调用 `init_password_for_user`；读 `source.platform_config.password_init` |
| `server/apps/system_mgmt/tasks.py` | **修改** | 加 Celery 任务 `send_initial_password_email`（用 `transaction.on_commit` 避免 race） |
| `server/apps/system_mgmt/nats/__init__.py` | **修改** | 注册 `email_status` 模块 |
| `server/apps/system_mgmt/nats/email_status.py` | **新增** | `update_email_status` 的 NATS handler |
| `server/apps/system_mgmt/nats/login.py` | **修改** | `reset_pwd` 守卫拒绝 sentinel 模式用户 |

#### 前端

| 路径 | 类型 | 职责 |
|------|------|------|
| `web/src/app/system-manager/components/user/user-sync/PasswordInitSection.tsx` | **新增** | mode Select + email_channel_id Select + uniform 输入 + 风险提示 |
| `web/src/app/system-manager/types/user-sync.ts` | **修改** | `UserSyncSourceConfigFormValues.platform_config.password_init` 字段；`PasswordInitConfig.mode` 改 optional |
| `web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx` | **修改** | 内联 channel fetch（用 `useRef` 防 React 18 strict mode 双调用）+ 集成 PasswordInitSection |
| `web/src/app/system-manager/components/user/user-sync/UserSyncConfigModal.tsx` | **修改** | form 初始值注入 `platform_config.password_init` |
| `web/src/app/system-manager/utils/userSyncUtils.ts` | **修改** | `buildConfigUpdatePayload` 等加 `passwordInitConfig` 参数 + payload 携带 |
| `web/src/app/system-manager/(pages)/user/user-sync/page.tsx` | **修改** | `handleConfigSubmit` / `handleConfigPreview` 传 `values.platform_config.password_init` |
| `web/src/app/system-manager/locales/zh.json`、`en.json` | **修改** | 12 个 i18n key (`system.user.userSyncPage.passwordInit.*`) |

### 数据契约

#### `UserSyncSource.platform_config.password_init`（**平台配置 JSONField 内的策略块**）

```json
{
  "password_init": {
    "mode": "none" | "uniform" | "random",
    "uniform_password": "<AES encrypted secret>",
    "email_channel_id": 7,
    "email_template_key": "user_sync_initial_password"
  }
}
```

- `mode`：三选一，可选（form 空值时为 undefined）
- `uniform_password`：仅 `mode=uniform` 必填；写入时先过 `PasswordValidator` 再 AES 加密，读取接口不返回该字段；已有统一密码的更新请求可留空保持原密文
- `email_channel_id`：仅 `mode ∈ {uniform, random}` 必填；下拉数据来自通用 `Channel` 表 `channel_type='email'` 通道
- `email_template_key`：通知中心模板 key，留空用默认模板

**字段位置关键决策**：从最初设计的 `business_config.password_init` 改为独立 `platform_config.password_init`。原因：飞书 / 企微等 provider manifest 校验 `business_config` 内的字段，未声明的字段被拒绝（"Unsupported user_sync business config fields: password_init"）。而 `platform_config` 明确承载 BK-Lite 平台侧策略，既绕开 provider contract，也为未来新增本地策略保留统一扩展位。

#### `UserSyncRun.payload.password_vault`（新增 JSON key）

```json
{
  "password_vault": {
    "alice": "<AES encrypted>",
    "bob": "<AES encrypted>"
  }
}
```

- key = username；value = `PasswordCrypto.encrypt(raw_password)` 结果
- `mode=uniform` 模式必填（管理 admin 也会收到通知）；`mode=random` 必填
- worker 发邮件成功后立即 pop 该 username
- 邮件成功或重试耗尽后均会移除对应 vault 条目；不额外保留清理命令

#### `UserSyncRun.payload.email_status`（新增 JSON key）

```json
{
  "email_status": {
    "total": 100,
    "sent": 95,
    "failed": 5,
    "failed_usernames": ["alice", "bob", "..."],
    "failed_reasons": {"alice": "邮箱为空", "bob": "SMTP 限流"},
    "completed": false
  }
}
```

- `total`：sync run 结束时的入队总数
- `sent` / `failed`：Celery 任务最终结果的累计值
- `completed`：`true` 表示全部邮件任务已 settle
- 前端仅展示发送中、成功数或失败数及核查建议；不展示失败用户名、邮箱、密码或底层错误

### 关键不变量

- `User.temporary_pwd = True` 当且仅当 `mode ∈ {uniform, random}` 且首次创建
- 「none」模式下 `user.password = "!UNSET_PASSWORD:UNSET_PASSWORD"`（非合法 hash 字符串），Django `check_password` 永远 False → 用户本地永远登录不上；reset_password 守卫通过前缀 `!UNSET_PASSWORD:` 识别后拒绝
- 仅首次创建触发密码初始化；后续同步**不重置** `password` / `temporary_pwd`
- 邮件失败**不影响** `UserSyncRun.status` 推断（同步本身成功；邮件是下游动作）
- `mode=none` 不入队 Celery；`mode=uniform`/`random` 必入队（uniform 模式默认必发邮件——产品决策）

### 数据流（random 模式）

```
[_sync_users 创建新 user, in atomic block]
  1. raw = secrets.token_urlsafe(12)
  2. user.password = make_password(raw)
  3. user.temporary_pwd = True
  4. user.save()
  5. crypto = PasswordCrypto(key=SECRET_KEY)
     run.payload["password_vault"][username] = crypto.encrypt(raw)
     run.payload["email_status"] = {total: 1, sent: 0, failed: 0, completed: False}
     run.save(update_fields=["payload"])
  6. transaction.on_commit(lambda: send_initial_password_email.delay(user_id, run_id))
  → atomic commit 后才入队 Celery (避免 worker 读到未 commit 的旧 payload)

[Celery worker (atomic commit 之后)]
  1. user = User.objects.get(id=user_id)
  2. run = UserSyncRun.objects.get(id=run_id)
  3. encrypted = (run.payload or {}).get("password_vault", {}).get(user.username)
  4. raw = PasswordCrypto(key=SECRET_KEY).decrypt(encrypted)
  5. password_init = ((run.payload or {}).get("platform_config", {}) or {}).get("password_init", {})  # 或 sync_source.platform_config.password_init
     channel_id = password_init.get("email_channel_id")
  6. channel = Channel.objects.filter(id=channel_id, channel_type="email").first()
  7. send_email_via_runtime(user, raw)  # 走 channel_utils.send_email
  8. 成功 → payload["password_vault"].pop(username); update_email_status(ok=True)
     失败 → autoretry 3 次 → 最终失败 → update_email_status(ok=False, reason=...)
```

### 数据流（uniform 模式）

与 random 类似但：
- `raw = business_config.uniform_password`（直接用，不生成随机）
- `user.password = make_password(raw)` + 同样的 vault / email_status / Celery 流程

### 数据流（none 模式）

```
  1. user.password = "!UNSET_PASSWORD:UNSET_PASSWORD"
  2. user.temporary_pwd = False
  3. user.save()
  4. 不入队 Celery，不写 vault，不写 email_status
```

### 错误处理

| 错误源 | 表现 | 处理策略 | 是否中断同步 |
|--------|------|----------|--------------|
| 外部源拉取失败 | provider 抛异常 | `UserSyncRun.status=FAILED`（已有逻辑） | 是 |
| Provider 返回空列表 | user_list=[] | `status=SUCCESS`，count=0 | 否 |
| `_ensure_user_sync_source_match` 冲突 | ValueError | 入 `conflict_usernames`，跳该用户；`status=PARTIAL` | 否 |
| uniform 密码不满足策略 | `PasswordValidator.validate_password` 失败 | 整批拒绝；UI 创建 source 时前端校验拦截 | 是（前置） |
| 缺 `email_channel_id`（uniform/random） | `init_password_for_user` 返回 failed | 该用户仍创建（password 已写入），但 vault 不写、Celery 不入队；`status=PARTIAL` | 否 |
| 邮件通道不存在 / 类型非 email | `send_email_via_runtime` 早 return | `update_email_status(ok=False, reason="...")` | 否 |
| 用户邮箱为空 | SMTP 拒收 | `update_email_status(ok=False, reason="用户邮箱为空")` | 否 |
| SMTP 限流 / 临时网络错 | `smtplib` 抛错 | Celery `autoretry_for=(Exception,)` + `retry_backoff=True` + `max_retries=3` | 否 |
| Vault 解密失败 | `PasswordCrypto.decrypt` 抛 ValueError | Celery 任务失败；不回滚 User（账户仍可用）；`failed_reasons="vault 解密失败"` | 否 |
| Worker 进程崩溃 / 队列丢消息 | Celery 任务丢失 | 用户 `temporary_pwd=True` 仍能登录改密；仅邮件通知缺失 | 否（功能保留） |
| 「none」模式下 admin 重置密码 | 前端 reset_password API | view 层守卫：user.password 以 `!UNSET_` 开头 → 拒绝 | 是（API 拦截） |

### 幂等保证

- `_sync_users` 用 `existing_user_map` 判断（已有）→ 已存在用户跳过创建
- 重跑同一 source 不会重复创建用户、不会重复发邮件
- `email_status` 用 `username` 做 key，多次结果以最后一条为准
- `password_vault.pop(username)` 重复 pop 是 no-op

### 资源边界

- 批量同步单次最大创建数：沿用 `bulk_create` batch_size=100
- 邮件入队：循环逐个 `.delay()`，不用 chord/group——失败单条不影响其他
- Vault 大小：单次同步最多几千条；AES 后每条约 200 字节；总 vault < 1MB

### 安全要点

1. **Celery args 只传 `id`**（与项目现有模式一致，无新攻击面）
2. **payload 内 password_vault 用 AES 加密**（DB 泄漏不直接暴露明文）
3. **邮件发送完立即 pop vault 条目**（内存不留；DB 也不长期存）
4. **Vault 收敛**：邮件成功或最终失败后立即移除对应 vault 条目；不引入额外清理命令和定时任务
5. **Worker 端 `raw` 变量函数返回即 GC**（无显式 log print）
6. **审计日志**：ops_log 记录「配置 password_init 策略变更」；不记明文密码
7. **`platform_config.password_init` 策略块**：避开 `business_config` 的 provider contract 校验，并为未来平台侧策略提供统一扩展入口（见 Decision Log）

---

## Testing Strategy

### 后端测试矩阵（关键场景覆盖）

#### `password_init_service.py` 单元测试（`tests/test_password_init_service.py`，8 项）

| # | 场景 | 断言 |
|---|------|------|
| 1 | `mode=none` | sentinel hash + `temporary_pwd=False` + Celery `delay` **不调** |
| 2 | `mode=uniform` 合规 | 密码 hash 正确 + `temporary_pwd=True` + `delay.assert_called_once_with` |
| 3 | `mode=uniform` 弱密码 | 返回 `{status: failed, reason: "weak_password"}` + Celery `delay` **不调** |
| 4 | `mode=uniform` 缺 channel_id | 返回 `{status: failed, reason: "missing_channel"}` |
| 5 | `mode=random` 长度 ≥ 12 | raw 长度 ≥ 12 + `temporary_pwd=True` + `delay.assert_called_once_with` |
| 6 | `mode=random` 缺 channel_id | 返回 `{status: failed, reason: "missing_channel"}` |
| 7 | `mode=random` vault 写入 | `run.payload["password_vault"][username]` 是加密结果（不含明文） |
| 8 | sentinel 常量 | `PASSWORD_INIT_SENTINEL == "UNSET_PASSWORD"` 等 |

#### Celery 任务测试（`tests/test_password_init_tasks.py`，4 项）

| # | 场景 | 断言 |
|---|------|------|
| 9 | 发送成功 → vault pop + email_status.sent++ | vault 不含 username + `sent=1` + `completed=True` |
| 10 | vault 解密失败 | `failed_reasons[username]="vault 解密失败"` + user 不回滚 |
| 11 | 通道失败 → retry 3 次耗尽 | `failed += 1` + `failed_reasons[username]="..."` + vault pop |
| 12 | 正式中文通知 | 标题、账号信息、首次登录和安全提醒文案正确 |

#### `_sync_users` 集成测试（`tests/test_sync_users_password_init.py`，6 项）

| # | 场景 | 断言 |
|---|------|------|
| 13 | mode=random 创建用户 | mock `init_password_for_user` 被调一次 |
| 14 | 已存在用户 + 后续同步 | **不调** `init_password_for_user` |
| 15 | mode=none 创建用户 | `temporary_pwd=False` + Celery 不调 |
| 16 | 旧 source（无 `platform_config.password_init`） | 行为与改动前一致（`make_password("")`） |
| 17 | service 返回 failed | 用户仍创建 + email_status 反映失败 |
| 18 | `_ensure_user_sync_source_match` 冲突 | 跳该用户，不影响其他 |

#### HTTP 端点集成测试（`tests/test_user_sync_source_preview.py`，3 项） ⭐ 关键

| # | 场景 | 断言 |
|---|------|------|
| 19 | preview 带 `business_config.password_init` | 400 + "Unsupported business_config fields: password_init" 回归守住 |
| 20 | preview 带 `platform_config.password_init` | 200 成功 |
| 21 | 旧 path 创建 source 仍被拒 | 400 |

#### 其他测试

| # | 文件 | 项 |
|---|---|---|
| 22-24 | `test_reset_pwd_sentinel_guard.py` | 3 项 |
| 25-27 | `test_password_vault.py`（helper） | 3 项 |

### 前端测试

`web/scripts/user-sync-password-init-test.ts`：i18n 12 个 key 全量覆盖 + 类型定义导出。

`web/scripts/user-sync-record-summary-test.ts`：覆盖无邮件状态、发送中、全部成功、部分失败和全部失败的摘要展示，以及中英文文案键。

### 不写的测试（YAGNI）

- 邮件正文模板的精确字符串（容易脆）
- Celery 重试间隔的精确秒数（Celery 自身保证）
- `make_password` 自身的 hash 算法（库保证）
- 前端图标 / 样式 class（视觉测试不在单元范围）

---

## Risks & Mitigations

| 风险 | 缓解 |
|------|------|
| 「统一密码」模式一封邮件泄露全员沦陷 | UI 配置处加风险提示文案（产品侧允许不二次拦截） |
| Email 通道批量发送可能触发 SMTP 限流 | Celery 重试 + 指数退避；前端展示「发送中」给管理员预期 |
| Vault 残留：邮件发送后未及时 pop（worker 崩溃） | 兜底清理脚本：`finished_at + 24h` 清空 |
| Vault 加密 KEY 与 SECRET_KEY 共用 | 后续可分专用 `PASSWORD_VAULT_KEY`（不在本轮） |
| 用户邮箱缺失导致邮件失败 | 写入 `email_status.failed_reasons`；前端展示失败列表 |
| 「none」模式被误重置 | reset_password API 层守卫 + sentinel hash 前缀识别 |
| **Celery 读到未 commit 的 vault** | `transaction.on_commit` 包裹 `.delay()`（race #3 修复） |
| **`_build_run_payload` 覆盖 vault** | 接受 `current_run` 继承 `password_vault` / `email_status`（race #4 修复） |
| **错表（IMNotificationChannel vs Channel）** | `send_email_via_runtime` 改查通用 `Channel` 表（race #6 修复） |
| **email provider 不存在** | `channel_utils.send_email` 直接 SMTP，不走 `RuntimeApplicationService`（race #7 修复） |
| 跨进程 Celery worker 写 `run.payload` 时的并发 | `update_email_status_via_rpc` 内部加版本号自旋（简化） |

---

## Decision Log（实施期间的关键调整）

### D1. 字段从 `business_config.password_init` → `platform_config.password_init`

**原计划**：把 password_init 放在 `UserSyncSource.business_config` JSON key 内。
**问题**：飞书 / 企微 provider manifest 校验 `business_config` 字段，未声明字段被拒绝。错误：`"Unsupported user_sync business config fields: password_init"`。
**决策**：加独立 `UserSyncSource.platform_config` JSONField，并将密码初始化收敛到 `platform_config.password_init`（`models/user_sync_source.py` + migration 0039）。
**理由**：BK-Lite 平台级配置不归 provider 管，避开 provider contract 校验；同时避免未来继续增加 `*_config` 顶层字段，让平台侧策略都收敛到统一容器。
**数据迁移**：旧 source 不会自动迁移，管理员在 UI 重新配置即可。

### D2. 三种模式的邮件发送规则

**原计划（spec 早期）**：uniform 模式发邮件可选，加 send_email 开关。
**决策**（用户决定）：none 不发；uniform / random **都必发**邮件（mode=uniform/random 模式下 email_channel_id 为必填）。
**理由**：简化产品规则；统一密码告知所有用户；随机密码必须告知。

### D3. 邮件发送走通用 `Channel` 表 + `channel_utils.send_email`，不走 `RuntimeApplicationService`

**原计划**：用 `RuntimeApplicationService.execute(provider_key='email', capability_key='email', ...)`。
**问题**：
- 项目**没有** email provider manifest（只有 `ad` / `feishu` / `wechat`），报 `Unknown provider 'email'`
- `IMNotificationChannel` 是 IM 类型（飞书/企微/钉钉），不含 email 通道
- 实际 `Channel` 表（通用）有 `email` 类型，且 `channel_utils.send_email` 直接走 SMTP
**决策**：`password_init_email.py:send_email_via_runtime` 改查 `Channel.objects.filter(id=channel_id, channel_type='email')` + 调 `channel_utils.send_email`。

### D4. `transaction.on_commit` 包裹 `.delay()`（race #3 修复）

**问题**：`_sync_users` 在 `with transaction.atomic():` 内。service 写 vault 后立即 `.delay()` 入队；Celery worker 立即启动查 DB，但 atomic 还没 commit → worker 拿到旧 payload 看不到 vault。
**修法**：`from django.db import transaction; transaction.on_commit(lambda: send_initial_password_email.delay(user_id, run_id))`—— atomic 成功 commit 后才入队。

### D5. `_build_run_payload` 继承 `password_vault` / `email_status`（race #4 修复）

**问题**：`execute_user_sync_source` 在 sync 完成后整个覆盖 `run.payload`，把 service 之前写的 `password_vault` 和 `email_status` 清空。
**修法**：`_build_run_payload(result, input_summary, sync_summary=None, current_run=None)` 接受 `current_run` 参数，从 `current_run.payload` 继承 `password_vault` / `email_status` key。

### D6. `Channel` 改用通用 `Channel` 表（race #6 修复）

**问题**：最初 `send_email_via_runtime` 查 `IMNotificationChannel`，但 IMNotificationChannel 是 IM 类型不含 email 通道。**用户的邮件服务器在通用 `Channel` 表**。
**修法**：改查 `Channel.objects.filter(id=channel_id, channel_type='email')`。

### D7. `channel_utils.send_email` 而非 `RuntimeApplicationService`（race #7 修复）

**问题**：项目**没有** email provider manifest，`RuntimeApplicationService.execute(provider_key='email', ...)` 报 `Unknown provider 'email'`。
**修法**：`password_init_email.py:send_email_via_runtime` 改调 `channel_utils.send_email(channel, title, content, user_list_queryset)` 直接 SMTP，**不走** provider 体系。

### D8. 初始密码邮件采用正式中文账号开通通知

**决策**：邮件标题统一为“BK-Lite 账号开通通知”；正文说明管理员已开通账号，分别展示用户名和初始密码，并提醒首次登录后立即修改密码。末尾增加不得转发、截图或长期保存邮件的安全提醒，以“BK-Lite 平台”署名。

**边界**：仅调整邮件标题和 HTML 正文，不改变收件人、密码生成、存储、重试、状态回写或邮件通道逻辑；不引入图片和外部资源，也不在日志或额外持久化位置记录明文密码。

### D9. 同步记录摘要展示异步邮件结果

**决策**：复用 `UserSyncRun.payload.email_status`，不新增后端字段或接口。`completed=false` 时展示发送中及总数；完成后按全部成功、部分失败、全部失败展示成功或失败数量和“核查用户邮箱和邮件通道”的建议。

**边界**：`email_status` 不存在时不展示邮件信息；摘要不得展示失败用户名、邮箱、密码或底层错误。同步主任务状态仍由同步结果决定，不等待邮件任务完成。

### D10. 初始密码邮件改为按同步运行批量投递（待实施）

**问题**：现有实现为每位用户投递一条 `send_initial_password_email(user_id, run_id)` Celery 任务；每条任务都会建立、认证并关闭一次 SMTP 连接。大规模同步会同时造成大量 Celery 消息和重复 SMTP 建连，且每个用户完成后都要竞争写入同一 `UserSyncRun.payload`。

**决策**：改为同步运行维度的批量任务。同步事务中只加密暂存待投递密码与用户标识；`transaction.on_commit` 后仅投递一条 `send_initial_password_email_batch(run_id)`。任务每次原子领取最多 200 位用户，复用一条 SMTP 连接，逐封构造个性化邮件并连续调用 `send_message()`；批结束后汇总回写状态，仍有待投递用户时只续投下一条批任务。

**状态模型**：在既有 `UserSyncRun.payload` 中增加仅供任务恢复使用的 `email_dispatch`，将待处理条目在行锁内从 `pending` 原子移动至带过期时间的 `inflight`。单个收件人失败只记录该用户并继续本批；连接、认证或 Worker 异常导致未尝试的条目回到 `pending`。定时恢复任务每天 00:00 只回收租约过期的 `inflight`，不是常规调度路径。

**安全与边界**：不将明文密码作为 Celery 参数；仅在发送该用户前从 vault 解密。保持 `email_status` 作为对外摘要，继续不展示用户名、邮箱、密码或底层错误。不会修改既有 `channel_utils.send_email_to_user` 的单封行为；新增仅面向密码初始化批处理的 SMTP 会话辅助能力，并设置有限连接/读写超时。

**取舍**：本轮不新增逐用户投递模型，接受 `payload` JSON 行锁、无逐用户查询与极端故障下的至少一次投递语义。该方案的目标是将队列消息数控制为约 `ceil(用户数 / 200)`，而非提供完整邮件外盒系统。

---

## Open Questions

（已无——所有关键决策已通过 Decision Log 记录）
