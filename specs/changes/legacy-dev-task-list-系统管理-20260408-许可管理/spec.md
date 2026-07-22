# 系统管理-许可管理 Dev Task List

Status: cancelled

> Migrated from `spec/dev_task_list/系统管理/20260408/许可管理.md` as historical change evidence.

日期：2026-04-08

关联文档：

- Solution Plan：`spec/solution_plan/系统管理/20260407.许可管理.md`
- Tech Plan：`spec/tech_plan/系统管理/20260408.许可管理.md`
- Tasks：`spec/tasks/系统管理/20260408.许可管理任务拆解.md`

## 0. 开发规范补充

### 0.1 后端规范

- Python 代码必须满足 PEP 8，特殊约束以 `server/.flake8` 为准。
- 后端格式化与导包排序统一使用 `black`、`isort`、`ruff`，对应配置以 `server/pyproject.toml`、`server/.isort.cfg`、`server/ruff.toml` 为准。
- 后端开发过程如需执行测试，统一使用 Python 环境：`D:\app\venv\bkliteserver`。

### 0.2 前端规范

- 前端代码满足 ESLint 标准即可，规则以 `web/.eslintrc.json` 为准。

## 1. 开发前检查（Gate）

- [ ] 企业版代码边界已确认：后端仅使用 `server/apps/license_mgmt`，前端真实实现仅使用 `web/src/app/system-manager/enterprise`。
- [ ] 菜单与权限口径已确认：仅内置超管可见，社区版不注册 `license_mgmt`，菜单初始化逻辑具备 `license_mgmt` 存在性判断。
- [ ] 并发与状态一致性口径已确认：新增、修改、停用许可后仅强制刷新许可列表，不要求模块摘要和生效许可数实时联动。
- [ ] 数据结构版本口径已确认：许可覆盖模块、通知渠道、通知人员第一版继续使用 `JSONField`，不提前拆 M2M 子表。
- [ ] 注册码策略已确认：运行时统一从 `server/apps/license_mgmt/registration_code.py` 读取，部署时覆盖为真实注册码。
- [ ] 许可验签顺序已确认：`base64url(JSON)` -> 去 `sig` -> canonical JSON -> `Ed25519` -> `nbf/exp`。
- [ ] 新增资源拦截口径已确认：仅限制 `node_mgmt`、`cmdb`、`monitor`、`log` 的新增资源入口，不影响存量资源使用。
- [ ] 发布与回滚路径已确认：企业版直接上线，可通过下线 `api/v1/license_mgmt/...` 和关闭 `LICENSE_MGMT_ENABLED` 执行降级。
- [ ] 测试范围已确认：后端测试覆盖许可主链路、注册码读取、`.lic` 外层解密、验签、提醒配置、统一拦截；前端测试覆盖入口权限、列表刷新、配置回显。
- [ ] 开发规范已确认：后端遵循 `server/.flake8`、`server/pyproject.toml`、`server/.isort.cfg`、`server/ruff.toml`；前端遵循 `web/.eslintrc.json`。
- [ ] 测试环境已确认：后端测试统一使用 `D:\app\venv\bkliteserver`。

## 2. P0 开发任务清单

| ID | 任务 | 负责人 | 依赖 | 预估 | 状态 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| BE-P0-01 | 建立 `license_mgmt` 企业版独立 app 骨架与 `apps.rpc.license_mgmt` RPC 封装 | 待分配 | 无 | 1-2d | Todo | 企业版 `INSTALLED_APPS` 可注册，社区版不受影响，RPC 可暴露注册码读取与许可校验入口。 |
| BE-P0-02 | 建立 `license_mgmt/config.py` 并接入 `LICENSE_APP_PERMISSIONS` 自动注入机制 | 待分配 | BE-P0-01 | 0.5d | Todo | 大写配置项可进入 `django.conf.settings`，默认结构可被服务层读取。 |
| BE-P0-03 | 实现注册码读取与 `.lic` 外层解密接入 | 待分配 | BE-P0-01 | 1-2d | Todo | 统一从 `registration_code.py` 读取注册码，`GET /api/v1/license_mgmt/license/registration-code/` 可返回展示值，`.lic` 内容可正确解出 `activationCode`。 |
| BE-P0-04 | 实现许可核心模型与首版 migration | 待分配 | BE-P0-01 | 1-2d | Todo | `LicenseRecord`、提醒相关模型可迁移，migration 独立于 `system_mgmt`。 |
| BE-P0-05 | 实现许可码解析、注册码匹配与新增/停用/历史查询接口 | 待分配 | BE-P0-03, BE-P0-04 | 2-3d | Todo | 合法许可可导入，非法签名/过期/注册码不匹配可拒绝，历史许可仅含手动停用和已到期数据。 |
| BE-P0-06 | 实现模块授权摘要接口 | 待分配 | BE-P0-05 | 0.5-1d | Todo | 可返回免激活、已激活、未激活模块及数量汇总，满足前端直接展示。 |
| BE-P0-07 | 实现默认提醒、单许可提醒、节点提醒、日志容量提醒接口 | 待分配 | BE-P0-04 | 2-3d | Todo | 四类提醒均支持读取、保存、回显，`follow/custom` 与阈值校验口径符合 Tech Plan。 |
| BE-P0-08 | 实现统一许可拦截能力：配置匹配、NATS 接口、中间件 | 待分配 | BE-P0-02, BE-P0-05 | 2-3d | Todo | 命中新建资源入口时可通过 RPC/NATS 校验并阻断，未启用或未命中配置时不影响现有请求。 |
| FE-P0-01 | 在系统管理设置页接入“许可”页签与 enterprise 加载点 | 待分配 | 无 | 0.5-1d | Todo | 设置页可识别企业版许可入口，社区版不承载许可业务代码。 |
| FE-P0-02 | 建立 enterprise 目录下的 `api / types / page / components` 骨架 | 待分配 | FE-P0-01 | 1d | Todo | 目录结构符合方案约束，前端请求统一走 `api/v1/license_mgmt/...`。 |
| FE-P0-03 | 实现许可列表、历史许可、注册码展示与新增/停用交互 | 待分配 | FE-P0-02, BE-P0-03, BE-P0-05 | 2-3d | Todo | 可展示许可列表和历史许可，支持复制注册码、新增许可、停用许可，操作后许可列表刷新。 |
| FE-P0-04 | 实现默认提醒、单许可提醒、模块摘要、节点提醒、日志容量提醒页面交互 | 待分配 | FE-P0-02, BE-P0-06, BE-P0-07 | 2-4d | Todo | 页面交互覆盖原型关键区域，支持回显、校验、取消恢复与失败提示。 |

## 3. P1 开发任务清单

| ID | 任务 | 负责人 | 依赖 | 预估 | 状态 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| BE-P1-01 | 组织 `node_mgmt / cmdb / monitor / log` 补齐 `LICENSE_APP_PERMISSIONS` 入口定义 | 待分配 | BE-P0-02 | 1-2d | Todo | 四个模块的新增资源入口已录入统一配置，能被 guard 服务识别。 |
| BE-P1-02 | 补齐后端单元/集成测试 | 待分配 | BE-P0-03, BE-P0-05, BE-P0-07, BE-P0-08 | 1-2d | Todo | 关键测试通过，覆盖注册码读取、`.lic` 解密、验签、提醒配置、拦截链路。 |
| FE-P1-01 | 补齐前端权限、回显、刷新与边界场景验证 | 待分配 | FE-P0-03, FE-P0-04 | 1-2d | Todo | 超管可见、普通用户不可见，列表刷新、模式切换、阈值校验均符合需求。 |
| INT-P1-01 | 完成前后端联调与错误码/失败提示对齐 | 待分配 | BE-P0-05, BE-P0-07, FE-P0-03, FE-P0-04 | 1d | Todo | 关键失败场景具备稳定提示文案，前后端字段口径一致。 |
| OPS-P1-01 | 确认 `registration_code.py` 覆盖方式与发布策略 | 待分配 | BE-P0-03 | 0.5-1d | Todo | 部署环境可稳定覆盖真实注册码，并形成明确变更流程。 |

## 4. 联调任务

| ID | 任务 | 负责人 | 依赖 | 预估 | 状态 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| INT-01 | 对齐 `LicenseRecord`、提醒配置、模块摘要、注册码展示接口字段 | 待分配 | BE-P0-05, BE-P0-06, BE-P0-07, FE-P0-02 | 0.5d | Todo | 前后端字段命名、空值策略、枚举值完全一致。 |
| INT-02 | 对齐许可停用后的统一拦截错误码和提示文案 | 待分配 | BE-P0-08, FE-P0-03 | 0.5d | Todo | 前端可稳定识别被拦截场景并展示统一提示。 |
| INT-03 | 对齐通知渠道/通知人员可见范围查询口径 | 待分配 | BE-P0-07, FE-P0-04 | 0.5d | Todo | 页面可选项与服务端校验范围一致，不出现前端可选但保存失败的错位。 |

## 5. 验证清单

- [ ] 企业版注册 `license_mgmt` 后，社区版环境不报错。
- [ ] 系统管理“设置”中存在“许可”页签，且仅内置超管可见。
- [ ] `registration_code.py` 在部署环境可被正确覆盖，接口返回的是注册码展示值。
- [ ] `.lic` 文件内容可通过注册码正确解出内层 `activationCode`。
- [ ] 合法许可可新增，非法签名、过期、注册码不匹配的许可被拒绝。
- [ ] 新增、修改、停用许可后，许可列表刷新为最新结果。
- [ ] 历史许可仅包含手动停用和已到期许可。
- [ ] 默认提醒、单许可提醒、节点提醒、日志容量提醒均可正确保存和回显。
- [ ] 通知渠道与通知人员范围均限制在当前用户拥有权限组下的可见范围。
- [ ] 停用许可后，`node_mgmt / cmdb / monitor / log` 新增入口会被统一拦截，存量资源不受影响。
- [ ] 后端代码符合 `PEP 8 + .flake8` 要求，必要格式化结果符合 `black / isort / ruff` 配置。
- [ ] 前端代码满足 `web/.eslintrc.json` 约束。
- [ ] 后端 `make test` 与前端 `pnpm lint && pnpm type-check` 通过。

## 6. 风险与阻塞记录

| 风险/阻塞 | 影响 | 处理策略 | 状态 |
| --- | --- | --- | --- |
| 生产环境公钥实际值与默认版本号尚未注入 | 影响许可验签联调与发布配置 | 按既定 `LICENSE_PUBLIC_KEYS + LICENSE_DEFAULT_PUBLIC_KEY_VERSION` 方案，由后端和运维在发布前完成配置注入 | Open |
| 四个业务模块新增资源入口尚未全部枚举 | 影响统一许可拦截覆盖范围 | 由各模块负责人补齐入口清单并纳入 `LICENSE_APP_PERMISSIONS` | Open |
| `registration_code.py` 部署覆盖方式未确认 | 影响许可添加页读取注册码和 `.lic` 解密稳定性 | 在发布前完成运维侧覆盖方案与发布校验确认 | Open |
| 前端 enterprise 加载方式若与现有模式不一致 | 影响社区版隔离边界 | 开发前复用既有 enterpriseStub / integration 模式，不另起新机制 | Open |

## 7. 发布批次建议

1. 批次一：后端 `license_mgmt` 骨架、注册码读取能力、许可主数据接口。
2. 批次二：提醒配置接口、模块摘要接口、统一新增资源拦截能力。
3. 批次三：前端 enterprise 页面与系统管理入口接入。
4. 批次四：联调、补测试、发布前检查与回滚演练。

## 8. 待确认项（TODO）

- TODO: 生产环境需要注入哪些 `LICENSE_PUBLIC_KEY_V*` 实际值，以及 `LICENSE_DEFAULT_PUBLIC_KEY_VERSION` 首发取值。影响范围：部署配置、验签联调、发码平台接入。需要谁确认：后端负责人 + 运维负责人。
- TODO: `node_mgmt`、`cmdb`、`monitor`、`log` 四个模块的新增资源入口完整清单。影响范围：`LICENSE_APP_PERMISSIONS`、统一许可拦截中间件、联调测试范围。需要谁确认：各模块负责人。
- TODO: `registration_code.py` 在部署环境中的覆盖方式、变更流程和发布校验。影响范围：注册码读取、`.lic` 解密稳定性、发布流程。需要谁确认：运维负责人。
