# Add Sensitive Info Management

Status: done

## Migration Context

- Legacy source: `openspec/changes/add-sensitive-info-management/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-30
```

## Capability Deltas

### sensitive-info-management

## ADDED Requirements

### Requirement: 社区版必须承载敏感信息能力所需的数据基座
系统 MUST 在社区版 `system_mgmt` 中保留敏感信息能力运行所需的数据基座，包括用户手机号字段、敏感信息保护全局配置以及授权数据模型；这些能力用于支撑商业版功能面，但本身不等价于社区版直接提供敏感信息管理页面或接口。

#### Scenario: 用户模型增加手机号字段
- **WHEN** 系统为用户模型增加手机号字段
- **THEN** 该字段 MUST 定义为可选字符串字段，属性为 `max_length=32`、`null=True`、`blank=True`
- **AND** 该字段 MUST 不设置唯一约束
- **AND** 该字段 MUST 不在模型层强制手机号格式正则校验

#### Scenario: 敏感信息全局配置保存到系统设置
- **WHEN** 系统需要持久化敏感信息保护开关或敏感信息类型
- **THEN** 相关值 MUST 存储在社区版 `SystemSettings` 中作为全局配置项
- **AND** 在无商业版功能面参与时，这些配置 MUST 允许保持默认值而不影响社区版运行

#### Scenario: 授权关系由社区版模型承载
- **WHEN** 系统保存敏感信息授权记录
- **THEN** 授权数据 MUST 存储在社区版 `system_mgmt` 的数据模型中
- **AND** 授权语义 MUST 表示全局“授权用户 + 敏感类型”关系

#### Scenario: 社区版单独运行时不要求暴露敏感信息管理接口
- **WHEN** 社区版在没有 enterprise 模块的情况下单独部署
- **THEN** 系统 MUST 仍可正常启动和运行
- **AND** 社区版 MUST 不要求暴露敏感信息管理页面、授权 CRUD 接口或 `current_user` 授权查询接口

### Requirement: 商业版必须承载敏感信息管理的后端功能面
系统 MUST 在商业版中提供基于 `SystemSettings` 与 `SensitiveInfoAuthorization` 数据基座的敏感信息管理后端能力，包括 serializer、viewset、url 注册、当前用户授权查询接口、授权变更审计，以及人类界面查询出口的展示控制服务。

#### Scenario: 敏感信息管理接口由商业版提供
- **WHEN** 管理员需要读取或保存敏感信息全局配置与授权数据
- **THEN** 对应 serializer、viewset 与 url 注册 MUST 由商业版承载
- **AND** 社区版 MUST 不再把这些接口作为自身长期承诺的能力边界

#### Scenario: 当前用户授权查询接口由商业版提供
- **WHEN** 前端需要根据当前请求用户的授权状态决定展示或编辑模式
- **THEN** 系统 MUST 由商业版提供当前用户已授权敏感类型的查询接口

#### Scenario: 授权记录新增与删除操作写入操作日志
- **WHEN** 管理员成功新增或删除敏感信息授权记录
- **THEN** 系统 MUST 写入 `system_mgmt.OperationLog`
- **AND** 日志 MUST 记录变更方向、目标用户与敏感类型范围

#### Scenario: 社区版通过可选装配点兼容商业版后端能力
- **WHEN** 社区版运行环境不存在 enterprise 模块
- **THEN** `urls.py`、viewset 导出与用户查询链路 MUST 能安全跳过商业版敏感信息管理装配
- **AND** 系统 MUST 不因硬导入商业版模块而启动失败

### Requirement: 商业版必须通过 enterprise 前端入口提供敏感信息菜单与页面
系统 MUST 通过现有 enterprise manifest、route/shim、命名空间 fallback 机制接入“安全管理 / 敏感信息”菜单与页面；社区版静态菜单源不得直接包含该入口。

#### Scenario: 商业版菜单通过 enterprise manifest 注入
- **WHEN** 商业版启用敏感信息管理菜单
- **THEN** 菜单项 MUST 存放于商业版 `web/manifests/menus.json`
- **AND** 菜单项 MUST 通过 patch 注入到 `security_management` 节点下

#### Scenario: 社区版静态菜单源不直接包含敏感信息入口
- **WHEN** 社区版前端加载 `web/src/app/system-manager/constants/menu.json`
- **THEN** 社区版静态菜单源 MUST 不直接包含“敏感信息”菜单项

#### Scenario: 商业版页面通过 enterprise route 与 generated shim 机制加载
- **WHEN** 用户访问敏感信息管理页面路由
- **THEN** 路由声明 MUST 存放于商业版 `web/manifests/routes.json`
- **AND** 页面实现 MUST 通过现有 enterprise route / generated shim / junction 机制加载，而不是在社区版直接落地页面业务代码

#### Scenario: 社区版在无 enterprise 时回退为安全默认态
- **WHEN** 社区版前端缺少商业版页面、API 或 EE hook
- **THEN** 系统 MUST 仍可完成构建和运行
- **AND** 用户基础表单中的敏感字段编辑行为 MUST 回退为 plain 模式

### Requirement: 商业版必须对已接入的人类界面用户查询出口执行敏感字段展示控制
系统 MUST 在商业版中对当前已接入的人类界面用户查询出口执行邮箱和手机号的脱敏与明文放行控制，同时保持未接入展示控制的机器消费路径不受影响。

#### Scenario: 敏感信息保护关闭时维持现有展示行为
- **WHEN** 全局“启用敏感信息保护”配置为关闭
- **THEN** 已接入的人类界面用户查询结果 MUST 按现有行为返回邮箱和手机号字段值

#### Scenario: 敏感信息保护开启时默认脱敏
- **WHEN** 全局“启用敏感信息保护”配置为开启
- **THEN** 当前已接入的人类界面用户查询出口 MUST 对已纳入敏感信息类型配置的邮箱和手机号执行脱敏展示

#### Scenario: 授权用户可查看对应类型明文
- **WHEN** 当前请求用户已被授权查看某一敏感信息类型
- **THEN** 已接入的人类界面用户查询结果 MUST 仅对该已授权类型返回明文

#### Scenario: 超级管理员不天然豁免
- **WHEN** 当前请求用户是超级管理员但未被授予对应敏感信息类型权限
- **THEN** 系统 MUST 继续返回脱敏后的邮箱或手机号，而不能因超管身份直接返回明文

#### Scenario: 机器消费路径保持原值能力
- **WHEN** 未接入展示脱敏逻辑的机器消费路径读取用户联系方式用于系统动作
- **THEN** 系统 MUST 保持这些路径的原值读取能力
- **AND** 商业版展示脱敏逻辑 MUST 不影响诸如 `get_all_users` 之类机器消费路径的现有行为

### Requirement: 社区版必须提供手机号基础资料维护能力，并在接口层对手机号执行宽松校验
系统 MUST 在社区版用户管理中提供手机号作为基础资料字段的新增、编辑和查询能力，并在接口层对手机号执行宽松校验。

#### Scenario: 新增用户时维护手机号
- **WHEN** 管理员在系统管理新增用户并填写手机号
- **THEN** 社区版用户新增流程 MUST 支持保存手机号字段

#### Scenario: 编辑用户时维护手机号
- **WHEN** 管理员在系统管理编辑现有用户资料并修改手机号
- **THEN** 社区版用户编辑流程 MUST 支持更新手机号字段

#### Scenario: 用户查询结果包含手机号基础字段
- **WHEN** 社区版用户详情或列表接口返回用户基础资料
- **THEN** 系统 MUST 在其基础资料契约中支持手机号字段
- **AND** 商业版可以在此基础上进一步决定该字段返回明文还是脱敏值

#### Scenario: 手机号在接口层采用宽松校验
- **WHEN** 新增或编辑用户提交手机号
- **THEN** 系统 MUST 允许空值直接通过
- **AND** 对非空值 MUST 允许数字、空格、`+`、`-`、`(`、`)` 组成的宽松格式
- **AND** 在移除分隔符后 MUST 以 7~15 位数字作为有效值范围

### Requirement: 未授权查看敏感字段时，编辑用户流程必须采用显式覆盖语义而不是写侧拒绝
系统 MUST 在编辑用户场景中避免因脱敏展示造成误覆盖；当当前用户不能查看明文时，敏感字段修改必须以显式覆盖语义完成，而不能把“无查看权限”等同为“无写入权限”。

#### Scenario: 受保护且未授权的敏感字段进入 overwrite 模式
- **WHEN** 全局敏感信息保护开启、字段类型被纳入保护范围，且当前编辑用户未被授权查看该字段明文
- **THEN** 商业版增强 hook MUST 让用户编辑弹窗中的对应敏感字段进入 overwrite 模式
- **AND** 该字段在进入编辑前 MUST 以只读方式展示

#### Scenario: 用户必须显式确认敏感字段修改
- **WHEN** 用户在 overwrite 模式下点击敏感字段的编辑动作
- **THEN** 系统 MUST 清空当前表单值并等待用户输入新值
- **AND** 系统 MUST 提供确认/取消动作来显式完成或放弃本次修改

#### Scenario: 敏感字段仍处于编辑中时阻止整单提交
- **WHEN** 任一 overwrite 模式的敏感字段仍处于编辑中
- **THEN** 系统 MUST 阻止底部确认提交流程继续执行

#### Scenario: 未显式确认的敏感字段不得覆盖原值
- **WHEN** overwrite 模式下的敏感字段未被显式确认修改
- **THEN** 前端提交 payload MUST 省略该字段
- **AND** 后端更新用户时 MUST 保留原有邮箱/手机号值不变

#### Scenario: 显式提供的新敏感字段值仍允许更新
- **WHEN** 保护开启且当前用户没有对应敏感字段的明文查看授权，但其在 overwrite 模式下显式确认了新的邮箱或手机号
- **THEN** 系统 MUST 允许该新值被保存
- **AND** 系统 MUST 不因为缺少查看权限而额外拒绝这次显式修改

#### Scenario: 无商业版增强 hook 时回退为 plain 模式
- **WHEN** 社区版前端在无 enterprise 模块时打开用户编辑弹窗
- **THEN** 基础 `useSensitiveFieldEditBehavior` MUST 继续以 plain 模式工作
- **AND** 系统 MUST 不因缺少商业版敏感信息功能面而阻断基础用户资料编辑流程

## Work Checklist

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
