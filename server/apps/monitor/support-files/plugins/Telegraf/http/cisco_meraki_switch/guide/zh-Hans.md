# Cisco Meraki 交换机 接入指南

本插件通过 Telegraf `inputs.prometheus` 从 Stargazer 拉取 Meraki Dashboard API v1 指标，覆盖交换机端口总览、分交换机端口与功耗历史。端口总览与分交换机端口为必选接口，失败时导出 `meraki_switch_connect_status=0`；功耗历史可软失败。空 `portId` 的端口会被跳过。端口启用/PoE 状态按启用、禁用展示。

## 前置条件

- 已准备只读或监控用途的**组织 API 密钥**。密钥通过 `X-Cisco-Meraki-API-Key` 传递。
- 选定节点可以访问对应区域 Dashboard API：`api.meraki.com / api.meraki.in / api.meraki.ca / api.meraki.cn / api.gov-meraki.com`。
- 已确认目标组织 ID，并且该密钥对该组织有读取权限。
- 采集间隔建议 ≥ 120 秒，避免触发每组织 10 次/秒的 API 预算；遇到 HTTP 429 时采集器会按 `Retry-After` 退避。

## 配置步骤

1. 选择区域端点。中国、印度、加拿大与美国政府区域使用对应主机，不要混用。
2. 填写组织 ID 和组织 API 密钥。不要把密钥写入 URL。
3. 选择容器采集节点（需能访问 Stargazer 与 Dashboard API）。
4. 保存后等待至少一个采集周期。

## 本插件调用的 API

- `GET /organizations/{id}/switch/ports/overview`
- `GET /organizations/{id}/switch/ports/bySwitch`
- `GET /organizations/{id}/summary/switch/power/history`

分页遵循响应头 `Link: rel=next`。

## 验证

至少等待一个采集周期后，确认实例出现，并检查连接状态类指标是否持续上报。
