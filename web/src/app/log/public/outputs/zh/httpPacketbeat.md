### Packetbeat http简介

- &zwnj;**基本功能**&zwnj;
  - HTTP 协议解析

  - 实时流量监控

  - 流量统计和可视化

  - 与 Elasticsearch/Logstash 集成

- &zwnj;**主要特点**&zwnj;
  - 轻量化

  - 非侵入式监控

  - 丰富的字段信息

  - 性能分析能力

  - 可与其他模块协作

  - 可配置性强


### Packetbeat http 输出字段


|分组|字段名|描述|类型|
|---|---|---|---|
|内置字段|collect_type|采集类型|-|
|内置字段|collector|采集器|-|
|内置字段|instance_id|实例id|-|
|http.request|http.request.headers|HTTP 请求头字段映射，可配置要捕获的头部；同名头部用逗号分隔|object|
|http.request|http.request.params|HTTP 请求参数|alias（url.query）|
|http.response|http.response.status_phrase|HTTP 状态短语，例如 "Not Found"|example|
|http.response|http.response.headers|HTTP 响应头字段映射，可配置要捕获的头部；同名头部用逗号分隔|object|
|http.response|http.response.code|HTTP 响应状态码|alias（http.response.status_code）|
|http.response|http.response.phrase|HTTP 响应状态短语|alias（http.response.status_phrase）|
