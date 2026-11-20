# RocketMQ Monitoring Guide

This capability collects broker throughput, CommitLog disk usage, current topic and consumer-group offsets, consume backlog, and dead-letter topic offsets for a RocketMQ 4.x cluster. RocketMQ 5.x is outside this capability.

## Prerequisites

- The collector node can reach NameServer, commonly on port 9876. When several addresses are entered, reaching one of them is enough.
- Leave the access key and secret key empty when access control is disabled. When it is enabled, enter both.
- If the Broker address registered in NameServer cannot be reached from the collector node, enter one reachable Broker address. Leave it empty to use the registered address.

## Setup Steps

1. From the actual collector node, confirm that the NameServer address is reachable.
2. Enter the NameServer address. Separate multiple addresses with commas.
3. Enter a Broker address, access key, and secret key only when needed.
4. Set the interval (default 60 seconds; 30 seconds or more is recommended).
5. In the monitored objects table, select the node and enter the same NameServer address, optional Broker address, instance name, and optional group.
6. Save the configuration and wait for at least one collection interval.

## Pre-checks

```bash
nc -vz namesrv.example.com 9876
```

The command should report that the port is reachable. Run it on the actual collector node.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| NameServer Address | Yes | One or more `host:port` values, separated by commas. Port 9876 is typical. |
| Broker Address | No | One reachable `host:port` when the registered address cannot be reached. Leave empty to use the registered address. |
| Access Key | No | Enter with the secret key when access control is enabled. Leave empty otherwise. |
| Secret Key | No | Enter with the access key when access control is enabled. Leave empty otherwise. |
| Interval | Yes | Collection interval in seconds. The default is 60; 30 seconds or more is recommended. |
| Node | Yes | Collector node that can reach the NameServer. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable:

- Collection Status (`bklite_rocketmq_up`)
- Broker Write TPS (`bklite_rocketmq_broker_tps`)
- Broker Read TPS (`bklite_rocketmq_broker_qps`)
- CommitLog Disk Usage (`bklite_rocketmq_broker_commitlog_disk_ratio`)
- Topic Current Offset (`bklite_rocketmq_producer_offset`)
- Consumer Group Current Offset (`bklite_rocketmq_consumer_offset`)
- Consume TPS (`bklite_rocketmq_consumer_tps`)
- Consumer Backlog (`bklite_rocketmq_group_diff`)
- Dead-Letter Topic Offset (`bklite_rocketmq_group_dlq`)

The dead-letter topic name is `%DLQ%` followed by the consumer group name.

## Common Issues

### Collection Status is 0

- From the actual collector node, check the NameServer address, port, and network.
- When access control is enabled, confirm that the access key and secret key are both set and have no leading or trailing spaces.

### Broker, topic, or consumer metrics are missing

- If the registered Broker address cannot be reached, enter a reachable Broker address and save again.
- Metrics for a topic or consumer group appear only when that topic or group exists on the cluster.
