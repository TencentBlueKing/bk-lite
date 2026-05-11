## Why

系统管理的敏感信息保护能力已经以社区版/商业版分层方式落地，但当前 change 工件仍停留在初始方案表述，与实际代码边界和行为已有明显偏差。当前实现不仅补齐了 `User.phone`、敏感信息授权与全局配置，还落地了商业版脱敏查询控制、敏感信息管理页面，以及用户编辑弹窗中的敏感字段显式覆盖交互。需要将 OpenSpec 内容回写到与现状一致，避免后续实现、验收和归档继续围绕过期方案推进。

## What Changes

- 社区版 `system_mgmt` 已为用户模型新增 `phone` 基础字段，并补齐用户新增、编辑、详情、列表与公开序列化契约。
- 社区版 `system_mgmt` 已新增 `SensitiveInfoAuthorization` 模型、migration、序列化器与 viewset，并在 `SystemSettings` 中承载 `sensitive_info_protection_enabled` / `sensitive_info_types` 两个全局配置项。
- 商业版 `server/apps/system_mgmt/enterprise/sensitive_info.py` 已实现敏感信息授权判定与脱敏逻辑，社区版 `UserViewSet` 通过 enterprise 可选导入将该逻辑接入 `search_user_list`、`get_user_detail`、`user_all` 等面向人类界面的查询出口。
- 商业版前端已通过 `web/manifests/menus.json` 与 `web/manifests/routes.json` 注入“安全管理 / 敏感信息”菜单和页面；社区版前端通过 `prepare-enterprise` 生成的 enterprise shim 页面/API/hook 与共享代码配合运行。
- 用户编辑弹窗已落地敏感字段 overwrite 交互：未授权查看的受保护字段默认只读，点击编辑后清空原值并通过确认/取消显式提交；未修改的敏感字段不会写回，显式新值在保护开启时仍允许更新。

## Capabilities

### New Capabilities
- `sensitive-info-management`: 为系统管理提供手机号基础资料、敏感信息全局配置、授权管理、人类界面查询脱敏控制，以及编辑态敏感字段显式覆盖修改能力。

### Modified Capabilities
- 无。

## Impact

- 后端社区版：`server/apps/system_mgmt/models/user.py`、`SensitiveInfoAuthorization` 相关模型/migrations/serializers/viewset、`SystemSettings` 默认值、`user_viewset.py` 查询与更新语义。
- 后端商业版：`server/apps/system_mgmt/enterprise/sensitive_info.py` 提供授权查询与脱敏服务。
- 前端社区版：用户基础表单、类型和资料展示支持 `phone`；共享 `useSensitiveFieldEditBehavior`、`useUserModalData` 与用户编辑弹窗支持 overwrite 交互；`prepare-enterprise` 生成 enterprise shim 页面/API/hook。
- 前端商业版：`web/manifests/menus.json`、`web/manifests/routes.json`、敏感信息页面、API 与 EE override hook。
- 查询控制面：当前脱敏控制仅作用于已接入的人类界面用户查询出口；机器消费路径保持原值能力，现有代码/测试已覆盖 `get_all_users` 等路径不受影响。
