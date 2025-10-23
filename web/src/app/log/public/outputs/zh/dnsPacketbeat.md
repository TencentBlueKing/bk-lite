### Packetbeat dns简介

- &zwnj;**基本功能**&zwnj;
  - DNS 协议解析

  - 查询与响应的关联

  - 结构化输出

  - 数据输出与分析


- &zwnj;**主要特点**&zwnj;
  - 非侵入式监控

  - 实时性强

  - 可用于安全场景

  - 性能分析能力

  - 可配置过滤和采样

  - 与可观测性生态集成

### Packetbeat dns 输出字段


|分组|字段名|描述|类型|
|--------|------|------|--------|
|内置字段|collect_type|采集类型|-|
|内置字段|collector|采集器|-|
|内置字段|instance_id|实例id|-|
|dns.flags|dns.flags.authoritative|指定响应服务器是否为该域名的权威服务器|boolean|
|dns.flags|dns.flags.recursion_available|指定名称服务器是否支持递归查询|boolean|
|dns.flags|dns.flags.recursion_desired|指定客户端是否要求服务器递归查询（递归可选）|boolean|
|dns.flags|dns.flags.authentic_data|指定递归服务器认为响应是可信的|boolean|
|dns.flags|dns.flags.checking_disabled|指定客户端是否禁用服务器对查询的签名验证|boolean|
|dns.flags|dns.flags.truncated_response|指定响应仅返回前 512 字节|boolean|
|dns.question|dns.question.etld_plus_one|有效顶级域名加一层标签，例如 "amazon.co.uk"|example|
|dns.answers|dns.answers_count|dns.answers 字段中包含的资源记录数|long|
|dns.authorities|dns.authorities|包含每个权威部分字典的数组|object|
|dns.authorities|dns.authorities_count|dns.authorities 字段中包含的资源记录数|long|
|dns.authorities|dns.authorities.name|该资源记录对应的域名|example|
|dns.authorities|dns.authorities.type|该资源记录的类型|example|
|dns.authorities|dns.authorities.class|该资源记录的类|example|
|dns.additionals|dns.additionals|包含每个附加部分字典的数组|object|
|dns.additionals|dns.additionals_count|dns.additionals 字段中包含的资源记录数|long|
|dns.additionals|dns.additionals.name|该资源记录对应的域名|example|
|dns.additionals|dns.additionals.type|该资源记录的类型|example|
|dns.additionals|dns.additionals.class|该资源记录的类|example|
|dns.additionals|dns.additionals.ttl|该资源记录可缓存的时间间隔（秒），0 表示不缓存|long|
|dns.additionals|dns.additionals.data|描述该资源的数据，具体含义取决于类型和类| |
|dns.opt|dns.opt.version|EDNS 版本|example|
|dns.opt|dns.opt.do|是否使用 DNSSEC|boolean|
|dns.opt|dns.opt.ext_rcode|扩展响应码字段|example|
|dns.opt|dns.opt.udp_size|请求方的 UDP 负载大小（字节）|long|