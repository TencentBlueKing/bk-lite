### Packetbeat flow简介

- &zwnj;**基本功能**&zwnj;
  - 流量聚合与统计

  - 关键元数据提取

  - 定时报告

  - 数据输出


- &zwnj;**主要特点**&zwnj;
  - 宏观视角，而非微观洞察

  - 极高的效率与可扩展性

  - 无代理的全流量监控

  - 强大的网络可视化与安全分析基础

  - 配置灵活

### Packetbeat flow 输出字段


|分组|字段名|描述|类型|
|--------|------|------|--------|
|内置字段|collect_type|采集类型|-|
|内置字段|collector|采集器|-|
|内置字段|instance_id|实例id|-|
|flow|flow.final|指示该事件是否为某个网络流的最后一个事件。如果值为true，表示该流已完成或关闭；如果值为false，表示这是该流过程中的中间状态，仅部分数据被记录。|boolean|
|flow|flow.id|基于连接元数据（如源/目的地址、端口、协议等）生成的内部唯一流 ID。用于在同一条连接的多个事件中保持一致的标识符，便于聚合和分析。|-|
|flow|flow.vlan|来自以太网 802.1q 帧的VLAN 标识符 (VID)。如果数据帧包含多个 VLAN 标签（多重标记帧），该字段将是一个数组，最外层 VLAN 的标识符排在前面。|long|
|alias|flow_id|flow.id字段的别名。用途：在部分系统或查询场景中，直接通过 flow_id 引用流 ID，而不必写完整的 flow.id。|alias|
|alias|final|flow.final字段的别名。用途：提供简化写法，用于判断流是否结束。|alias|
|alias|vlan|flow.vlan字段的别名。用途：提供简化写法，在查询 VLAN 标识时更方便。|alias|
|source|source.stats.net_bytes_total|source.bytes的别名。表示该流的源端累计发送的网络字节总数。|alias|
|source|source.stats.net_packets_total|source.packets的别名。表示该流的源端累计发送的网络数据包总数。|alias|
|destination|dest.stats.net_bytes_total|destination.bytes的别名。表示该流的目的端累计接收的网络字节总数。|alias|
|destination|dest.stats.net_packets_total|destination.packets的别名。表示该流的目的端累计接收的网络数据包总数。|alias|