### Packetbeat icmp简介

- &zwnj;**基本功能**&zwnj;
  - 流量捕获与过滤

  - 事务关联与统计

  - 关键字段提取

  - 数据上报与集成


- &zwnj;**主要特点**&zwnj;
  - 专注于性能指标，而非内容

  - 网络健康与延迟监控的利器

  - 轻量级且无侵入性

  - 与 Elastic Stack 无缝集成实现自动化

  - 配置简单，用途明确

### Packetbeat icmp 输出字段


|分组|字段名|描述|类型|
|--------|------|------|--------|
|内置字段|collect_type|采集类型|-|
|内置字段|collector|采集器|-|
|内置字段|instance_id|实例id|-|
|icmp|icmp.version|ICMP 协议版本。 例如：ICMPv4 或 ICMPv6，用于区分不同版本的 ICMP 协议格式。|-|
|icmp|icmp.request.message|请求报文的可读文本形式。 通常为对请求的解释说明，例如 "Echo Request"（回显请求）。|keyword|
|icmp|icmp.request.type|请求类型 (Type)，对应 ICMP 协议中的 type 字段。 例如：8 表示 Echo Request。|long|
|icmp|icmp.request.code|请求代码 (Code)，对应 ICMP 协议中的 code 字段。 和 type 一起定义具体的请求语义。|long|
|icmp|icmp.response.message|响应报文的可读文本形式。 通常为对响应的解释说明，例如 "Echo Reply"（回显响应）。|keyword|
|icmp|icmp.response.type|响应类型 (Type)，对应 ICMP 协议中的 type 字段。 例如：0 表示 Echo Reply。|long|
|icmp|icmp.response.code|响应代码 (Code)，对应 ICMP 协议中的 code 字段。 和 type 一起定义具体的响应语义。|long|