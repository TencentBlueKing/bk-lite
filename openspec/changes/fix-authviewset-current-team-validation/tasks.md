## 1. 添加依赖导入

- [x] 1.1 在 `server/apps/core/utils/viewset_utils.py` 中添加 `from rest_framework.exceptions import PermissionDenied` 导入

## 2. 实现验证逻辑

- [x] 2.1 在 `GenericViewSetFun.filter_by_group()` 方法中，`current_team = cls._parse_current_team_cookie(request)` 之后添加验证逻辑
- [x] 2.2 验证逻辑：如果 `user.is_superuser` 为 False，则检查 `current_team` 是否在 `user.group_list` 的 id 集合中
- [x] 2.3 验证失败时抛出 `PermissionDenied("无权访问该团队")`

## 3. 验证

- [x] 3.1 运行 `make test` 确保现有测试通过
- [x] 3.2 手动验证：正常用户访问自己团队的数据应正常返回
- [x] 3.3 手动验证：伪造 current_team cookie 应返回 403
