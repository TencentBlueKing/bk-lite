"""用同一份配置约束 worker 命令、部署预算与 supervisor。"""

import os
from dataclasses import dataclass

POOL_IMPLEMENTATION = "celery.concurrency.prefork:TaskPool"
DEDICATED_QUEUES = {
    "dashboard-report-render": ("dashboard_report_render",),
    "patch-maintenance": ("patch_maintenance",),
    "opspilot": ("opspilot_channel", "opspilot_wiki", "opspilot_maintenance", "opspilot_chat_parse"),
}
POOL_QUEUES = {
    "critical": ("critical",),
    "notification": ("notification",),
    "state": ("state",),
    "background": ("background", "celery"),
}


def positive_integer(env, name, default=None):
    raw = env.get(name, default)
    if raw is None or not str(raw).isascii() or not str(raw).isdigit() or int(raw) < 1:
        raise ValueError(f"{name} 必须显式配置为正整数")
    return int(raw)


@dataclass(frozen=True)
class PoolConfig:
    name: str
    minimum: int
    maximum: int


@dataclass(frozen=True)
class RuntimeConfig:
    pools: tuple[PoolConfig, ...]
    total_limit: int = 0
    replicas: int = 1
    keepalive: int = 60
    run_beat: bool = True
    dedicated: tuple[PoolConfig, ...] = ()

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        enabled = env.get("ENABLE_CELERY", "false").lower()
        if enabled not in ("true", "false"):
            raise ValueError("ENABLE_CELERY 必须为 true 或 false")
        if enabled == "false":
            return cls(())
        if env.get("CELERY_CONCURRENCY"):
            raise ValueError("请移除 CELERY_CONCURRENCY，改用各池 MIN/MAX")
        pools = []
        for name in POOL_QUEUES:
            minimum = positive_integer(env, f"CELERY_{name.upper()}_MIN")
            maximum = positive_integer(env, f"CELERY_{name.upper()}_MAX")
            if minimum > maximum:
                raise ValueError(f"{name} 的 MIN 不能大于 MAX")
            pools.append(PoolConfig(name, minimum, maximum))
        replicas = positive_integer(env, "CELERY_WORKER_REPLICAS", "1")
        beat = env.get("CELERY_RUN_BEAT", "true" if replicas == 1 else "").lower()
        if beat not in ("true", "false"):
            raise ValueError("多副本部署必须用 CELERY_RUN_BEAT 显式指定唯一 Beat 所属实例")
        render_capacity = positive_integer(env, "DASHBOARD_REPORT_RENDER_CONCURRENCY", "2")
        dedicated = [PoolConfig("dashboard-report-render", render_capacity, render_capacity), PoolConfig("patch-maintenance", 1, 1)]
        installed = {item.strip() for item in env.get("INSTALL_APPS", "").split(",") if item.strip()}
        if not installed or "opspilot" in installed:
            opspilot_capacity = positive_integer(env, "OPSPILOT_CELERY_CONCURRENCY", "2")
            dedicated.append(PoolConfig("opspilot", opspilot_capacity, opspilot_capacity))
        config = cls(
            tuple(pools),
            positive_integer(env, "CELERY_TOTAL_CONCURRENCY_LIMIT"),
            replicas,
            positive_integer(env, "AUTOSCALE_KEEPALIVE", "60"),
            beat == "true",
            tuple(dedicated),
        )
        if config.maximum_concurrency > config.total_limit:
            raise ValueError("所有副本的 MAX 总和超过 CELERY_TOTAL_CONCURRENCY_LIMIT")
        return config

    @property
    def maximum_concurrency(self):
        return sum(pool.maximum for pool in (*self.pools, *self.dedicated)) * self.replicas

    def worker_args(self, name):
        pool = next((pool for pool in self.pools if pool.name == name), None)
        if pool is None:
            raise ValueError(f"未启用的执行池：{name}")
        return [
            "-A",
            "apps.core.celery",
            "worker",
            "--loglevel=info",
            "--pool=prefork",
            f"--autoscale={pool.maximum},{pool.minimum}",
            "-Q",
            ",".join(POOL_QUEUES[name]),
            "-n",
            f"{name}@%h",
            "--prefetch-multiplier=1",
        ]

    def supervisor_config(self):
        sections = ["; 此文件由 celery_runtime.launcher 生成，不要同时启动旧 celery/beat 配置。\n"]
        for pool in self.pools:
            command = "celery " + " ".join(self.worker_args(pool.name)).replace("%", "%%")
            sections.append(self._program(f"celery_{pool.name}", command))
        if self.pools and self.run_beat:
            sections.append(
                self._program(
                    "beat", "celery -A apps.core.celery beat --loglevel=info " "--scheduler django_celery_beat.schedulers.DatabaseScheduler"
                )
            )
        return "\n".join(sections)

    def _program(self, name, command):
        # TERM 只发给主进程，让 Celery 等待任务完成；不使用 supervisor 默认的短等待后强杀。
        return f"""[program:{name}]
command={command}
directory=/apps
environment=AUTOSCALE_KEEPALIVE="{self.keepalive}"
autostart=true
priority=10
autorestart=true
stopsignal=TERM
stopasgroup=false
killasgroup=false
stopwaitsecs=2147483647
redirect_stderr=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
"""
