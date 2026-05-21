# Tasks: 修复 set_role_menus 缓存清除问题

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
