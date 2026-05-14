## 1. 社区版数据基座与基础资料能力

- [x] 1.1 在 `server/apps/system_mgmt/models/user.py` 中新增 `phone` 字段，并创建对应 migration。
- [x] 1.2 调整社区版用户新增、编辑、详情、列表相关后端链路，使手机号作为基础资料字段可被保存、更新和返回。
- [x] 1.3 调整社区版用户管理前端表单、类型与基础展示链路，支持手工维护手机号字段。
- [x] 1.4 收紧公开用户序列化字段白名单，避免 `UserSerializer` 在引入手机号后继续扩大公开暴露面。
- [x] 1.5 在社区版 `system_mgmt` 中新增 `SensitiveInfoAuthorization` 数据模型及其 migration，并为 `SystemSettings` 补齐敏感信息配置数据承载与默认值。

## 2. 商业版后端敏感信息管理功能面

- [x] 2.1 将敏感信息管理相关 serializer、viewset、url 注册与 `current_user` 授权查询接口迁入 enterprise 承载。
- [x] 2.2 在商业版中承载授权记录的新增/删除审计日志，并保持基于 `SensitiveInfoAuthorization` 数据模型的读写语义不变。
- [x] 2.3 将敏感字段展示控制与授权判定服务收敛到商业版后端能力，并通过可选装配方式接入现有用户查询出口。
- [x] 2.4 确保社区版无 enterprise 时不会因 `urls.py`、`viewset/__init__.py` 或查询链路中的硬导入而启动失败。

## 3. 商业版前端敏感信息管理功能面

- [x] 3.1 保持“安全管理 / 敏感信息”菜单与页面入口由商业版 `web/manifests/menus.json`、`web/manifests/routes.json` 承载。
- [x] 3.2 将敏感信息页面、页面 API、授权管理交互与 EE override hook 统一收敛在商业版目录中。
- [x] 3.3 保持社区版只承载手机号基础资料展示、共享表单与 plain-mode 基础 hook，不直接承载敏感信息页面业务。
- [x] 3.4 确保 `prepare-enterprise`、`(enterprise)` 命名空间、shim/junction 与 `enterpriseStub.ts` fallback 仍可支撑 CE-only 构建与运行。

## 4. 展示控制与编辑保护语义

- [x] 4.1 在商业版已接入的人类界面用户查询出口继续对邮箱/手机号按全局配置与授权关系返回脱敏值或明文。
- [x] 4.2 保持超级管理员无天然豁免，仅在授权命中对应敏感类型时返回明文。
- [x] 4.3 保持未接入展示控制的机器消费路径原值读取能力，不把本次责任范围扩展到 alerts、通知、RPC 与自动化链路。
- [x] 4.4 继续保留编辑用户时的 overwrite 语义：编辑中阻止提交、未确认字段不写回、显式新值允许更新；无 enterprise 时回退为 plain 模式。

## 5. 兼容性与验证

- [x] 5.1 已完成 OpenSpec 边界改写：明确社区版只保留数据基座，商业版承载敏感信息管理功能面。
- [x] 5.2 验证社区版无 enterprise 时不暴露敏感信息菜单、页面与 API，且后端启动、前端构建与基础用户管理流程保持正常。
- [x] 5.3 验证商业版启用后，菜单 patch、route shim、页面/API/EE hook、后端授权接口与脱敏控制可按新边界协同工作。
- [x] 5.4 复核所有实现与测试证据均符合新的 CE/EE 边界，不再把超出本次责任范围的链路计入完成标准。
