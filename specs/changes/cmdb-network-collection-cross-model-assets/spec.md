# CMDB 网络采集跨模型选择资产

Status: done

## Problem Statement

运维创建 Network 采集任务并打开「是否采集关系」后，希望一次任务覆盖交换机、路由器、防火墙和负载均衡上的拓扑邻居。当前「选择资产」只能从四个模型里点开其中一个，确认后会覆盖已选列表，无法把不同模型的实例放进同一任务。拓扑重放只使用本任务已入库的接口，分任务采集会导致跨模型邻居无法建边。

## Solution

Network 任务在「选择资产」时允许同时勾选交换机、路由器、防火墙、负载均衡四个模型，查询这些模型下的实例并合并进同一任务。设备通道和拓扑通道继续共享这批目标。选择 IP 段的路径保持不变。网络设备配置文件采集仍按原单模型下拉选择。

## User Stories

1. As a CMDB 管理员, I want 在 Network 任务的选择资产里同时勾选交换机、路由器、防火墙和负载均衡, so that 一次任务能覆盖多种网络设备模型
2. As a CMDB 管理员, I want 资产抽屉能查出已勾选模型下的实例并带上对象类型, so that 我能区分不同模型的同名或相近资产
3. As a CMDB 管理员, I want 确认选择时保留其他模型里已经勾过的实例, so that 换模型继续选时不会把前面的选择清掉
4. As a CMDB 管理员, I want 同一任务里重复的管理 IP 被拒绝, so that 下发不会对同一地址采两次
5. As a CMDB 管理员, I want 打开拓扑采集后这批混模资产进入同一拓扑通道, so that 交换机和路由器之间的邻居能在本任务内建边
6. As a CMDB 管理员, I want 选择 IP 段和网络设备配置文件采集的选资产方式保持原样, so that 这次改动不扩大到无关任务

## Implementation Decisions

- 允许的资产模型固定为 `switch`、`router`、`firewall`、`loadbalance`。不按 `interface --belong--> 模型` 动态发现自定义网络模型。
- 只改 Network 采集任务（任务族 `model_id=network`）的资产模式。任务仍是一条 CollectModels 记录；设备通道和拓扑通道继续共享目标和凭据，不新增第二条页面任务，不改 Stargazer 插件。
- 资产查询继续使用现有按单模型搜索接口。前端对已勾选模型并发查询，把当前页结果拼接进同一张表；分页页码对每个模型相同，总数为各模型 count 之和。不新增跨模型搜索 API。
- 选择资产的确认语义是按 `inst_uuid` 合并：当前页未勾选的实例从已选列表移除，当前页勾选的实例加入，未出现在当前页的已选实例保留。不得整表覆盖。
- 已选列表和抽屉表都展示对象类型。四个模型的展示名沿用现有网络设备文案。
- 提交后的 `instances` 仍是实例快照列表，每条带自己的 `model_id`、`inst_uuid`、`ip_addr`。服务端在身份规范化之后校验：仅允许上述四个模型、每条必须有管理 IP、同一任务内管理 IP 不得重复。IP 段模式（`instances` 为空）不走这条校验。
- 非这四个模型的实例、缺少管理 IP、重复管理 IP，创建和更新都拒绝，错误挂在 `instances` 字段。
- 目标构建和下发继续按实例管理 IP 拼成主机列表。混模列表里各实例的 `model_id` 进入目标快照，但 Stargazer 仍只按 IP 采集。
- 入库身份仍按采集生成的 `{ip}-{device_type}` 和 OID 特征库分类，不在本期改成按选中 `inst_uuid` 回写。
- 网络设备配置文件任务继续使用原来的单模型下拉，不接入这次的多选合并。
- 选择资产的合并、重复 IP 判断、允许模型集合放在独立 seam，供页面和测试共用；`baseTask` 只负责渲染和请求。

## Testing Decisions

只测外部行为：用户能选哪些模型、提交的实例快照含哪些字段、非法目标是否被拒绝、下发主机列表是否包含混模 IP。不把抽屉内部 state 名称或请求顺序当契约。

测试 seam：

- Web：网络资产选择纯函数（允许模型、合并选择、重复 IP、拼接搜索页）以及选择资产抽屉不得用 `100vh` 估高。对标 SNMP 拓扑周期的 `professCollection` 常量测试。
- Server：Network 任务实例校验策略，以及序列化器在创建/更新时的拒绝与放行。对标 SSL 证书任务和网络配置文件的实例校验测试。
- Server：混模实例构建采集目标、设备/拓扑节点配置仍共享同一批主机。对标 `CollectTargetService` 与 Network 双通道节点参数测试。
- 不测 Stargazer 插件、拓扑解析算法、OID 分类和按 `inst_uuid` 回写。

### Web（9）

1. 允许模型集合恰好是 switch、router、firewall、loadbalance。
2. 合并选择：已选路由器加上当前页新勾选的交换机后，两个都在；当前页取消勾选的交换机会去掉，未出现在当前页的路由器仍保留。
3. 同一 `inst_uuid` 再次勾选不产生重复行。
4. 两条已选资产管理 IP 相同则判定为重复。
5. 管理 IP 比较忽略首尾空白。
6. 拼接两个模型的搜索页时，行按模型查询顺序排列，总数为 count 之和。
7. 未勾选任何模型时不发出查询，结果为空。
8. 中英文都有对象类型、设备模型多选和重复 IP 的文案。
9. 选择资产抽屉按父容器铺满表格，不得再用 `calc(100vh - …)`，避免设备模型多选把总数和分页裁出可视区域。

### Server（10）

1. 资产模式提交 switch + router 实例，校验通过，快照保留各自 `model_id` 和 `ip_addr`。
2. 四个允许模型都可以单独通过。
3. 提交 host 或其他非允许模型，拒绝。
4. 实例缺少管理 IP，拒绝。
5. 两个实例管理 IP 相同（含首尾空白），拒绝。
6. `instances` 为空且带 IP 段时不跑资产模型校验。
7. 更新已有 Network 任务为混模资产时，同样拒绝非法模型与重复 IP。
8. `CollectTargetService` 对 switch + router 产出两个目标，`model_id` 取实例而不是任务族 `network`，object_key 仍按 SNMP 的任务+主机+端口。
9. 设备节点配置 `get_hosts` 把混模实例的管理 IP 拼进同一主机列表。
10. 开启拓扑后，拓扑节点配置与设备通道使用同一批主机。

## Out of Scope

- 自定义或未在四个列表中的网络设备模型
- 新增跨模型实例搜索 API
- 网络设备配置文件采集的选资产交互
- 按选中 `inst_uuid` 更新原资产，而不是按 `{ip}-{device_type}` 对账
- 修改 Stargazer、拓扑解析、OID 特征库或双通道容量舱壁
- 选择 IP 段时按模型过滤扫描范围

## Further Notes

- IP 段模式本来就会按 OID 把设备写入多个模型；本期只补齐资产模式，让拓扑任务也能显式选中已有的跨模型实例。
- 拓扑重放按本任务 `collect_task` 加载接口。混选的产品价值是把邻居放进同一个 Network 任务，而不是改解析器。
- 四个模型与网络配置文件采集的允许模型集合一致，但两条任务的选择交互仍然分开。

## Verification Evidence（2026-09-21）

- Server：`test_network_collection_asset_policy.py`、`test_network_collection_asset_serializer.py`、`test_collect_target_uuid_contract.py::test_snmp_targets_keep_instance_model_not_task_family`、`test_network_channel_split.py::test_device_and_topology_share_mixed_model_hosts` 通过。
- Web：`networkAssetSelection.test.ts` 9 passed；既有 `snmpTask.test.tsx` 12 passed。
- 浏览器端到端未跑：本地没有可用的采集页面会话。选择资产抽屉已改为 flex 铺满剩余高度，CustomTable 按父容器计算表体，分页和「共 N 条」应出现在抽屉底部。
