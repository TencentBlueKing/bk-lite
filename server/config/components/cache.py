# 缓存配置
import os

REDIS_CACHE_URL = os.environ.get("REDIS_CACHE_URL", "")

CACHES = {
    "db": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    },
    "dummy": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
    "locmem": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "redis": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "OPTIONS": {
            # "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
        },
    },
}
if REDIS_CACHE_URL:
    CACHES["default"] = CACHES["redis"]
else:
    CACHES["default"] = CACHES["locmem"]
