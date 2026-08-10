# CMDB PC 配置采集简化

## 意图

在明确“一台 PC 只属于一个采集任务”的产品边界下，移除多任务权威来源状态机，补齐 PC 硬件字段、快照时间、状态聚合与脚本采集缺口，使配置与软件采集形成可验证闭环。

## 产品边界

- 支持 Windows/WinRM 与 macOS/SSH。
- 一个任务一种 OS。
- 不支持多个任务采集同一 PC；任务配置与资产范围由用户负责避免重叠。
- 不考虑删除原任务后，由新任务重新接管同一台已保留 PC 的场景。
- 手工任务动作同步 VictoriaMetrics 已上报的最新结果，不承诺立即远程采集。
- 删除任务不级联删除图中的 PC 或软件资产。

## 数据设计

- PostgreSQL 只复用 `CollectModels`，不新增 PC 业务表。
- 不引入 `PCDiscoveryAuthority`；移除尚未提交的模型与迁移，以及对应的移交 API、来源冲突、删除任务保护和快照水位实现。
- 图中复用 `pc`，新增/保留 `pc_software`，通过 `install_on` n:1 关联 PC。
- `collect_task` 仅是创建来源/历史字段，不作为并发控制依据。
- PC 与软件的 `last_collect_time`、运行字段 `collect_time` 统一取 Server 解析出的快照指标时间。

## 行为规则

1. PC 按规范化硬件 UUID 标识；UUID 无效时使用序列号。
2. 软件实例 ID 由 PC 身份和稳定软件 key 派生。
3. PC 和软件仅更新采集白名单字段，保护人工资产字段。
4. 每台 PC 独立解析和对账；一台失败不阻断其他 PC。
5. complete 快照且软件写入无失败时才允许差集删除。
6. 差集范围必须限定为当前 PC 的 `install_on` 软件集合。
7. partial 快照可更新但不删除，并使任务为 `PARTIAL_SUCCESS`。
8. `after_expiration` 只删除任务来源 PC 下过期软件，永不删除 PC。
9. Windows/macOS 都必须采集 CPU、内存和磁盘容量；Windows 无论 UUID 是否有效都采 BIOS 序列号。
10. 查询不到任何 PC 快照时任务为失败，并提示检查目标采集和数据上报时间。
11. Stargazer 只允许读取并下发 PC 插件目录中的四个内置发现/身份脚本，拒绝任意路径。
12. 本轮新建的软件实体若 `install_on` 关联失败，必须补偿删除，避免留下孤立节点。

## 已移除

- `PCDiscoveryAuthority` 模型和表；
- `PCAuthorityService` / `PCAuthorityDecision`；
- `pc_handover` API；
- `SOURCE_TASK_CONFLICT`、`STALE_SNAPSHOT`、`source_conflict`；
- 删除采集任务前的 PC 权威归属校验。

## 测试接缝

- `PCInventoryCollector`：脚本输出、身份、资源边界、错误脱敏。
- `parse_pc_vm_rows`：快照聚合、最新轮次、完整性降级。
- `PCSnapshotReconciler` / `apply_pc_snapshots`：白名单、时间、关联、差集删除和失败隔离。
- `_decide_collect_exec_status`：全失败、混合、partial、完整空快照。
- `model_config.xlsx`：`pc_software` 字段与 `install_on` 关联。
- PC Web 静态契约：动作明确显示“同步最新结果”。

## 验收

- 上述目标测试通过率不低于 80%，目标是全部通过。
- Django migration state 无漂移。
- 当前生产代码、迁移、测试与现行架构文档不再引用权威模型、移交端点和冲突错误码；
  `docs/reviews`、`docs/superpowers` 中带日期的历史评审/计划/旧规格保留原始记录。
- Windows/macOS 采集脚本保持只读并通过静态安全合同。
