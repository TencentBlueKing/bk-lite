## 1. 后端 — AppSerializer 创建角色

- [x] 1.1 在 `AppSerializer.create()` 中引入 `transaction.atomic`，保证 App 和 Role 同事务写入
- [x] 1.2 在 `AppSerializer.create()` 中调用 `Role.objects.get_or_create(name='user', app=validated_data['name'])` 创建外部应用的 user 角色

## 2. 后端 — AppViewSet 级联删除角色

- [x] 2.1 在 `AppViewSet.destroy()` 中，于父类 `destroy()` 调用前执行 `Role.objects.filter(app=obj.name).delete()`，级联清理角色数据

## 3. 后端 — get_role_tree 去除 is_build_in 过滤

- [x] 3.1 在 `RoleViewSet.get_role_tree()` 中，将 `client_list = [i for i in ... if i.get("is_build_in")]` 改为接受所有应用（移除 `is_build_in` 过滤条件）

## 4. 验证

- [x] 4.1 创建外部应用后，确认 Role 表中存在对应 `user` 角色记录
- [x] 4.2 调用 `get_role_tree` API，确认响应中包含外部应用的角色节点
- [x] 4.3 为组织分配外部应用 `user` 角色后，组织内用户登录可在 ops-console 和应用切换列表看到该应用
- [x] 4.4 删除外部应用后，确认对应 Role 记录被清除
