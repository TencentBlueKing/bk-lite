# Historical Superpowers change: 2026-06-01-network-flow-onboarding

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-01-network-flow-onboarding-design.md

## 1. 背景

当前监控模块下的网络设备对象默认以 SNMP 类插件为主，现需为网络设备内置对象新增两种流量采集方式：

- 流量分析（NetFlow）
- 流量分析（sFlow）

本次需求目标是在不破坏现有网络设备 SNMP 接入能力、不影响 K8s 和日志系统已有接入体验的前提下，为交换机、路由器、防火墙、负载均衡提供 Flow 接入能力，并复用现有监控接入体系完成接入资产、接入指引、接入检测和接入完成流程。

## 2. 设计目标

### 2.1 目标

1. 为 4 类网络设备内置对象分别新增 NetFlow、sFlow 两个内置监控模板。
2. 提供与现有 K8s 接入一致的三步式接入向导。
3. 支持新建监控侧网络设备资产或绑定已有资产。
4. 在接收到 Flow 数据后，将设备数据映射到监控实例，并补齐标准化字段。
5. 将采样率统一归一化到 `effective_sampling_rate`。
6. 将 Flow 接入影响面控制在指定对象、指定模板、指定云区域内。

### 2.2 非目标

1. 不新增新的监控对象类型。
2. 不同步创建或维护 CMDB 主资产。
3. 不改造现有 SNMP 模板和 SNMP 接入流程。
4. 不引入新的配置分发体系，复用现有 `env_config` 下发链路。

## 3. 范围

### 3.1 监控对象范围

以下网络设备内置对象纳入本次方案：

1. 交换机
2. 路由器
3. 防火墙
4. 负载均衡

### 3.2 模板范围

每个对象新增两个内置监控模板：

1. 流量分析（NetFlow）
2. 流量分析（sFlow）

同一台网络设备资产可以同时绑定两个模板。

## 4. 总体方案

### 4.1 总体原则

本次采用“保留现有对象体系 + 增量扩展模板、接入页、资产扩展字段、Flow 映射和接入检测”的方案，不新建平行对象体系。

### 4.2 分层设计

1. **对象与模板层**：在现有 4 类网络设备对象下新增两个内置模板。
2. **资产层**：复用现有监控实例/资产体系，仅新增 Flow 相关资产扩展字段。
3. **接入向导层**：复用 K8s 三步向导骨架和 snmptrap 接入指引模式。
4. **Flow 映射层**：使用 `env_config` 通道向对应 Telegraf 配置下发 Flow 资产映射。
5. **接入检测层**：按“最近时间窗是否收到该资产对应协议的 Flow 数据”判定是否接入成功。

## 5. 前端方案

### 5.1 接入入口

入口保留在监控模板详情中的配置/接入位置。NetFlow 与 sFlow 共用一套接入页面骨架，仅按模板类型展示不同协议名称、接入地址和检测参数。

### 5.2 三步向导

#### 第一步：接入资产

参考 K8s 接入页，支持两种方式：

1. **新建资产**
   - 选择云区域
   - 填写 IP
   - 填写资产名称
   - 填写兜底采样率，默认值为 `1000`
2. **选择已有资产**
   - 从当前对象下已有网络设备资产中选择

交互规则：

1. 新建资产仅创建监控侧资产，不创建 CMDB 主资产。
2. 同一资产在后续可重复用于 NetFlow 和 sFlow 两个模板。
3. 资产维度维护一个 `fallback_sampling_rate`。

兜底采样率提示文案固定为：

> 系统优先使用 Flow 数据中携带的采样率进行流量换算；当上报数据中未包含采样率信息时，使用此默认采样率计算。

#### 第二步：接入指引

参考日志系统 snmptrap 接入页，展示：

1. 当前协议对应的接入地址
2. 接入说明文案
3. 采样率归一化规则说明
4. 检测接入状态按钮

NetFlow 与 sFlow 仅在以下内容上有差异：

1. 协议文案
2. 监听端口/接入地址
3. 协议检测参数

#### 第三步：接入完成

当检测到接入成功后跳转到完成页，页面提供：

1. 查看监控视图
2. 接入新资产
3. 返回模板列表

## 6. 后端方案

### 6.1 模板扩展

为 4 类网络设备对象分别新增两个内置模板：

1. `flow_netflow`
2. `flow_sflow`

模板层负责：

1. 控制页面入口和模板展示
2. 标识当前协议类型
3. 挂接接入指引和接入检测能力

模板层不负责维护设备资产主数据。

### 6.2 资产扩展

网络设备资产在监控侧补充以下 Flow 相关信息：

1. `cloud_region_id`
2. `ip`
3. `fallback_sampling_rate`
4. `enabled_protocols`

说明：

1. `fallback_sampling_rate` 挂在资产层，而不是模板绑定层。
2. `enabled_protocols` 反映该资产已接入的 Flow 协议集合。
3. 同一资产可以同时启用 NetFlow 与 sFlow。

### 6.3 接口建议

建议新增或扩展以下能力：

1. **获取接入指引**
   - 输入：模板 ID / 协议类型 / 对象 ID
   - 输出：接入地址、说明文案、采样率归一化规则、检测说明
2. **创建或绑定 Flow 资产**
   - 负责新建监控侧资产或绑定已有资产
   - 记录资产与模板的绑定关系
3. **刷新 Flow 映射**
   - 在资产新增、删除、修改兜底采样率、启停协议绑定时触发
4. **检测接入状态**
   - 按 `cloud_region_id + source_ip + protocol` 查询最近时间窗内是否收到 Flow 数据
   - 输出检测成功/失败和检测详情

## 7. Flow 映射与 env_config 方案

### 7.1 设计原则

复用现有 node_mgmt 的 `env_config` 下发通道，不新增独立配置分发机制。

### 7.2 映射下发位置

映射配置写入对应云区域下 Telegraf 配置的 `env_config`，而不是直接混入云区域公共基础环境变量。

原因：

1. Flow 资产映射属于业务动态配置，变更频率高。
2. Flow 资产映射与 Telegraf Flow 采集配置强相关。
3. 将其放在 Telegraf 配置自己的 `env_config` 上，边界更清晰，便于排障和局部刷新。

### 7.3 映射结构

在 `env_config` 中保留一个统一映射变量，例如：

- `FLOW_ASSET_MAP_JSON`

其 value 为 JSON 字符串，映射内部 key 使用复合主键：

- `cloud_region_id:ip`

示例：

```json
{
  "1:10.0.0.12": {
    "instance_id": "xxx",
    "instance_type": "switch",
    "fallback_sampling_rate": 1000,
    "protocols": ["netflow", "sflow"]
  },
  "3:172.16.1.8": {
    "instance_id": "yyy",
    "instance_type": "firewall",
    "fallback_sampling_rate": 2000,
    "protocols": ["sflow"]
  }
}
```

### 7.4 映射刷新策略

以下场景触发映射刷新：

1. 新增网络设备资产
2. 删除网络设备资产
3. 修改资产 IP
4. 修改 `fallback_sampling_rate`
5. 绑定或解绑 NetFlow / sFlow 模板

刷新范围：

1. 仅刷新目标资产所在云区域
2. 不触发全云区域全量刷新
3. 不影响其他云区域的 Telegraf 配置

### 7.5 Telegraf / Flow enrichment 行为

Telegraf 或对应 Flow enrichment 逻辑在接收到数据后执行：

1. 提取 `cloud_region_id`
2. 提取 `source_ip`
3. 生成 `composite_key = {cloud_region_id}:{source_ip}`
4. 在 `FLOW_ASSET_MAP_JSON` 中查找映射
5. 命中后补齐：
   - `instance_id`
   - `instance_type`
   - 采样率回退所需资产信息

## 8. 采样率归一化方案

### 8.1 目标

无论设备上报的采样率字段名称是什么，进入监控计算链路前统一归一化为标准字段：

- `effective_sampling_rate`

### 8.2 归一化规则

1. 如果原始数据中已存在 `effective_sampling_rate`，直接使用。
2. 如果不存在 `effective_sampling_rate`，但存在以下任一字段，则将其值映射生成新的 `effective_sampling_rate`：
   - `SAMPLING_INTERVAL`
   - `SAMPLING_ALGORITHM`
   - `sampling_rate`
   - `samplingRate`
3. 如果上述字段全部不存在，再使用资产上的 `fallback_sampling_rate` 生成 `effective_sampling_rate`。

### 8.3 实现要求

1. 归一化逻辑集中实现为独立 enrichment helper。
2. 图表、公式和后续计算统一消费 `effective_sampling_rate`。
3. 后续若新增采样率候选字段，仅修改归一化 helper，不扩散改动到页面或公式层。

## 9. 接入检测方案

### 9.1 检测口径

接入成功以“最近时间窗内是否收到该资产对应协议的 Flow 数据”为准。

### 9.2 检测维度

检测维度为：

1. 资产
2. 协议模板
3. 云区域
4. 时间窗

说明：

1. NetFlow 成功不代表 sFlow 成功。
2. sFlow 成功不影响 NetFlow 模板接入状态。

### 9.3 检测接口返回建议

返回内容建议包括：

1. 是否检测成功
2. 最近命中数据时间
3. 命中的协议类型
4. 当前 `effective_sampling_rate` 来源
   - 设备已上报
   - 原始字段归一化
   - 兜底采样率回退

## 10. 测试围栏

### 10.1 对象围栏

仅对以下对象新增 Flow 模板：

1. 交换机
2. 路由器
3. 防火墙
4. 负载均衡

不修改其他对象默认模板集合。

### 10.2 协议围栏

Flow 相关逻辑仅在：

1. 流量分析（NetFlow）
2. 流量分析（sFlow）

两个模板中生效，不影响：

1. 现有 SNMP 接入流程
2. K8s 接入流程
3. 日志系统 snmptrap 接入流程

### 10.3 云区域围栏

1. 映射刷新按单云区域执行
2. 单个资产变更只刷新其所属云区域对应配置
3. 不做跨云区域连带更新

### 10.4 数据围栏

Flow enrichment 只新增或补齐以下标准字段：

1. `instance_id`
2. `instance_type`
3. `effective_sampling_rate`
4. 必要协议标签

不修改原始数据中已有字段的语义。

### 10.5 测试分层

#### 后端测试

1. `cloud_region_id:ip` 复合 key 生成
2. `FLOW_ASSET_MAP_JSON` 映射生成
3. 资产增删改触发单云区域映射刷新
4. `effective_sampling_rate` 归一化逻辑
5. 接入检测接口成功/失败分支

#### 前端测试

1. 三步向导渲染
2. 新建资产/已有资产切换
3. NetFlow / sFlow 文案和接入地址切换
4. 检测成功后跳转完成页

#### 集成回归

1. 现有网络设备 SNMP 接入不退化
2. K8s 接入流程不受影响
3. snmptrap 接入页不受影响

### 10.6 灰度建议

实施时建议按以下顺序灰度：

1. 单云区域验证
2. 单对象类型验证（优先交换机）
3. 四类网络设备全量开放

## 11. 验收标准

1. 目标 4 类网络设备对象下可见 NetFlow / sFlow 两个新增模板。
2. 新建或删除资产后，对应云区域 Telegraf 配置中的 `FLOW_ASSET_MAP_JSON` 同步更新。
3. 原始数据有 `effective_sampling_rate` 时直接使用。
4. 原始数据无 `effective_sampling_rate` 但有采样率候选字段时，可正确归一化生成 `effective_sampling_rate`。
5. 原始数据无采样率字段时，可正确回退到 `fallback_sampling_rate`。
6. 接入检测仅以“最近时间窗收到该资产对应协议的 Flow 数据”为成功标准。
7. 现有 SNMP、K8s、snmptrap 接入流程回归通过。
