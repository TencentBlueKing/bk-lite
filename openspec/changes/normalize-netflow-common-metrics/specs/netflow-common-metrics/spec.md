## ADDED Requirements

### Requirement: NetFlow v5 and v9 share one monitor plugin
The system SHALL keep NetFlow v5 and NetFlow v9 as one user-facing NetFlow monitor plugin while collecting them through version-specific Telegraf listeners.

#### Scenario: NetFlow listeners are version-specific
- **WHEN** the built-in Telegraf collector definition is initialized
- **THEN** it contains one NetFlow v5 listener on UDP 2055 and one NetFlow v9 listener on UDP 2056
- **AND** both listeners tag records with `collect_type=netflow`
- **AND** each listener tags records with the corresponding `netflow_version`

#### Scenario: Monitor plugin remains protocol-level
- **WHEN** a user opens or configures a NetFlow Flow analysis plugin
- **THEN** the system presents one NetFlow plugin rather than separate v5 and v9 plugins
- **AND** the access guide explains which listener endpoint to use for each export version

### Requirement: Collector preprocessing exposes common NetFlow dimensions
The system SHALL convert common NetFlow flow-record dimensions into queryable tags before metrics are sent to storage.

#### Scenario: Endpoint and protocol dimensions are tags
- **WHEN** Telegraf processes a NetFlow record
- **THEN** `protocol`, `src`, `src_port`, `dst`, and `dst_port` are available as tags for grouping and filtering

#### Scenario: Interface dimensions are tags
- **WHEN** Telegraf processes a NetFlow record that contains interface index fields
- **THEN** `in_snmp` and `out_snmp` are available as tags for grouping and filtering

### Requirement: NetFlow metrics use portable bytes and packets fields
The system SHALL base NetFlow byte and packet metrics on fields that are portable across NetFlow v5 and v9.

#### Scenario: NetFlow plugin does not depend on out bytes fields
- **WHEN** built-in NetFlow monitor plugin metrics are imported or tested
- **THEN** NetFlow metric queries do not reference `netflow_out_bytes`
- **AND** NetFlow metric queries do not reference `netflow_out_packets`

#### Scenario: Overview metrics use flow record counters
- **WHEN** the system queries NetFlow overview traffic metrics
- **THEN** byte metrics aggregate `netflow_in_bytes`
- **AND** packet metrics aggregate `netflow_in_packets`
- **AND** the queries apply the asset's effective sampling rate

#### Scenario: Protocol, port, endpoint, and conversation metrics use common dimensions
- **WHEN** the system queries NetFlow protocol, port, endpoint, or conversation metrics
- **THEN** the queries aggregate `netflow_in_bytes` or `netflow_in_packets`
- **AND** the queries group only by common NetFlow dimensions such as `protocol`, `src`, `dst`, `src_port`, and `dst_port`

### Requirement: Interface direction is derived from interface dimensions
The system SHALL represent NetFlow interface direction by grouping the same flow-record bytes and packets by input and output interface labels.

#### Scenario: Ingress interface metrics use in_snmp
- **WHEN** the system queries ingress interface traffic for NetFlow
- **THEN** the query groups `netflow_in_bytes` or `netflow_in_packets` by `in_snmp`
- **AND** the resulting series identifies the direction as ingress

#### Scenario: Egress interface metrics use out_snmp
- **WHEN** the system queries egress interface traffic for NetFlow
- **THEN** the query groups `netflow_in_bytes` or `netflow_in_packets` by `out_snmp`
- **AND** the resulting series identifies the direction as egress

### Requirement: Existing Flow assets remain compatible
The system SHALL preserve existing Flow asset and monitor instance contracts while changing the NetFlow metric query contract.

#### Scenario: Existing NetFlow assets continue to match incoming records
- **WHEN** an existing Flow asset has `netflow` enabled
- **THEN** incoming NetFlow v5 and v9 records that match the asset source IP continue to receive `instance_id`, `instance_type`, `collect_type`, and `effective_sampling_rate`

#### Scenario: Operational refresh updates persisted collector configs
- **WHEN** the optimized collector definition is deployed to an environment with existing nodes
- **THEN** running `node_init` followed by `repair_node_config` updates persisted collector defaults and repairs existing node configurations
