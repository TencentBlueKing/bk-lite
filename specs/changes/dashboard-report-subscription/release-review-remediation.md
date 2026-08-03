# 仪表盘报告订阅 Release Review 修复跟踪

Status: approved

Last reviewed commit: `c2754d0dabdf9df07c22140651816a6caa91ca31`

Originating spec: [`spec.md`](./spec.md)

## 1. 目的

本文档固定 DataSource Runtime Snapshot 调整后的最终 Release Review
结论，并作为剩余问题的唯一修复状态入口。修复不得只更新代码而不更新
本文档的状态、验证证据和决策记录。

当前发布结论：**Approve**。RR-01 至 RR-05 已完成修复、契约校准与完整回归；
后续修改仍必须维持本文档中的安全和并发边界。

## 2. 状态规则

| 状态 | 含义 |
|---|---|
| `confirmed` | 问题已由 spec 和代码证据确认，尚未开始修复 |
| `decision_required` | 代码与 spec 存在冲突，必须先冻结设计决策 |
| `in_progress` | 修复已开始，但验收条件尚未全部满足 |
| `fixed` | 代码和文档已完成，尚缺完整验证 |
| `verified` | 修复、必须测试和回归验证全部通过 |
| `deferred` | 已明确不阻塞当前发布，并记录了延期理由 |

状态不得从 `fixed` 直接变为 `verified`，除非同一次更新同时记录了
针对性测试、相关完整回归和迁移检查证据。

## 3. 已关闭的 Review 项

| 项目 | 结论 | 状态 | 证据 |
|---|---|---|---|
| DataSource Runtime Snapshot | 明确不冻结 DataSource 运行配置；Render Snapshot 只保留 DataSource identity，查询时实时解析定义、权限和凭据 | `verified` | commit `c2754d0d`；相关回归 215 passed / 1 skipped |
| DataSource Snapshot Secret | 原 reviewer 结论随上述字段和构建链路删除而失效；Snapshot 不再保存 `query_config` / `field_schema` / connection / credential | `verified` | `DashboardReportRenderSnapshot` 和 render-input API 已不包含 `datasource_snapshots` |

## 4. 发布阻塞项总览

| ID | 问题 | 分类 | 优先级 | 状态 | 依赖 |
|---|---|---|---|---|---|
| RR-01 | 跨 domain 同名用户 IDOR | Confirmed Bug | Blocker | `verified` | 无 |
| RR-02 | Render Token 没有全局 execution scope | Confirmed Bug | Blocker | `verified` | RR-01 |
| RR-03 | Email Channel 组织范围变化后仍可投递 | Confirmed Bug | Blocker | `verified` | RR-01 |
| RR-04 | Execution 终态不可变与 Delivery Fact 仲裁冲突 | Spec Conflict | Blocker | `verified` | 无 |
| RR-05 | Subscription 乐观锁非原子，并发 PATCH 可静默覆盖 | Confirmed Bug | Blocker | `verified` | RR-01 |

## 5. RR-01：跨 Domain 稳定身份与 IDOR

### 问题契约

`User` 的唯一身份是 `(username, domain)`，但 Subscription、Execution、
Input Snapshot 及 API queryset 只使用 `username`。不同 domain 的同名用户
可能读取、修改、删除或执行对方资源。

### 必须修复

- Subscription 和 Execution 保存 `creator_domain`。
- Input Snapshot 冻结 `creator_username + creator_domain`。
- list/retrieve/PATCH/DELETE/execute 全部按二元身份过滤。
- PermissionStep 按 `(username, domain, active)` 精确解析创建者。
- Render Token 和审计 actor 使用相同稳定身份。
- 增加适合 API 查询的组合索引。

### 必须验证

- [x] 不同 domain 同 username 用户不能互相 list/retrieve/PATCH/DELETE/execute Subscription。
- [x] 不能读取对方 Execution 及 Snapshot。
- [x] PermissionStep 和 Render Token 只解析目标 domain 用户。
- [x] 超级用户行为与功能 spec 一致。

## 6. RR-02：受限 Render Execution Identity

### 问题契约

当前 Render JWT 携带创建者 `user_id`，通用 authentication/permission 链路
可将其视为普通用户凭证。`render_execution_id` 仅在 render-input 内局部
校验，且 Token 未绑定 `render_snapshot_id`。

### 必须修复

- JWT 明确携带 `token_type=dashboard_report_render`、`execution_id`、
  `render_snapshot_id`、`attempt_no`、创建者稳定身份、`jti` 和 `exp`。
- Authentication middleware 建立专用 scoped render principal，不建立普通用户 Session。
- Render principal 默认拒绝所有普通 API，只允许本 Execution 的内部渲染页、
  render-input 和必需的 Widget 数据查询。
- Widget 查询继续实时使用 creator 权限，但必须叠加 execution scope。
- 新 attempt 废止上一 attempt 的 Token 及已建立 Render Session。

### 必须验证

- [x] Render JWT 访问普通业务 API 返回 401/403。
- [x] 跨 Execution、Snapshot 或 attempt 访问被拒绝。
- [x] 新 attempt 后旧 Session 失效。
- [x] 合法 Widget 查询仍按 creator 当前权限执行。
- [x] creator 权限下降后，已建立 Render Session 不能继续越权查询。

## 7. RR-03：Email Channel 组织边界

### 问题契约

创建和编辑会验证当前组织可用 Channel，但 Delivery 只检查 Channel
存在且类型为 email。Channel 删除、转移组织或创建者退出组织后，旧
Execution 仍可能使用其配置和凭据。

### 必须修复

- Subscription 绑定明确的 organization/team identity。
- Input Snapshot 冻结本次 `execution_team_id`，不冻结 Channel 配置或凭据。
- Delivery 通过 Channel Service 实时验证存在性、email 类型、team 归属、
  creator 当前 team 成员资格和配置有效性。
- 失效时在 email 阶段终止，不自动切换 Channel。
- 稳定区分 `channel_missing`、`channel_not_email`、`channel_team_denied`、
  `channel_config_invalid`。

### 必须验证

- [x] Channel 删除后 Delivery 失败。
- [x] Channel 从 team A 移至 team B 后，A 的旧 Execution 失败。
- [x] creator 退出 team 后 Delivery 失败。
- [x] Subscription 后续更换 Channel 不影响已冻结 Execution。
- [x] Channel 在原 team 内合法更新配置后，Delivery 使用实时新配置。

## 8. RR-04：Execution 终态与 Delivery Fact 仲裁

### 冲突

当前 spec 要求所有终态不可覆盖，代码则允许持久化投递事实将
`failed/unknown` 修正为 `succeeded`，以及将 `failed` 修正为 `unknown`。
这是 SMTP 外部副作用与 timeout 并发下的真实取舍，不得在未修订 spec
前直接删除或放开该路径。

### 已确认决策

- 普通生命周期终态不可复活。
- 持久化 Delivery Fact 允许通过专用 reconciliation 做单向仲裁：
  `delivered > smtp_unknown > not_delivered`。
- 不把 reconciliation 建模为通用 `transition()`。

### 决策后必须修复

- 先修订原始 spec 的终态不变与 timeout 仲裁条款。
- 将当前对齐入口收敛为显式 `reconcile_delivery_fact()`。
- 仅允许持久化 `delivery_outcome` 驱动，不允许普通 writer 修改终态。
- 将 `failed → succeeded/unknown` 限制在 timeout/Delivery 竞态，不允许
  permission、snapshot 或 render 业务失败被修正。
- 记录 previous status、reconciliation reason/time/source，并使用 CAS。

### 必须验证

- [x] 普通 `transition()` 拒绝所有终态迁移。
- [x] timeout 先 failed、SMTP 后确认 delivered 时按决策仲裁。
- [x] permission/snapshot/render failed 不能被伪造 Delivery Fact 复活。
- [x] 并发 timeout、Worker 和 reconciliation 不会降级 delivered 事实或重复发送。
- [x] reconciliation 审计字段完整。

## 9. RR-05：Subscription 原子乐观锁

### 问题契约

当前实现只比较已加载对象的 `version`，然后执行普通 `save()`。两个
并发 PATCH 可能同时通过比较并静默覆盖；非调度字段变化也不递增
当前版本。

### 必须修复

- 区分所有变更使用的 `revision` 与调度审计使用的 `schedule_version`。
- 所有 PATCH 必须携带 `revision`。
- 使用 `id + revision + deleted_at is null` 的单条条件更新，成功时
  `revision = revision + 1`。
- 受影响行数为 0 时返回 409，不允许“先比较、后普通 save”。
- 暂停、恢复、编辑和用户删除遵循同一 revision 边界。
- `schedule_version` 仅在调度语义变化时递增，并冻结到 Input Snapshot。

### 必须验证

- [x] 两个相同 revision 的并发调度 PATCH 只有一个成功。
- [x] 并发修改邮箱、Channel、筛选或名称不会静默覆盖。
- [x] 旧 revision 统一返回 409，且不改变 `next_run_at`。
- [x] Scanner 与调度编辑通过 Subscription 行锁线性化，不基于已失效配置创建 Execution。
- [x] Input Snapshot 同时保留执行时的 revision 和 schedule version。

## 10. Non-blocking Follow-up

| ID | 问题 | 状态 | 处理策略 |
|---|---|---|---|
| FU-01 | 长期 capability 文档局部仍将 Retry、Cleanup、missed-run compensation 写为未实现 | `verified` | 已校准 capability 文档事实 |
| FU-02 | Orchestrator 多套 attempt 流程及大型 Service 职责膨胀 | `deferred` | 安全修复后单独设计与重构，不与 Blocker 混合提交 |
| FU-03 | Render Scope 漏放行 manifest DataSource 关联 Namespace，渲染等待超时 | `verified` | 仅允许实时关联 Namespace 的非空 ID 子集；补 HTTP 与越界拒绝回归 |
| FU-04 | claim orphan 与活跃 Render 共用超时预算，且默认预算不足以覆盖三次 Render | `verified` | attempt=0 使用 60 秒短 deadline；活跃执行默认总预算 420 秒 |
| FU-05 | Render Session 被普通用户上下文阻塞，页面未挂载或 widget 无法解析 scoped DataSource | `verified` | execution render 路由使用最小 Provider 集合；OpsAnalysis 使用独立 Render Provider，不读取普通用户组，DataSource 最终授权由后端 execution scope 实时校验 |
| FU-06 | Render Worker 无 `current_team` cookie，DataSource 二次组织过滤返回 200 空列表并触发 `datasource_missing` | `verified` | scoped middleware 将冻结的 `execution_team_id` 注入可信请求组织上下文；复用现有 DataSource 实时成员、权限与 groups 校验，不绕过普通权限链 |
| FU-07 | RC Review：migration 0019 是否需要拆出 0020 | `verified` | **不需要 0020**。事实：0019 未推送远程；本地已按修改后的 0019 重新 migrate。CreateModel 原地修订仅影响本分支未发布库，等价于新表创建。 |

## 11. 实施顺序

1. RR-01：建立 domain-aware 稳定身份。
2. RR-02：建立 scoped Render Principal。
3. RR-03：冻结执行组织 identity，发送前实时校验 Channel。
4. RR-05：引入原子 revision CAS。
5. RR-04：确认 Delivery Fact 仲裁决策，先更新 spec，再收敛代码。
6. 运行安全、并发、状态机、Scheduler、Render 和 Delivery 完整回归。
7. 校准 FU-01；FU-02 保持独立后续任务。

## 12. 状态更新模板

每次修复完成后，必须同时：

1. 更新第 4 节对应 Issue 状态。
2. 勾选对应“必须验证”条目。
3. 在下表追加一条记录。
4. 若行为契约变更，先更新 [`spec.md`](./spec.md)，再实现代码。

| 日期 | Issue | 旧状态 | 新状态 | Commit / Diff | 验证证据 | 备注 |
|---|---|---|---|---|---|---|
| 2026-08-01 | DataSource Runtime Snapshot | `confirmed` | `verified` | `c2754d0d` | 215 passed / 1 skipped；migration check 通过 | 采用 DataSource 实时运行上下文，不支持历史配置重放 |
| 2026-08-01 | RR-01 | `confirmed` | `verified` | 当前 WIP | 跨域 CRUD/execute/Execution/Render identity 用例；完整回归 218 passed / 1 skipped | 稳定身份统一为 `(username, domain)`，审计 actor 同步保存 domain |
| 2026-08-01 | RR-02 | `confirmed` | `verified` | 当前 WIP | 普通 API 拒绝、跨 execution、旧 attempt、无普通 Session、权限下降查询用例通过 | scoped Render principal；旧格式 Render claims fail closed |
| 2026-08-01 | RR-03 | `confirmed` | `verified` | 当前 WIP | Channel 删除/迁移、成员退出、配置无效/解密失败/合法更新用例通过 | 冻结 team identity，配置与凭据实时读取 |
| 2026-08-01 | RR-04 | `decision_required` | `verified` | 当前 WIP | 状态机、timeout/SMTP race、非法复活与审计字段用例通过 | 普通终态不可变；仅 Delivery Fact 专用 CAS reconciliation |
| 2026-08-01 | RR-05 | `confirmed` | `verified` | 当前 WIP | 双连接同 revision PATCH 仅 200/409；stale PATCH/DELETE 回归通过 | `revision` 全字段 CAS；`version` 保留调度语义 |
| 2026-08-01 | Release Gate | `request_changes` | `approved` | 当前 WIP | 后端 218 passed / 1 skipped；Core Auth 18 passed；Web 18 passed + type-check；migration rebuild/check、Django check 通过 | Chromium 集成用例按环境标记 skipped |
| 2026-08-01 | FU-03 / FU-04 | `confirmed` | `verified` | 当前 WIP | 针对性 4 passed；订阅/调度/状态机/Render 完整回归 241 passed / 1 skipped | 修复 Namespace scoped read、claim orphan 短回收与三次 Render 总预算 |
| 2026-08-01 | FU-05 | `confirmed` | `verified` | 当前 WIP | Render Auth、路由边界、Render OpsAnalysis 与 Render Page 8 passed；运行时 Execution 8 已请求 render-input/scoped DataSource；Render Contract passed | 修复根布局与嵌套 OpsAnalysis 两层普通用户上下文依赖；普通路由 Provider 链保持不变 |
| 2026-08-01 | FU-06 | `confirmed` | `verified` | 当前 WIP | Execution 9 复现 `datasource_missing`；manifest scope + execution team 注入回归通过 | 不伪造 cookie；使用与 API Key 相同的 `_api_current_team` 可信入口，list/query 共用既有实时权限逻辑 |
| 2026-08-01 | RC-P0 Render fail-closed / creator 权限复核 | `request_changes` | `verified` | 当前 WIP | dashboard_report_* + core auth 212 passed / 4 skipped；Web render/subscription 24 passed；`_verify_token` 拒绝 Render JWT；离开组织/无实例权限 widget 403 | `_verify_token` 全局拒绝 Render JWT；middleware 经 resolve_request_user 建 scoped principal；get_source_data 叠加成员与实例权限复核；0019 不新增 0020（未推远程且本地已重建） |

## 13. 最终发布准入

只有同时满足以下条件，本文档 `Status` 才可从
`request_changes` 更新为 `approved`：

- RR-01、RR-02、RR-03、RR-04、RR-05 全部为 `verified`。
- 所有必须验证项已勾选并有新鲜测试证据。
- Django migration check、system check 和影响范围完整回归通过。
- Web 安全边界测试通过，不依赖隐藏按钮或前端路由保护。
- 最终 Release Review 无未关闭 Blocker。
