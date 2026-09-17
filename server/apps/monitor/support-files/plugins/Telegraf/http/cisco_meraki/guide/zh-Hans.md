# Cisco Meraki 接入指南

Cisco Meraki 是网络设备下的单一监控能力。在 **网络设备 → Cisco Meraki** 接入一次，使用同一套组织 API 密钥与区域端点，即可采集该组织下的组织、网络、设备、无线 AP、交换机与 MX（安全设备）指标。采集器通过 Telegraf `inputs.prometheus` 从 `/cisco_meraki/metrics` 拉取 Dashboard API v1 数据，指标名为 `meraki_*`。

组织级请求失败时，各面子的 `connect_status` 均为 `0`。某一面子（设备 / 无线 AP / 交换机 / MX）单独失败时，只将该面子的 `connect_status` 置 `0`。

## 监控内容

一次接入覆盖以下面子：

- **组织**：Dashboard 连通性、网络数量
- **网络**：组织内网络清单
- **设备**：设备清单、在线状态、上行时延与丢包
- **无线 AP**：AP 数量、上下行丢包、以太网链路
- **交换机**：活跃/空闲端口、PoE 功耗
- **MX（安全设备）**：VPN 网络数、对端可达、时延与利用率

## 前置条件

- 已在 Meraki Dashboard 准备**组织 API 密钥**（只读或监控用途即可）。采集器以 `X-Cisco-Meraki-API-Key` 传递，不要把密钥写入 URL。
- 该密钥对目标组织有读取权限。组织 ID 可在 Dashboard 组织设置中查看。
- 选定的容器采集节点能访问对应区域 Dashboard API：`api.meraki.com` / `api.meraki.in` / `api.meraki.ca` / `api.meraki.cn` / `api.gov-meraki.com`。区域主机不要混用。
- 采集间隔建议 ≥ 120 秒。一次采集会顺序请求多个 Dashboard 端点；过短更容易触发每组织 10 次/秒的 API 预算。遇到 HTTP 429 时采集器会按 `Retry-After` 退避。

## 接入步骤

1. 打开监控接入，进入 **网络设备 → Cisco Meraki**，新建实例。
2. 选择与组织所在区域一致的**区域端点**。
3. 填写**组织 ID**、共享的**组织 API 密钥**、实例名称，并选择能访问 Dashboard API 的容器采集节点。
4. 保存并启动采集，等待至少一个采集周期（默认 120 秒）。

## 页面字段

| 字段 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 区域端点 | 是 | `https://api.meraki.com` | Dashboard API 区域根地址，采集器请求 `/api/v1`。 |
| 组织 ID | 是 | 无 | Meraki 组织 ID。 |
| 组织 API 密钥 | 是 | 无 | 组织级密钥，经环境变量注入请求头。 |
| 间隔 | 是 | `120` 秒 | 采集周期；过短更容易触发 API 限流。 |
| 节点 | 是 | 无 | 执行采集的容器节点。 |
| 实例名称 | 是 | 无 | 平台中的展示名称。 |
| 组 | 否 | 无 | 实例所属分组。 |

## 接入后可见内容

等待一个采集周期后，在 Cisco Meraki 对象页确认：

- `meraki_org_connect_status` 为 `1`，表示组织级 Dashboard API 调用成功。
- 主看板卡片有数：连接状态、网络数量、设备数量、无线 AP 数量、交换机活跃端口数、MX VPN 网络数。
- 可在 Network / Device / Wireless AP / Switch / Appliance 子视图查看对应指标组。

## 常见问题

### 密钥或权限失败（HTTP 401 / 403）

核对组织 API 密钥是否完整、是否属于该组织，以及是否具备读取权限。不要把密钥填进 URL 或普通请求头。

### 组织不存在或端点不匹配（HTTP 404）

确认组织 ID 正确，并且区域端点与该组织所在 Dashboard 区域一致。

### 触发限流（HTTP 429）

拉长采集间隔（建议 ≥ 120 秒）。采集器会按 `Retry-After` 退避；持续 429 时检查该组织是否还有其它高频 API 调用。

### `connect_status` 为 0 或主看板无数据

先看 `meraki_org_connect_status`。若为 `0`，组织级请求失败，各面子都不会有健康数据。若组织级为 `1` 而某一面子为 `0`，检查该面子对应的 Dashboard 权限与网络连通（例如组织未启用交换机或 MX）。

## 本能力调用的 API

采集节点需能访问以下 Dashboard API v1 路径（分页遵循响应头 `Link: rel=next`）：

- `GET /organizations/{id}`
- `GET /organizations/{id}/networks`
- `GET /organizations/{id}/devices`
- `GET /organizations/{id}/devices/availabilities`
- `GET /organizations/{id}/devices/uplinksLossAndLatency`（可选，失败不影响该面子健康）
- `GET /organizations/{id}/wireless/devices/ethernet/statuses`
- `GET /organizations/{id}/wireless/devices/packetLoss/byDevice`
- `GET /organizations/{id}/switch/ports/overview`
- `GET /organizations/{id}/switch/ports/bySwitch`
- `GET /organizations/{id}/summary/switch/power/history`（可选）
- `GET /organizations/{id}/appliance/vpn/statuses`
- `GET /organizations/{id}/appliance/vpn/stats`（可选）
- `GET /organizations/{id}/summary/top/appliances/byUtilization`（可选）
