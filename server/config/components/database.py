import os
from pathlib import Path

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Migration 补丁的包目录，用于信创数据库适配
REPLACE_MIGRATION_MODULE_PATH = "migrate_patch.patches"

db_engine = os.getenv("DB_ENGINE", "postgresql").lower()


if db_engine == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT"),
        }
    }

elif db_engine == "mysql":
    import pymysql

    pymysql.install_as_MySQLdb()

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT"),
        }
    }

elif db_engine == "sqlite":
    database_name = os.getenv("DB_NAME", "bk-lite.sqlite3")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.path.join(Path(__file__).resolve().parent.parent, database_name),
        }
    }

elif db_engine == "dameng":
    DATABASES = {
        "default": {
            "ENGINE": "cw_cornerstone.db.dameng.backend",
            "NAME": os.getenv("DB_NAME", "SYSDBA"),
            "USER": os.getenv("DB_USER", "SYSDBA"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "5236"),
            # 达梦数据库连接选项
            "OPTIONS": {
                "connection_timeout": 30,  # 连接超时时间(秒)
                "login_timeout": 10,  # 登录超时时间(秒)
            },
            # 每次请求后关闭连接，避免连接状态异常导致后续请求卡死
            "CONN_MAX_AGE": 0,
        }
    }
    # 达梦环境下使用本地内存 Session，避免 Session 数据库操作的兼容性问题
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "locmem"

    # ============================================================
    # 达梦数据库 Migration 补丁说明
    # ============================================================
    # Migration 补丁通过 cw_cornerstone.migrate_patch 自动加载
    # 补丁文件位于: migrate_patch/patches/dameng/{app_label}/{migration_name}.py
    # 补丁机制: 在 pre_migrate 信号时替换原始 migration 的 operations
    # 当前已有补丁:
    #   - django_celery_results/0006_taskresult_date_created.py (重复索引)
    #   - django_celery_results/0009_groupresult.py (重复索引)
    #   - alerts/0001_initial.py (PostgreSQL 专属索引: GinIndex, BTreeIndex)

    # ============================================================
    # 达梦数据库 + ASGI 重要提示：
    # ============================================================
    # 由于达梦数据库驱动是同步的，在 uvicorn ASGI 模式下可能导致：
    # 1. 线程池耗尽 -> 后续请求卡住
    # 2. 单 worker 时，一个慢查询会阻塞所有请求
    #
    # 推荐解决方案（二选一）：
    # 1. 使用 gunicorn 同步模式（推荐）:
    #    gunicorn wsgi:application --workers 4 --bind 0.0.0.0:8989 --timeout 120
    # 2. 使用 uvicorn 多 worker 模式:
    #    uvicorn asgi:application --workers 4 --host 0.0.0.0 --port 8989
    # ============================================================

elif db_engine == "gaussdb":
    DATABASES = {
        "default": {
            "ENGINE": "cw_cornerstone.db.gaussdb.backend",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }

    # ============================================================
    # GaussDB 数据库 Migration 补丁说明
    # ============================================================
    # Migration 补丁通过 cw_cornerstone.migrate_patch 自动加载
    # 补丁文件位于: migrate_patch/patches/gaussdb/{app_label}/{migration_name}.py
    # 补丁机制: 在 pre_migrate 信号时替换原始 migration 的 operations
    #
    # GaussDB ustore 不支持的操作及解决方案:
    #   1. GIN 索引 (gin index is not supported for ustore)
    #      - GinIndex 使用 FakeAddIndex 跳过
    #   2. jsonb 列 ubtree 索引 (data type jsonb has no default operator class for access method "ubtree")
    #      - JSONField 上的普通 Index 使用 FakeAddIndex 跳过
    #   3. BTreeIndex on datetime (db_index=True 已创建索引)
    #      - 使用 FakeAddIndex 跳过避免重复
    #
    # 当前已有补丁:
    #   - alerts/0001_initial.py (跳过 GinIndex/BTreeIndex)
    #   - alerts/0005_*.py (跳过重复 ForeignKey 索引 + FakeAlterField)
    #   - alerts/0010_*.py (跳过 RemoveIndex/AddIndex on JSONField)

elif db_engine == "goldendb":
    DATABASES = {
        "default": {
            "ENGINE": "cw_cornerstone.db.goldendb.backend",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "8880"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "collation": "utf8mb4_bin",
            },
        }
    }

    # ============================================================
    # GoldenDB 数据库 Migration 补丁说明
    # ============================================================
    # Migration 补丁通过 cw_cornerstone.migrate_patch 自动加载
    # 补丁文件位于: migrate_patch/patches/goldendb/{app_label}/{migration_name}.py
    # 补丁机制: 在 pre_migrate 信号时替换原始 migration 的 operations
    # 当前已有补丁:
    #   - alerts/0001_initial.py (跳过 JSONField 上的 GinIndex/BTreeIndex)
    #   - alerts/0005_*.py (跳过重复 ForeignKey 索引)
    #   - alerts/0010_*.py (跳过 RemoveIndex/AddIndex on JSONField)

elif db_engine == "oceanbase":
    DATABASES = {
        "default": {
            "ENGINE": "cw_cornerstone.db.oceanbase.backend",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "2881"),
            "OPTIONS": {
                "charset": "utf8mb4",
            },
        }
    }

    # ============================================================
    # OceanBase 数据库 Migration 补丁说明
    # ============================================================
    # Migration 补丁通过 migrate_patch 自动加载
    # 补丁文件位于: migrate_patch/patches/oceanbase/{app_label}/{migration_name}.py
    # 补丁机制: 在 pre_migrate 信号时替换原始 migration 的 operations
    #
    # OceanBase 不支持的操作及解决方案:
    #   1. JSON 列索引 (错误码 3152)
    #      - GinIndex/BTreeIndex 替换为通用 models.Index (排除 JSON 列)
    #   2. ALTER 非字符串类型字段 (错误码 1235)
    #      - 使用 FakeAlterField 跳过，在初始迁移中直接定义最终类型
    #   3. 删除 rowkey 列 (错误码 1235)
    #      - 使用 FakeRemoveField 跳过
    #   4. 删除不存在的约束 (错误码 1091)
    #      - 使用 FakeRemoveConstraint 跳过
    #
    # 当前已有补丁:
    #   - alerts/0001_initial.py (GinIndex/BTreeIndex → models.Index)
    #   - alerts/0005_*.py (GinIndex → models.Index)
    #   - alerts/0010_*.py (FakeRemoveIndex 跳过删除)
    #   - log/0003_*.py (EventRawData.data 直接定义为 S3JSONField)
    #   - log/0004_*.py, log/0009_*.py (FakeAlterField 跳过)
    #   - mlops/0021_*.py (TimeSeriesPredictTrainData 直接定义最终类型)
    #   - mlops/0027_*.py (ImageClassificationTrainData 直接定义最终类型)
    #   - mlops/0032_*.py, 0036-0039_*.py (FakeAlterField 跳过)
    #   - operation_analysis/0003_*.py, 0004_*.py (FakeRemoveConstraint 跳过)

else:
    raise ValueError(f"Unsupported DB_ENGINE: '{db_engine}'. Supported values: postgresql, mysql, sqlite, dameng, gaussdb, oceanbase, goldendb")


# ============================================================
# 达梦数据库补丁 - 必须在 Django 开始使用缓存前应用
# ============================================================
# 注意：这里只应用无法延迟的补丁（如 DatabaseCache 写入禁用）。
# 其他补丁（如 JSONField、bulk_create）在 CoreConfig.ready() 中应用。
if db_engine == "dameng":
    from apps.core.db_patches.dameng import apply_early_patches

    apply_early_patches()
