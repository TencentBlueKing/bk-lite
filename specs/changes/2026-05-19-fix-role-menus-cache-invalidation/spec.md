# Proposal: 修复 set_role_menus 接口未正确清除用户菜单缓存

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-19-fix-role-menus-cache-invalidation/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

调用 `system_mgmt/role/set_role_menus/` 接口更新角色菜单权限后，用户的菜单缓存 `menus-user:{user_id}` 没有被正确清除，导致用户调用接口时仍然使用旧的权限数据，报错无权限。

**根因**: `RoleManage.get_cache_keys()` 方法使用 SQL 查询 `django_cache` 表获取缓存键，但当使用 Redis 缓存后端时，该表不存在或为空，导致返回空列表，缓存无法被清除。

## What Changes

### 1. 修改 `set_role_menus` 缓存清除逻辑

**文件**: `server/apps/system_mgmt/viewset/role_viewset.py`

将 SQL 查询方式改为直接构造缓存键：

```python
# 修改前 (有问题)
cache_key = f"all_menus_{role_obj.app}"
keys = RoleManage.get_cache_keys(cache_key)
user_menu_cache = "menus-user:"
keys.extend(RoleManage.get_cache_keys(user_menu_cache))
cache.delete_many(keys)

# 修改后 (兼容 Redis)
affected_users = User.objects.filter(role_list__contains=int(role_id))
menu_cache_keys = [f"menus-user:{user.id}" for user in affected_users]
if menu_cache_keys:
    cache.delete_many(menu_cache_keys)
```

### 2. 删除废弃的 `get_cache_keys` 方法

**文件**: `server/apps/system_mgmt/services/role_manage.py`

删除仅在 `set_role_menus` 中使用的 `get_cache_keys` 方法，避免未来误用。

## 根因分析

### 缓存流程

```
verify_token (nats_api.py:221)
    │
    ├── cache.get(f"menus-user:{user.id}")  ← 读取用户菜单缓存
    │
    └── 如果缓存不存在，从数据库查询并缓存 60 秒
        cache.set(f"menus-user:{user.id}", menus, 60)
```

### 当前清除逻辑 (有问题)

`set_role_menus` (role_viewset.py:227-231) 尝试清除缓存：

```python
cache_key = f"all_menus_{role_obj.app}"
keys = RoleManage.get_cache_keys(cache_key)
user_menu_cache = "menus-user:"
keys.extend(RoleManage.get_cache_keys(user_menu_cache))  # ❌ 问题在这里
cache.delete_many(keys)
```

### 问题根因

`RoleManage.get_cache_keys()` 的实现 (role_manage.py:63-66)：

```python
@staticmethod
def get_cache_keys(cache_key):
    sql = "select * from django_cache where cache_key like %(key)s"
    data = SQLExecute.execute_sql(sql, {"key": f"%{cache_key}%"})
    return [i["cache_key"].split(":", 3)[-1] for i in data]
```

**这个方法查询 `django_cache` 表，只在使用数据库缓存后端时有效。**

当配置了 `REDIS_CACHE_URL` 使用 Redis 缓存时 (cache.py:22-23)，`django_cache` 表是空的，`get_cache_keys()` 返回空列表，缓存不会被清除。

### 对比正确做法

其他地方清除 `menus-user:` 缓存的方式：

```python
# user_viewset.py:399-400 ✅
menu_cache_keys = [f"menus-user:{user['id']}" for user in user_info_list]

# user_viewset.py:472-473 ✅
cache.delete(f"menus-user:{pk}")

# group_viewset.py:245 ✅
menu_cache_keys = [f"menus-user:{user['id']}" for user in affected_users_list]
```

它们直接构造缓存键，不依赖 `RoleManage.get_cache_keys()`。

## 修复方案

修改 `set_role_menus` 方法，直接构造受影响用户的菜单缓存键并删除：

```python
# 获取受影响用户的 ID 列表
affected_user_ids = User.objects.filter(role_list__contains=int(role_id)).values_list("id", flat=True)

# 直接构造缓存键并删除
menu_cache_keys = [f"menus-user:{uid}" for uid in affected_user_ids]
if menu_cache_keys:
    cache.delete_many(menu_cache_keys)
```

## 影响范围

### 需要修改的文件

| 文件 | 修改内容 |
|------|---------|
| `server/apps/system_mgmt/viewset/role_viewset.py` | 修改 `set_role_menus` 方法的缓存清除逻辑 |
| `server/apps/system_mgmt/services/role_manage.py` | 删除或标记废弃 `get_cache_keys` 方法 |

### 调查结论

经过全面搜索，`RoleManage.get_cache_keys()` 方法**仅在 `set_role_menus` 一处被调用**，没有其他地方使用这个有问题的方法。

### 风险评估

- 风险：低，仅修改缓存清除逻辑，不影响业务数据
- `get_cache_keys` 方法可以安全删除，因为没有其他调用者

## 验证方式

1. 使用 Redis 缓存后端
2. 用户 A 登录系统，触发 `verify_token` 缓存菜单权限
3. 管理员调用 `set_role_menus` 修改用户 A 所属角色的菜单权限
4. 用户 A 再次请求，验证新权限生效

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-19
```

## Work Checklist

## Task 1: 修改 set_role_menus 方法的缓存清除逻辑

**文件**: `server/apps/system_mgmt/viewset/role_viewset.py`

**当前代码** (行 227-231):
```python
cache_key = f"all_menus_{role_obj.app}"
keys = RoleManage.get_cache_keys(cache_key)
user_menu_cache = "menus-user:"
keys.extend(RoleManage.get_cache_keys(user_menu_cache))
cache.delete_many(keys)
```

**修改为**:
```python
# 获取受影响用户的 ID 列表
affected_user_ids = User.objects.filter(role_list__contains=int(role_id)).values_list("id", flat=True)

# 直接构造缓存键并删除 (兼容 Redis 缓存后端)
menu_cache_keys = [f"menus-user:{uid}" for uid in affected_user_ids]
if menu_cache_keys:
    cache.delete_many(menu_cache_keys)
```

**说明**:
- 移除对 `RoleManage.get_cache_keys()` 的调用
- 移除 `all_menus_{app}` 缓存清除（代码中未找到设置此缓存的地方，可能是遗留代码）
- 直接构造 `menus-user:{user_id}` 缓存键，与 `user_viewset.py` 和 `group_viewset.py` 的做法保持一致

**验收标准**:
- [x] 使用 Redis 缓存后端时，`menus-user:{user_id}` 缓存能被正确清除
- [x] 代码风格与现有代码保持一致

---

## Task 2: 删除废弃的 get_cache_keys 方法

**文件**: `server/apps/system_mgmt/services/role_manage.py`

**删除代码** (行 62-66):
```python
@staticmethod
def get_cache_keys(cache_key):
    sql = "select * from django_cache where cache_key like %(key)s"
    data = SQLExecute.execute_sql(sql, {"key": f"%{cache_key}%"})
    return [i["cache_key"].split(":", 3)[-1] for i in data]
```

**说明**:
- 此方法仅在 `set_role_menus` 中被调用，Task 1 完成后将无调用者
- 此方法使用 SQL 查询 `django_cache` 表，在 Redis 缓存后端下无法工作
- 删除此方法可避免未来误用

**验收标准**:
- [x] 方法已删除
- [x] 无其他代码引用此方法（已确认仅 `set_role_menus` 调用）

---

## Task 3: 清理 role_viewset.py 中不再需要的导入

**文件**: `server/apps/system_mgmt/viewset/role_viewset.py`

**检查**: 完成 Task 1 后，检查 `RoleManage` 是否还有其他用途。

当前 `RoleManage` 的使用情况:
- 行 74: `RoleManage().get_all_menus(...)` - 仍在使用
- 行 228, 230: `RoleManage.get_cache_keys(...)` - Task 1 会移除

**结论**: `RoleManage` 仍有其他用途，保留导入。

**验收标准**:
- [x] 确认 `RoleManage` 导入保留（因为 `get_all_menus` 仍在使用）
