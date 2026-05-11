## 1. 社区版基础数据与用户资料能力

- [x] 1.1 在 `server/apps/system_mgmt/models/user.py` 中新增 `phone` 字段，并创建对应 migration。
- [x] 1.2 调整社区版用户新增、编辑、详情、列表相关后端链路，使手机号作为基础资料字段可被保存、更新和返回。
- [x] 1.3 调整社区版用户管理前端表单、类型与基础展示链路，支持手工维护手机号字段。
- [x] 1.4 收紧公开用户序列化字段白名单，避免 `UserSerializer` 在引入手机号后继续扩大敏感字段暴露面。

## 2. 社区版敏感信息配置与授权数据承载

- [x] 2.1 在社区版 `system_mgmt` 中新增敏感信息授权数据模型及其 migration，表达全局“授权用户 + 敏感类型”关系。
- [x] 2.2 为社区版 `SystemSettings` 补齐敏感信息保护所需的全局配置项承载，并初始化默认值。
- [x] 2.3 补齐社区版基础接口契约，使商业版可以读取和保存敏感信息全局配置与授权数据。

## 3. 商业版后端敏感信息保护逻辑

- [x] 3.1 在 `server/apps/system_mgmt/enterprise/...` 中实现敏感信息授权判定与脱敏处理服务。
- [x] 3.2 将商业版展示控制接入当前已实现的人类界面用户查询出口，对邮箱/手机号按全局配置和授权关系返回脱敏值或明文。
- [x] 3.3 确保超级管理员不具备天然豁免，仅在授权命中对应敏感类型时返回明文。
- [x] 3.4 保持未接入展示脱敏的机器消费路径原值读取能力，当前至少已验证 `get_all_users` 在保护开启后仍返回原始联系方式。
- [x] 3.5 在共享用户编辑弹窗中实现敏感字段 overwrite 交互，并通过 EE hook 按全局配置与当前用户授权决定 `email` / `phone` 是否进入 overwrite 模式。
- [x] 3.6 调整编辑提交流程与后端更新语义：编辑中阻止提交，overwrite 模式未确认字段不写回，显式新值在保护开启时仍允许更新。

## 4. 商业版前端菜单与页面接入

- [x] 4.1 在商业版 `web/manifests/menus.json` 中通过 patch 向 `security_management` 注入“敏感信息”菜单项。
- [x] 4.2 在商业版 `web/manifests/routes.json` 中声明敏感信息管理页面路由，并通过现有 enterprise route / generated shim 机制接入页面源码。
- [x] 4.3 实现商业版“安全管理 / 敏感信息”页面，提供全局开关、敏感信息类型和授权用户管理能力。
- [x] 4.4 接入商业版前端 API / hooks / components，使页面可读写全局配置并维护授权记录，同时与社区版共享用户编辑弹窗联动。

## 5. 联调与验证

- [ ] 5.1 补社区版无 enterprise 时的运行态验证证据：需同时验证 CE 不显示“敏感信息”菜单、基础导航与路由保持正常，以及用户编辑弹窗中的 `email` / `phone` 在缺少 enterprise hook 时直接展示并保持可直接编辑的 plain 模式；`server/support-files/system_mgmt/menus/system-manager.json` 中的 `sensitive_info` 仅为权限定义而非前端菜单入口。
- [x] 5.2 已验证商业版菜单 patch、route shim 与页面接入：`pnpm prepare-enterprise` 可生成 `/system-manager/security/sensitive-info` shim 页面，本地 `http://127.0.0.1:3000/system-manager/security/sensitive-info` 返回 200，菜单 API 返回结果已包含 `security_management -> sensitive_info`。
- [x] 5.3 已补后端关键场景验证：全局开关关闭、未授权超管脱敏、授权命中、编辑时省略字段不覆盖、保护开启下显式敏感字段可更新。
- [ ] 5.4 补更完整的通知、RPC、自动化链路联调验证；当前已验证 `get_all_users` 在保护开启后保持原始联系方式。
