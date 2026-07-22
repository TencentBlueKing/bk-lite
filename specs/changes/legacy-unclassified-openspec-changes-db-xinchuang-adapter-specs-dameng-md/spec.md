# 达梦 (DM) 适配规格

Status: cancelled

## Migration Context

非标准旧 artifact，原路径为 `openspec/changes/db-xinchuang-adapter/specs/dameng.md`。完整内容保留如下。

## 概述

达梦数据库是国产数据库，需要特殊的驱动和补丁支持。

## 数据库配置

```python
# config/components/database.py
elif db_engine == "dameng":
    DATABASES = {
        "default": {
            "ENGINE": "cw_cornerstone.db.dameng.backend",
            "NAME": os.getenv("DB_NAME", "SYSDBA"),
            "USER": os.getenv("DB_USER", "SYSDBA"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "5236"),
            "OPTIONS": {
                "connection_timeout": 30,
                "login_timeout": 10,
            },
            "CONN_MAX_AGE": 0,  # 每次请求后关闭连接
        }
    }
    # 使用本地内存 Session
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "locmem"
```

## 不支持的操作

| 操作 | 解决方案 |
|------|----------|
| 重复索引 | `FakeAddIndex` 跳过 |
| GinIndex/BTreeIndex | `FakeAddIndex` 跳过 |

## 特殊注意事项

### ASGI 模式

达梦数据库驱动是同步的，在 uvicorn ASGI 模式下可能导致：
1. 线程池耗尽 → 后续请求卡住
2. 单 worker 时，一个慢查询会阻塞所有请求

推荐解决方案：
1. 使用 gunicorn 同步模式：
   ```bash
   gunicorn wsgi:application --workers 4 --bind 0.0.0.0:8989 --timeout 120
   ```
2. 使用 uvicorn 多 worker 模式：
   ```bash
   uvicorn asgi:application --workers 4 --host 0.0.0.0 --port 8989
   ```

### 早期补丁

达梦需要在 Django 开始使用缓存前应用早期补丁：

```python
if db_engine == "dameng":
    from apps.core.db_patches.dameng import apply_early_patches
    apply_early_patches()
```

## 已创建的补丁文件

### ORM 补丁
- `apps/core/db_patches/dameng.py`

### Migration 补丁

| 文件路径 | 说明 |
|----------|------|
| `migrate_patch/patches/dameng/django_celery_results/0006_taskresult_date_created.py` | 重复索引 |
| `migrate_patch/patches/dameng/django_celery_results/0009_groupresult.py` | 重复索引 |
| `migrate_patch/patches/dameng/alerts/0001_initial.py` | GinIndex/BTreeIndex |

## 验证

```bash
cd server && python manage.py migrate
```
