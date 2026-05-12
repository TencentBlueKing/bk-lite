## 1. 添加依赖导入

- [x] 1.1 在 `server/apps/core/utils/viewset_utils.py` 中添加 `from rest_framework.exceptions import PermissionDenied` 导入

## 2. 实现 AuthViewSet 验证逻辑

- [x] 2.1 在 `GenericViewSetFun.filter_by_group()` 方法中，`current_team = cls._parse_current_team_cookie(request)` 之后添加验证逻辑
- [x] 2.2 验证逻辑：如果 `user.is_superuser` 为 False，则检查 `current_team` 是否在 `user.group_list` 的 id 集合中
- [x] 2.3 验证失败时抛出 `PermissionDenied("无权访问该团队")`
- [x] 2.4 在 `AuthViewSet` 中添加 `_validate_current_team_permission()` 方法，供子类调用

## 3. opspilot 模块权限修复

- [x] 3.1 创建 `server/apps/opspilot/utils/team_permission_mixin.py` - TeamPermissionMixin
- [x] 3.2 创建 `server/apps/opspilot/utils/vendor_model_mixin.py` - VendorModelMixin
- [x] 3.3 修改 KnowledgeBaseViewSet, KnowledgeDocumentViewSet 添加 current_team 验证
- [x] 3.4 修改 FileKnowledgeViewSet, ManualKnowledgeViewSet, WebPageKnowledgeViewSet 添加 current_team 验证
- [x] 3.5 修改 QAPairsViewSet, KnowledgeGraphViewSet, HistoryViewSet 添加 current_team 验证
- [x] 3.6 修改 BotViewSet, LLMViewSet 添加 current_team 验证
- [x] 3.7 修改 ChatApplicationViewSet, WorkFlowTaskResultViewSet 添加 current_team 验证
- [x] 3.8 修改 EmbedProviderViewSet, RerankProviderViewSet, OCRProviderViewSet, ModelVendorViewSet 添加 current_team 验证

## 4. opspilot 模块添加 @HasPermission 装饰器

- [x] 4.1 WorkFlowTaskResultViewSet 添加 `@HasPermission("bot_conversation_log-View")`
- [x] 4.2 ChatApplicationViewSet 添加 `@HasPermission("bot_list-View")`
- [x] 4.3 BotViewSet list/retrieve 添加 `@HasPermission("bot_list-View")`
- [x] 4.4 ModelVendorViewSet 添加 `@HasPermission("provide_list-View/Add/Setting/Delete")`

## 5. system_mgmt 模块权限修复

- [x] 5.1 在 `server/apps/system_mgmt/utils/group_filter_mixin.py` 添加 GroupPermissionMixin
- [x] 5.2 修改 ChannelViewSet 添加 @HasPermission + 组权限验证
- [x] 5.3 修改 UserViewSet 添加用户过滤和目标用户权限验证
- [x] 5.4 修改 GroupViewSet 添加组权限验证 (get_detail, get_group_detail_with_roles)
- [x] 5.5 修改 GroupDataRuleViewSet 添加组权限验证

## 6. 验证

- [x] 6.1 运行 flake8 检查所有修改文件语法正确
- [x] 6.2 手动验证：opspilot API - 未授权团队返回 403，已授权团队返回 200
- [x] 6.3 手动验证：system_mgmt API - 未授权组返回 403，已授权组返回 200
