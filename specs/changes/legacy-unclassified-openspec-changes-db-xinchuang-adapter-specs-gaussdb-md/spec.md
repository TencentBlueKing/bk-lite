# GaussDB 适配规格

Status: cancelled

## Migration Context

非标准旧 artifact，原路径为 `openspec/changes/db-xinchuang-adapter/specs/gaussdb.md`。完整内容保留如下。

## 概述

GaussDB 基于 PostgreSQL 协议，但 ustore 存储引擎不支持部分 PostgreSQL 专属特性。

## 数据库配置

```python
# config/components/database.py
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
```

## 不支持的操作

| 操作 | 错误信息 | 解决方案 |
|------|----------|----------|
| GIN 索引 | `gin index is not supported for ustore` | `FakeAddIndex` 跳过 |
| jsonb ubtree 索引 | `data type jsonb has no default operator class for access method "ubtree"` | `FakeAddIndex` 跳过 |
| BTreeIndex on datetime | 与 `db_index=True` 重复 | `FakeAddIndex` 跳过 |
| RemoveIndex 不存在的索引 | 索引在补丁中未创建 | `FakeRemoveIndex` 跳过 |
| TextField → JSONField | 类型变更可能不支持 | `FakeAlterField` 跳过 |

## 已创建的补丁文件

### ORM 补丁
- `apps/core/db_patches/gaussdb.py`

### Migration 补丁

| 文件 | 说明 |
|------|------|
| `migrate_patch/patches/gaussdb/__init__.py` | 补丁目录 |
| `migrate_patch/patches/gaussdb/alerts/__init__.py` | alerts 模块 |
| `migrate_patch/patches/gaussdb/alerts/0001_initial.py` | 跳过 GinIndex/BTreeIndex |
| `migrate_patch/patches/gaussdb/alerts/0005_sessioneventrelation_aggregationrules_image_and_more.py` | 跳过重复索引 + AlterField |
| `migrate_patch/patches/gaussdb/alerts/0010_remove_alert_alert_created_btree_and_more.py` | 跳过 JSONField 索引操作 |

## 跳过的索引清单

### 0001_initial.py
- `incident_created_btree` - BTreeIndex on datetime
- `incident_operator_gin` - GinIndex on JSONField
- `event_labels_gin` - GinIndex on JSONField
- `alert_created_btree` - BTreeIndex on datetime
- `alert_operator_gin` - GinIndex on JSONField

### 0005_*.py
- `alerts_sess_event_i_5ab59a_idx` - ForeignKey 重复索引
- `aggregationrules.description` AlterField (在 0001 中直接定义为 JSONField)

### 0010_*.py
- 所有 RemoveIndex 操作（索引在 0001 补丁中未创建）
- `alert_operator_gin` - Index on JSONField
- `event_labels_gin` - Index on JSONField
- `incident_operator_gin` - Index on JSONField

## 验证

```bash
cd server && python manage.py migrate
```
