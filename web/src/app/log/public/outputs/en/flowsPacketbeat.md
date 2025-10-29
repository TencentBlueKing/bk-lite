### Packetbeat Flow Introduction

- &zwnj;**Core Features**&zwnj;
  - Traffic aggregation and statistics

  - Key metadata extraction

  - Scheduled reporting

  - Data output


- &zwnj;**Key Characteristics**&zwnj;
  - Macro perspective, not micro insights

  - Extremely high efficiency and scalability

  - Agentless full traffic monitoring

  - Strong foundation for network visualization and security analysis

  - Flexible configuration

### Packetbeat Flow Output Fields


|Group|Field Name|Description|Type|
|--------|------|------|--------|
|Built-in Fields|collect_type|Collection type|-|
|Built-in Fields|collector|Collector|-|
|Built-in Fields|instance_id|Instance ID|-|
|flow|flow.final|Indicates whether this event is the last event of a network flow. If the value is true, it means the flow has completed or closed; if the value is false, it means this is an intermediate state in the flow process, with only partial data recorded.|boolean|
|flow|flow.id|Internal unique flow ID generated based on connection metadata (such as source/destination addresses, ports, protocols, etc.). Used to maintain consistent identifiers across multiple events of the same connection for aggregation and analysis.|-|
|flow|flow.vlan|VLAN identifier (VID) from Ethernet 802.1q frames. If the data frame contains multiple VLAN tags (multi-tagged frames), this field will be an array with the outermost VLAN identifier first.|long|
|alias|flow_id|Alias for the flow.id field. Purpose: In some systems or query scenarios, directly reference the flow ID through flow_id without having to write the complete flow.id.|alias|
|alias|final|Alias for the flow.final field. Purpose: Provides a simplified notation for determining whether the flow has ended.|alias|
|alias|vlan|Alias for the flow.vlan field. Purpose: Provides a simplified notation that is more convenient when querying VLAN identifiers.|alias|
|source|source.stats.net_bytes_total|Alias for source.bytes. Represents the total network bytes sent by the source end of this flow.|alias|
|source|source.stats.net_packets_total|Alias for source.packets. Represents the total network packets sent by the source end of this flow.|alias|
|destination|dest.stats.net_bytes_total|Alias for destination.bytes. Represents the total network bytes received by the destination end of this flow.|alias|
|destination|dest.stats.net_packets_total|Alias for destination.packets. Represents the total network packets received by the destination end of this flow.|alias|