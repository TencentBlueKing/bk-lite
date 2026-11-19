# 节点退出后监控停采待处理

Status: implemented

2026-11-18 修订：同一节点之后的每次心跳都会再尝试挂回，失败不阻断心跳。`node_id` 唯一约束冲突时跳过这一台的关联，其余配置仍挂回并清掉快照。存量恢复命令把实例上还在的 `node_id` 抄到没有身份的配置上，再清空实例上的 `node_id`；两边都没有身份时报告 `node=none`，不编造节点。

## Problem Statement

节点管理页面删除节点或远程卸载控制器后，监控把联动主机写成 `is_deleted=True`、`is_active=False`，主机从资产列表消失。采集配置正文仍在节点管理的 `ChildConfig`，监控 `CollectConfig` 也还在，但用户看不到、清除不了，也换不了节点。同一台机器再推送时监控另建一台 uuid 实例，旧行仍占着 `cmdb_id`；主机接入页撞上旧主键时会物理删除旧行和它的配置。页面删除不停控制器，旧节点心跳会按原节点 ID 建回一个没有 `monitor_id` 的空节点。远程卸载不清 CMDB 主机的 `node_id`。离线只在节点列表显示，监控不知道。

监控的清除、更换采集节点直接导入节点管理服务并读 `Node` 表；更换时只校验节点存在，不校验当前用户对目标节点的权限。

## Solution

节点删除和远程卸载把监控实例停在「停采待处理」：实例留在列表，配置保留，采集节点列标注已删除，不再产生无数据告警。同一台机器回来时接回原实例和原配置。离线只在采集节点列展示，不进退出流程。监控和日志的清除、更换用 `NodeMgmt(is_local_client=True)` 在本进程调用 `apps/rpc/node_mgmt.py` 已注册的 NATS 方法。

## Implementation Decisions

### 状态

- 停采待处理不新增实例字段。实例至少有一条 `CollectConfig` 且全部 `executor_node_removed=True`，即为停采待处理。
- 离线：节点仍在，`updated_at` 超过 60 秒。监控实例、配置、告警都不改。
- 用户在监控里删除实例仍按 ADR 0002 物理删除。

### 删除与卸载

- `MonitorCollectorNodeExit.on_node_removed` 在一个监控库事务内：联动主机（`node_id` 命中或 `id == node.monitor_id`）只清 `node_id`，不写 `is_deleted`/`is_active`；本次 `config_ids` 内的 `CollectConfig` 全部写 `executor_node_removed/executor_node_id/executor_node_name`，包括联动主机自己的配置；关闭活动告警保留。
- 远程卸载成功、删除节点前，调用与页面删除相同的 `best_effort_unlink_cmdb`，授权组织用 `actor_scope_with_instance_orgs` 从节点自身组织补齐。两条路径都只清 CMDB 主机 `node_id`，`monitor_id` 不变。
- 日志退出行为不变。

### 节点管理 NATS 方法

在 `server/apps/node_mgmt/nats/node.py` 注册，在 `apps/rpc/node_mgmt.py` 加同名方法：

- `delete_owned_child_configs(config_ids)`：沿用 `NodeCollectionExitService.delete_owned_configs`，删子配置，父配置无剩余子配置才删。
- `move_child_configs_to_node(config_ids, node_id, owner_config_ids, organization_ids)`：沿用 `move_configs_to_node`；目标节点不在组织范围内则拒绝。
- `get_child_config_nodes_by_ids` 返回的每个节点增加 `active`，规则与节点列表一致（60 秒）。已删除快照节点响应带 `removed: true, active: false`。

### 监控与日志

- `MonitorCollectorNodeExit.clear/reassign`、`LogCollectorNodeExit.clear/reassign` 用 `NodeMgmt(is_local_client=True)` 在本进程调用上述已注册 NATS 方法，不再导入节点管理服务或读 `Node` 表。
- `reassign` 先经 `get_authorized_nodes_by_ids` 按当前用户权限校验目标节点，查不到拒绝。

### 策略

- 停采待处理实例从无数据检测中排除；阈值检测不改；离线实例不排除。

### 节点回来

- 同一节点 ID 心跳重建：`sidecar.py` 的 `_notify_collectors_node_returned` 在 `create_default_config` 之后（与 `_consume_deferred_module_push` 同处，事务外），失败不阻断心跳。监控按 `executor_node_id` 找配置，经 `NodeMgmt(is_local_client=True)` 挂到该节点，清快照，把主机实例 `node_id` 写回，并回填 `Node.monitor_id`。日志按 `removed_collector_node_id` 同样挂回。环境安装身份已登记被拒绝的情况不处理。
- 重装后同云区域、同 IP 节点推送：ingest 命中已有实例且主机 Telegraf/host 配置全部带已删除标记时，在 ingest 事务外把停采主机配置挂到新节点并清标记。挂回失败会让该次推送报错。
- 主机接入页再接同 IP：已有实例主机配置全部带已删除标记时，挂到所选节点，不报已存在、不物理删除。
- 日志、数据库等另建采集不按 IP 自动挂回。

### 采集节点列

- 监控资产列表在采集模板列后加「采集节点」列，按节点 ID 去重：在线显示名称；`active=false` 标注离线；已删除快照节点（`removed: true, active: false`）标注「采集节点已删除」；无节点显示「未关联」。清除、更换按钮保持现位置。

### 存量与删除项

- 存量命令 `python manage.py restore_node_exit_parked_hosts`：默认 dry-run；`--apply` 把 `is_deleted=True,is_active=False` 且有 `CollectConfig`、同对象同 IP 同云区域无活实例的行恢复为活实例，并把配置标 `executor_node_removed=True`。冲突只报告、不落库；节点列仍用同一套身份，两边都没有才是 `node=none`。局限：候选不区分软删来源；两条同 IP 软删行之间不判冲突。
- 删除 `module_ingest.py` 的 `_retired_by_node_exit`（不再对软删行另建 uuid）、`_handle_lifecycle` 的 node_mgmt 软删分支（node_mgmt 来源 lifecycle 直接 skipped）、`module_push.py` 的 `best_effort_retire_linked` / `parse_retire_linked_flag`、前端 `retireLinkedConfirm`。`retire_linked` 查询参数被忽略。
- 更新 `legacy-ard-modules-monitor.md`、`legacy-ard-modules-node-mgmt.md`、`legacy-ard-modules-cmdb.md` 中与节点退役软删监控相关的句子。

### 上线顺序

- 部署完成后，立即对生产跑 `python manage.py restore_node_exit_parked_hosts`（默认 dry-run）。
- 人工确认报告，重点看冲突与同 IP 重复候选，再执行 `--apply`。
- 必须立即跑：旧软删行若在命令前被推送命中，会被 `_update_instance` 恢复，但配置没有已删除标记，不会挂到新节点，会无数据。

## Testing Decisions

行为测试覆盖：

- 删节点后主机仍在列表（`is_deleted=False`），配置带快照，`ChildConfig.content` 保留，无数据告警不再产生。
- 远程卸载同样结果，并调用 CMDB 解绑。
- 同一节点 ID 重建后配置挂回新默认父配置、标记清除、`Node.monitor_id` 回填、主机实例 `node_id` 写回。
- 重装同 IP 推送后监控只有一台实例且配置挂到新节点。
- 接入页同 IP 再接走挂回。
- 更换到组织外节点被拒绝。
- 离线节点不打标、不关告警，NATS 返回 `active=false`。
- 管理命令 dry-run 不写库，`--apply` 只恢复无冲突行。

## Out of Scope

- 采集器卸载任务（`uninstall_collector` 仍为空）。
- 本机卸载回调平台。
- 共享父配置在部分节点离开后的拆分。
- CMDB `Node.cmdb_id` 在节点重建后的回填（由下一次推送或拉同步处理）。
