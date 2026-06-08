# Flow Region Receiver Telegraf Design

## Background

Network Flow collection is passive. NetFlow and sFlow devices send data to a receiver address, so the platform must run one stable receiver per cloud region instead of creating per-asset Telegraf child configs.

The existing Telegraf default configuration already uses this pattern for `inputs.http_listener_v2`: listener configuration lives in `server/apps/node_mgmt/support-files/collectors/Telegraf.json` under `default_config.add_config`, and node management appends `add_config` only for container nodes. Flow should follow the same container-node receiver model.

## Decision

Use a cloud-region-level Flow receiver on the container/proxy node Telegraf base configuration.

The implementation must not create Flow child toml configs. Flow plugin instances manage assets and mappings only. Listener and enrichment logic live in the Telegraf base configuration appended for container nodes.

## Architecture

```text
Cloud region
  -> One Flow receiver address
  -> Container/proxy node Telegraf base configuration
  -> inputs.netflow, inputs.sflow, and Flow processor in add_config
  -> FLOW_ASSET_MAP_JSON stored in base config env_config
```

The receiver address remains cloud-region scoped. The guide page can continue to show one NetFlow endpoint and one sFlow endpoint for the selected cloud region.

## Components

### Telegraf Base Configuration

`server/apps/node_mgmt/support-files/collectors/Telegraf.json` should include the Flow receiver and enrichment processor in `default_config.add_config`, next to `inputs.http_listener_v2`.

Required listener entries:

```toml
[[inputs.netflow]]
    service_address = "udp://:2055"

[[inputs.sflow]]
    service_address = "udp://:6343"
```

The same `add_config` block should include a processor that enriches Flow metrics using `FLOW_ASSET_MAP_JSON`.

### Flow Mapping Env Config

`FlowEnvConfigService` owns the Flow asset mapping.

For a cloud region, it builds:

```json
{
  "1:10.0.0.12": {
    "instance_id": "('flow-device-1',)",
    "instance_type": "switch",
    "fallback_sampling_rate": 1000,
    "protocols": ["netflow", "sflow"]
  }
}
```

The key format is:

```text
{cloud_region_id}:{device_ip}
```

### Node Management Target

Refreshing Flow env config should update Telegraf base configurations bound to container nodes in the target cloud region.

Selection rules:

1. Find nodes in the target cloud region whose node type is container.
2. Find Telegraf collector configurations bound to those nodes.
3. Prefer pre-created/default Telegraf base configurations.
4. Merge `FLOW_ASSET_MAP_JSON` into each selected base configuration `env_config`.
5. Preserve unrelated env_config keys.

If a cloud region has multiple container nodes, update all of them. This keeps failover or migration setups consistent. If a cloud region has no container Telegraf base configuration, log the miss and return without failing the user-facing asset operation.

## Data Flow

```text
Flow asset create/update/delete
  -> FlowEnvConfigService.build_asset_map(cloud_region_id)
  -> FlowEnvConfigService.refresh_region_receiver_env_config(cloud_region_id)
  -> NodeMgmt.update_config_content(base_config_id, existing_content, env_config)
  -> Sidecar get_node_config_env returns FLOW_ASSET_MAP_JSON
  -> Telegraf runs receiver and processor
  -> Flow metrics carry normalized tags
```

## Enrichment Rules

The processor should only enrich NetFlow and sFlow metrics.

For each Flow metric:

1. Determine `collect_type` from the input or metric name: `netflow` or `sflow`.
2. Determine device IP from the Flow exporter/source address exposed by the Telegraf input.
3. Match `{cloud_region_id}:{device_ip}` in `FLOW_ASSET_MAP_JSON`.
4. Skip enrichment if there is no mapping or the mapping does not include the current protocol.
5. Add tags:
   - `instance_id`
   - `instance_type`
   - `fallback_sampling_rate`
   - `collect_type`
   - `effective_sampling_rate`

`effective_sampling_rate` priority:

```text
effective_sampling_rate
SAMPLING_INTERVAL
SAMPLING_ALGORITHM
sampling_rate
samplingRate
fallback_sampling_rate
```

A valid sampling rate is a non-empty numeric value greater than or equal to zero. Invalid values are ignored and the processor tries the next candidate.

## Error Handling

Flow asset operations should not fail only because Telegraf config refresh fails. They should log the refresh failure with cloud region and config identifiers, then continue.

The next asset update or a manual refresh can repair the env_config. This matches the existing asynchronous refresh behavior and avoids blocking asset onboarding on collector management availability.

## Testing Plan

Use TDD for implementation.

Required red-green tests:

1. Telegraf collector definition includes `inputs.netflow`, `inputs.sflow`, and the Flow processor in `add_config`.
2. Flow env refresh targets container-node Telegraf base configurations, not Flow child configs.
3. Non-container-node Telegraf configurations are not updated.
4. Multiple container nodes in the same cloud region are all updated.
5. Existing base `env_config` keys are preserved when `FLOW_ASSET_MAP_JSON` is merged.
6. Missing container Telegraf base configuration is logged and does not raise.
7. Asset mapping includes `instance_id`, `instance_type`, `fallback_sampling_rate`, and `protocols`.
8. Processor logic covers sampling-rate priority and fallback behavior.

## Out Of Scope

This design does not add Flow child toml configs.

This design does not introduce per-asset receiver addresses.

This design does not replace Telegraf with a server-side Flow receiver.
