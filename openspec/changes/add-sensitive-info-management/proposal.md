## Why

`add-sensitive-info-management` 当前工件仍将敏感信息管理描述为“社区版承载基础接口、商业版承载增强能力”的混合边界，但新的目标边界已经明确：社区版只保留数据基座，敏感信息管理的后端功能面和前端功能面都应由商业版承载，同时不能影响社区版单独运行。

这意味着 OpenSpec 需要从“回写现状”改为“校正目标边界”。否则，后续实现仍会继续把 serializer、viewset、url、页面、API、hook 等功能层代码留在社区版，与 open-core 分层目标相冲突，也会让验收与归档继续围绕错误边界进行。

## What Changes

- 社区版 `system_mgmt` 只承载敏感信息能力所需的数据基座：`User.phone`、`SensitiveInfoAuthorization` 相关模型/migrations，以及 `SystemSettings` 中的敏感信息配置项与默认值。
- 商业版承载敏感信息管理的后端功能面，包括基于上述数据基座的 serializers、viewsets、urls、当前用户授权查询接口、授权变更审计，以及脱敏控制服务。
- 商业版前端承载敏感信息管理的功能入口，包括菜单 patch、route manifest、页面源码、API、EE hook；社区版只保留基础用户资料能力与可安全降级的共享 plain-mode 逻辑。
- 社区版与商业版之间继续通过可选导入、条件注册、enterprise shim / manifest / fallback 机制解耦，保证社区版在无 enterprise 依赖时仍可正常启动、构建和运行。

## Capabilities

### New Capabilities
- `sensitive-info-management`: 以“社区版数据基座 + 商业版功能面”的方式提供手机号基础资料、敏感信息全局配置、授权关系管理、敏感字段展示控制，以及编辑态显式覆盖能力。

### Modified Capabilities
- 无。

## Impact

- 后端社区版：保留 `server/apps/system_mgmt/models/user.py`、`SensitiveInfoAuthorization` 相关模型/migrations、`SystemSettings` 中的敏感信息配置数据承载，以及不依赖 enterprise 即可运行的基础用户资料能力。
- 后端商业版：承载敏感信息管理的 serializers、viewsets、urls、`current_user` 授权查询接口、授权审计日志与脱敏控制服务，并通过可选装配方式接入现有用户查询出口。
- 前端社区版：保留手机号基础资料的共享表单/类型/展示能力，以及无 enterprise 时可直接退化为 plain 模式的基础 hook / fallback 结构。
- 前端商业版：承载 `web/manifests/menus.json`、`web/manifests/routes.json`、敏感信息页面、API、EE override hook，并通过现有 `prepare-enterprise` 生成 shim/junction/fallback 机制接入。
- 兼容性：社区版单独部署时不暴露“敏感信息”菜单、页面与 API，也不因缺少 enterprise 模块而在后端导入、前端构建或运行时报错。
