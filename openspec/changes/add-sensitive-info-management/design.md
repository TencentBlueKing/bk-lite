## Context

当前 `add-sensitive-info-management` change 已在代码中形成明确的社区版/商业版分层实现。社区版仓库 `D:\Work\bk-lite\bk-lite` 负责承载基础数据与共享交互，包括 `User.phone`、`SensitiveInfoAuthorization`、`SystemSettings` 默认值与基础 API 契约，以及用户编辑弹窗的共享 overwrite 状态机；商业版仓库 `D:\Work\bk-lite\WeOpsX-Enterprise` 负责承载脱敏逻辑、enterprise 菜单/路由 manifest、敏感信息页面源码，以及基于全局配置/授权关系的 EE override hook。

后端查询出口的实际接入方式不是新建独立 app，而是由社区版 `server/apps/system_mgmt/viewset/user_viewset.py` 通过可选导入 `apps.system_mgmt.enterprise.sensitive_info` 来应用商业版脱敏逻辑。前端页面的实际接入方式也不是“社区版完全没有商业版代码痕迹”，而是由商业版提供 manifest 与源码，再由 `prepare-enterprise` 在社区版生成 enterprise shim 页面/API/hook 供运行时引用。

现有测试证据集中在 `server/apps/system_mgmt/tests/nats_api_test.py`，已覆盖设置默认值、授权记录 CRUD/current_user、保护关闭时明文、保护开启时未授权超管脱敏、编辑时省略字段不覆盖、保护开启下显式敏感字段仍可更新，以及 `get_all_users` 等机器消费路径保持原值等关键后端场景。

## Goals / Non-Goals

**Goals:**
- 在社区版 `system_mgmt` 中承载 `User.phone`、敏感信息全局配置与授权数据模型，并提供商业版可直接消费的基础 API 契约。
- 在商业版 `server/apps/system_mgmt/enterprise` 中提供邮箱/手机号的授权判定与脱敏逻辑，并将其接入当前已实现的人类界面用户查询出口。
- 在商业版前端通过 enterprise manifest + route 机制提供“安全管理 / 敏感信息”菜单与页面，同时保留社区版静态菜单源不直接展示该入口。
- 在用户编辑弹窗中，通过共享 hook + EE override hook 实现敏感字段 overwrite 模式，防止未授权查看明文时出现误覆盖。
- 明确保护能力的职责边界：当前保护目标是展示控制与防误覆盖，而不是新增基于查看权限的写入拒绝逻辑。

**Non-Goals:**
- 不新建独立 enterprise app。
- 不把“敏感信息”菜单直接写入社区版 `web/src/app/system-manager/constants/menu.json`。
- 不让超管天然绕过敏感信息授权。
- 不在一期支持按应用、按组织或按资源粒度的授权范围。
- 不因为缺少敏感信息查看授权而额外禁止显式修改邮箱/手机号。
- 不把所有内部通知、RPC、自动化链路统一改造成展示脱敏出口。

## Decisions

### 1. 社区版承载基础数据与共享交互，商业版承载保护能力与入口
- **Decision**: `User.phone`、`SensitiveInfoAuthorization`、`SystemSettings` 敏感信息配置项，以及共享的敏感字段编辑状态机放在社区版；脱敏服务、菜单/路由 manifest、敏感信息管理页面源码、EE override hook 放在商业版。
- **Why**: 这与“字段添加和模型添加放社区版，功能实现和页面放商业版”的既定边界一致，同时允许社区版作为基础运行时承载共享表单与 enterprise shim。

### 2. 商业版脱敏逻辑通过社区版 `UserViewSet` 的可选导入接入
- **Decision**: 在 `server/apps/system_mgmt/viewset/user_viewset.py` 中通过 `try/except` 可选导入 `apps.system_mgmt.enterprise.sensitive_info`，并将脱敏逻辑接入 `search_user_list`、`get_user_detail`、`user_all`。
- **Why**: 这让社区版在没有 EE 模块时仍可运行，同时在存在 EE 模块时自动获得展示控制能力，而无需拆分独立用户查询栈。

### 3. 前端入口由商业版 manifest 驱动，社区版通过 generated shim 消费
- **Decision**: 商业版使用 `web/manifests/menus.json` 向 `security_management` 注入“敏感信息”菜单，并使用 `web/manifests/routes.json` 声明页面路由；社区版通过 `prepare-enterprise` 生成 `(pages)/(enterprise)/security/sensitive-info/page.tsx`、`(enterprise)/api/sensitive_info`、`(enterprise)/hooks/useSensitiveFieldEditBehavior` 等 shim 文件与共享代码配合。
- **Why**: 这是当前实际落地的接入方式。社区版静态菜单源仍不直接包含“敏感信息”入口；`server/support-files/system_mgmt/menus/system-manager.json` 中保留的 `sensitive_info` 权限项仅用于权限定义，不等价于社区版前端菜单展示，运行态入口仍由 enterprise patch / generated shim 决定。

### 4. 只对已接入的人类界面查询出口做展示控制，机器消费路径保留原值
- **Decision**: 当前仅对 `UserViewSet` 中已接入的面向人类界面查询出口执行脱敏控制；像 `get_all_users` 这样的机器消费路径继续保持原值能力。
- **Why**: 代码与测试都表明当前实现没有把展示脱敏扩散到所有用户读取路径，这符合“只控制人类界面展示，不误伤机器消费”的边界。

### 5. 授权模型维持全局“用户 + 敏感类型”语义，超管无天然豁免
- **Decision**: 授权模型以 `username + domain + sensitive_types` 表达全局授权关系，脱敏逻辑仅根据授权记录判断是否返回明文，不因超管身份直接放行。
- **Why**: 这与当前 `SensitiveInfoAuthorization` 模型和 `enterprise/sensitive_info.py` 的实现完全一致，也符合既定业务约束。

### 6. 手机号在模型层保持宽松，在接口层做轻量校验
- **Decision**: `phone` 字段在模型层仅作为可选 `CharField(max_length=32, null=True, blank=True)` 存储，不做模型层正则约束；在 `create_user` / `update_user` 接口层执行宽松校验，允许空值以及 `+`、`-`、空格、括号等格式。
- **Why**: 这同时满足宽松存储、兼容手工维护以及避免明显脏数据的要求，也与现有实现一致。

### 7. 编辑用户时敏感字段采用 overwrite 模式，而不是写侧权限拒绝
- **Decision**: 当保护开启且当前用户对 `email` / `phone` 无查看授权时，用户编辑弹窗中的对应字段进入 overwrite 模式：默认只读，点击编辑后清空原值，使用确认/取消显式提交；若字段仍处于编辑中则阻止整单提交；提交时 `cleanPayload()` 会省略未确认修改的敏感字段；后端 `update_user()` 仅对显式传入的 `email` / `phone` 做更新。
- **Why**: 这正是当前已实现的“防误覆盖”语义。保护能力不额外引入基于查看权限的后端写入拒绝，显式新值在保护开启时仍允许更新。

## Risks / Trade-offs

- **[公开字段白名单仍包含 email/phone]** → `UserSerializer` 已从 `__all__` 收紧为白名单，但 `email` / `phone` 仍属于基础公开字段；当前安全边界依赖查询出口是否接入脱敏控制，而不是单靠序列化器隔离。
- **[社区版 generated shim 与商业版源码需要同步]** → 页面/API/hook 同时存在 EE 源码和 CE generated shim，两侧结构若不同步，容易造成文档、代码和构建结果的理解偏差。
- **[机器消费路径的验证证据仍偏集中]** → 当前已有 `get_all_users` 保持原值的测试证据，但通知、RPC、自动化等更广泛链路仍缺少更完整的联调验证记录。
- **[OpenSpec 任务状态易与实际代码脱节]** → 本次 change 的任务列表此前长期保持全未勾选状态，说明若不回写工件，后续归档判断很容易失真。

## Migration Plan

- 迁移顺序已经落地为：先执行 `0030_user_phone` 增加 `phone` 字段，再执行 `0031_sensitive_info_authorization_and_settings` 创建授权模型并初始化敏感信息默认配置。
- 全局开关默认关闭（`sensitive_info_protection_enabled = 0`），保护能力需由商业版页面显式开启。
- 商业版入口通过 manifest + generated shim 接入；如需回滚显示能力，可保留社区版 schema 与共享代码，仅下线商业版 manifest、页面和 enterprise 脱敏服务。
- 用户编辑覆盖语义的回滚点在于前端 overwrite 模式与后端条件更新逻辑；保留当前 schema 不会影响基础用户资料能力。

## Open Questions

- 目前已验证 `get_all_users` 等机器消费路径在保护开启后保持原值，但是否需要补充更完整的通知、RPC、自动化链路联调证据，仍需在归档前决定。
