# Historical Superpowers change: 2026-06-30-cmdb-ipam-discovery-c2

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-30-cmdb-ipam-discovery-c2.md

## 目标

按 2.7 要求把 IP 发现采集接入现有配置采集链路：子网选择作为任务输入，接入点下发到 NodeMgmt，Telegraf 调 Stargazer，结果进入 VM 后由 CMDB 拉取并回写 IPAM 台账。删除旧 NATS 回调链路。

## TDD 步骤

1. 先补红灯测试：采集对象树出现 `ipam/ip_discovery`；`NodeParamsFactory` 能为 `model_id=ip` 生成标准节点配置；Stargazer `ip_discovery` 插件能从子网推导扫描目标并输出 `ip_info` 数据；CMDB `CollectPluginTypes.IP` 能解析 VM 数据并调用 IPAM 回写服务。
2. 逐步实现绿灯：常量注册、IPAM NodeParams、Stargazer 扫描器标准化、CMDB IP 采集插件、回写服务抽取。
3. 删除旧链路：移除 `maybe_dispatch_ip_discovery`、RPC `dispatch_ip_discovery`、Stargazer `ip_scan` NATS handler、CMDB `receive_ip_discovery_result`。
4. 验证：运行新增/受影响的 server 与 stargazer 测试；完成前按 `verification-before-completion` 做新一轮验证。

## 边界

- 仅改 IPAM 发现采集相关文件。
- 不新增独立 IP 表，回写继续使用 CMDB 模型实例。
- 手工记录不被自动发现覆盖。
- 不保留旧 NATS 影子入口。

## specs: 2026-06-30-cmdb-ipam-discovery-c2-design.md

- 日期：2026-06-30
- 范围：CMDB IP 地址管理（IPAM）2.7 IP 发现采集
- 结论：IP 发现采集回归标准配置采集链路，不再使用旧的 IPAM NATS 业务回调链路。

## 背景

IPAM 2.7 要求复用现有采集任务框架，包括接入点下发、周期调度、凭据、数据清理，同时录入方式必须不同于现有「选实例」或「填 IP 段」：IP 发现应直接选择子网。

现有代码中已有一条 IPAM 专用 NATS 回调链路：

```text
sync_collect_task
  -> maybe_dispatch_ip_discovery
  -> Stargazer.dispatch_ip_discovery
  -> {namespace}.ip_scan
  -> handle_ip_scan
  -> receive_ip_discovery_result
  -> apply_discovery_result
```

这条链路绕过了标准配置采集的 node_mgmt / Telegraf / VictoriaMetrics / CMDB 拉取更新链路，导致任务摘要、数据清理、接入点下发和结果消费口径都容易分叉。本设计选择删除这条旧链路，IP 发现以标准配置采集插件形式落地。

## 目标

1. 用户创建 IP 发现任务时直接选择一个或多个子网。
2. 后端根据子网地址和掩码推导扫描范围，自动排除网络号、广播地址、网关。
3. 接入点通过 node_mgmt 下发 Telegraf 子配置。
4. Telegraf 周期请求 Stargazer，Stargazer 执行 ICMP/TCP 探活。
5. 探测结果以 Prometheus 指标写入 VictoriaMetrics。
6. CMDB 执行采集任务时从 VictoriaMetrics 拉取指标并写回 IPAM 台账。
7. ping 通或 TCP 端口通即认为该 IP 被现网使用。
8. 空闲 IP 不落库；手工记录不被自动采集覆盖。

## 非目标

1. 不保留旧 IPAM NATS 回调链路作为正式能力。
2. 不新建独立 IP 扫描任务表。
3. 不做 DHCP / DNS 联动。
4. 不做审批、维护窗口、扫描报表中心等高级治理能力。

## 标准链路

```text
创建/编辑 IP 发现任务
  CollectModels(task_type=ip, model_id=ip, input_method=SUBNET)
        │
        ▼
CollectModelService.create/update
        │
        ▼
NodeParamsFactory.get_node_params(task)
        │
        ▼
IPDiscoveryNodeParams
  subnet_ids -> cidr/gateway/scan_method/ports
        │
        ▼
NodeMgmt.batch_add_node_child_config
        │
        ▼
接入点 Telegraf 周期请求 Stargazer /api/collect/collect_info
        │
        ▼
Stargazer CollectionService
        │
        ▼
ip_discovery 插件执行 ICMP/TCP 探活
        │
        ▼
Prometheus 指标写入 VictoriaMetrics
        │
        ▼
sync_collect_task
  -> ProtocolCollect
  -> RegisteredCollect
  -> MetricsCannula
        │
        ▼
IPCollectMetrics 查询 ip_info_gauge
        │
        ▼
IPAM 台账写回
```

## 任务定义

IP 发现任务继续使用 `CollectModels`：

```json
{
  "task_type": "ip",
  "model_id": "ip",
  "input_method": 2,
  "instances": {
    "subnet_ids": [101, 102],
    "scan_method": "icmp",
    "ports": [22, 80, 443, 3389]
  },
  "access_point": [{"id": "node-id", "name": "接入点"}],
  "scan_cycle": {"value_type": "...", "value": "..."},
  "data_cleanup_strategy": "no_cleanup"
}
```

约束：

- `input_method=SUBNET` 仅对 `task_type=ip` 合法。
- `subnet_ids` 必填且支持多选。
- 子网必须属于当前组织权限范围。
- `scan_method` 支持 `icmp` 和 `tcp`，默认 `icmp`。
- `tcp` 默认端口为 `22/80/443/3389`，可配置。

## 采集对象树入口

`server/apps/cmdb/constants/constants.py` 的 `COLLECT_OBJ_TREE` 是自动发现采集对象树的社区版基线。IP 发现需要在该树中显式登记，否则 `CollectModelViewSet.tree` 返回给前端的 `collect_model_tree` 不会包含 IP 发现入口，前端也无法进入现有 `IpTask` 表单。

新增一个 IPAM/IP 发现采集节点：

```python
{
    "id": "ipam",
    "name": "IP 地址管理",
    "children": [
        {
            "id": "ip_discovery",
            "model_id": "ip",
            "name": "IP 发现",
            "task_type": CollectPluginTypes.IP,
            "type": CollectDriverTypes.PROTOCOL,
            "tag": ["Agentless", "ICMP", "TCP"],
            "desc": "按子网执行 IP 探活，发现现网已使用 IP 并写回 IPAM 台账",
            "encrypted_fields": [],
        }
    ],
}
```

说明：

- `id="ip_discovery"` 是采集对象树中的插件入口 ID。
- `model_id="ip"` 表示结果写回 IP 模型。
- `task_type=CollectPluginTypes.IP` 用于前端选择 `IpTask` 表单，也用于后端选择 `IPCollectMetrics`。
- `type=CollectDriverTypes.PROTOCOL` 表示接入点通过标准 Stargazer HTTP 采集接口执行，不需要 SSH 凭据。
- `encrypted_fields=[]`，本期 ICMP/TCP 探活不需要凭据；字段保留为后续 SNMP/ARP 增强预留入口。

`apps.cmdb.views.collect.CollectModelViewSet.tree` 不需要新增独立接口逻辑，它已经通过 `get_collect_obj_tree()` 返回 `COLLECT_OBJ_TREE` 与企业扩展合并后的结果。验收时需要确认 `/cmdb/api/collect/collect_model_tree/` 返回的树中包含 `ipam -> ip_discovery`，且前端自动发现页面点击该节点后进入 `IpTask`。

## NodeParams 下发

新增 `IPDiscoveryNodeParams` 并注册到 `NodeParamsFactory`：

```text
supported_model_id = "ip"
plugin_name = "ip_discovery"
```

职责：

1. 从 `instances.subnet_ids` 读取子网实例。
2. 组装子网扫描配置。
3. 生成标准 Telegraf child config。
4. 下发到任务选择的 `access_point[0].id`。

下发给 Stargazer 的参数建议使用子网配置，不展开完整 targets：

```json
{
  "subnets": [
    {
      "subnet_id": "101",
      "cidr": "10.0.1.0/24",
      "gateway": "10.0.1.1"
    }
  ],
  "scan_method": "icmp",
  "ports": [22, 80, 443, 3389],
  "collect_task_id": 88,
  "model_id": "ip",
  "plugin_name": "ip_discovery"
}
```

理由：大网段展开为全部 IP 后会让 headers 和配置膨胀；使用 CIDR 由 Stargazer 本地推导更稳。

## Stargazer 插件

正式插件路径：

```text
agents/stargazer/plugins/inputs/ip_discovery/
  plugin.yml
  ip_discovery_scanner.py
```

插件由现有 `CollectionService` 调用，不再注册 `ip_scan` NATS handler 作为主链路。

探测规则：

- ICMP：逐地址 Ping，通则在线。
- TCP：连接配置端口，任一端口通则在线。
- MAC：best-effort，同二层可记录，跨三层允许为空。
- 并发：默认限制，例如 50。
- 超时：设置单 IP 超时和任务总超时，避免接入点资源被拖垮。
- 保留地址：Stargazer 根据 CIDR 推导目标时排除网络号、广播地址和网关。

返回结构：

```json
{
  "success": true,
  "result": {
    "ip": [
      {
        "subnet_id": "101",
        "subnet_cidr": "10.0.1.0/24",
        "ip_addr": "10.0.1.88",
        "ip_status": "online",
        "scan_method": "icmp",
        "auto_collect": "true",
        "mac": "00:0C:29:3A:7B:88"
      }
    ]
  }
}
```

`CollectionService` 继续使用 `convert_to_prometheus_format` 输出指标。

指标示例：

```text
ip_info{
  instance_id="cmdb_88",
  subnet_id="101",
  subnet_cidr="10.0.1.0/24",
  ip_addr="10.0.1.88",
  ip_status="online",
  scan_method="icmp",
  auto_collect="true",
  mac="00:0C:29:3A:7B:88"
} 1
```

## CMDB 消费与写回

新增 `IPCollectMetrics` 和 `IPCollectionPlugin`：

```text
supported_task_type = CollectPluginTypes.IP
supported_model_id = "ip"
metric_names = ("ip_info_gauge",)
```

CMDB 执行任务时通过标准链路查询：

```text
ip_info_gauge{instance_id="cmdb_<task_id>"}
```

写回规则：

1. 探测通的 IP 认为被现网使用，写 `ip_status=online`。
2. 新发现 IP 创建 `ip` 实例，写 `auto_collect=true`、`collect_time`、`mac`、`subnet_id`。
3. 已存在且 `auto_collect=true` 的 IP 更新在线状态、MAC、采集时间。
4. 手工记录不覆盖人工字段，包括分配状态、使用人、描述等。
5. 本轮子网完整扫描成功后，原自动发现但本轮未探到的 IP 置 `offline`。
6. 扫描失败、超时、子网未完整扫描时，不做批量 offline 判定。
7. 同一 IP 多占用者或与 CMDB 对账关系冲突时置 `conflict` 或进入冲突清单。
8. 建立或维护 `subnet -> ip` 组成关联。
9. 最后回写子网容量、已用、剩余和利用率。

## 在线与空闲口径

核心口径：

```text
ping 得通 / TCP 探测通 = 该 IP 被现网使用
```

- `online`：本轮扫描探测通。
- `offline`：自动发现记录在完整扫描成功后未再探测到。
- `unknown`：未被本轮覆盖或无法判断。
- `conflict`：同 IP 多占用者或与 CMDB 对账不一致。
- 空闲 IP：不落库。

## 删除旧 NATS 回调链路

实施本方案时删除旧 IPAM NATS 旁路，不保留双链路：

- 删除 `maybe_dispatch_ip_discovery`。
- 删除 `Stargazer.dispatch_ip_discovery`。
- 删除 Stargazer `ip_scan` NATS handler。
- 删除 `receive_ip_discovery_result`。
- 将 `apply_discovery_result` 的可复用业务写回逻辑迁移到新的 IPAM 写回服务中，供 `IPCollectMetrics` 调用。
- 删除旧链路对应测试，改为覆盖标准采集链路。

这样避免同一 IPAM 数据被 NATS 回调和 VM 消费两条链路同时写入，保证任务状态、摘要、清理策略和数据口径统一。

## 前端交互

任务创建页：

- 子网多选。
- 接入点选择。
- ICMP/TCP 采集方式切换。
- TCP 端口输入。
- 周期配置。
- 数据清理策略沿用现有采集任务能力。
- 大网段扫描二次确认。
- 安全提示必现：

```text
大批量 IP 扫描可能被安全设备识别为端口扫描 / 黑客探测行为，请提前与安全部门报备并合理控制扫描范围与频率。
```

## 异常处理

- 子网不存在或无权限：任务保存失败。
- 子网地址或掩码非法：任务保存失败。
- 接入点为空或不可用：任务保存或下发失败。
- Stargazer 插件执行失败：输出失败指标或无成功结果，CMDB 任务摘要显示失败。
- 本轮扫描失败：不将历史自动发现 IP 批量置离线。
- VM 无数据：任务按现有采集框架进入错误或无有效数据状态。

## 测试策略

遵循 TDD，按模块补测试：

1. `IPDiscoveryNodeParams`：子网参数提取、CIDR 组装、接入点下发参数、阈值校验。
2. Stargazer `ip_discovery`：ICMP/TCP 判活、保留地址排除、MAC best-effort、并发和超时。
3. `IPCollectMetrics`：VM 指标解析、online/offline/conflict、手工记录保护。
4. 端到端 fixture：参考 host pipeline，覆盖：
   - Stargazer 原始结果；
   - Prometheus 指标；
   - VM 查询响应；
   - CMDB 写回结果。
5. 前端：子网多选、TCP 端口校验、安全提示、大网段确认。

## 验收口径

1. 可创建 IP 发现任务，录入方式为选择子网。
2. 不需要手填 IP 段。
3. 子网范围由后端或 Stargazer 根据 CIDR 自动推导。
4. 网络号、广播地址、网关不扫描。
5. 任务创建后能向 node_mgmt 下发 `ip_discovery` Telegraf 子配置。
6. 接入点 Telegraf 能请求 Stargazer 标准采集接口。
7. Stargazer 能执行 ICMP/TCP 探测并输出 `ip_info` 指标。
8. Telegraf 能将指标写入 VictoriaMetrics。
9. CMDB 能从 VM 拉取 `ip_info_gauge` 并写回 IPAM。
10. ping/TCP 通的 IP 自动入账并置 `online`。
11. 空闲 IP 不落库。
12. 自动发现旧记录在完整扫描成功但未探到时置 `offline`。
13. 手工记录不被覆盖。
14. 冲突能被置为 `conflict` 或进入冲突清单。
15. 子网利用率正确回写。
16. 旧 IPAM NATS 回调链路已删除，不存在双写路径。
