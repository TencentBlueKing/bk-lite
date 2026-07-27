from django.core.cache import caches
from django.core.cache.backends.dummy import DummyCache
from django.core.cache.backends.locmem import LocMemCache
from django.core.cache.backends.redis import RedisCache
from django.core.management import BaseCommand, CommandError

from apps.core.utils.permission_cache import (
    API_TOKEN_PERMISSION_CACHE_PREFIX,
    API_TOKEN_PERMISSION_KEYS_PREFIX,
    PERM_CACHE_PREFIX,
    TOKEN_INFO_PREFIX,
    USER_PERM_KEYS_PREFIX,
)

ROLLBACK_PERMISSION_CACHE_PATTERNS = (
    f"{PERM_CACHE_PREFIX}*",
    f"{USER_PERM_KEYS_PREFIX}*",
    f"{TOKEN_INFO_PREFIX}*",
    f"{API_TOKEN_PERMISSION_CACHE_PREFIX}:*",
    f"{API_TOKEN_PERMISSION_KEYS_PREFIX}*",
)


def _clear_permission_namespaces(cache_backend) -> int:
    """只清理权限键；支持 django-redis、Django RedisCache 与已排空的进程内缓存。"""
    delete_pattern = getattr(cache_backend, "delete_pattern", None)
    if callable(delete_pattern):
        return sum(int(delete_pattern(pattern) or 0) for pattern in ROLLBACK_PERMISSION_CACHE_PATTERNS)

    if isinstance(cache_backend, RedisCache):
        client = cache_backend._cache.get_client(None, write=True)
        deleted = 0
        for pattern in ROLLBACK_PERMISSION_CACHE_PATTERNS:
            physical_pattern = cache_backend.make_key(pattern)
            batch = []
            for key in client.scan_iter(match=physical_pattern, count=1000):
                batch.append(key)
                if len(batch) == 1000:
                    deleted += int(client.delete(*batch) or 0)
                    batch = []
            if batch:
                deleted += int(client.delete(*batch) or 0)
        return deleted

    if isinstance(cache_backend, (LocMemCache, DummyCache)):
        # 命令要求先排空全部 Worker；新命令进程中的本地缓存没有旧 Worker 数据。
        return 0

    raise CommandError("当前缓存后端不支持安全的权限命名空间清理；请保持 Worker 停止并等待权限缓存 TTL 到期")


class Command(BaseCommand):
    help = "回滚到旧版权限缓存前清除权限缓存命名空间，避免旧无版本权限快照重新生效"

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="确认已排空全部 Server Worker，并允许清空默认缓存",
        )

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError("必须先排空全部 Server Worker，再使用 --confirm 清除权限缓存")

        try:
            deleted = _clear_permission_namespaces(caches["default"])
        except CommandError:
            raise
        except Exception as error:
            raise CommandError(f"权限缓存清理失败，禁止启动旧版本 Server Worker: {error}") from error

        self.stdout.write(self.style.SUCCESS(f"权限缓存命名空间已清理（删除 {deleted} 个键），可以启动旧版本 Server Worker"))
