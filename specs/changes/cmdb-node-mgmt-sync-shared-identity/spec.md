# CMDB 节点管理同步默认打开，并与多模块联动共用身份

Status: implemented

## Completion evidence

- 共用身份：`server/apps/cmdb/services/host_sync_identity.py`（`node_id` → `cmdb_id` → ip+cloud；实例名 `{ip}[{云区域}]`）。
- 节点→CMDB ingest 与拉同步 `_persist_hosts` 走同一套认领；节点来源忽略节点名；拉同步创建写 `node_id`、不写 `monitor_id`、`schedule_post_actions=False`，写入后回填 `Node.cmdb_id`。
- `PUSH_LINKAGE_REPLACES_PULL_SYNC = False`；`NodeMgmtSyncConfig.auto_sync_enabled` 字段默认 `True`（迁移 `0047` 只改默认，不刷现网已有行）。节点管理「推送到 CMDB」勾选不变。
- 验证（2026-08-13）：`uv run pytest apps/cmdb/tests/test_node_mgmt_sync_*.py apps/cmdb/tests/test_module_ingest_*.py apps/cmdb/tests/test_host_sync_identity.py apps/node_mgmt/tests/test_module_link.py apps/node_mgmt/tests/test_node_module_ingest.py apps/node_mgmt/tests/test_module_push*.py -q --no-cov` → 413 passed, 2 skipped。

## Problem Statement

多模块联动上线时，为避免和「用户勾选是否推送」双写，CMDB 把节点管理拉同步关掉了。现在需要默认重新打开：节点仍要镜像成 CMDB 主机库存。直接拨开关会和推送抢同一台主机——拉同步只按 ip+cloud 匹配且不写 `node_id`，推送按 `node_id` 匹配且实例名优先用节点名，并发时会重复建实例或把名称来回改。

## Solution

拉同步默认打开，作为 host 库存管道；勾选框仍控制即时推送和监控，不再表示「取消勾选则 CMDB 里不能有这台主机」。拉同步与节点→CMDB 推送共用同一套认实体规则和同一套主机字段：业务身份是 **ip + 云区域**，硬关联补上 **`node_id`**，实例名统一为 `{ip}[{云区域}]`。命中同一条则更新，禁止双建。

## User Stories

1. As a CMDB 管理员, I want CMDB「节点管理同步」任务默认开启, so that 新环境不用再手动打开就能把节点镜像成主机库存。
2. As a 节点管理员, I want 取消勾选推送到 CMDB 时节点仍能被拉同步写入主机, so that 库存完整，且之后再推送是更新同一条而不是新建。
3. As a 平台用户, I want 拉同步和节点推送按同一套规则认同一台主机, so that 先拉后推、先推后拉或并发都不会出现两条 host。
4. As a CMDB 用户, I want 从节点进入的主机实例名是 IP 加云区域, so that 两条管道写出的显示名一致，不会周期来回改。

## Implementation Decisions

### 取代的一期决定

- 取代 `node-cmdb-monitor-push-linkage` 中「推送就绪后关闭并退役 NodeMgmtSync」和「取消勾选则 CMDB 绝不出现该主机」。
- 勾选「推送到 CMDB」仍表示即时推送；不勾选时拉同步仍可建/更新 host。
- 勾选「推送到监控」、无级联暗建、lifecycle 清指针不删 CMDB 实例，均保持不变。

### 共用认实体（仅 host）

拉同步持久化与节点→CMDB ingest 必须走同一套解析，禁止再各写一套匹配键。

1. 有 `node_id` → 只按 `node_id` 查找。
2. 否则有 `cmdb_id` → 只按 CMDB 实例 ID 查找。
3. 都未命中 → 按 **ip + cloud** 认领。缺少 ip 或 cloud 则跳过该节点，不新建。
4. 认领对象已绑定别的 `node_id` → `link_conflict`：跳过，不合并、不新建。
5. 创建撞唯一规则 → 当作认领/更新，不得当成第二条主机。

### 共用写入（仅 host）

- `inst_name` = `{ip}[{云区域名}]`；无云区域名时用云区域 ID。节点→CMDB 推送忽略节点名称。
- `ip_addr`、`cloud`、`os_type`、`organization` 取自当前节点快照；两边公式一致。
- `node_id`：新建必写；已有为空则补；已有且相同则保持；冲突不覆盖。
- `monitor_id`：拉同步不读不写；只由推送/监控路径维护。
- 现网已用节点名当实例名的 host，下次拉同步或节点再推一律改成 `IP[云区域]`。

### 回填与钩子

- 拉同步写入 host 后，按已有 `node_id` 回填 `Node.cmdb_id`（只关联、不创建节点）。
- 拉同步创建/更新仍不跑主机创建钩子，不得因此通知监控或暗建监控对象。
- 不把拉同步改成直接调用 ingest；采集任务、`source` 等仍走拉同步自己的持久化。抽共用的「找主机 + 算实例名」。

### 默认打开

- 打开的是 **CMDB「节点管理同步」任务**（`NodeMgmtSyncConfig.auto_sync_enabled` + 周期 Beat），不是节点管理「推送到 CMDB」勾选。
- 新库：`auto_sync_enabled` 默认 `True`；关掉 `PUSH_LINKAGE_REPLACES_PULL_SYNC`，reconcile 会注册拉取周期任务。
- 不刷现网已有配置行。现网若单例仍是 `False`，在 CMDB 页面打开即可。
- `auto_collect_enabled` 本变更不改。节点管理推送默认勾选也不改。

### 范围与删除

- 只覆盖 **host**。网络设备 / 物理服务器 IPMI 仍只走推送。
- 拉同步不因节点从源侧消失而删除 CMDB 主机。节点删除以及拉同步发现源侧 sidecar 节点已消失时，都只清 `node_id`，不删实例。IPMI/RPC 等非 sidecar `node_id` 不在此列。

## Testing Decisions

只验外部行为：同一节点不会落成两条 host、实例名格式、默认打开、冲突跳过。不测内部函数拆分方式。

优先沿用现有服务缝：拉同步持久化/认领、CMDB host ingest、节点关联回填。补齐而不是另起一套测试风格。

必测：

- 新配置 `auto_sync_enabled` 为 `True`；采集开关不变；节点推送勾选不变。
- 节点→CMDB：实例名为 `IP[云区域]`，写入 `node_id`，回填 `Node.cmdb_id`。
- 先拉后推、先推后拉、同步已加载后再推导致撞唯一：均为同一条 host。
- 取消勾选推 CMDB：拉同步仍建库存且带 `node_id`；之后再推是更新。
- ip+cloud 已绑定别的 `node_id`：跳过，不覆盖、不新建。
- 拉同步不改已有 `monitor_id`，不触发监控新建。

## Out of Scope

- 打开或关闭自动采集。
- 网络设备 / IPMI 拉同步。
- 监控对象命名。
- 拉同步删除 CMDB 主机，或改变 lifecycle 删实例策略。
- 跨模块主键切到 `inst_uuid`。
- 拉同步存量的一次性清洗任务（靠打开后的周期同步 + 推送认领收敛）。
- 把拉同步整条管道替换成 ingest。

## Further Notes

- 一期联动规格仍描述推送、勾选监控、lifecycle；其中「退役拉同步」以本变更为准。
- 监控手建→CMDB、CMDB 手建→监控的实例名规则不在本变更修改；一旦该 host 也被节点管道命中，实例名按本规则改为 `IP[云区域]`。
