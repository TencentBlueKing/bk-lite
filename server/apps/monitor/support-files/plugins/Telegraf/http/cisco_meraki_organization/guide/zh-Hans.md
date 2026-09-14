# Cisco Meraki 组织 接入指南

本插件通过 Telegraf `inputs.prometheus` 从 Stargazer 拉取 Meraki Dashboard API v1 指标，覆盖指定组织、网络列表与组织健康。采集失败时仍会导出 `meraki_org_connect_status=0`，以便「API 不可用」策略生效。

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

- `GET /organizations/{id}`
- `GET /organizations/{id}/networks`

分页遵循响应头 `Link: rel=next`。

## 验证

至少等待一个采集周期后，确认实例出现，并检查连接状态类指标是否持续上报。
