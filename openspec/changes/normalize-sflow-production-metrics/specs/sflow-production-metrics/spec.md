## ADDED Requirements

### Requirement: sFlow traffic metrics use Telegraf-adjusted values directly
The system SHALL treat Telegraf sFlow traffic measurements as already sampling-rate adjusted and SHALL NOT apply a second sampling-rate multiplier in sFlow monitor plugin traffic queries.

#### Scenario: Device sFlow byte rate does not multiply sampling rate
- **WHEN** built-in sFlow monitor plugin metrics are imported or tested
- **THEN** sFlow byte-rate queries aggregate `sflow_bytes`
- **AND** those queries do not multiply `sflow_bytes` by `effective_sampling_rate`
- **AND** those queries do not multiply `sflow_bytes` by `sflow_sampling_rate`

#### Scenario: Device sFlow packet rate does not multiply sampling rate
- **WHEN** built-in sFlow monitor plugin metrics are imported or tested
- **THEN** sFlow packet-rate queries aggregate `sflow_packets`
- **AND** those queries do not multiply `sflow_packets` by `effective_sampling_rate`
- **AND** those queries do not multiply `sflow_packets` by `sflow_sampling_rate`

#### Scenario: NetFlow normalization remains separate
- **WHEN** built-in NetFlow monitor plugin metrics are imported or tested
- **THEN** NetFlow byte and packet queries continue to apply the asset's effective sampling rate according to the NetFlow metric contract

### Requirement: sFlow sampling rate is diagnostic metadata
The system SHALL expose sFlow sampling-rate information for diagnostics without using it as a second-pass traffic normalization operand.

#### Scenario: Sampling diagnostics remain visible
- **WHEN** sFlow records include `sflow_sampling_rate`, `effective_sampling_rate`, or `fallback_sampling_rate`
- **THEN** the sFlow plugin can expose sampling-rate metrics or labels for troubleshooting
- **AND** traffic, packet, interface, protocol, endpoint, port, and conversation queries do not use those values as multipliers

### Requirement: sFlow metrics use production sFlow dimensions
The system SHALL group sFlow metrics by labels observed in production sFlow records instead of NetFlow-style labels that are not part of the sFlow production contract.

#### Scenario: Endpoint metrics use sFlow IP labels
- **WHEN** the system queries sFlow endpoint metrics
- **THEN** source endpoint metrics group by `src_ip`
- **AND** destination endpoint metrics group by `dst_ip`
- **AND** endpoint queries do not group by `src` or `dst`

#### Scenario: Protocol metrics use sFlow protocol labels
- **WHEN** the system queries sFlow protocol metrics
- **THEN** protocol metrics group by `header_protocol`
- **AND** protocol queries do not group by `protocol`

#### Scenario: Port metrics use sFlow port labels
- **WHEN** the system queries sFlow port metrics
- **THEN** source port metrics group by `src_port`
- **AND** destination port metrics group by `dst_port`

#### Scenario: Conversation metrics use sFlow conversation labels
- **WHEN** the system queries top sFlow conversations
- **THEN** conversation metrics group by `src_ip`, `dst_ip`, `header_protocol`, and `dst_port`
- **AND** conversation metrics do not group by `src`, `dst`, or `protocol`

### Requirement: sFlow interface direction uses interface indexes and direction labels
The system SHALL represent sFlow interface traffic direction through production sFlow interface labels.

#### Scenario: Ingress interface metrics use input interface index
- **WHEN** the system queries ingress interface traffic for sFlow
- **THEN** the query groups `sflow_bytes` or `sflow_packets` by `input_ifindex`
- **AND** the resulting series identifies the direction as ingress

#### Scenario: Egress interface metrics use output interface index
- **WHEN** the system queries egress interface traffic for sFlow
- **THEN** the query groups `sflow_bytes` or `sflow_packets` by `output_ifindex`
- **AND** the resulting series identifies the direction as egress

#### Scenario: Reported sample direction remains available
- **WHEN** sFlow records include `sample_direction`
- **THEN** queries or rendered dimensions may expose `sample_direction` as diagnostic context
- **AND** the interface query contract still works from `input_ifindex` and `output_ifindex`

### Requirement: Existing sFlow onboarding contracts remain compatible
The system SHALL preserve existing Flow asset and monitor instance contracts while changing sFlow metric query behavior.

#### Scenario: Existing sFlow assets continue to match incoming records
- **WHEN** an existing Flow asset has `sflow` enabled
- **THEN** incoming sFlow records that match the asset source IP continue to receive `instance_id`, `instance_type`, `collect_type`, `effective_sampling_rate`, and `fallback_sampling_rate`

#### Scenario: sFlow listener and access guide stay stable
- **WHEN** a user opens the sFlow access guide
- **THEN** the system continues to present the existing sFlow listener endpoint and UDP port
- **AND** no user-facing split by vendor or sFlow variant is introduced
