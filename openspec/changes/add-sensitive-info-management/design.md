## Context

当前 `add-sensitive-info-management` change 相关代码已经形成“社区版数据 + 商业版增强”的混合落点，但新的设计目标更收敛：社区版只保留敏感信息能力所需的数据基座，不再承载敏感信息管理的功能层实现；商业版承载面向管理员和业务页面的后端/前端功能面，同时保证社区版在没有 enterprise 模块时仍可正常运行。

后端已确认的基础事实是：`User.phone`、`SensitiveInfoAuthorization`、`SystemSettings` 配置项都位于社区版数据模型范围；而当前 `urls.py`、`viewset/__init__.py`、`sensitive_info_authorization_viewset.py`、`sensitive_info_authorization_serializer.py` 仍存在社区版功能层落点。前端已确认的基础事实是：商业版通过 `web/manifests/menus.json`、`web/manifests/routes.json`、敏感信息页面/API/EE hook 承载功能面，社区版通过 `prepare-enterprise`、`enterpriseStub.ts`、`(enterprise)` 命名空间 fallback 机制保持可构建、可运行。

因此，本次设计不是描述“当前代码已经完全满足的边界”，而是明确后续实现应收敛到的目标边界，并把社区版兼容性规则写清楚。

## Goals / Non-Goals

**Goals:**
- 将社区版边界收敛为敏感信息能力的数据基座，只保留模型、migrations、默认配置和值域语义。
- 将敏感信息管理的后端功能面收敛到商业版，包括 serializers、viewsets、urls、授权查询接口、授权审计与脱敏服务。
- 将敏感信息管理的前端功能面收敛到商业版，包括菜单、路由、页面、API 与 EE override hook。
- 保证社区版在没有 enterprise 模块时仍能正常启动、构建和运行，不因敏感信息管理功能缺席而产生导入或路由错误。
- 保持手机号作为社区版用户基础资料字段的维护能力，同时让商业版在此基础上叠加展示控制与 overwrite 交互。

**Non-Goals:**
- 不新建独立 app，也不改变现有 `system_mgmt` 作为数据基座的归属。
- 不把“敏感信息”菜单直接写入社区版静态菜单源。
- 不让社区版单独提供敏感信息管理页面、授权 CRUD 接口或 `current_user` 授权查询接口。
- 不因为缺少敏感信息查看授权而引入新的写侧拒绝逻辑；显式新值更新语义保持不变。
- 不在本次设计中扩展到 alerts、通知、RPC 或更广泛的自动化链路责任边界。

## Decisions

### 1. 社区版只承载数据基座，不承载敏感信息管理功能面
- **Decision**: 社区版仅保留 `User.phone`、`SensitiveInfoAuthorization` 相关模型/migrations、`SystemSettings` 中的敏感信息配置数据承载与默认值语义，以及基础用户资料读写所需的共享能力。
- **Why**: 这满足“模型留在 CE”的边界，同时避免社区版继续对敏感信息管理功能层承担长期责任。

### 2. 商业版承载敏感信息管理的后端功能面
- **Decision**: 敏感信息管理的 serializer、viewset、url 注册、`current_user` 授权查询接口、授权记录操作日志，以及人类界面查询出口的脱敏控制服务都属于商业版功能面。
- **Why**: 这些能力共同构成“敏感信息管理”这一功能，而不仅仅是数据持久化；它们应与 enterprise 授权与展示控制一起收敛在商业版。

### 3. 社区版通过可选装配点兼容商业版，而不是反向依赖商业版
- **Decision**: 后端需要以可选导入、条件注册或等价的延迟装配方式接入商业版能力，使 `urls.py`、`viewset/__init__.py`、用户查询链路在无 enterprise 时不会因硬导入而失败；前端继续使用 `prepare-enterprise`、`(enterprise)` 命名空间、manifest、shim/junction 和 `enterpriseStub.ts` fallback 模式保持兼容。
- **Why**: 这是保证社区版可单独运行的核心兼容性约束，也是现有前端模式已经证明可行的方向。目标边界是“CE 提供扩展点，EE 挂载功能”，而不是“CE 在启动时必须成功导入 EE 代码”。

### 4. 手机号基础资料能力仍属于社区版用户管理范畴
- **Decision**: `phone` 继续作为社区版用户基础资料字段存在于用户新增、编辑、详情、列表等基础契约中；商业版只在这些基础契约之上叠加敏感信息展示控制与编辑态保护语义。
- **Why**: 手机号字段本身不是企业专属功能，而是基础资料数据；将其留在社区版能避免 schema 与基础用户管理能力分裂。

### 5. 前端共享基础态留在社区版，敏感信息功能态收敛到商业版
- **Decision**: 社区版仅保留基础表单、手机号展示、plain-mode `useSensitiveFieldEditBehavior` 等共享底座；敏感信息页面、API、菜单/路由注入、基于授权与全局配置决定 `plain/overwrite` 的 EE hook 由商业版承载。
- **Why**: 前端当前已经具备明确的 enterprise seam。共享基础态留在社区版可以保持用户编辑弹窗在无 EE 时正常工作，而敏感信息管理本身则完全由 EE 提供。

### 6. 保护语义仍聚焦展示控制与防误覆盖
- **Decision**: 商业版对已接入的人类界面用户查询出口执行脱敏控制；未接入展示控制的机器消费路径继续保持原值能力。编辑用户时，受保护且未授权查看的敏感字段进入 overwrite 模式，但显式确认的新值仍允许更新。
- **Why**: 这保持了当前能力的业务边界：控制展示与误覆盖风险，而不是把“无查看权限”升级为“无写入权限”。

## Risks / Trade-offs

- **[当前代码与目标边界暂时不一致]** → 目前部分 serializer/viewset/url 仍在社区版；本次文档更新描述的是目标边界，后续仍需代码迁移才能完全对齐。
- **[社区版存在硬导入风险点]** → `server/apps/system_mgmt/urls.py` 与 `server/apps/system_mgmt/viewset/__init__.py` 目前若继续直接导入敏感信息管理 viewset，会阻碍 CE-only 运行；实现阶段必须优先处理这些装配点。
- **[后端扩展点收敛需要避免破坏已有查询链路]** → 敏感字段展示控制最终应由商业版服务承载，但接入方式必须维持用户查询链路在无 EE 时安全退化。
- **[前端 generated shim 与 manifest 需要持续同步]** → 页面/API/hook 若与 `prepare-enterprise` 的生成规则不一致，容易造成 CE 构建可过但运行时行为偏差。
- **[验证范围需要继续聚焦]** → 当前设计明确不把 alerts、通知、RPC、自动化链路纳入本次责任边界，避免再次把 change 拉回过宽范围。

## Migration Plan

- 继续保留已经落地的社区版 schema：`User.phone` migration、`SensitiveInfoAuthorization` migration、`SystemSettings` 默认配置数据承载。
- 后续实现阶段将敏感信息管理 serializer、viewset、url 注册、`current_user` 授权接口和脱敏服务迁入商业版目录，并让社区版改为通过可选装配点消费这些能力。
- 前端继续沿用现有 enterprise seam：商业版提供 manifests、页面、API、EE hook；社区版保留共享基础代码和 fallback，不直接承载敏感信息页面业务。
- 回滚或禁用商业版能力时，保留社区版数据基座与基础用户资料能力即可；在无 enterprise 情况下，敏感信息菜单、页面与 API 不出现，用户编辑弹窗回退为 plain 模式。

## Open Questions

- 后续代码迁移时，商业版脱敏服务的最终承载路径应继续复用现有命名，还是顺势调整为更清晰的 enterprise service 命名，需要在实现阶段结合仓库结构再定。
