# GoldenDB 适配规格

Status: cancelled

## Migration Context

非标准旧 artifact，原路径为 `openspec/changes/db-xinchuang-adapter/specs/goldendb.md`。完整内容保留如下。

## 概述

GoldenDB 兼容 MySQL 协议，不支持 PostgreSQL 专属索引类型。

## 数据库配置

```python
# config/components/database.py
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
```

## 不支持的操作

| 操作 | 解决方案 |
|------|----------|
| GinIndex | `FakeAddIndex` 跳过 |
| BTreeIndex | `FakeAddIndex` 跳过 |
| JSONField 索引 | `FakeAddIndex` 跳过 |

## 已创建的补丁文件

### ORM 补丁
- `apps/core/db_patches/goldendb.py`

### Migration 补丁

| 文件路径 | 说明 |
|----------|------|
| `migrate_patch/patches/goldendb/alerts/0001_initial.py` | 跳过 GinIndex/BTreeIndex |
| `migrate_patch/patches/goldendb/alerts/0005_*.py` | 跳过重复 ForeignKey 索引 |
| `migrate_patch/patches/goldendb/alerts/0010_*.py` | 跳过 RemoveIndex/AddIndex on JSONField |

## 验证

```bash
cd server && python manage.py migrate
```
