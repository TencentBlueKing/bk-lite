# CMDB 网络拓扑发现增强

> Migrated from `spec/requirements/CMDB/20260610.CMDB网络拓扑发现增强.md` as legacy capability evidence.

## 1. 背景与问题

CMDB 当前的网络拓扑采集链路为：stargazer agent（network_topo 插件）通过 SNMP 采集设备数据 → 转换为指标（`network_topo_info_gauge` / `network_topology_facts_info_gauge`）写入 VictoriaMetrics → server 端 CMDB 采集插件（`collect_plugin/network.py`）查询指标并做两阶段关系发现（LLDP/CDP/FDB facts → ARP+MAC 兜底）→ 产出 `interface_connect_interface` 接口连接关联。

现有链路的主要痛点：

- **采集证据不全**：LLDP 仅采 3 个 OID，无 PortId subtype 解码、无 RemChassisId；CDP 不采管理地址；不支持 FDP（Foundry/Ruckus 设备）；FDB 不采 QBRIDGE（dot1q）表、不区分 learned 状态；`bulkCmd` 一旦失败（如 OID not increasing）整台设备采集失败，无降级。
- **关系发现质量弱**：无置信度体系；FDB/ARP 推断没有双侧佐证校验，接入设备间仅因共享二层广播域互相可达就可能被误判为直连；逻辑口（Vlanif/Loopback 等）可能被当成物理链路端点；镜像/重复关系无收敛；无法解析的邻居证据被静默丢弃，无法排查。
- **参数摆设**：采集任务的 `min_confidence` 参数定义了但实际未生效。

已有独立工具 `snmp_topo_tool`（从本插件早期版本剥离后重构）实现了完整的「采集 → 归一化 → 链路推断 → 去重/收敛」四阶段流水线，并经 4 台真实设备（华为堆叠 / H3C 二层 / H3C 三层 / Cisco 三层，v2c+v3 混合）联采验证，结果与真实物理连线一致。本需求将该工具的能力合入 CMDB 网络拓扑采集链路。

## 2. 需求项

### 2.1 agent 侧采集增强（stargazer network_topo 插件）

1. 补齐 OID 采集覆盖：LLDP 本地端口表（LocPortId/LocPortIdSubtype/LocPortDesc）、LLDP 远端补充（RemChassisId/RemChassisIdSubtype/RemPortIdSubtype/RemPortDesc）、CDP 补充（AddressType/Address/Platform/SysName）、FDP 邻居组（DeviceId/DevicePort/Platform/Version）、QBRIDGE FDB 表（FdbPort/FdbStatus）、FDB-Status、sysName。
2. 每条证据记录携带证据分组标识（system / interfaces / ip / arp / neighbors / bridge / fdb），随指标标签上报。
3. `bulkCmd` 失败时按 OID 逐个降级采集（表 OID 走 nextCmd、标量 OID 走 getCmd），可识别 "OID not increasing" / "Empty SNMP response message" 类可重试错误；可选 OID（CDP/FDP/sysName 等）不可用时跳过并继续，必采 OID 全部失败才报错。
4. 采集协议开关沿用现有 `topology_protocols` 参数链路（CollectModels → node_configs → agent），FDP 加入可选协议集。
5. 上报指标格式只增不改：仍走 `network_topo_info_gauge`，新增行与 `group` 标签为增量；`list_all_resources` 返回结构不变。

### 2.2 server 侧关系发现流水线（CMDB collect_plugin）

1. 新增拓扑流水线模块（移植 `snmp_topo_tool` 的 `topology_models.py` + `parse_topology.py`），实现：证据归一化 → 链路推断 → 去重/收敛三阶段。
2. 推断优先级：直接邻居协议（LLDP/CDP/FDP）→ authoritative 链路；双侧 FDB + 双向 ARP 互见强佐证 → 高置信 inferred 链路（confidence 95）；FDB → inferred（60–75）；ARP → inferred（50）。
3. 收敛规则：authoritative 始终压制同端点对的 inferred；镜像/重复关系合并，被压制项进入 stale；逻辑口（Vlan-interface/Vlanif/Vlan*/Loopback/Null0 等）不作为物理链路端点；fdb+arp 强佐证仅在双方都在唯一物理口学到对方 MAC 且双向 ARP 互见时触发；远端接口名做保守归一化匹配（GigabitEthernet/Gi 等常见缩写）。
4. `network.py` 中原有 `find_topology_fact_relationships` + `find_interface_relationships` 两阶段逻辑由新流水线**替换**；输入为按 `instance_id` 聚合的 `network_topo` 证据行；设备身份解析沿用现有 device_lookup（instance_id / IP / sysname）。
5. 任务参数 `min_confidence` 真正生效：低于阈值的 inferred 链路不写入关联。
6. confidence / evidence_source / stale 链路 / unresolved 邻居等过程数据写入采集任务的 `format_data` / `collect_data` 供排查；**不**新增 CMDB 模型字段、关联属性或 UI。
7. stale 检测以上一轮采集任务的 format_data 作为 previous snapshot；stale 仅标记记录，**不**联动删除已有关联。
8. 输出契约不变：最终产出仍为 `interface_connect_interface` 接口连接关联（`assos` 格式不变），实例增删改对比逻辑（Management）不动。

### 2.3 已知缺陷修复（合入时一并完成，先在 snmp_topo_tool 修复验证再移植）

1. 本地端口解析顺序：CDP/FDP 索引即 ifIndex，不应优先查 bridge basePort 映射；LLDP 路径 bridge 映射命中后需用 LLDP-LocPortId/LocPortDesc 交叉校验，不一致时降级名称匹配。
2. fallback 采集全部 OID 被跳过时的报错信息应反映真实原因（设备不支持相关 MIB），不得误报为 "OID not increasing"。
3. 清理 `normalize_topology_data` 中未使用的 `unresolved_neighbors` 局部变量。
4. QBRIDGE VLAN 提取基于 dot1qFdbId≈VLAN ID 的假设，需注释说明。

## 3. 验收口径

1. **真实设备回归**：用 10.10.69.245/246/247/248 四台设备联采，结果与 snmp_topo_tool 当前验证结论一致 —— 2 条 authoritative 链路（245↔247、248↔247）+ 1 条 fdb+arp 高置信 inferred 链路（246↔247），无误报直连（245/246/248 两两之间不产生链路），unresolved=0、errors=0。
2. **CMDB 落库**：上述链路在 CMDB 中体现为对应接口实例间的 `interface_connect_interface` 关联，关联格式与升级前一致。
3. **降级采集**：对返回 "OID not increasing" 的设备，采集不失败，可选 OID 跳过后必采证据完整。
4. **min_confidence**：设为 95 时仅 authoritative 与 fdb+arp 强佐证链路写入关联，可验证。
5. **过程数据可排查**：采集任务详情中可查看链路的 confidence/evidence_source、stale 链路、unresolved 邻居记录。
6. **测试**：snmp_topo_tool 现有回归测试（LLDP subtype 解码、basePort 解析、FDB port 0 防御、双侧佐证、VLAN-aware 推断、stale 标记等）随移植落入 `apps/cmdb/tests/`（_pure 层）并全部通过；`tests/e2e/test_network_pipeline.py` 适配新流水线后通过；agent 侧 fallback 与 OID 注册表有单测覆盖。

## 4. 约束与边界

**In Scope**

- stargazer `plugins/inputs/network_topo/`（protocol_oids / snmp_topo）采集增强。
- server `apps/cmdb/collection/collect_plugin/` 新增拓扑流水线模块并重构 `network.py` 关系发现部分。
- snmp_topo_tool 缺陷修复（作为移植前置）。

**Out of Scope**

- 老 agent 兼容路径：agent 与 server **同步升级**，server 不保留对旧简化指标的两阶段发现逻辑。
- UI 展示、CMDB 关联边属性扩展、stale 联动删除关联。
- 企业版插件目录。
- `network_topology_facts_info_gauge` 指标：agent 暂保留产出但 server 不再消费，下线另行处理。
- agent 侧 FDB 表 learned-only 过滤（QBRIDGE 全量上报会增加大 FDB 表指标行数，每 MAC 2 行；现有链路 FDB 亦为全量上报、非回归，如现场有压力再做过滤优化）。
