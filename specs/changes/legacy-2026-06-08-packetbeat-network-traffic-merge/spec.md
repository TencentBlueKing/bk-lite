# Historical Superpowers change: 2026-06-08-packetbeat-network-traffic-merge

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-08-packetbeat-network-traffic-merge-design.md

## 背景

日志系统当前把 Packetbeat 的 HTTP 流量和网络流量拆成两个采集入口：

- `collect_type=http`：生成 `packetbeat.protocols` 下的 HTTP 协议配置。
- `collect_type=flows`：生成 `packetbeat.flows` 的 TCP/UDP flow 配置。

两者底层都是同一个 Packetbeat 探针，而 Packetbeat 的 `packetbeat.interfaces.device` 是全局配置。若两个入口都开放网卡配置，用户分别配置 HTTP 和网络流量时会互相覆盖，最终下发配置不可预测。

产品目标是把这两个入口合并为一个采集配置：同一个 Packetbeat 配置中统一设置网卡，并通过开关决定是否启用 HTTP 流量和 TCP/UDP 网络流量。

## 结论

采用“保留 `flows` 作为唯一网络流量入口，合并 HTTP 能力”的方案。

```text
日志集成列表
  -> 只展示 Packetbeat / 网络流量
  -> 一个表单配置 device、HTTP 开关、TCP/UDP 开关
  -> 同一个 Packetbeat 实例生成一组组合子配置
  -> Packetbeat 父配置只存在一个 packetbeat.interfaces.device
```

`http` 采集类型不再作为新建入口展示。旧的 `http` 配置模板和编辑兼容能力先保留，避免已有 HTTP 实例无法读取、编辑或回滚。

## 用户体验

网络流量配置页面顶部新增全局网卡输入框：

- 字段名：`device`
- 默认值：`any`
- 输入方式：文本输入
- 多网卡格式：逗号分隔，例如 `eth0,eth1`

网络流量支持两个采集模块：

1. HTTP
   - 开关字段：`enable_http`
   - 默认开启
   - 开启后显示 HTTP 端口和抓取请求/响应体配置。
2. TCP/UDP
   - 开关字段：`enable_tcp_udp`
   - 默认开启
   - 开启后显示统计周期和超时时间配置。

校验规则：

- `device` 为空时使用 `any`。
- `enable_http` 和 `enable_tcp_udp` 不能同时关闭。
- HTTP 开启时端口必填，沿用当前 HTTP 默认端口。
- TCP/UDP 开启时统计周期和超时时间沿用当前 flows 默认值。

## 前端改造

`web/src/app/log/hooks/integration/collectors/packetbeat/flows.tsx` 成为 Packetbeat 网络流量唯一新建入口。

默认表单值：

```json
{
  "device": "any",
  "enable_http": true,
  "enable_tcp_udp": true,
  "ports": [80, 8080, 8000, 5000, 8002],
  "capture_body": false,
  "flows_period": 10,
  "flows_timeout": 30
}
```

提交参数仍使用 `collector=Packetbeat` 和 `collect_type=flows`，但 `configs[0]` 同时携带 HTTP 与 TCP/UDP 参数。前端负责把 `ports` 数组转成当前模板可接受的逗号字符串。

编辑回显时从实例配置中读取：

- Packetbeat 父配置或父配置环境变量中的 `device`
- `packetbeat.protocols` 中的 HTTP 配置
- `packetbeat.flows`

如果旧配置中没有新字段，按默认双开回显。

`web/src/app/log/hooks/integration/collectTypes/http.tsx` 和 HTTP collector 代码暂时保留，仅用于旧实例兼容。列表新建入口通过移除或隐藏 `server/apps/log/support-files/plugins/Packetbeat/http/collect_type.json` 实现；`log_init` 后数据库不再展示 HTTP 采集类型。

## 后端模板改造

Packetbeat 父配置位于 `server/apps/node_mgmt/support-files/collectors/Packetbeat.json`，侧车下发时会先使用父配置，再追加该父配置下的 Packetbeat 子配置。为了避免重复全局项，`device` 只写在父配置中，不写在 HTTP 或 flows 子配置中。

父配置调整：

- Linux 默认 `packetbeat.interfaces.device` 从固定 `any` 改为模板变量，默认 `any`。
- Windows 默认值从固定 `"0"` 改为模板变量，默认 `"0"`。
- 创建或更新网络流量配置时，把表单中的 `device` 写入目标节点 Packetbeat 父配置的环境变量或等价父配置字段。
- 父配置保持唯一全局 device，不在 HTTP 和 flows 子配置中重复定义 device。

`server/apps/log/support-files/plugins/Packetbeat/flows/flows.child.yaml.j2` 扩展为组合模板：

- 当 `enable_tcp_udp` 为 true 时输出 `packetbeat.flows`。
- 当 `enable_http` 为 true 时输出 `packetbeat.protocols` 下的 HTTP 协议配置。
- 两个模块都写入 `fields.collector=Packetbeat` 和对应 `collect_type`，HTTP 事件仍写 `collect_type=http`，flow 事件仍写 `collect_type=flows`，保证现有搜索和仪表盘查询不需要迁移。

如果后端收到两个开关都关闭的配置，应拒绝创建或更新，避免下发无采集能力配置。

## 旧数据与兼容

本方案不迁移已有 `collect_type=http` 实例。

兼容策略：

- 已有 HTTP 实例仍可通过旧模板读取和编辑。
- 新建入口不再展示 HTTP。
- 新网络流量实例启用 HTTP 后，事件仍标记为 `collect_type=http`，因此现有 HTTP 分析视图可继续基于日志字段查询。
- 后续如产品需要统一实例列表，可单独设计迁移，把旧 HTTP 实例合并到网络流量实例。

## 错误处理

- 前端在提交前阻止两个模块同时关闭。
- 后端模板或服务层也要进行同样校验，防止绕过前端调用接口。
- 端口格式错误应返回明确错误，不生成非法 Packetbeat YAML。
- `device` 只做去空格和空值兜底，不校验网卡是否存在，因为不同节点网卡名只能在运行环境确认。

## 测试计划

实现必须按 TDD 进行。

后端红绿测试：

1. Packetbeat 默认配置支持通过 env/base 变量渲染 `packetbeat.interfaces.device`，未传时使用默认值。
2. 创建或更新网络流量配置会把 `device` 写入目标节点 Packetbeat 父配置，不写入 HTTP/flows 子配置。
3. flows 组合模板默认同时输出 `packetbeat.flows` 和 HTTP `packetbeat.protocols`。
4. 关闭 HTTP 时不输出 HTTP 协议块。
5. 关闭 TCP/UDP 时不输出 `packetbeat.flows`。
6. 两个开关同时关闭时创建或更新被拒绝。
7. HTTP 事件字段保持 `collect_type=http`，flow 事件字段保持 `collect_type=flows`。
8. HTTP `collect_type.json` 不再作为新入口导入或展示。

前端红绿测试或最小验证：

1. 网络流量表单默认 `device=any` 且两个开关开启。
2. 提交参数包含 `device`、`enable_http`、`enable_tcp_udp`、HTTP 参数和 TCP/UDP 参数。
3. 两个开关同时关闭时阻止提交。
4. 编辑旧 flows 配置时按默认双开回显。

## 不做的事情

本方案不新增 `collect_type=network`。

本方案不迁移已有 HTTP 实例。

本方案不修改 Packetbeat 事件写入链路或 Logstash/NATS 输出。

本方案不校验真实网卡存在性。
