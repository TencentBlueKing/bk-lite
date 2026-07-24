export const KAFKA_LAG_TOP_N = 10;

export const KAFKA_LAG_RISK_QUERIES = [
  {
    key: 'lag',
    unit: 'counts',
    query: `topk(${KAFKA_LAG_TOP_N}, max by (consumergroup, topic, partition) (kafka_consumergroup_lag_gauge{__$labels__}))`,
  },
  {
    key: 'currentOffset',
    unit: 'counts',
    query: 'max by (consumergroup, topic, partition) (kafka_consumergroup_current_offset_gauge{__$labels__})',
  },
  {
    key: 'oldestOffset',
    unit: 'counts',
    query: 'max by (topic, partition) (kafka_topic_partition_oldest_offset_gauge{__$labels__})',
  },
] as const;
