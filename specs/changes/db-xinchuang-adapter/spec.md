# Db Xinchuang Adapter

Status: draft

## Migration Context

- Legacy source: `openspec/changes/db-xinchuang-adapter/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

BK-Lite 需要支持国产信创数据库（达梦、GaussDB、OceanBase、GoldenDB 等），这些数据库与 PostgreSQL/MySQL 存在兼容性差异，特别是在 Migration 执行时会遇到不支持的索引类型、字段类型变更等问题。

## What Changes

建立统一的数据库信创适配框架：
- ORM 补丁层：`apps/core/db_patches/{db_engine}.py`
- Migration 补丁层：`migrate_patch/patches/{db_engine}/{app_label}/{migration_name}.py`
- 数据库配置：`config/components/database.py`

## Capabilities

### 已支持的数据库

| 数据库 | ENGINE | 状态 |
|--------|--------|------|
| PostgreSQL | `django.db.backends.postgresql` | ✅ 原生支持 |
| MySQL | `django.db.backends.mysql` | ✅ 原生支持 |
| SQLite | `django.db.backends.sqlite3` | ✅ 原生支持 |
| 达梦 (DM) | `cw_cornerstone.db.dameng.backend` | ✅ 已适配 |
| GaussDB | `cw_cornerstone.db.gaussdb.backend` | ✅ 已适配 |
| OceanBase | `cw_cornerstone.db.oceanbase.backend` | ✅ 已适配 |
| GoldenDB | `cw_cornerstone.db.goldendb.backend` | ✅ 已适配 |

### 补丁加载机制

Migration 补丁通过 `cw_cornerstone.migrate_patch` 自动加载，在 `pre_migrate` 信号时替换原始 migration 的 operations。

## Impact

**代码目录结构:**
```
server/
├── apps/core/db_patches/
│   ├── __init__.py          # 数据库引擎到补丁模块的映射
│   ├── dameng.py             # 达梦 ORM 补丁
│   ├── gaussdb.py            # GaussDB ORM 补丁
│   ├── goldendb.py           # GoldenDB ORM 补丁
│   └── oceanbase.py          # OceanBase ORM 补丁
├── migrate_patch/patches/
│   ├── dameng/               # 达梦 Migration 补丁
│   ├── gaussdb/              # GaussDB Migration 补丁
│   ├── goldendb/             # GoldenDB Migration 补丁
│   └── oceanbase/            # OceanBase Migration 补丁
└── config/components/
    └── database.py           # 数据库配置（DB_ENGINE 环境变量）
```

**环境变量:**
- `DB_ENGINE`: 数据库类型（postgresql/mysql/sqlite/dameng/gaussdb/oceanbase/goldendb）
- `DB_NAME`: 数据库名
- `DB_USER`: 用户名
- `DB_PASSWORD`: 密码
- `DB_HOST`: 主机地址
- `DB_PORT`: 端口号

## Implementation Decisions

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                      Django ORM Layer                        │
├─────────────────────────────────────────────────────────────┤
│                   apps/core/db_patches/                      │
│    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│    │  dameng  │ │ gaussdb  │ │oceanbase │ │ goldendb │      │
│    └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
├─────────────────────────────────────────────────────────────┤
│                  migrate_patch/patches/                      │
│    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│    │  dameng  │ │ gaussdb  │ │oceanbase │ │ goldendb │      │
│    └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
├─────────────────────────────────────────────────────────────┤
│               cw_cornerstone.db.{engine}.backend             │
│    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│    │  dameng  │ │ gaussdb  │ │oceanbase │ │ goldendb │      │
│    └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
├─────────────────────────────────────────────────────────────┤
│                    Database Drivers                          │
│    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│    │   dmPy   │ │  psycopg │ │  pymysql │ │  pymysql │      │
│    └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## 补丁类型

### 1. Fake 操作类

用于跳过不支持的 Migration 操作：

```python
class FakeAddIndex(migrations.AddIndex):
    """跳过不支持的索引创建"""
    def database_forwards(self, *args, **kwargs):
        pass
    def database_backwards(self, *args, **kwargs):
        pass

class FakeRemoveIndex(migrations.RemoveIndex):
    """跳过不存在的索引删除"""
    def database_forwards(self, *args, **kwargs):
        pass
    def database_backwards(self, *args, **kwargs):
        pass

class FakeAlterField(migrations.AlterField):
    """跳过不支持的字段类型变更"""
    def database_forwards(self, *args, **kwargs):
        pass
    def database_backwards(self, *args, **kwargs):
        pass

class FakeRemoveField(migrations.RemoveField):
    """跳过不支持的字段删除（如 rowkey 列）"""
    def database_forwards(self, *args, **kwargs):
        pass
    def database_backwards(self, *args, **kwargs):
        pass

class FakeRemoveConstraint(migrations.RemoveConstraint):
    """跳过不存在的约束删除"""
    def database_forwards(self, *args, **kwargs):
        pass
    def database_backwards(self, *args, **kwargs):
        pass
```

### 2. 初始 Migration 修改

在 `0001_initial.py` 补丁中直接定义最终字段类型，避免后续 AlterField：

```python
# 原始定义
("description", models.TextField(...))
# 后续有 AlterField 改为 JSONField

# 补丁中直接定义
("description", models.JSONField(blank=True, default=dict, help_text="规则描述", null=True))
```

## 各数据库不支持的特性

### GaussDB (ustore)

| 问题 | 错误信息 | 解决方案 |
|------|----------|----------|
| GIN 索引 | `gin index is not supported for ustore` | `FakeAddIndex` |
| jsonb ubtree 索引 | `data type jsonb has no default operator class for access method "ubtree"` | `FakeAddIndex` |
| BTreeIndex 重复 | 与 `db_index=True` 重复 | `FakeAddIndex` |

### OceanBase

| 问题 | 错误信息 | 解决方案 |
|------|----------|----------|
| JSON 列索引 | 错误码 3152 | `FakeAddIndex` |
| ALTER 非字符串类型 | 错误码 1235 | `FakeAlterField` |
| 删除 rowkey 列 | 错误码 1235 | `FakeRemoveField` |
| 删除不存在约束 | 错误码 1091 | `FakeRemoveConstraint` |

### GoldenDB

| 问题 | 错误信息 | 解决方案 |
|------|----------|----------|
| GinIndex | 不支持 | `FakeAddIndex` |
| BTreeIndex | 不支持 | `FakeAddIndex` |
| JSONField 索引 | 不支持 | `FakeAddIndex` |

### 达梦 (DM)

| 问题 | 错误信息 | 解决方案 |
|------|----------|----------|
| 重复索引 | Duplicate key name | `FakeAddIndex` |
| GinIndex/BTreeIndex | 不支持 | `FakeAddIndex` |

## 新增数据库适配流程

1. **创建 ORM 补丁**
   ```
   apps/core/db_patches/{new_db}.py
   ```

2. **注册补丁映射**
   ```python
   # apps/core/db_patches/__init__.py
   DB_PATCHES = {
       "new_db": "apps.core.db_patches.new_db",
   }
   ```

3. **创建 Migration 补丁目录**
   ```
   migrate_patch/patches/{new_db}/
   migrate_patch/patches/{new_db}/__init__.py
   ```

4. **为有问题的 app 创建补丁**
   ```
   migrate_patch/patches/{new_db}/{app_label}/__init__.py
   migrate_patch/patches/{new_db}/{app_label}/{migration_name}.py
   ```

5. **添加数据库配置**
   ```python
   # config/components/database.py
   elif db_engine == "new_db":
       DATABASES = {
           "default": {
               "ENGINE": "cw_cornerstone.db.new_db.backend",
               ...
           }
       }
   ```

## 补丁文件模板

```python
# {DB_NAME} 数据库兼容补丁
# 原始文件: apps/{app_label}/migrations/{migration_name}.py
# 问题: [描述问题]
# 处理策略: [描述解决方案]

from django.db import migrations, models


class FakeAddIndex(migrations.AddIndex):
    """跳过不支持的索引"""
    def database_forwards(self, *args, **kwargs):
        pass
    def database_backwards(self, *args, **kwargs):
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("{app_label}", "{previous_migration}"),
    ]

    operations = [
        # ... 复制原始 operations，将不支持的替换为 Fake 类
    ]
```

## 验证命令

```bash
# 检查 migration 计划
python manage.py migrate --plan

# 执行 migration
python manage.py migrate

# 语法验证
python -m py_compile migrate_patch/patches/{db}/{app}/{migration}.py
```

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-03-03
```
