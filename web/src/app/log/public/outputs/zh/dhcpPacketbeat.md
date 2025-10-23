### Packetbeat dhcp简介

- &zwnj;**基本功能**&zwnj;
  - 实时监控与捕获

  - 协议解析与字段提取

  - 事务关联

  - 数据丰富与标准化

  - 数据输出与集中化


- &zwnj;**主要特点**&zwnj;
  - 轻量级且资源友好

  - 无需客户端代理

  - 强大的集成生态（ELK Stack）

  - 关键运维与安全洞察

  - 配置简单

### Packetbeat dhcp 输出字段


|分组|字段名|描述|类型|
|--------|------|------|--------|
|内置字段|collect_type|采集类型|-|
|内置字段|collector|采集器|-|
|内置字段|instance_id|实例id|-|
|dhcpv4|dhcpv4.transaction_id|事务 ID，由客户端随机生成，用于在客户端和服务器之间关联请求与响应消息，确保消息匹配。|keyword|
|dhcpv4|dhcpv4.seconds|客户端自开始地址获取或续约过程以来经过的秒数。|long|
|dhcpv4|dhcpv4.flags|客户端设置的标志位，用于指示 DHCP 服务器应如何回复：单播（unicast）或广播（broadcast）。|keyword|
|dhcpv4|dhcpv4.client_ip|客户端当前的 IP 地址。|ip|
|dhcpv4|dhcpv4.assigned_ip|DHCP 服务器分配给客户端的 IP 地址（也称为 “your” IP 地址）。|ip|
|dhcpv4|dhcpv4.server_ip|客户端在启动过程中下一步应使用的 DHCP 服务器的 IP 地址。|ip|
|dhcpv4|dhcpv4.relay_ip|客户端用于联系服务器的中继 IP 地址（即 DHCP 中继服务器的地址）。|ip|
|dhcpv4|dhcpv4.client_mac|客户端的 MAC 地址（链路层地址）。|keyword|
|dhcpv4|dhcpv4.server_name|发送消息的服务器名称（可选）。通常出现在 DHCPOFFER 或 DHCPACK 消息中。|keyword|
|dhcpv4|dhcpv4.op_code|消息操作码，用于指示报文类型，如bootrequest或bootreply。|keyword|
|dhcpv4|dhcpv4.hops|DHCP 消息经过的跳数（hop 数）。|long|
|dhcpv4|dhcpv4.hardware_type|本地网络所使用的硬件类型，例如 Ethernet、LocalTalk 等。|keyword|
|dhcpv4|dhcpv4.option.message_type|DHCP 消息类型，例如discover、offer、request、decline、ack、nak、release、inform。|keyword|
|dhcpv4|dhcpv4.option.parameter_request_list|客户端使用此选项来请求指定配置参数的值。|keyword|
|dhcpv4|dhcpv4.option.requested_ip_address|客户端在请求（如 DHCPDISCOVER）中使用该选项，要求分配一个特定的 IP 地址。|ip|
|dhcpv4|dhcpv4.option.server_identifier|处理该消息的具体 DHCP 服务器的 IP 地址。|ip|
|dhcpv4|dhcpv4.option.broadcast_address|指定客户端子网中使用的广播地址。|ip|
|dhcpv4|dhcpv4.option.max_dhcp_message_size|指定客户端愿意接受的最大 DHCP 消息长度。|long|
|dhcpv4|dhcpv4.option.class_identifier|客户端可选地用来标识厂商类型和配置的字段。供应商可定义专用标识符以传递特定配置信息（例如硬件配置）。|keyword|
|dhcpv4|dhcpv4.option.domain_name|指定客户端在通过 DNS 解析主机名时应使用的域名。|keyword|
|dhcpv4|dhcpv4.option.dns_servers|指定客户端可用的一组 DNS 服务器 IP 地址。|ip|
|dhcpv4|dhcpv4.option.vendor_identifying_options|用于唯一标识客户端所运行硬件的制造商、使用的软件，或其所属的行业联盟（定义见 RFC 3925）。|object|
|dhcpv4|dhcpv4.option.subnet_mask|指定客户端在当前网络中应使用的子网掩码。|ip|
|dhcpv4|dhcpv4.option.utc_time_offset_sec|指定客户端子网相对于协调世界时 (UTC) 的时差，单位为秒。|long|
|dhcpv4|dhcpv4.option.router|指定客户端子网上可用的路由器（网关） IP 地址列表。|ip|
|dhcpv4|dhcpv4.option.time_servers|指定客户端可用的 RFC 868 时间服务器列表。|ip|
|dhcpv4|dhcpv4.option.ntp_servers|指定客户端可用的 NTP 时间服务器的 IP 地址列表。|ip|
|dhcpv4|dhcpv4.option.hostname|指定客户端的主机名。|keyword|
|dhcpv4|dhcpv4.option.ip_address_lease_time_sec|客户端请求租期（DHCPDISCOVER/DHCPREQUEST）时使用，服务器应答（DHCPOFFER）时返回的租期（单位：秒）。|long|
|dhcpv4|dhcpv4.option.message|DHCP 服务器在 DHCPNAK 消息中使用该选项向客户端返回错误消息；客户端可在 DHCPDECLINE 消息中使用该选项说明拒绝原因。|text|
|dhcpv4|dhcpv4.option.renewal_time_sec|指定从地址分配开始到客户端进入 RENEWING 状态的时间间隔。|long|
|dhcpv4|dhcpv4.option.rebinding_time_sec|指定从地址分配开始到客户端进入 REBINDING 状态的时间间隔。|long|
|dhcpv4|dhcpv4.option.boot_file_name|当 DHCP 报文头部中的 "file" 字段被用于 DHCP 选项时，用该字段来标识引导文件名。|keyword|