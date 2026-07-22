# OceanBase 适配规格

Status: cancelled

## Migration Context

非标准旧 artifact，原路径为 `openspec/changes/db-xinchuang-adapter/specs/oceanbase.md`。完整内容保留如下。

## 概述

OceanBase 兼容 MySQL 协议，但在索引、字段变更等方面有特殊限制。

## 数据库配置

```python
# config/components/database.py
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
```

## 不支持的操作

| 操作 | 错误码 | 解决方案 |
|------|--------|----------|
| JSON 列索引 | 3152 | `FakeAddIndex` 跳过 |
| ALTER 非字符串类型字段 | 1235 | `FakeAlterField` 跳过 |
| 删除 rowkey 列 | 1235 | `FakeRemoveField` 跳过 |
| 删除不存在的约束 | 1091 | `FakeRemoveConstraint` 跳过 |

## 已创建的补丁文件

### ORM 补丁
- `apps/core/db_patches/oceanbase.py`

### Migration 补丁

| 文件路径 | 说明 |
|----------|------|
| `migrate_patch/patches/oceanbase/alerts/0001_initial.py` | GinIndex/BTreeIndex → models.Index |
| `migrate_patch/patches/oceanbase/alerts/0005_*.py` | FakeAddIndex + FakeAlterField |
| `migrate_patch/patches/oceanbase/alerts/0010_*.py` | FakeRemoveIndex 跳过删除 |
| `migrate_patch/patches/oceanbase/log/0003_*.py` | EventRawData.data 直接定义为 S3JSONField |
| `migrate_patch/patches/oceanbase/log/0004_*.py` | FakeAlterField 跳过 |
| `migrate_patch/patches/oceanbase/log/0009_*.py` | FakeAlterField 跳过 |
| `migrate_patch/patches/oceanbase/mlops/0021_*.py` | TimeSeriesPredictTrainData 直接定义最终类型 |
| `migrate_patch/patches/oceanbase/mlops/0027_*.py` | ImageClassificationTrainData 直接定义最终类型 |
| `migrate_patch/patches/oceanbase/mlops/0032_*.py` | FakeAlterField 跳过 |
| `migrate_patch/patches/oceanbase/mlops/0036-0039_*.py` | FakeAlterField 跳过 |
| `migrate_patch/patches/oceanbase/operation_analysis/0003_*.py` | FakeRemoveConstraint 跳过 |
| `migrate_patch/patches/oceanbase/operation_analysis/0004_*.py` | FakeRemoveConstraint 跳过 |

## 验证

```bash
cd server && python manage.py migrate
```
