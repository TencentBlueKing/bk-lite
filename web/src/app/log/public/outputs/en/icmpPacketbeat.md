### Packetbeat ICMP Introduction

- &zwnj;**Core Features**&zwnj;
  - Traffic capture and filtering

  - Transaction correlation and statistics

  - Key field extraction

  - Data reporting and integration


- &zwnj;**Key Characteristics**&zwnj;
  - Focus on performance metrics, not content

  - A powerful tool for network health and latency monitoring

  - Lightweight and non-intrusive

  - Seamless integration with Elastic Stack for automation

  - Simple configuration with clear purpose

### Packetbeat ICMP Output Fields


|Group|Field Name|Description|Type|
|--------|------|------|--------|
|Built-in Fields|collect_type|Collection type|-|
|Built-in Fields|collector|Collector|-|
|Built-in Fields|instance_id|Instance ID|-|
|icmp|icmp.version|ICMP protocol version. For example: ICMPv4 or ICMPv6, used to distinguish between different versions of ICMP protocol formats.|-|
|icmp|icmp.request.message|Readable text form of the request message. Usually an explanation of the request, such as "Echo Request"."|keyword|
|icmp|icmp.request.type|Request type, corresponding to the type field in the ICMP protocol. For example: 8 indicates Echo Request.|long|
|icmp|icmp.request.code|Request code, corresponding to the code field in the ICMP protocol. Together with type, it defines the specific request semantics.|long|
|icmp|icmp.response.message|Readable text form of the response message. Usually an explanation of the response, such as "Echo Reply".|keyword|
|icmp|icmp.response.type|Response type, corresponding to the type field in the ICMP protocol. For example: 0 indicates Echo Reply.|long|
|icmp|icmp.response.code|Response code, corresponding to the code field in the ICMP protocol. Together with type, it defines the specific response semantics.|long|