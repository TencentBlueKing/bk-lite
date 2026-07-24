"""补丁管理模块配置常量。

魔法数字集中在此，避免散落在 service / view / task 中。
环境变量可覆盖，便于不同部署灵活调整。
"""

import os
from datetime import timedelta


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# 手工 Windows 补丁包单文件上限（MB）
PATCH_MGMT_MAX_PACKAGE_SIZE_MB = _int_env("PATCH_MGMT_MAX_PACKAGE_SIZE_MB", 4096)

# 手工 Windows 补丁记录等待浏览器上传的最长时间（秒）
PATCH_MGMT_PACKAGE_UPLOAD_TIMEOUT = _int_env(
    "PATCH_MGMT_PACKAGE_UPLOAD_TIMEOUT", 24 * 60 * 60
)


# ── 扫描任务执行配置 ─────────────────────────────────────────────────────────

# 主机子任务调度超时（秒）
DISPATCH_TIMEOUT = _int_env("PATCH_GOVERNANCE_DISPATCH_TIMEOUT", 300)

# 单台主机评估/验证阶段超时（秒）
ASSESS_STAGE_TIMEOUT = _int_env("PATCH_ASSESS_STAGE_TIMEOUT", 1800)
VERIFY_STAGE_TIMEOUT = _int_env("PATCH_VERIFY_STAGE_TIMEOUT", 1800)

# 兼容既有配置名；治理执行统一通过 get_stage_timeout 取值
SCAN_TASK_TIMEOUT = ASSESS_STAGE_TIMEOUT

# 源连通性探测超时（秒）
SOURCE_CONNECTIVITY_TIMEOUT = _int_env("PATCH_SOURCE_CONNECTIVITY_TIMEOUT", 30)

# 过期扫描任务周期兜底检查间隔（分钟）
SCAN_STALE_CHECK_INTERVAL_MINUTES = _int_env("PATCH_SCAN_STALE_CHECK_INTERVAL_MINUTES", 10)

# ── 安装任务执行配置 ─────────────────────────────────────────────────────────

# 单台主机安装阶段超时（秒）
INSTALL_STAGE_TIMEOUT = _int_env("PATCH_INSTALL_TASK_TIMEOUT", 7200)
INSTALL_TASK_TIMEOUT = INSTALL_STAGE_TIMEOUT

# 重启命令下发超时（秒）
REBOOT_COMMAND_TIMEOUT = _int_env("PATCH_REBOOT_COMMAND_TIMEOUT", 300)

# 超时后的只读结果核验配置
RECONCILE_TIMEOUT = _int_env("PATCH_GOVERNANCE_RECONCILE_TIMEOUT", 1800)
RECONCILE_INTERVAL = _int_env("PATCH_GOVERNANCE_RECONCILE_INTERVAL", 120)
GOVERNANCE_WATCHDOG_INTERVAL = _int_env("PATCH_GOVERNANCE_WATCHDOG_INTERVAL", 60)

# install -> reboot -> verify 连续治理链路超期线（秒）
CHAIN_TIMEOUT = _int_env("PATCH_GOVERNANCE_CHAIN_TIMEOUT", 14400)

# Celery soft/hard limit 相对业务 deadline 的缓冲（秒）
CELERY_SOFT_LIMIT_GRACE = _int_env("PATCH_GOVERNANCE_SOFT_LIMIT_GRACE", 120)
CELERY_HARD_LIMIT_GRACE = _int_env("PATCH_GOVERNANCE_HARD_LIMIT_GRACE", 300)

# 过期安装任务周期兜底检查间隔（分钟）
INSTALL_STALE_CHECK_INTERVAL_MINUTES = _int_env("PATCH_INSTALL_STALE_CHECK_INTERVAL_MINUTES", 15)

# ── 重启后自动验证配置 ───────────────────────────────────────────────────────

# 重启后主机恢复探测定时任务间隔（秒）
REBOOT_VERIFY_POLL_INTERVAL = _int_env("PATCH_REBOOT_VERIFY_POLL_INTERVAL", 60)

# 重启后主机恢复最大等待时间（秒），超时标记失败
REBOOT_VERIFY_MAX_WAIT = _int_env("PATCH_REBOOT_VERIFY_MAX_WAIT", 3600)

CELERY_BEAT_SCHEDULE: dict = {
    "patch_mgmt_watch_governance_timeouts": {
        "task": "apps.patch_mgmt.tasks.watch_governance_timeouts",
        "schedule": timedelta(seconds=GOVERNANCE_WATCHDOG_INTERVAL),
    },
    "patch_mgmt_verify_pending_reboot": {
        "task": "apps.patch_mgmt.tasks.verify_pending_reboot_hosts",
        "schedule": timedelta(seconds=REBOOT_VERIFY_POLL_INTERVAL),
    },
}


def get_stage_timeout(task_type: str) -> int:
    """返回单台主机指定治理阶段的业务超时。"""
    return {
        "assess": ASSESS_STAGE_TIMEOUT,
        "install": INSTALL_STAGE_TIMEOUT,
        "reboot": REBOOT_COMMAND_TIMEOUT,
        "verify": VERIFY_STAGE_TIMEOUT,
    }.get(task_type, ASSESS_STAGE_TIMEOUT)


def get_host_task_limits(task_type: str) -> tuple[int, int]:
    """返回 Celery 主机子任务 soft/hard time limit。"""
    timeout = get_stage_timeout(task_type)
    return timeout + CELERY_SOFT_LIMIT_GRACE, timeout + CELERY_HARD_LIMIT_GRACE
