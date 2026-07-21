# 用户同步-本地密码初始化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在「系统管理 → 用户同步」中新增对同步用户的本地密码初始化方式配置能力,每个 `UserSyncSource` 独立配置三种模式(不设置密码 / 设置统一密码 / 设置随机密码),邮件异步发送且失败可追溯。

**Architecture:** 复用现有 `User.temporary_pwd` 机制 + 新增 `password_init_service` + Celery 异步任务 + `UserSyncRun.payload` JSON 字段承载临时 vault 与 email_status。前端 `PasswordInitSection` 作为 UserSyncConfigModal 内的 section。

**Tech Stack:** Django 4.2 + Celery + AES (PyCryptodome) + Next.js 16 + Ant Design + TypeScript

**Spec:** `docs/superpowers/specs/2026-07-13-user-sync-password-init-design.md`

## Global Constraints

- **中文优先**:commit message / 注释 / 测试名 / 用户可见文案一律中文
- **覆盖率**:后端核心模块 ≥85%,前端 PasswordInitSection ≥75%(CLAUDE.md 红线)
- **TDD**:每个 task 必须先写失败测试,再实现,再验证通过
- **YAGNI**:不新增 UserSyncRecord model / failure_reason / retry_count 字段 / retry-email 端点(已与产品侧敲定)
- **不重置已有用户密码**:仅首次创建时触发密码初始化,后续周期同步不动 `password` / `temporary_pwd`
- **Celery args 只传 id**:与项目现有模式一致(`execute_im_notification_sync_run_task(run_id)`),raw_password 走 `UserSyncRun.payload.password_vault` AES 加密
- **i18n 必做**:新增 key 必须在中英双语文件都有,禁止回退硬编码([login-i18n-mandatory])
- **commit 前先询问**:本计划**不**在每个 Task 完成后单独 commit;整个需求总体实施完成、用户确认无问题后,做**一次总提交**(Task 7 Step 7)。实施过程中每个 Task 的"跑测试通过"步骤后,**不要** git add / git commit。
- **测试命令**:`cd server && make test`(后端);`cd web && pnpm lint && pnpm type-check`(前端)

---

## Task 1: PasswordCrypto 帮助函数 + 单测

**Files:**
- Create: `server/apps/core/utils/crypto/password_crypto.py` (已存在,确认现状)
- Create: `server/apps/system_mgmt/utils/password_vault.py`
- Test: `server/apps/system_mgmt/tests/test_password_vault.py`

**Interfaces:**
- Consumes: 无
- Produces: `encrypt_for_vault(plaintext: str) -> str` / `decrypt_from_vault(ciphertext: str) -> str`

- [ ] **Step 1: 写失败测试**

```python
# server/apps/system_mgmt/tests/test_password_vault.py
from django.test import TestCase, override_settings
from apps.system_mgmt.utils.password_vault import encrypt_for_vault, decrypt_from_vault


class PasswordVaultTest(TestCase):
    @override_settings(SECRET_KEY="test-secret-key-32bytes-padded!!")
    def test_roundtrip(self):
        plain = "MyRandomP@ssw0rd!2026"
        cipher = encrypt_for_vault(plain)
        self.assertNotIn(plain, cipher)
        self.assertEqual(decrypt_from_vault(cipher), plain)

    @override_settings(SECRET_KEY="test-secret-key-32bytes-padded!!")
    def test_decrypt_invalid_raises(self):
        with self.assertRaises(ValueError):
            decrypt_from_vault("not-a-valid-ciphertext")

    @override_settings(SECRET_KEY="test-secret-key-32bytes-padded!!")
    def test_empty_string_roundtrip(self):
        self.assertEqual(decrypt_from_vault(encrypt_for_vault("")), "")

    @override_settings(SECRET_KEY="")
    def test_missing_secret_key_raises(self):
        with self.assertRaises(ValueError):
            encrypt_for_vault("anything")
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_password_vault.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'apps.system_mgmt.utils.password_vault'`

- [ ] **Step 3: 实现最小代码**

```python
# server/apps/system_mgmt/utils/password_vault.py
from django.conf import settings

from apps.core.utils.crypto.password_crypto import PasswordCrypto


def _get_cipher() -> PasswordCrypto:
    key = getattr(settings, "SECRET_KEY", "") or ""
    if not key:
        raise ValueError("SECRET_KEY 未配置,无法加解密 vault")
    return PasswordCrypto(key=key)


def encrypt_for_vault(plaintext: str) -> str:
    """用 SECRET_KEY 派生的 AES 密钥加密密码,用于 UserSyncRun.payload.password_vault 临时存放"""
    return _get_cipher().encrypt(plaintext)


def decrypt_from_vault(ciphertext: str) -> str:
    """解密 vault 中的密码;失败时抛 ValueError"""
    return _get_cipher().decrypt(ciphertext)
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_password_vault.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 跑全量 core 测试确认无回归**

Run: `cd server && python -m pytest apps/core/tests/test_crypto_pure.py -v`
Expected: PASS (既有 PasswordCrypto 测试不破)

---

## Task 2: PasswordInitService + 单测

> **实施修订 (2026-07-15, 方案收敛)**: service 内部不直接读 `source.business_init_config`,而是从 caller 传入的参数 dict 读。caller (`_sync_users`) 从 `source.platform_config.password_init` 读。函数签名第三参数为 `business_config: dict` 保留命名(避免大规模改动),实际内容来自 `platform_config.password_init`。

**Files:**
- Create: `server/apps/system_mgmt/services/password_init_service.py`
- Create: `server/apps/system_mgmt/tests/test_password_init_service.py`

**Interfaces:**
- Consumes: `User` (实例), `mode: str`, `business_config: dict`, `run: UserSyncRun`
- Produces: `init_password_for_user(user, mode, business_config, run) -> dict` 返回 `{status, reason, raw_password_or_none}`
- 副作用:
  - 修改 `user.password` / `user.temporary_pwd` 并 `user.save()`
  - `mode in {uniform, random}` 时把 AES 加密的 raw_password 写入 `run.payload["password_vault"][username]`
  - `mode in {uniform, random}` 时入队 Celery 任务 `send_initial_password_email.delay(user.id, run.id)`

- [ ] **Step 1: 写失败测试**

```python
# server/apps/system_mgmt/tests/test_password_init_service.py
from unittest import mock
from django.test import TestCase, override_settings
from apps.system_mgmt.models import User, UserSyncSource, UserSyncRun, Group
from apps.system_mgmt.services.password_init_service import init_password_for_user
from apps.system_mgmt.utils.password_vault import encrypt_for_vault


@override_settings(SECRET_KEY="test-secret-key-32bytes-padded!!")
class InitPasswordForUserTest(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="root", parent_id=0)
        self.source = UserSyncSource.objects.create(
            name="test-source",
            integration_instance_id=1,
            root_group_name="root",
            business_config={"password_init": {"mode": "none"}},
        )
        self.run = UserSyncRun.objects.create(
            source=self.source,
            status="running",
            payload={},
        )

    def _make_user(self, username="alice"):
        from django.contrib.auth.hashers import make_password
        return User.objects.create(
            username=username,
            display_name=username,
            email=f"{username}@example.com",
            password=make_password(""),
            domain="domain.com",
            disabled=False,
            group_list=[self.group.id],
            sync_source=self.source,
        )

    def test_mode_none_uses_sentinel_and_no_celery(self):
        with mock.patch("apps.system_mgmt.services.password_init_service.send_initial_password_email.delay") as delay:
            user = self._make_user()
            result = init_password_for_user(user, "none", {}, self.run)
            user.refresh_from_db()
            self.assertEqual(result["status"], "ok")
            self.assertTrue(user.password.startswith("!UNSET_"))
            self.assertFalse(user.temporary_pwd)
            delay.assert_not_called()

    def test_mode_uniform_success(self):
        with mock.patch("apps.system_mgmt.services.password_init_service.send_initial_password_email.delay") as delay:
            user = self._make_user()
            cfg = {"uniform_password": "Str0ngP@ss!", "email_channel_id": 7}
            result = init_password_for_user(user, "uniform", cfg, self.run)
            user.refresh_from_db()
            self.assertEqual(result["status"], "ok")
            self.assertTrue(user.check_password("Str0ngP@ss!"))
            self.assertTrue(user.temporary_pwd)
            delay.assert_called_once_with(user.id, self.run.id)

    def test_mode_uniform_weak_password_rejected(self):
        with mock.patch("apps.system_mgmt.services.password_init_service.send_initial_password_email.delay") as delay:
            user = self._make_user()
            cfg = {"uniform_password": "123", "email_channel_id": 7}
            result = init_password_for_user(user, "uniform", cfg, self.run)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reason"], "weak_password")
            delay.assert_not_called()

    def test_mode_uniform_missing_channel(self):
        with mock.patch("apps.system_mgmt.services.password_init_service.send_initial_password_email.delay") as delay:
            user = self._make_user()
            cfg = {"uniform_password": "Str0ngP@ss!"}
            result = init_password_for_user(user, "uniform", cfg, self.run)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reason"], "missing_channel")
            delay.assert_not_called()

    def test_mode_random_generates_strong_password(self):
        with mock.patch("apps.system_mgmt.services.password_init_service.send_initial_password_email.delay") as delay:
            user = self._make_user("u1")
            cfg = {"email_channel_id": 7}
            result = init_password_for_user(user, "random", cfg, self.run)
            self.assertEqual(result["status"], "ok")
            self.assertGreaterEqual(len(result["raw_password"]), 12)
            user.refresh_from_db()
            self.assertTrue(user.temporary_pwd)
            delay.assert_called_once_with(user.id, self.run.id)

    def test_mode_random_writes_vault(self):
        with mock.patch("apps.system_mgmt.services.password_init_service.send_initial_password_email.delay") as delay:
            user = self._make_user("bob")
            cfg = {"email_channel_id": 7}
            init_password_for_user(user, "random", cfg, self.run)
            self.run.refresh_from_db()
            vault = self.run.payload.get("password_vault", {})
            self.assertIn("bob", vault)
            self.assertNotIn("Str0ngP@ss", vault["bob"])  # 加密结果不含明文
            # 验证能解回原始密码
            raw = result_raw = init_password_for_user(
                type("U", (), {"username": "bob", "id": user.id})(),
                "random", cfg, self.run,
            )

    def test_mode_random_missing_channel(self):
        with mock.patch("apps.system_mgmt.services.password_init_service.send_initial_password_email.delay") as delay:
            user = self._make_user()
            cfg = {}
            result = init_password_for_user(user, "random", cfg, self.run)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reason"], "missing_channel")
            delay.assert_not_called()
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_password_init_service.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'apps.system_mgmt.services.password_init_service'`

- [ ] **Step 3: 实现最小代码**

```python
# server/apps/system_mgmt/services/password_init_service.py
"""
用户同步-本地密码初始化 service。

对外接口: init_password_for_user(user, mode, business_config, run) -> dict
"""
import secrets
from typing import Any

from django.contrib.auth.hashers import make_password

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.nats.login import PasswordValidator
from apps.system_mgmt.tasks.password_init_tasks import send_initial_password_email
from apps.system_mgmt.utils.password_vault import encrypt_for_vault


PASSWORD_INIT_SENTINEL = "UNSET_PASSWORD"


def _validate_uniform_password(password: str) -> tuple[bool, str]:
    is_valid, error_message = PasswordValidator.validate_password(password)
    if not is_valid:
        return False, error_message or "密码强度不够"
    return True, ""


def init_password_for_user(user, mode: str, business_config: dict, run) -> dict:
    """
    根据 mode 给同步创建的用户初始化本地密码。
    仅在首次创建时调用,后续同步不再触发。

    Returns: {"status": "ok" | "failed", "reason": str | None,
              "raw_password": str | None} (raw_password 仅 random 模式返回)
    """
    if mode == "none":
        user.password = make_password(PASSWORD_INIT_SENTINEL)
        user.temporary_pwd = False
        user.save()
        return {"status": "ok", "reason": None, "raw_password": None}

    if mode == "uniform":
        raw = (business_config or {}).get("uniform_password", "")
        channel_id = (business_config or {}).get("email_channel_id")
        if not channel_id:
            return {"status": "failed", "reason": "missing_channel", "raw_password": None}
        ok, msg = _validate_uniform_password(raw)
        if not ok:
            return {"status": "failed", "reason": "weak_password", "raw_password": None}
        user.password = make_password(raw)
        user.temporary_pwd = True
        user.save()
        _stash_to_vault(run, user.username, raw)
        send_initial_password_email.delay(user.id, run.id)
        return {"status": "ok", "reason": None, "raw_password": raw}

    if mode == "random":
        raw = secrets.token_urlsafe(12)
        channel_id = (business_config or {}).get("email_channel_id")
        if not channel_id:
            return {"status": "failed", "reason": "missing_channel", "raw_password": None}
        user.password = make_password(raw)
        user.temporary_pwd = True
        user.save()
        _stash_to_vault(run, user.username, raw)
        send_initial_password_email.delay(user.id, run.id)
        return {"status": "ok", "reason": None, "raw_password": raw}

    return {"status": "failed", "reason": f"unknown_mode:{mode}", "raw_password": None}


def _stash_to_vault(run, username: str, raw_password: str) -> None:
    """把 raw_password AES 加密后塞进 run.payload.password_vault,初始化 email_status。"""
    payload = dict(run.payload or {})
    vault = dict(payload.get("password_vault", {}))
    vault[username] = encrypt_for_vault(raw_password)
    payload["password_vault"] = vault
    email_status = dict(payload.get("email_status", {}))
    email_status.setdefault("total", 0)
    email_status["total"] = email_status.get("total", 0) + 1
    email_status.setdefault("sent", 0)
    email_status.setdefault("failed", 0)
    email_status.setdefault("failed_usernames", [])
    email_status.setdefault("failed_reasons", {})
    email_status["completed"] = False
    payload["email_status"] = email_status
    run.payload = payload
    run.save(update_fields=["payload"])
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_password_init_service.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: 跑既有 user_sync_service 测试确认无回归**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_user_sync_service.py -v`
Expected: PASS (既有测试不破)

---

## Task 3: Celery 任务 + NATS handler + 单测

> **实施修订 (2026-07-15)**:
> 1. `send_email_via_runtime` 改用 `channel_utils.send_email` 直接 SMTP,不走 `RuntimeApplicationService`(项目没有 email provider manifest)
> 2. `send_email_via_runtime` 查通用 `Channel` 表 `channel_type='email'`,不是 `IMNotificationChannel`
> 3. `_enqueue_email` 用 `transaction.on_commit` 包裹 `.delay()`(避免 race)
> 4. Celery 任务代码最终落在 `server/apps/system_mgmt/tasks.py`,**没有**独立的 `tasks/password_init_tasks.py` 文件
> 5. 详细修订记录见 Task 8

**Files:**
- Create: `server/apps/system_mgmt/tasks/password_init_tasks.py`
- Create: `server/apps/system_mgmt/nats/email_status.py`
- Create: `server/apps/system_mgmt/tests/test_password_init_tasks.py`
- Modify: `server/apps/system_mgmt/nats_api.py` (注册新 handler)

**Interfaces:**
- Consumes: `send_initial_password_email(user_id: int, run_id: int)` Celery args only
- Produces: 调用 NATS `update_email_status(run_id, username, ok, reason)` 完成回写

- [ ] **Step 1: 写失败测试**

```python
# server/apps/system_mgmt/tests/test_password_init_tasks.py
from unittest import mock
from django.test import TestCase, override_settings
from apps.system_mgmt.models import User, UserSyncSource, UserSyncRun, Group
from apps.system_mgmt.tasks.password_init_tasks import send_initial_password_email
from apps.system_mgmt.utils.password_vault import encrypt_for_vault


@override_settings(SECRET_KEY="test-secret-key-32bytes-padded!!")
class SendInitialPasswordEmailTest(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="root", parent_id=0)
        self.source = UserSyncSource.objects.create(
            name="test-source",
            integration_instance_id=1,
            root_group_name="root",
            business_config={},
        )
        from django.contrib.auth.hashers import make_password
        self.user = User.objects.create(
            username="alice",
            display_name="Alice",
            email="alice@example.com",
            password=make_password("RandomP@ss!"),
            domain="domain.com",
            disabled=False,
            group_list=[self.group.id],
            sync_source=self.source,
            temporary_pwd=True,
        )
        self.run = UserSyncRun.objects.create(
            source=self.source,
            status="running",
            payload={
                "password_vault": {"alice": encrypt_for_vault("RandomP@ss!")},
                "email_status": {
                    "total": 1, "sent": 0, "failed": 0,
                    "failed_usernames": [], "failed_reasons": {},
                    "completed": False,
                },
            },
        )

    @mock.patch("apps.system_mgmt.tasks.password_init_tasks.update_email_status_via_rpc")
    @mock.patch("apps.system_mgmt.tasks.password_init_tasks.send_email_via_runtime")
    def test_success_pops_vault_and_updates_status(self, send_email, update_rpc):
        send_email.return_value = {"result": True, "message": "ok"}
        update_rpc.return_value = None
        send_initial_password_email.run(self.user.id, self.run.id)
        self.run.refresh_from_db()
        self.assertNotIn("alice", self.run.payload.get("password_vault", {}))
        self.assertEqual(self.run.payload["email_status"]["sent"], 1)
        self.assertTrue(self.run.payload["email_status"]["completed"])

    @mock.patch("apps.system_mgmt.tasks.password_init_tasks.send_email_via_runtime")
    def test_vault_decrypt_failure(self, send_email):
        self.run.payload["password_vault"]["alice"] = "garbage-not-aes-cipher"
        self.run.save(update_fields=["payload"])
        send_initial_password_email.run(self.user.id, self.run.id)
        self.run.refresh_from_db()
        self.assertEqual(self.run.payload["email_status"]["failed"], 1)
        self.assertIn("alice", self.run.payload["email_status"]["failed_usernames"])
        self.assertIn("vault 解密失败", self.run.payload["email_status"]["failed_reasons"]["alice"])

    @mock.patch("apps.system_mgmt.tasks.password_init_tasks.update_email_status_via_rpc")
    @mock.patch("apps.system_mgmt.tasks.password_init_tasks.send_email_via_runtime")
    def test_channel_failure_marks_failed(self, send_email, update_rpc):
        send_email.return_value = {"result": False, "message": "channel disabled"}
        # 关闭 autoretry 走同步分支
        with mock.patch.object(send_initial_password_email, "retry", side_effect=Exception("max retry")):
            try:
                send_initial_password_email.run(self.user.id, self.run.id)
            except Exception:
                pass
        self.run.refresh_from_db()
        self.assertEqual(self.run.payload["email_status"]["failed"], 1)
        self.assertIn("alice", self.run.payload["email_status"]["failed_usernames"])
        self.assertNotIn("alice", self.run.payload.get("password_vault", {}))
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_password_init_tasks.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: 实现最小代码**

```python
# server/apps/system_mgmt/nats/email_status.py
"""
邮件发送状态回写 NATS handler。
worker 端(可能跨进程)调用此 handler,跨进程同步 run.payload。
"""
from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import UserSyncRun


def update_email_status_via_rpc(run_id: int, username: str, ok: bool, reason: str = "") -> dict:
    """
    增量更新 UserSyncRun.payload.email_status。

    ok=True:  sent += 1
    ok=False: failed += 1, failed_usernames += [username], failed_reasons[username] = reason
    全部 settle 后 completed=True
    """
    try:
        run = UserSyncRun.objects.filter(id=run_id).first()
        if not run:
            return {"result": False, "message": f"run {run_id} not found"}

        payload = dict(run.payload or {})
        email_status = dict(payload.get("email_status", {}))

        sent = int(email_status.get("sent", 0))
        failed = int(email_status.get("failed", 0))
        failed_usernames = list(email_status.get("failed_usernames", []))
        failed_reasons = dict(email_status.get("failed_reasons", {}))

        if ok:
            sent += 1
        else:
            failed += 1
            if username not in failed_usernames:
                failed_usernames.append(username)
            failed_reasons[username] = reason or "未知错误"

        total = int(email_status.get("total", 0))
        completed = (sent + failed) >= total

        email_status.update({
            "sent": sent,
            "failed": failed,
            "failed_usernames": failed_usernames,
            "failed_reasons": failed_reasons,
            "completed": completed,
        })
        payload["email_status"] = email_status
        run.payload = payload
        run.save(update_fields=["payload"])
        return {"result": True, "data": {"sent": sent, "failed": failed, "completed": completed}}
    except Exception as e:
        logger.error(f"update_email_status 失败 run_id={run_id} username={username}: {e}", exc_info=True)
        return {"result": False, "message": str(e)}
```

```python
# server/apps/system_mgmt/tasks/password_init_tasks.py
"""
用户同步-初始密码邮件发送 Celery 任务。
"""
from celery import shared_task

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import User, UserSyncRun
from apps.system_mgmt.providers import RuntimeApplicationService
from apps.system_mgmt.tasks.password_init_tasks_compat import (
    send_email_via_runtime,
    update_email_status_via_rpc,
)
from apps.system_mgmt.utils.password_vault import decrypt_from_vault


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
    name="apps.system_mgmt.tasks.password_init_tasks.send_initial_password_email",
)
def send_initial_password_email(self, user_id: int, run_id: int):
    """
    Celery worker 端:
      1. 取 user + run
      2. 解密 vault 拿 raw_password
      3. 调 RuntimeApplicationService 发送邮件
      4. 成功后 pop vault 该 username + 回写 email_status
      5. 失败重试 3 次,最终失败同样 pop + 写 failed
    """
    user = User.objects.filter(id=user_id).first()
    run = UserSyncRun.objects.filter(id=run_id).first()
    if not user or not run:
        logger.error(f"send_initial_password_email user={user_id} run={run_id} 数据缺失")
        return

    username = user.username
    encrypted = (run.payload or {}).get("password_vault", {}).get(username)
    if not encrypted:
        logger.warning(f"vault 缺 username={username},run={run_id} 已发送或丢失")
        return

    try:
        raw_password = decrypt_from_vault(encrypted)
    except Exception as e:
        logger.error(f"vault 解密失败 user={username} run={run_id}: {e}")
        update_email_status_via_rpc(run_id, username, ok=False, reason="vault 解密失败")
        _pop_vault(run_id, username)
        return

    try:
        result = send_email_via_runtime(user, raw_password)
    except Exception as exc:
        logger.warning(f"邮件发送异常 username={username}: {exc};触发重试")
        try:
            raise self.retry(exc=exc)
        except Exception:
            update_email_status_via_rpc(run_id, username, ok=False, reason=str(exc))
            _pop_vault(run_id, username)
            return

    if result.get("result"):
        update_email_status_via_rpc(run_id, username, ok=True)
        _pop_vault(run_id, username)
    else:
        msg = result.get("message", "未知错误")
        try:
            raise self.retry(exc=Exception(msg))
        except Exception:
            update_email_status_via_rpc(run_id, username, ok=False, reason=msg)
            _pop_vault(run_id, username)


def _pop_vault(run_id: int, username: str) -> None:
    """从 run.payload.password_vault 中删除 username(幂等)。"""
    try:
        run = UserSyncRun.objects.filter(id=run_id).first()
        if not run:
            return
        payload = dict(run.payload or {})
        vault = dict(payload.get("password_vault", {}))
        vault.pop(username, None)
        payload["password_vault"] = vault
        run.payload = payload
        run.save(update_fields=["payload"])
    except Exception as e:
        logger.error(f"_pop_vault 失败 run_id={run_id} username={username}: {e}")
```

```python
# server/apps/system_mgmt/tasks/password_init_tasks_compat.py
"""
同进程内的兼容 helper(便于单测 monkeypatch;生产经 NATS 调用)。
"""
from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.nats.email_status import update_email_status_via_rpc
from apps.system_mgmt.providers import RuntimeApplicationService


def send_email_via_runtime(user, raw_password: str) -> dict:
    """
    通过 RuntimeApplicationService 调用 im_notification 通道发送邮件。
    返回 {"result": bool, "message": str}
    """
    try:
        from apps.system_mgmt.models import IMNotificationChannel
        channel_id = (user.sync_source.business_config or {}).get("password_init", {}).get("email_channel_id")
        if not channel_id:
            return {"result": False, "message": "缺少 email_channel_id"}

        channel = IMNotificationChannel.objects.filter(id=channel_id, enabled=True).first()
        if not channel:
            return {"result": False, "message": f"邮件通道 {channel_id} 不存在或未启用"}

        runtime = RuntimeApplicationService()
        result = runtime.execute(
            provider_key=channel.integration_instance.provider_key,
            capability_key="im_notification",
            operation="send_message",
            config=channel.integration_instance.get_runtime_config(),
            title="您的 BK-Lite 账号已开通",
            content=f"用户名:{user.username}\n初始密码:{raw_password}\n首次登录后请立即修改密码。",
            receive_id_type=channel.external_receive_field,
            receive_ids=[user.email] if user.email else [],
        )
        return {"result": result.success, "message": result.summary}
    except Exception as e:
        logger.error(f"send_email_via_runtime 失败 user={user.username}: {e}", exc_info=True)
        return {"result": False, "message": str(e)}
```

- [ ] **Step 4: 修改 nats_api.py 注册 handler**

修改 `server/apps/system_mgmt/nats_api.py`,在 `_sync_compat_globals` 注册 `update_email_status_via_rpc` 与新 module:

```python
# 在 _sync_compat_globals / nats_client 路由表加 update_email_status_via_rpc
# 同时在 apps.system_mgmt.nats 包下加 __init__.py 导出
```

具体路径参考 `server/apps/system_mgmt/nats_api.py:1-50` 的现有模式;若 handler 不走 NATS RPC 而走同进程(worker 与 web 共进程),可在 `server/apps/system_mgmt/nats/email_status.py` 加 `@nats_client.register` 装饰器(参考 `server/apps/system_mgmt/nats/login.py:6` 的 `@nats_client.register`)。

- [ ] **Step 5: 跑测试验证通过**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_password_init_tasks.py -v`
Expected: PASS (3 tests)

---

## Task 4: `_sync_users` 集成 + 单测

> **实施修订 (2026-07-15)**:
> 1. 字段从 `source.business_config.password_init` 改为 `source.platform_config.password_init`（独立平台配置 JSONField 内的策略块）
> 2. `_build_run_payload` 接受 `current_run` 参数继承 `password_vault` / `email_status` key(避免覆盖 service 写入)
> 3. 详细修订记录见 Task 8

**Files:**
- Modify: `server/apps/system_mgmt/services/user_sync_service.py:_sync_users`
- Modify: `server/apps/system_mgmt/tests/test_user_sync_service.py`

- [ ] **Step 1: 扩展 test_user_sync_service.py**

在 `tests/test_user_sync_service.py` 末尾追加以下测试(假设现有 setup 已创建 source/group):

```python
# 在 test_user_sync_service.py 末尾追加
from unittest import mock
from apps.system_mgmt.services.password_init_service import init_password_for_user


class SyncUsersPasswordInitTest(TestCase):
    def setUp(self):
        # 复用现有 setUp 模式创建 source + group + integration_instance
        ...

    @mock.patch("apps.system_mgmt.services.user_sync_service.init_password_for_user")
    def test_new_user_triggers_init(self, init_mock):
        init_mock.return_value = {"status": "ok", "reason": None, "raw_password": None}
        source = UserSyncSource.objects.create(
            name="random-src",
            integration_instance=self.instance,
            root_group_name="root",
            business_config={"password_init": {"mode": "random", "email_channel_id": 7}},
        )
        _sync_users(source, [{"user_id": "alice", "name": "Alice", "email": "a@b.c"}],
                    group_id_mapping={}, root_group_id=self.group.id, root_department_id="all")
        init_mock.assert_called_once()

    @mock.patch("apps.system_mgmt.services.user_sync_service.init_password_for_user")
    def test_existing_user_skips_init(self, init_mock):
        # 预先创建一个已存在的 user,后续同步不应触发 init
        ...

    @mock.patch("apps.system_mgmt.services.user_sync_service.init_password_for_user")
    def test_mode_none_skips_celery(self, init_mock):
        init_mock.return_value = {"status": "ok", "reason": None, "raw_password": None}
        ...

    def test_legacy_source_no_password_init_unchanged(self):
        """回归:旧 source(无 password_init)行为不变"""
        source = UserSyncSource.objects.create(
            ...,
            business_config={},  # 无 password_init
        )
        # 不应有 init_password_for_user 调用
        with mock.patch("apps.system_mgmt.services.user_sync_service.init_password_for_user") as m:
            _sync_users(...)
            m.assert_not_called()
```

- [ ] **Step 2: 修改 `_sync_users` 集成 `init_password_for_user`**

修改 `server/apps/system_mgmt/services/user_sync_service.py:_sync_users` (大约 line 433-448 的 create_users 循环):

```python
# 在 server/apps/system_mgmt/services/user_sync_service.py 顶部加 import
from apps.system_mgmt.services.password_init_service import init_password_for_user

# 修改 create_users 构造逻辑 (around line 436)
for item in normalized_users:
    user = existing_user_map.get(item["username"])
    if user is None:
        new_user = User(
            username=item["username"],
            display_name=item["display_name"],
            email=item["email"],
            phone=item["phone"],
            password=make_password(""),
            domain=legacy_domain,
            disabled=False,
            group_list=item["group_list"],
            sync_source=source,
        )
        new_user.save()  # 先入库拿到 id
        # 触发密码初始化(新用户才触发)
        password_init_cfg = (source.business_config or {}).get("password_init", {})
        mode = password_init_cfg.get("mode")
        if mode:
            init_password_for_user(new_user, mode, password_init_cfg, current_run)
        continue
    ...
```

需要在 `_sync_users` 入口增加 `current_run` 参数(从 `execute_user_sync_source` 传入);如果现有签名不允许,在 service 层通过 `UserSyncRun.objects.filter(source=source, status=RUNNING).first()` 兜底查找。

- [ ] **Step 3: 把 `current_run` 接入**

修改 `_sync_users` 的调用方(`server/apps/system_mgmt/services/user_sync_service.py:sync_users` 之类),把当前 run 实例传进来;如果调用栈找不到,在 `_sync_users` 内 `UserSyncRun.objects.filter(source=source, status="running").first()`。

- [ ] **Step 4: 跑测试验证通过**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_user_sync_service.py apps/system_mgmt/tests/test_password_init_service.py -v`
Expected: PASS

---

## Task 5: reset_password 守卫 + 单测

**Files:**
- Modify: `server/apps/system_mgmt/viewset/user_viewset.py`
- Modify: `server/apps/system_mgmt/tests/test_user_viewset.py` (或新文件)

- [ ] **Step 1: 写失败测试**

```python
# server/apps/system_mgmt/tests/test_user_reset_password_sentinel_test.py
from django.test import TestCase
from apps.system_mgmt.models import User, Group
from apps.system_mgmt.services.password_init_service import PASSWORD_INIT_SENTINEL
from django.contrib.auth.hashers import make_password


class ResetPasswordSentinelGuardTest(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="root", parent_id=0)
        self.user = User.objects.create(
            username="ext-alice",
            display_name="Alice",
            email="a@b.c",
            password=make_password(PASSWORD_INIT_SENTINEL),
            domain="domain.com",
            disabled=False,
            group_list=[self.group.id],
            sync_source=None,
            temporary_pwd=False,
        )

    def test_reset_blocked_when_password_is_sentinel(self):
        # 直接调用 reset_pwd NATS handler,模拟 API 请求
        from apps.system_mgmt.nats.login import reset_pwd
        result = reset_pwd("ext-alice", "domain.com", "NewP@ssw0rd!", caller_token="any")
        self.assertFalse(result["result"])
        self.assertIn("外部同步用户", result["message"])
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_user_reset_password_sentinel_test.py -v`
Expected: FAIL(目前未拦截)

- [ ] **Step 3: 在 `reset_pwd` NATS handler 加守卫**

修改 `server/apps/system_mgmt/nats/login.py:reset_pwd` (around line 130-145):

```python
@nats_client.register
def reset_pwd(username, domain, password, caller_token=""):
    """重置用户密码(NATS接口)"""
    # ... 既有 caller_token 校验保留 ...
    user = User.objects.filter(**filter_kwargs).first()
    if not user:
        return {"result": False, "message": "Username not exists"}

    # 新增守卫:同步用户 + password 是 sentinel → 拒绝
    from apps.system_mgmt.services.password_init_service import PASSWORD_INIT_SENTINEL
    if user.sync_source_id and user.password.startswith(make_password(PASSWORD_INIT_SENTINEL)[:20]):
        loader = LanguageLoader(app="system_mgmt", default_lang=user.locale or "en")
        msg = loader.get("login.external_sync_no_password", "外部同步用户未设置本地密码,无法在此修改")
        return {"result": False, "message": msg}

    # ... 既有密码复杂度校验保留 ...
```

⚠️ 注意:`make_password` 每次结果不同,所以判断不能用整串 hash 比较;用 `user.password.startswith("!UNSET_")`(Django `make_password` 输出格式以 `!` 开头标识算法)即可识别 sentinel。

简化实现:不依赖 PASSWORD_INIT_SENTINEL 常量,直接 `user.password.startswith("!UNSET_")` 即可——因为 `make_password("UNSET_PASSWORD")` 的 Django 输出格式固定以 `!UNSET_` 开头。

- [ ] **Step 4: 跑测试验证通过**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_user_reset_password_sentinel_test.py -v`
Expected: PASS

- [ ] **Step 5: 跑全量 user_viewset 测试确认无回归**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_user_reset_password_3752.py apps/system_mgmt/tests/test_user_viewset.py -v`
Expected: PASS(既有 reset_password 测试 #0004 不破)

---

## Task 6: 前端 PasswordInitSection + i18n

> **实施修订 (2026-07-15)**:
> 1. form field path 从 `['business_config', 'password_init']` 改为 `['platform_config', 'password_init']`（独立平台配置字段）
> 2. 邮件通道 fetch 移到 `UserSyncConfigFields` 内部,用 `useRef` 锁住避免 React 18 strict mode 双调用导致无限循环
> 3. `UserSyncConfigFields` 改用 `Select` 而非 `Radio.Group`(用户反馈)
> 4. i18n 文件名实际是 `zh.json` / `en.json`(不是 `zh-CN.json` / `en-US.json`)
> 5. 前端 API 实际是 `web/src/app/system-manager/api/user-sync/index.ts`(不是 `api/user-sync.ts`)
> 6. 详细修订记录见 Task 8

**Files:**
- Create: `web/src/app/system-manager/components/user/user-sync/PasswordInitSection.tsx`
- Modify: `web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx`
- Modify: `web/src/app/system-manager/types/user-sync.ts`
- Modify: `web/src/app/system-manager/api/user-sync.ts`
- Modify: `web/src/app/system-manager/locales/zh-CN.json`
- Modify: `web/src/app/system-manager/locales/en-US.json`
- Create: `web/scripts/user-sync-password-init-test.ts`

**Interfaces:**
- 组件 props:
  ```ts
  interface PasswordInitSectionProps {
    value?: PasswordInitConfig;
    onChange?: (next: PasswordInitConfig) => void;
    t: (key: string, fallback?: string) => string;
  }
  interface PasswordInitConfig {
    mode: "none" | "uniform" | "random";
    uniform_password?: string;
    email_channel_id?: number;
  }
  ```

- [ ] **Step 1: 写失败前端测试**

```typescript
// web/scripts/user-sync-password-init-test.ts
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(__dirname, "..");
const zhCN = JSON.parse(
  readFileSync(resolve(ROOT, "src/app/system-manager/locales/zh-CN.json"), "utf8"),
);
const enUS = JSON.parse(
  readFileSync(resolve(ROOT, "src/app/system-manager/locales/en-US.json"), "utf8"),
);

const REQUIRED_KEYS = [
  "system.user.userSyncPage.passwordInit.sectionTitle",
  "system.user.userSyncPage.passwordInit.modeNone",
  "system.user.userSyncPage.passwordInit.modeUniform",
  "system.user.userSyncPage.passwordInit.modeRandom",
  "system.user.userSyncPage.passwordInit.uniformPasswordLabel",
  "system.user.userSyncPage.passwordInit.emailChannelLabel",
  "system.user.userSyncPage.passwordInit.uniformWarning",
];

for (const key of REQUIRED_KEYS) {
  assert.ok(zhCN[key], `zh-CN 缺 key: ${key}`);
  assert.ok(enUS[key], `en-US 缺 key: ${key}`);
}

console.log("✓ i18n key 全量覆盖");
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd web && npx tsx scripts/user-sync-password-init-test.ts`
Expected: FAIL(键缺失)

- [ ] **Step 3: 扩展类型定义**

`web/src/app/system-manager/types/user-sync.ts` 加:

```typescript
export type PasswordInitMode = "none" | "uniform" | "random";

export interface PasswordInitConfig {
  mode: PasswordInitMode;
  uniform_password?: string;
  email_channel_id?: number;
}

// UserSyncSourceConfigFormValues 加字段
export interface UserSyncSourceConfigFormValues {
  business_config: {
    password_init?: PasswordInitConfig;
    // ... 既有字段保留
  };
}
```

- [ ] **Step 4: 扩展 api 层**

`web/src/app/system-manager/api/user-sync.ts` 加:

```typescript
export const useUserSyncApi = () => {
  // ... 既有
  const getEmailChannels = async (): Promise<{ id: number; name: string; type: string }[]> => {
    // 调通知中心 channel list API,client 端 filter type=email
    const data = await request.get("/api/system_mgmt/notification_channel/", {
      params: { type: "email" },
    });
    return data?.items ?? data ?? [];
  };
  return { ..., getEmailChannels };
};
```

(具体 endpoint 参考 `web/src/app/system-manager/api/integration-center/index.ts` 的 `getAvailableInstances` 模式;若通知中心有专门 endpoint 如 `/channel/email-channels/`,按实际 URL 调整)

- [ ] **Step 5: 添加 i18n key**

`web/src/app/system-manager/locales/zh-CN.json`:
```json
"passwordInit": {
  "sectionTitle": "本地密码初始化",
  "modeNone": "不设置密码",
  "modeNoneHint": "同步用户仅允许通过外部身份源登录,本地无密码",
  "modeUniform": "设置统一密码",
  "modeUniformHint": "所有同步用户共用同一初始密码",
  "modeRandom": "设置随机密码",
  "modeRandomHint": "为每个同步用户生成独立随机密码",
  "uniformPasswordLabel": "统一初始密码",
  "uniformPasswordPlaceholder": "请输入符合系统安全策略的密码",
  "emailChannelLabel": "邮件通知通道",
  "emailChannelPlaceholder": "请选择邮件通道",
  "uniformWarning": "提示:统一密码模式下,所有同步用户共用同一密码。若邮件列表泄露,所有账号将面临风险。",
  "weakPasswordHint": "密码强度不够,请遵循系统安全策略",
}
```

`web/src/app/system-manager/locales/en-US.json` 加对应英文。

- [ ] **Step 6: 实现 PasswordInitSection 组件**

`web/src/app/system-manager/components/user/user-sync/PasswordInitSection.tsx`:

```tsx
'use client';

import React, { useEffect } from 'react';
import { Form, Input, Radio, Select, Alert } from 'antd';
import type { PasswordInitConfig } from '@/app/system-manager/types/user-sync';

interface PasswordInitSectionProps {
  value?: PasswordInitConfig;
  onChange?: (next: PasswordInitConfig) => void;
  emailChannels: { id: number; name: string }[];
  t: (key: string, fallback?: string) => string;
}

const PasswordInitSection: React.FC<PasswordInitSectionProps> = ({
  value,
  onChange,
  emailChannels,
  t,
}) => {
  const mode = value?.mode ?? 'none';

  const update = (patch: Partial<PasswordInitConfig>) => {
    onChange?.({ ...(value ?? { mode: 'none' }), ...patch });
  };

  return (
    <div className="flex flex-col gap-3">
      <Form.Item label={t('system.user.userSyncPage.passwordInit.sectionTitle')} required>
        <Radio.Group
          value={mode}
          onChange={(e) => update({ mode: e.target.value })}
        >
          <Radio.Button value="none">{t('system.user.userSyncPage.passwordInit.modeNone')}</Radio.Button>
          <Radio.Button value="uniform">{t('system.user.userSyncPage.passwordInit.modeUniform')}</Radio.Button>
          <Radio.Button value="random">{t('system.user.userSyncPage.passwordInit.modeRandom')}</Radio.Button>
        </Radio.Group>
        <div className="mt-2 text-xs text-[var(--color-text-3)]">
          {t(`system.user.userSyncPage.passwordInit.mode${mode[0].toUpperCase() + mode.slice(1)}Hint`)}
        </div>
      </Form.Item>

      {mode === 'uniform' && (
        <Form.Item
          label={t('system.user.userSyncPage.passwordInit.uniformPasswordLabel')}
          required
        >
          <Input.Password
            value={value?.uniform_password ?? ''}
            placeholder={t('system.user.userSyncPage.passwordInit.uniformPasswordPlaceholder')}
            onChange={(e) => update({ uniform_password: e.target.value })}
          />
          <Alert
            className="mt-2"
            type="warning"
            showIcon
            message={t('system.user.userSyncPage.passwordInit.uniformWarning')}
          />
        </Form.Item>
      )}

      {(mode === 'uniform' || mode === 'random') && (
        <Form.Item
          label={t('system.user.userSyncPage.passwordInit.emailChannelLabel')}
          required
        >
          <Select
            value={value?.email_channel_id}
            placeholder={t('system.user.userSyncPage.passwordInit.emailChannelPlaceholder')}
            onChange={(v) => update({ email_channel_id: v })}
            options={emailChannels.map((c) => ({ value: c.id, label: c.name }))}
          />
        </Form.Item>
      )}
    </div>
  );
};

export default PasswordInitSection;
```

- [ ] **Step 7: 集成到 UserSyncConfigFields**

修改 `web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx`,在合适位置(根 scope 字段下,业务字段上方)插入 `<PasswordInitSection ...>`;`value` / `onChange` 走 `business_config.password_init` 路径;`emailChannels` 通过 `useUserSyncApi().getEmailChannels()` 在父层取一次传入。

- [ ] **Step 8: 跑前端测试验证通过**

Run: `cd web && npx tsx scripts/user-sync-password-init-test.ts`
Expected: PASS (i18n keys 全有)

- [ ] **Step 9: 跑前端 lint + type-check**

Run: `cd web && pnpm lint && pnpm type-check`
Expected: 0 errors

---

## Task 7: 端到端验证 + 回归

- [ ] **Step 1: 跑后端全部 user_sync / password 相关测试**

Run: `cd server && python -m pytest apps/system_mgmt/tests/test_user_sync_service.py apps/system_mgmt/tests/test_password_init_service.py apps/system_mgmt/tests/test_password_init_tasks.py apps/system_mgmt/tests/test_user_reset_password_sentinel_test.py apps/system_mgmt/tests/test_user_reset_password_3752.py -v`
Expected: ALL PASS

- [ ] **Step 2: 跑 server 全量测试确认无回归**

Run: `cd server && make test`
Expected: ALL PASS(覆盖率统计 ≥85% for 新模块)

- [ ] **Step 3: 跑前端 lint + type-check**

Run: `cd web && pnpm lint && pnpm type-check`
Expected: 0 errors

- [ ] **Step 4: 跑前端现有 user-sync 端到端冒烟(若 scripts/cmdb-app-overview-wiring-test.mjs 类有则跑)**

Run: `cd web && npx tsx scripts/user-sync-password-init-test.ts`
Expected: PASS

- [ ] **Step 5: 添加 vault 24h 兜底清理**

新增 `server/apps/system_mgmt/management/commands/cleanup_password_vault.py`(或扩展现有清理命令):

```python
# server/apps/system_mgmt/management/commands/cleanup_password_vault.py
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.system_mgmt.models import UserSyncRun


class Command(BaseCommand):
    help = "清理 finished_at > 24h 的 UserSyncRun.payload.password_vault 残留"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=24)
        runs = UserSyncRun.objects.filter(finished_at__lt=cutoff).exclude(payload__password_vault={})
        cleaned = 0
        for run in runs:
            payload = dict(run.payload or {})
            if payload.get("password_vault"):
                payload["password_vault"] = {}
                run.payload = payload
                run.save(update_fields=["payload"])
                cleaned += 1
        self.stdout.write(self.style.SUCCESS(f"清理 {cleaned} 条残留 vault"))
```

并在 `server/config/celery.py` 的 beat_schedule 加每日执行:

```python
app.conf.beat_schedule["cleanup-password-vault-daily"] = {
    "task": "apps.system_mgmt.tasks.cleanup_password_vault",
    "schedule": crontab(hour=3, minute=0),  # 每日凌晨 3 点
}
```

实现 cleanup_password_vault Celery task:

```python
# server/apps/system_mgmt/tasks/cleanup_tasks.py (新增文件)
from celery import shared_task
from apps.core.logger import system_mgmt_logger as logger


@shared_task(name="apps.system_mgmt.tasks.cleanup_password_vault")
def cleanup_password_vault():
    from django.core.management import call_command
    call_command("cleanup_password_vault")
    logger.info("cleanup_password_vault done")
```

- [ ] **Step 6: 更新 docs/operations.md 第 4 节 env 变量表(如新增 PASSWORD_VAULT_KEY,本轮不引入但占位 TODO)**

参考 `docs/operations.md`;本轮用 SECRET_KEY 暂不分专用 key,加 TODO 注释:`TODO: 后续可分 PASSWORD_VAULT_KEY,目前共用 SECRET_KEY`。

- [ ] **Step 7: 汇总改动清单并询问用户进行一次总提交**

按用户约定,本轮**不做**每 task 一个 commit。汇总以下清单供用户过目:

- 后端新增文件清单:`password_init_service.py` / `tasks/password_init_tasks.py` / `tasks/cleanup_tasks.py` / `nats/email_status.py` / `tasks/password_init_tasks_compat.py` / 4 个测试文件 / `management/commands/cleanup_password_vault.py`
- 后端修改文件清单:`user_sync_service.py` / `nats/login.py` / `viewset/user_viewset.py` / `nats_api.py` / `config/celery.py` / `tests/test_user_sync_service.py` / `tests/test_user_reset_password_sentinel_test.py`
- 前端新增文件清单:`components/user/user-sync/PasswordInitSection.tsx` / `scripts/user-sync-password-init-test.ts`
- 前端修改文件清单:`components/user/user-sync/UserSyncConfigFields.tsx` / `types/user-sync.ts` / `api/user-sync.ts` / `locales/zh-CN.json` / `locales/en-US.json`
- 文档:`docs/superpowers/specs/2026-07-13-user-sync-password-init-design.md`(本次未提交,作为参考) / `docs/superpowers/plans/2026-07-13-user-sync-password-init.md`(本次未提交,作为参考) / `docs/operations.md`(更新 env 变量表)

确认无问题后,**用一次 commit 提交全部改动**。commit message 草稿:

```
feat(user-sync): 支持本地密码初始化方式配置(不设/统一/随机)

- 新增 PasswordInitService: 三种模式处理 password + temporary_pwd + vault 写入
- 新增 Celery 任务 send_initial_password_email: 自动重试 + 邮件状态回写
- 新增 cleanup_password_vault 兜底清理(每日凌晨 3 点)
- 新增 reset_password sentinel 守卫: none 模式用户不被本地重置
- _sync_users 集成: 仅首次创建触发密码初始化,后续同步不动 password
- 新增 Payload 字段 password_vault / email_status(不增加 model 字段)
- 前端 PasswordInitSection + i18n 双语 + 邮件通道从通知中心拉取

测试: 后端 31 项 + 前端 7 项 + 既有 reset_password 回归
```

---

## Task 8: 实施修订记录(2026-07-15 用户验证通过后回写)

**本轮实施过程中发现的关键修订**,每条都是用户操作时触发的真实 bug,逐一修。

### Step 1: 字段从 `business_config.password_init` → `platform_config.password_init`

**问题**: preview HTTP 接口报 `"Unsupported user_sync business config fields: password_init"`。feishu / ad / dingtalk provider manifest 校验 `business_config` 内的字段,未声明字段被拒绝。

**修法**:
- `server/apps/system_mgmt/models/user_sync_source.py` 加 `platform_config = models.JSONField(default=dict, blank=True)`
- 生成 `migrations/0039_*.py` 并 `migrate system_mgmt`
- `server/apps/system_mgmt/services/user_sync_service.py:_sync_users` line 462 从 `(source.platform_config or {}).get("password_init", {})` 读(替代 `business_config.password_init`)

**测试**: `tests/test_user_sync_source_preview.py` 守 "business_config.password_init 仍被拒绝" 的回归。

### Step 2: 前端 payload builder 携带 `platform_config.password_init`

**问题**: 用户在 UI 上填了统一密码并保存,`source.platform_config.password_init` 一直空——因为前端 `buildConfigUpdatePayload` 函数签名没接收 `passwordInitConfig`,`handleConfigSubmit` 也没把它放进 payload。

**修法**:
- `web/src/app/system-manager/utils/userSyncUtils.ts:buildConfigUpdatePayload` 加 `passwordInitConfig` 参数;`buildConfigPreviewPayload` 透传
- `web/src/app/system-manager/utils/userSyncUtils.ts:buildCreateSyncSourcePayload` 写 `platform_config: { password_init: { ...(values.platform_config?.password_init || {}) } }`
- `web/src/app/system-manager/(pages)/user/user-sync/page.tsx:handleConfigSubmit` / `handleConfigPreview` 传 `values.platform_config?.password_init`
- `web/src/app/system-manager/types/user-sync.ts:UserSyncSourceConfigFormValues` 加 `platform_config.password_init` 字段;`PasswordInitConfig.mode` 改 optional

### Step 3: `transaction.on_commit` 包裹 `.delay()`(race #1)

**问题**: `_sync_users` 在 `with transaction.atomic():` 块内。service 写 vault 后立即 `.delay()` 入队;Celery worker 立即启动查 DB,但 atomic 还没 commit → worker 拿到旧 payload 看不到 vault → 日志 `"vault 缺 username=... 已发送或丢失"`。

**修法**:
- `server/apps/system_mgmt/services/password_init_service.py:62` `_enqueue_email` 改为:
  ```python
  transaction.on_commit(
      lambda: send_initial_password_email.delay(user_id, run_id)
  )
  ```
- 测试 `tests/test_password_init_service.py` 所有会触发 enqueue 的测试加 `with patch("django.db.transaction.on_commit", side_effect=lambda fn, *a, **kw: fn(*a, **kw)):` 让 callback 立即同步执行(模拟 commit 完成)

### Step 4: `_build_run_payload` 继承 `password_vault` / `email_status`(race #2)

**问题**: `execute_user_sync` 完成后 `run.payload = _build_run_payload(...)` 整个覆盖,service 之前写的 `password_vault` 和 `email_status` 被清空。on_commit 触发后 worker 看到 vault 仍然缺。

**修法**:
- `server/apps/system_mgmt/services/user_sync_service.py:_build_run_payload` 加 `current_run` 参数,从 `current_run.payload` 继承 `password_vault` / `email_status` key(不覆盖 service 写入)
- 三处调用 `_build_run_payload(result, input_summary, current_run=run)` / `_build_run_payload(result, input_summary, sync_summary, current_run=run)` 传 current_run

### Step 5: `password_init_email.py` 改读 `platform_config.password_init`

**问题**: `send_email_via_runtime` 仍从 `sync_source.business_config.password_init` 读,字段已迁移到 `platform_config.password_init`,读不到 → `"缺少 email_channel_id"`。

**修法**:
- `server/apps/system_mgmt/services/password_init_email.py:25-27` 改:
  ```python
  password_init = ((sync_source.platform_config or {}) if sync_source else {}).get("password_init", {})
  channel_id = password_init.get("email_channel_id")
  ```

### Step 6: 改查通用 `Channel` 表(不是 `IMNotificationChannel`)

**问题**: `send_email_via_runtime` 查 `IMNotificationChannel` 但用户邮件服务器在通用 `Channel` 表(`channel_type='email'`)。IMNotificationChannel 是 IM 类型(飞书/企微/钉钉),不含 email 通道。报错 `"邮件通道 2 不存在或未启用"`。

**修法**:
- `password_init_email.py:32` 改:
  ```python
  from apps.system_mgmt.models import Channel
  channel = Channel.objects.filter(id=channel_id, channel_type="email").first()
  ```

### Step 7: 改用 `channel_utils.send_email` 直接 SMTP(不走 `RuntimeApplicationService`)

**问题**: `RuntimeApplicationService.execute(provider_key='email', ...)` 报 `"Unknown provider 'email"`。项目**没有** email provider manifest(只有 `ad` / `feishu` / `wechat`),email 通道没有对应 provider。错误:

```
ValueError: Unknown provider 'email'
```

**修法**:
- `password_init_email.py` 改用 `channel_utils.send_email`:
  ```python
  from apps.system_mgmt.utils.channel_utils import send_email as channel_send_email
  result = channel_send_email(
      channel, title="您的 BK-Lite 账号已开通",
      content=f"<p>用户名:{user.username}</p>...",
      user_list=User.objects.filter(id=user.id),
  )
  ```
- `channel_utils.send_email(channel_obj, ...)` 直接走 SMTP,不走 provider 体系
- import `User` 用于 user_list query

### Step 8: 清理调试 log

实施过程中临时加的 `logger.warning("[DEBUG] ...")` 已删除。最终代码不带调试 log。

### 最终验证

- 后端 29/29 测试 PASS
- 前端 i18n 12 项契约测试 + type-check 0 错误
- 用户验证: 飞书 user `6ba5916e` 收到含初始密码的邮件,登录成功触发首次改密
- 完整修复链共 **7 个 race condition / 实施陷阱**,每个都是真实工程问题

## Task 9: 邮件通知与同步记录摘要（已实施）

### Step 1: 正式化初始密码邮件

- 标题调整为“BK-Lite 账号开通通知”。
- 正文明确账号由管理员开通，展示用户名和初始密码，提醒首次登录后立即修改密码。
- 增加“请勿转发、截图或长期保存本邮件；如非本人操作，请联系管理员”的安全提醒，并以“BK-Lite 平台”署名。
- 保持基础 HTML，不引入图片或外部资源；密码明文只存在于既有发送链路。
- `tests/test_password_init_tasks.py` 增加正式中文文案回归断言。

### Step 2: 在同步记录摘要展示邮件结果

- 复用 `UserSyncRun.payload.email_status`，不新增后端字段或接口。
- `completed=false`：展示“初始密码邮件发送中（共 {{total}} 封）”。
- 全部成功：展示已发送数量；部分或全部失败：展示失败数量并提示核查用户邮箱和邮件通道。
- 不展示失败用户名、邮箱、密码或底层错误；无 `email_status` 时维持原有摘要。
- `web/scripts/user-sync-record-summary-test.ts` 覆盖无邮件、发送中、全部成功、部分失败和全部失败状态，并覆盖中英文文案键。

### Step 3: 删除未接入的 vault 清理命令

原 Task 7 中的 `cleanup_password_vault` 命令和测试未形成有效运行链路，已删除，不保留定时任务。邮件任务在成功或重试耗尽后移除对应 vault 条目。

## Task 10: 初始密码邮件批量投递（待实施）

**目标**：将按用户投递的 Celery 邮件任务改为按 `UserSyncRun` 批量投递，默认每批 200 位用户，复用单条 SMTP 连接，避免大规模同步挤占默认队列。

**涉及文件**：

- 修改：`server/apps/system_mgmt/services/password_init_service.py`
- 修改：`server/apps/system_mgmt/services/password_init_email.py`
- 修改：`server/apps/system_mgmt/tasks.py`
- 修改：`server/apps/system_mgmt/nats/email_status.py`
- 修改：`server/apps/system_mgmt/utils/channel_utils.py`
- 修改：`server/config/components/celery.py`
- 修改：`server/apps/system_mgmt/tests/test_password_init_service.py`
- 修改：`server/apps/system_mgmt/tests/test_password_init_tasks.py`
- 修改：`server/apps/system_mgmt/tests/test_password_vault.py`

### Step 1: 先补批量状态与领取行为测试

- 验证同步过程只在 commit 后调用一次 `send_initial_password_email_batch.delay(run_id)`，不按用户 `.delay()`。
- 验证行锁领取将最多 200 个待投递条目从 `email_dispatch.pending` 原子移动到 `inflight`，并写入租约到期时间。
- 验证两个并发领取者不能领取同一用户；领取失败或无待投递条目时不创建后续任务。

### Step 2: 将 vault 写入和任务入队改为运行级

- `password_vault` 继续只保存 AES 加密密码；`email_dispatch.pending` 保存用户 ID 与用户名，不保存明文密码、邮箱或 SMTP 凭据。
- `email_status` 初始化时记录 `total/sent/failed/failed_usernames/failed_reasons/completed`，并保持现有前端摘要契约。
- `transaction.on_commit` 仅登记一次 `send_initial_password_email_batch.delay(run_id)`；同一同步运行中后续用户只扩充 pending，不重复入队。

### Step 3: 增加个性化批量 SMTP 会话能力

- 不改变 `channel_utils.send_email_to_user` 的现有单封接口和行为。
- 新增仅由密码初始化批任务使用的会话辅助方法：从 `Channel.config` 解密 SMTP 密码，以 SSL 或 STARTTLS 建连并登录；每位用户单独构造 MIME 消息并调用同一连接的 `send_message()`；在 `finally` 中关闭连接。
- 连接和读写必须使用有限超时；单个收件人错误可继续后续用户，连接或认证错误必须中止本批并保留未尝试条目。

### Step 4: 实现批任务、结果汇总和恢复

- `send_initial_password_email_batch(run_id)` 在事务中领取 200 个条目，逐位解密密码并投递；完成后一次性汇总成功、失败和 vault 清理结果，降低同一 `payload` 的锁竞争。
- 本批仍有 pending 时，在当前任务提交后仅续投一条同 run 的批任务；全部 settle 后将 `email_status.completed=true` 并清理 `email_dispatch`。
- 为 `inflight` 设置租约；新增每日 00:00 的 Beat 恢复任务只扫描近期未完成运行，回收过期 inflight 后重新投递一个对应 run 的批任务。正常流程不依赖扫描。
- 明确至少一次语义：SMTP 已接受但 Worker 在状态写回前崩溃时，恢复后可能重复投递，不能把该场景误记为精确一次。

### Step 5: 回归验证

- `test_password_init_service.py`：none、uniform、random 三种模式及单 run 只入队一次。
- `test_password_init_tasks.py`：200 条领取上限、同连接连续发送个性化消息、单用户失败继续、连接失败退回 pending、租约恢复、完成摘要。
- `test_password_vault.py`：批处理按用户即时解密，完成或终态失败后删除对应 vault；不得将明文密码写入 dispatch 或 Celery 参数。
- 执行系统管理定向测试；确认既有用户同步、邮件通道、同步记录摘要测试均通过。
