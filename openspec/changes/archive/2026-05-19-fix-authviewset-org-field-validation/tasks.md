## 1. 添加校验方法

- [x] 1.1 在 `AuthViewSet` 类中添加 `_validate_org_field_permission(self, request, org_values)` 方法，校验组织字段是否在用户可管理范围内

## 2. 实现 create 方法

- [x] 2.1 在 `AuthViewSet` 类中添加 `create(self, request, *args, **kwargs)` 方法
- [x] 2.2 在 create 方法中提取并校验组织字段，然后调用 `super().create()`

## 3. 修改 update 方法

- [x] 3.1 在 `AuthViewSet.update` 方法中，计算新增的组织（`new_groups = set(org_values) - set(instance_org_value)`）
- [x] 3.2 对新增的组织调用 `_validate_org_field_permission` 进行校验

## 4. 验证

- [x] 4.1 运行 `server/` 目录下的相关测试，确保现有功能不受影响
- [x] 4.2 检查 LSP 诊断，确保无类型错误
