# CMDB 实例 UUID 重设计规格与需求契约

Status: **approved**（2026-08-10 用户批准；实现须另开 Plan，本文件为验收准绳）  
Date: 2026-08-10  
Approved: 2026-08-10  
Branch baseline: `local_codex/cmdb-instance-uuid`  

配套文档：

- 事实清单：[BASELINE_INVENTORY.md](./BASELINE_INVENTORY.md)
- Grill 结论：[GRILL_DECISIONS.md](./GRILL_DECISIONS.md)
- 延期项：[DEFER.md](./DEFER.md)

参考但不作准：2026-08-02 原文、`worktrees/cmdb-instance-uuid` 旧实现。

### 已锁定决定（不可在未再确认时改回）

- **对外业务身份** = `inst_uuid`：在 **CMDB 前后端**以及跨模块（至少含 **节点管理、监控中心、告警中心**，以及 OpenAPI/NATS/RPC、配置采集目标、运营分析等活跃引用）中，均以 UUID **唯一确定同一 CMDB 实例**。  
- **CMDB 后端内部**可继续使用图 `_id` / `inst_id` 作为一次图操作工作集。  
- 数字 ID **不得**作为跨模块或 CMDB Web 的对外业务定位键，不得写入跨模块活跃持久化契约，不得跨请求缓存为业务身份。  
- 不提供长期双身份；默认不提供仓外数字入参废弃窗。

**边界一句话（2026-08-10 澄清）**：跨系统/跨模块认 UUID；CMDB 服务进程内部图操作仍可用 `inst_id`。

---

## 1. 用户故事

作为 CMDB 与跨模块集成方，我希望每个实例有稳定、可移植的业务主键，以便图库重建或数据搬迁后，持久引用仍指向同一实例，而不是依赖会变化的图引擎数字节点 ID。

## 2. 要解决的问题

当前实例身份 = FalkorDB/Neo4j 原生 `ID(n)`，经 `_id` / `inst_id` 进入 API、边属性、PostgreSQL 与相邻模块。该 ID 跨库不可移植，重建后会变，导致引用失效或错指。需要引入不可变业务主键并完成引用切换与发版转换。

## 3. 范围

- 为每个 CMDB `instance` 节点增加不可变 `inst_uuid`（UUIDv4）。
- 统一创建路径生成/校验；封闭漏写旁路。
- 关联边改为端点 UUID 属性；对外关系键稳定。
- PostgreSQL 与活跃 JSON 一等实例引用切换到 UUID（含清单内跨模块）。
- 配置采集目标/回调改为 UUID；**保持** VM/Telegraf `cmdb_{task_id}` 不变。
- 发版维护窗口一次性转换 + verifyify 门禁；符合启动依赖边界。
- 后端 OpenAPI / NATS / RPC 契约同步。

## 4. 明确非目标

- 前端改动（确认后端契约后再评估）——见 [DEFER.md](./DEFER.md)。
- 修改 `worktrees/cmdb-instance-uuid` 旧实现或以其为准。
- 本阶段写业务代码 / 迁移落地（契约确认后另开实现 Plan）。
- 跨系统合并冲突策略、双向同步、tombstone。
- 把图引擎内部 ID 改成 UUID。
- 强制重写历史快照内全部嵌套数字 ID。
- classification / model / credential 等非实例实体 UUID。
- 完整「跨系统迁移工具产品」。
- 机械替换 Monitor/Log/云厂商/OpsPilot 同名 `instance_id`。

## 5. 领域术语与身份边界

| 术语 | 含义 |
|---|---|
| CMDB 实例 UUID (`inst_uuid`) | **跨模块业务主键**；UUIDv4；小写带连字符；创建后不可变；单 BK-Lite 内跨模型全局唯一；**CMDB 前后端、节点管理、监控中心、告警中心等**均以此唯一确定同一实例 |
| 图内部 ID (`_id` / 内部 `inst_id`) | 图引擎节点/关系 ID；**仅 CMDB 后端内部**同进程 Adapter / `InstanceManage` 一次操作可用；不是跨模块业务契约 |
| 实例关系业务键 | `(model_asst_id, src_inst_uuid, dst_inst_uuid)` |
| 采集实例标识 | `instance_id=cmdb_<CollectModels.id>`；非 CMDB 实例 UUID |
| 受控迁移写入 | 仅迁移/内部命令可为存量节点写入既有 UUID；非产品常规入口 |

**边界一句话**：跨模块认 UUID；数字 ID 留在 CMDB 后端图操作内部。

## 6. 业务规则

1. **生成**：日常创建仅服务端 `uuid4()`；禁止客户端指定（本阶段）。  
2. **不可变**：任何 update 含 `inst_uuid` → 拒绝。  
3. **唯一**：全局唯一；索引 + 创建前查重；引擎无唯一约束时文档标明缺口。  
4. **对外 / 跨模块契约**：CMDB Web、OpenAPI、NATS/RPC、节点管理、监控中心、告警中心、配置采集目标、运营分析等活跃引用，均以 `inst_uuid` **唯一确定实例**。  
5. **对内允许**：CMDB 后端解析 UUID 后，同进程内可用 `_id`/`inst_id` 执行图查询、建边、拓扑；**不得**把数字 ID 当作跨模块业务键回传或持久化。  
6. **关联**：边属性存 `src_inst_uuid`/`dst_inst_uuid`；移除 `src_inst_id`/`dst_inst_id`。  
7. **硬删**：保持 `DETACH DELETE`；不新增 tombstone。  
8. **ChangeRecord**：当前查询用 `inst_uuid`；无法映射历史可保留数字 `inst_id`。  
9. **孤儿**：活跃配置清理/禁用并报告；默认失败阻断无法映射的必填引用。  
10. **权限**：不得因身份改造放宽可见范围。

## 7. 权限矩阵

| 主体 | 读 | 写实例/关系 | 迁移命令 |
|---|---|---|---|
| 已授权 CMDB 用户 | 现有模型+组织规则，以 UUID 定位（最终态） | 同左 | 否 |
| OpenAPI/NATS | 现有鉴权 fail-closed | 同左 | 否 |
| 运维（维护窗） | — | — | 是 |

## 8. API / UI 行为（最终态）

### 8.1 CMDB 前后端与实例 API

- CMDB Web ↔ Server：**只**使用 `inst_uuid` 定位与传参（路径、query、body、列表 rowKey 语义）。  
- 响应必含 `inst_uuid`；**不得**再把图 `_id` / 数字 `inst_id` 作为对外业务主键返回给前端或 OpenAPI 调用方。  
- 无效 UUID → 400；不存在/无权限 → 现有 404/403。  
- 后端内部服务在处理请求时：先按 UUID 解析节点，再可用内部 `_id` 做图操作；序列化出站前剥离图 ID。

### 8.2 关联

- 入参/出参：`model_asst_id` + `src_inst_uuid` + `dst_inst_uuid`（或当前实例上下文 + `target_inst_uuid`）。  
- 不暴露图关系 ID 作为业务键。  
- 边存储：`src_inst_uuid` / `dst_inst_uuid`（无数字端点属性）。

### 8.3 配置采集

- 下发 `target_instance_uuid`；回调 `instance_uuid`；协议版本化；拒绝旧数字目标。  
- VM/Telegraf `cmdb_{task_id}` 不变。

### 8.4 字段命名

- 实例：`inst_uuid`  
- 通用参数：`instance_uuid` / `instance_uuids`  
- 关系：`src_inst_uuid` / `dst_inst_uuid`  
- 配置目标：`target_instance_uuid`  
- OA：默认 `bk_inst_uuid`（假设；批准时可改为保留名改类型）

## 9. 正常流程

1. 维护公告，停写 CMDB 实例/关联/相关派发。  
2. 备份图库 + PostgreSQL。  
3. dry-run → apply → verify（幂等）。  
4. 部署同版本后端（及随后评估的前端/Agent）。  
5. 烟测后恢复流量。

## 10. 空状态与失败流程

- dry-run 零写入。  
- verify 失败 → 非零退出，阻断切流。  
- 重复 apply：已有合法 UUID 不重新生成。  
- 旧数字协议（最终态或废弃窗结束后）：安全拒绝，不落脏数据。  
- 流量恢复后禁止热回滚到「无 UUID」模型。

## 11. 数据模型变化

### 图节点

```text
instance.inst_uuid: string, required, immutable, globally unique
```

### 图边 `instance_association`

- 增加：`src_inst_uuid`, `dst_inst_uuid`  
- 删除：`src_inst_id`, `dst_inst_id`  
- 保留：`model_asst_id` 等非端点业务属性  

### PostgreSQL（首期必须，详见清单 P0/P1）

| 数据 | 最终 |
|---|---|
| ChangeRecord | +`inst_uuid`；历史数字可空保留 |
| ConfigFileVersion | `instance_uuid`（替换数字语义的 `instance_id`） |
| SubscriptionRule | `instance_uuids` / 快照键改 UUID |
| 关注资产 JSON | `inst_uuid` |
| Collect 目标快照 | UUID |
| OA 画布活跃配置 | UUID 字段 |
| 操作日志历史 | 不迁 |

## 12. 兼容及迁移策略

- 一次性发版转换；无长期双写。  
- 映射：旧 `_id` → `inst_uuid`（审计用，运行时不读）。  
- 启动：转换命令 ∈ 维护编排，**∉** `batch_init` 普通初始化。  
- 空库：仅新创建逻辑。

## 13. 验收标准（Given / When / Then）

| # | 标准 | 验证 |
|---|---|---|
| 1 | Given 任一创建旁路，When 创建成功，Then 节点有合法唯一 UUIDv4 | 自动化测试 |
| 2 | Given 更新含 `inst_uuid`，When 提交，Then 拒绝且值不变 | 自动化测试 |
| 3 | Given 关联创建，When 成功，Then 边仅有 UUID 端点属性、无数字端点属性 | 自动化测试 |
| 4 | Given 发版转换，When verify，Then 无缺 UUID/无重复/无缺端点边/活跃 PG 无未映射 | 自动化 + 运行时 |
| 5 | Given 图 `_id` 因重建变化但 `inst_uuid` 保留，When 按 UUID 读实例与关系及一条 PG 引用，Then 仍正确 | 人工/运行时烟测 |
| 6 | Given Telegraf 标签，When 采集，Then 仍为 `cmdb_{task_id}` | 自动化 + 人工 |
| 7 | Given CMDB 前端或 OpenAPI 使用数字 `inst_id` 定位实例（最终态），When 请求，Then 安全拒绝且不命中 | 自动化测试 |
| 8 | Given 旧数字目标配置回调（最终态），When 提交，Then 安全拒绝 | 自动化测试 |
| 9 | Given 权限用户，When 用 UUID 访问越权实例，Then 不放宽为可见 | 自动化测试 |
| 10 | Given 后端内部图操作，When 创建关联/拓扑，Then 允许使用已解析的内部 `_id`，且出站响应无该数字业务键 | 自动化测试 |

## 14. 测试矩阵（实现阶段）

- 纯身份规则；Adapter 双驱动；各创建旁路必有 UUID  
- 转换幂等与门禁；关联/拓扑/订阅/配置文件/OA/告警 enrichment  
- OpenAPI/NATS 契约；配置采集协议版本  

## 15. 发布与回滚

- 见 §9；流量前可协调恢复双库备份；流量后只前向修复。  
- 副本演练测时后再定维护窗口。

## 16. 假设、风险、待确认

### 已锁定

- Q2：跨模块（含节点管理/监控/告警）与 CMDB 前后端 = UUID 唯一定位实例；后端内部可保留 `_id` / `inst_id` 工作集。  

### 假设（未反对则随整约一并批准）

- Q1 成功标准含图重建后引用稳定。  
- Q3 边存端点 UUID。  
- Q4–Q7、Q9 按 [GRILL_DECISIONS.md](./GRILL_DECISIONS.md)。  
- 前端**代码改动**延期到后端契约定稿后评估；最终交互契约已定为 UUID。  
- OA 字段默认改名 `bk_inst_uuid`。  
- 不提供仓外数字入参短废弃窗。  

### 仍可在批准时批注修改

1. OA 字段命名是否改为「保留 `bk_inst_id`、值改 UUID」。  
2. 是否破例增加仓外短废弃窗（须写截止日期）。  

### 风险

- 创建旁路遗漏 → 无 UUID 实例；用清单+测试封闭。  
- 仓外/旧前端客户端破坏 → 发布说明；前后端同版本切换。  
- 图无属性唯一约束 → 应用查重 + verify。  
- 内部 `_id` 泄漏到响应 → 序列化契约测试强制剥离。  

## 17. 相对参考设计的取舍

| 来源 | 采纳 | 否决/修改 |
|---|---|---|
| 08-02 双身份无限期 | — | **否决**；最终态对外只 UUID |
| 08-02 边存 UUID | 采纳 | — |
| 08-02 受控带入 UUID 产品化 | 仅保留内部迁移形状 | 本阶段不交付仓外带入 API |
| 08-02 发版一次性转换 | 采纳 | — |
| 旧实现「边不存端点」 | — | 否决（契约采用边存 UUID） |
| 旧实现「对外 UUID、文档却含糊」 | 对外 UUID | **明确**内部可用 `_id`/`inst_id`，避免再写「图 ID 完全消失」造成实现与文档打架 |
| 旧实现「大爆炸」 | — | 契约确认后分票；前端后置 |

## 18. 推荐实施步骤（确认契约后，不在本阶段执行）

1. 身份纯函数与创建必经路径封闭（含采集/PC 旁路）。  
2. 图 Adapter：UUID 索引、按 UUID 查询、边 UUID 属性。  
3. Instance 服务与 OpenAPI/NATS。  
4. PG schema + 迁移命令 + 启动维护编排。  
5. 跨模块：订阅、配置文件、OA、告警、OpsPilot、Stargazer。  
6. 前端评估与改动（独立变更）。  
7. 副本演练与发布。

## 19. 确认栏

- [x] **批准本契约**（含已锁定 Q2 与 §16 假设） — 2026-08-10  
- [ ] 批准但修改：_______________  
- [ ] 驳回，回到 grill：_______________  

**已批准。** 实现须另开实现 Plan（tracer-bullet）；未开 Plan 前仍不改业务代码、启动脚本、前端与 worktree 旧实现。  
验收与设计争议以本文 + [BASELINE_INVENTORY.md](./BASELINE_INVENTORY.md) + [GRILL_DECISIONS.md](./GRILL_DECISIONS.md) 为准。
