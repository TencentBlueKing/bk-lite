# M2 实现备忘

外部服务注册链路（KV → 渲染器 → provider 端点 → ForwardAuth）实现期决策。

## 实现细节决策

1. **provider 端点保护**：渲染结果内含解引用后的密钥值（`X-BK-Gateway-Auth` / 服务令牌），端点以 `X-Provider-Token` 头校验（env `OPENAPI_PROVIDER_TOKEN`，常数时间比较）；未配置该 env 时端点返回 503 拒绝服务（fail-closed）。Traefik 侧 `providers.http.headers` 配置携带同一令牌（M4 落地）。
2. **provider 端点返回 Traefik 原生配置格式**（非统一 envelope）：`providers.http` 消费原生 `{"http": {...}}` 结构，该端点属基础设施端点，不在 `/openapi/v1/{service}` 业务契约范围内；`_provider/*` 归入下划线保留命名空间。
3. **KV bucket 惰性创建**：读取时 bucket 不存在则尝试幂等创建，创建失败按空注册表处理并告警——满足「非关键资源失败不阻断启动」硬约束；部署侧显式初始化归 M4 / wxc。
4. **双层降级**：渲染层持有最近一次成功快照，KV 整体不可达时返回快照并告警；Traefik `providers.http` 拉取失败时自身保留最后配置——两层兜底叠加。
5. **ForwardAuth 快照查无 service 时返回 404（fail-closed）**：正常情况下路由存在即条目存在，查无仅发生在快照滞后的极小窗口；404 与 invoke 路径的资源不存在语义一致，不泄漏存在性。
6. **`X-On-Behalf-Of` 处理**：该头列入 `authResponseHeaders`，认证视图对 API 令牌凭据回显原值、对 JWT 凭据返回空串覆盖清除——实现 design.md 3.2.2 配套约束 4「仅服务账号场景接受」的机制（M2 以凭据类型近似「服务账号」判定，专属服务账号标记留二期）。
7. **KV 字段 → Traefik 参数显式映射**：`rate_limit.average/burst` → `rateLimit`、`strip_prefix` → `stripPrefix`、`paths` → `PathPrefix(...) ||` 规则均经 renderer 显式转换，两端命名不耦合（design.md 评审意见落实）。
8. **渲染器快照为进程内状态**（线程锁保护）：多 worker 各自持有快照，一致性由 Traefik 轮询天然收敛，不引入跨进程存储。

## 测试经验教训（M1 用例修正）

- **JWT 登录态的用户体系是 `system_mgmt.User`**，`_verify_token` 按其 `id` 查询；M1 测试误用 `base.User` 的 id 签发 JWT，凭两表自增 id 巧合命中而通过，M2 新增测试文件改变建表顺序后暴露。已修正 `make_jwt_tenant` 为创建 `system_mgmt.User`（含 `group_list`）。此差异对实现无影响（identity 层只消费 `verify_token` 返回值），但值得写入认知：**平台存在 base.User 与 system_mgmt.User 两套用户表，API 令牌链路校验前者与后者的存在性，JWT 链路只走后者**。

## 测试与验证

- `apps/core/openapi/tests` 共 64 项全部通过（M1 32 + M2 32：渲染器 20 项单测覆盖四类坏条目 / 未知字段前向兼容 / gateway_versions 过滤 / fail-closed 分支；外部链路 12 项集成覆盖 provider 保护、快照降级、ForwardAuth 与 invoke 401 逐字段同构、required_roles 空数组语义、身份头注入与 X-On-Behalf-Of 回显、_me 外部 service 合并）。
- KV I/O 层（kv.py）：单测以 mock 覆盖；真实 NATS 冒烟见下节。

## 真实 NATS 冒烟

本机 nats-server v2.14.5（`-js`，临时端口 4231）验证 kv.py 真实链路：

- 首次 `fetch_entries()`：bucket 不存在 → 惰性创建成功 → 返回空注册表 `{}`；
- nats-py 写入 itsm 条目后再次 `fetch_entries()`：正确返回 `{"itsm": {...}}`。

惰性创建与读取链路均验证通过；端到端（Traefik providers.http 实际拉取 + 反代）联调归 M4。
