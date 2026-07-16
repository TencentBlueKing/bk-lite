# Task 7 节点采集参数补偿式对账报告

## 状态

已完成。节点采集参数按配置版本和云区域持久化两阶段状态，关闭只删除，开启先删除再推送；失败保留阶段供下一轮安全重试。

## 合同

- 区域 ID 只接受 `system_code` 的 `node_mgmt_sync_host_collect_` 后纯 ASCII 数字；非法编码不猜测字段，配置聚合为 `degraded`。
- 区域幂等键固定为 `config:{version}:region:{id}`。
- `auto_collect_enabled=false`：`delete_pending -> disabled`，绝不 push。
- `auto_collect_enabled=true`：`delete_pending -> push_pending -> healthy`；delete 失败保留 `delete_pending`，push 失败保留 `push_pending`，下一轮从对应阶段重试。
- collect 开启但 sync 关闭：`waiting_sync`，不产生 delete/push 外部调用。
- 没有区域采集任务：`unknown`，不把未执行状态标成健康。
- 任一区域失败：配置聚合为 `degraded`；全部成功时按开关聚合为 `healthy` 或 `disabled`。
- 配置健康状态使用 `pk + version` 条件更新；旧版本完成不能覆盖当前版本。
- 错误只持久化稳定 reason、异常类型和固定摘要；节点参数、凭据、RPC 原始结果和异常原文不进入日志。

## 变更文件

- `server/apps/cmdb/services/node_mgmt_sync_reconciler.py`
- `server/apps/cmdb/services/collect_service.py`
- `server/apps/cmdb/tests/test_node_mgmt_sync_node_config.py`

## TDD 与验证

- RED：新增合同首轮 `9 failed, 1 passed`；强化日志检查后日志合同单测也稳定 RED。
- GREEN：Task 7 聚焦 `10 passed`。
- reconciler + Task 7：`20 passed`。
- Task 2–7 组合（models/views/reconciler/helpers/persistence/resilience/execution/node_config）：`157 passed`。
- 覆盖率：新增生产可执行行 `81/88 = 92.05%`；`node_mgmt_sync_reconciler.py` 模块覆盖率 `94%`。
- 静态门禁：新增 reconciler/测试通过 black、isort、flake8；`git diff --check` 通过。

## 已知基线

`collect_service.py` 全文件 flake8 仍有一个未触及的历史 `ProtocolCollect` F401；本任务为保持最小 diff 未顺手清理。
