# Flow 云区域接收器 Telegraf 方案

## 背景

NetFlow 和 sFlow 是被动接收型采集。网络设备会主动把 Flow 数据发送到一个接收地址，因此平台侧应该按云区域提供稳定接收地址，而不是为每个 Flow 资产生成一份 Telegraf 子配置。

现有 Telegraf 默认配置已经有类似模式：`inputs.http_listener_v2` 放在 `server/apps/node_mgmt/support-files/collectors/Telegraf.json` 的 `default_config.add_config` 中，节点管理只会在容器节点创建/更新 Telegraf 默认配置时追加 `add_config`。Flow 接收能力也应沿用这个容器节点代理模式。

## 结论

采用“云区域级 Flow 接收器”方案：

```text
一个云区域
  -> 一个 Flow 接收地址
  -> 容器/代理节点上的 Telegraf 基础配置
  -> inputs.netflow、inputs.sflow、Flow processor 都放在 add_config
  -> FLOW_ASSET_MAP_JSON 写入 Telegraf 基础配置 env_config
```

Flow 插件实例只负责维护资产和映射关系，不创建 Flow child toml，不创建实例级接收地址。

## 配置分层

### Telegraf 基础配置

`Telegraf.json` 的 `default_config.add_config` 中需要包含：

```toml
[[inputs.http_listener_v2]]
    service_address = "tcp://:19090"

[[inputs.netflow]]
    service_address = "udp://:2055"

[[inputs.sflow]]
    service_address = "udp://:6343"

[[processors.starlark]]
    # 根据 FLOW_ASSET_MAP_JSON 补充 Flow 指标标签
```

这些配置跟 `inputs.http_listener_v2` 一样，只在容器节点 Telegraf 默认配置中生效。

### Flow 资产映射

`FlowEnvConfigService` 负责生成云区域内的 Flow 资产映射，并写入容器节点 Telegraf 基础配置的 `env_config.FLOW_ASSET_MAP_JSON`。

映射示例：

```json
{
  "1:10.0.0.12": {
    "instance_id": "flow-device-1",
    "instance_type": "switch",
    "fallback_sampling_rate": 1000,
    "protocols": ["netflow", "sflow"]
  }
}
```

说明：

- 映射 key 格式为 `{cloud_region_id}:{device_ip}`。
- `instance_id` 是写入指标 tag 的逻辑实例值，例如 `flow-device-1`。
- 生成映射时应使用现有实例 ID 解析逻辑，将数据库存储 ID 转为逻辑实例值。代码里已有类似逻辑：`parse_instance_id(instance.id)[0]`。

## 刷新目标

Flow 资产新增、更新、删除后，应刷新目标云区域下容器节点绑定的 Telegraf 基础配置，而不是刷新 Flow child config。

选择规则：

1. 查找目标云区域下的容器节点。
2. 查找这些容器节点绑定的 Telegraf 采集器基础配置。
3. 优先更新预置/默认 Telegraf 基础配置。
4. 将 `FLOW_ASSET_MAP_JSON` 合并到基础配置 `env_config`。
5. 保留已有的其他 `env_config` key。

如果同一个云区域有多个容器节点，应全部刷新，避免代理节点迁移或双代理场景下配置不一致。

如果目标云区域没有容器节点或没有 Telegraf 基础配置，应记录日志并跳过刷新，不阻断用户创建/更新 Flow 资产。

## 数据流

```text
Flow 资产创建/更新/删除
  -> FlowEnvConfigService.build_asset_map(cloud_region_id)
  -> FlowEnvConfigService.refresh_region_receiver_env_config(cloud_region_id)
  -> 找到云区域下容器节点 Telegraf 基础配置
  -> 更新基础配置 env_config.FLOW_ASSET_MAP_JSON
  -> Sidecar 下发 Telegraf 配置和 env_config
  -> Telegraf inputs.netflow / inputs.sflow 接收 Flow 数据
  -> Telegraf processor 根据映射补充标签
  -> 指标写入后带上实例和采样率标签
```

## 标签补充规则

Processor 只处理 NetFlow 和 sFlow 指标。

每条 Flow 指标处理步骤：

1. 判断协议类型，得到 `collect_type`：`netflow` 或 `sflow`。
2. 从 Telegraf Flow 数据中取设备来源 IP。
3. 用 `{cloud_region_id}:{device_ip}` 匹配 `FLOW_ASSET_MAP_JSON`。
4. 如果没有匹配映射，跳过实例标签补充。
5. 如果映射命中但当前协议不在 `protocols` 中，跳过实例标签补充。
6. 命中后补充以下 tag：
   - `instance_id`
   - `instance_type`
   - `fallback_sampling_rate`
   - `collect_type`
   - `effective_sampling_rate`

`instance_id` 必须写逻辑实例值，不能写数据库存储 ID。也就是说指标 tag 应是：

```text
instance_id="flow-device-1"
```

不能是：

```text
instance_id="('flow-device-1',)"
```

## 采样率规则

`effective_sampling_rate` 按以下优先级取第一个有效值：

```text
effective_sampling_rate
SAMPLING_INTERVAL
SAMPLING_ALGORITHM
sampling_rate
samplingRate
fallback_sampling_rate
```

有效值定义：

- 非空
- 可转换为数字
- 大于或等于 0

如果设备上报字段存在但非法，应忽略该字段并继续尝试下一个候选字段。

## 错误处理

Flow 资产操作不应只因为刷新 Telegraf env_config 失败而失败。

刷新失败时应记录云区域、节点、配置 ID 等信息，然后继续完成资产操作。后续再次保存资产或手动触发刷新时，可以修复 Telegraf 基础配置中的映射。

## 测试计划

后续实现必须按 TDD 进行。

需要覆盖的红绿测试：

1. `Telegraf.json` 的 `add_config` 包含 `inputs.netflow`、`inputs.sflow` 和 Flow processor。
2. Flow env 刷新目标是容器节点 Telegraf 基础配置，不是 Flow child config。
3. 非容器节点 Telegraf 配置不会被刷新。
4. 同云区域多个容器节点都会被刷新。
5. 合并 `FLOW_ASSET_MAP_JSON` 时保留基础配置原有 `env_config`。
6. 云区域没有容器节点或没有 Telegraf 基础配置时记录日志且不抛错。
7. 资产映射包含 `instance_id`、`instance_type`、`fallback_sampling_rate`、`protocols`。
8. `instance_id` 使用逻辑实例值。
9. Processor 的采样率优先级和兜底逻辑有测试覆盖。

## 不做的事情

本方案不创建 Flow child toml。

本方案不创建实例级 Flow 接收地址。

本方案不把 Flow 接收器改成服务端自研接收器。
