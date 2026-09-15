# Cisco Meraki 接入指南

本插件通过 Telegraf `inputs.prometheus` 从 Stargazer 拉取 Meraki Dashboard API v1 指标。一次接入使用同一套组织 API 密钥与区域端点，在单个 `/cisco_meraki/metrics` 入口顺序采集组织、设备、无线 AP、交换机与 MX（安全设备）指标族。组织级失败会导出全部 `connect_status=0`；设备/无线/交换机/MX 分族失败只将该族 `connect_status` 置 0。

## 已有实例须重新配置（破坏性变更）

原先五个并列插件（Cisco Meraki Organization / Device / Wireless AP / Switch / Appliance）已下线，合并为网络设备下的单一 **Cisco Meraki** 能力。`plugin_init` 会清理旧插件与清单对象，**已接入的五个独立实例不会自动迁移**。

升级后请：

1. 停用并删除旧的五个并列接入实例（若控制台仍能看到残留项）。
2. 在 **网络设备 → Cisco Meraki** 下用同一套组织 API 密钥与区域端点重新接入。
3. 保存后等待至少一个采集周期，在 Network / Device / Wireless AP / Switch / Appliance 子视图核对五族指标。

Prometheus 指标名仍为 `meraki_*`；采集入口改为 `/cisco_meraki/metrics`。不要继续配置已下线的五个独立插件。

## 前置条件

- 已准备只读或监控用途的**组织 API 密钥**。密钥通过 `X-Cisco-Meraki-API-Key` 传递。
- 选定节点可以访问对应区域 Dashboard API：`api.meraki.com / api.meraki.in / api.meraki.ca / api.meraki.cn / api.gov-meraki.com`。
- 已确认目标组织 ID，并且该密钥对该组织有读取权限。
- 采集间隔建议 ≥ 120 秒。一次采集会连续请求多个 Dashboard 端点，过短更容易触发每组织 10 次/秒的 API 预算；遇到 HTTP 429 时采集器会按 `Retry-After` 退避。

## 配置步骤

1. 选择区域端点。中国、印度、加拿大与美国政府区域使用对应主机，不要混用。
2. 填写组织 ID 和组织 API 密钥。不要把密钥写入 URL。
3. 选择容器采集节点（需能访问 Stargazer 与 Dashboard API）。
4. 保存后等待至少一个采集周期。接入后可在 Cisco Meraki 对象页签中查看 Network / Device / Wireless AP / Switch / Appliance 子视图。

## 本插件调用的 API

- `GET /organizations/{id}`
- `GET /organizations/{id}/networks`
- `GET /organizations/{id}/devices`
- `GET /organizations/{id}/devices/availabilities`
- `GET /organizations/{id}/devices/uplinksLossAndLatency`（可选，失败不影响该族健康）
- `GET /organizations/{id}/wireless/devices/ethernet/statuses`
- `GET /organizations/{id}/wireless/devices/packetLoss/byDevice`
- `GET /organizations/{id}/switch/ports/overview`
- `GET /organizations/{id}/switch/ports/bySwitch`
- `GET /organizations/{id}/summary/switch/power/history`（可选）
- `GET /organizations/{id}/appliance/vpn/statuses`
- `GET /organizations/{id}/appliance/vpn/stats`（可选）
- `GET /organizations/{id}/summary/top/appliances/byUtilization`（可选）

分页遵循响应头 `Link: rel=next`。

## 验证

至少等待一个采集周期后，确认实例出现，并检查 `meraki_org_connect_status` 以及各指标族的连接状态是否持续上报。
