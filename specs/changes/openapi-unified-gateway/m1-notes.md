# M1 实现备忘

实现期决策与对设计文档（design.md v2.2）的偏差记录。条目按「须回填文档」与「实现细节」分类。

## 须回填设计文档（错误码枚举 additive 增补）

- **`TIMEOUT`(504)**：design.md 3.4.3 要求分发器强制超时，但 3.8 错误码枚举未定义超时语义，实现新增该枚举值；
- **`BUSINESS_REJECTED`(400)**：暴露函数沿用现有 `{"result": false, "message": ...}` 软错误约定时，分发器无法辨别具体语义（越权 / 参数错），统一映射为该通用业务拒绝码。函数返回结构化 code 的机制留 M2 讨论。

两者均为 additive 新增，符合「错误码只增不改不删」的演进规则；design.md 3.8 第 2 条待同步。

## 实现细节决策

1. **认证缓存边界（plan M1 风险项）**：不新增缓存层。API 令牌路径直接调用 `APISecretAuthBackend().authenticate(request=None, api_token=...)`（自带 permission_version 围栏 + 600s 快照缓存）；JWT 路径直接调用 `system_mgmt.nats.auth.verify_token`（自带 token 缓存 + jti 黑名单）。设计文档「TTL ≤ 60s 的进程内快缓存」按「如叠加」条款暂不实现，吊销延迟即两条现有链路各自的既有语义。
2. **URL 挂载**：`/openapi/v1/` 在根 `server/urls.py` 顶层静态挂载。走 `apps/core/urls.py` 会被动态循环强加 `/api/v1/core/` 前缀（该循环内路径不可覆盖），无法得到干净的网关前缀。
3. **登录保护豁免语义**：网关视图使用 `@api_exempt` 仅为绕过 `AuthMiddleware` 的平台登录态保护；每个视图第一步执行自带的双凭据强制认证（fail-closed），非公开裸端点。未复用 `APISecretMiddleware` 链路：其读取的是 `Api-Authorization` 头，与网关冻结契约（`Authorization: Bearer`）不同。
4. **强制超时开关**：`settings.OPENAPI_INVOKE_TIMEOUT`（秒）> 0 时经线程池施加硬超时（生产配置）；为 0（默认）同步执行——pytest 事务型用例的数据在独立线程的 DB 连接中不可见，测试必须走同步路径。生产部署侧须显式配置该值。
5. **权限位判断**：`HasPermission` 为 Django view 装饰器，无法直接套用于 invoke 路径；dispatcher 复用其权限数据模型（`user.permission` 的 `{app: set}` 结构 + 交集判断 + superuser 直通）自行实现，`permission_app` 由装饰器显式声明（不做模块路径推断魔法）。
6. **cmdb 试点收窄**：`get_cmdb_module_data` 的 `PERMISSION_MODEL` / `PERMISSION_TASK` 分支在现有实现中不做按用户过滤，serializer 将 `module` 限定为 `instances` 单值枚举，未过滤分支不得经网关暴露。
7. **锚点式注入负载**：键名按现有代码为 `user`（非 design.md 3.3.2 早版的 `username`）+ `domain` + `team` + `include_children`；serializer 声明的 `team` / `include_children` 由 dispatcher 抽入 `user_info`，API 令牌凭据下锚点强制覆盖为绑定组织。

## 测试与基线证据

- 本地运行：`postgresql@15`（brew），env：`DB_ENGINE=postgresql DB_NAME=bklite DB_USER=<local> MINIO_ACCESS_KEY/SECRET_KEY=<假值> ENABLE_CELERY=true SECRET_KEY=<任意>`；命令 `uv run --all-extras --group dev pytest apps/core/openapi/tests`。
- 结果：32 passed（17 registry fail-closed 单测 + 15 网关端到端集成）。
- 回归：`apps/patch_mgmt/tests + apps/base/tests` 共 612 passed / 5 skipped / 1 failed；该失败项 `test_uncovered_patch_contracts.py::test_linux_assessment_reports_missing_detail_and_empty_package_name`（断言「缺少 Linux 补丁详情」≠「补丁未配置包名」）经 `git stash` 后在干净基线复现，为基线固有失败，与本变更无关。
- sqlite 引擎（`DB_ENGINE=sqlite`）下全量 app 的 migration 存在基线不兼容（alerts 相关 `NewSessionEventRelation` 建库报错），网关测试请使用 postgresql。
