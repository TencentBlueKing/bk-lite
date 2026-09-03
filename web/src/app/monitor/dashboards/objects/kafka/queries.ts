export const KAFKA_LAG_TOP_N = 10;

export const KAFKA_LAG_TOP_QUERY = `topk(${KAFKA_LAG_TOP_N}, max by (consumergroup, topic, partition) (kafka_consumergroup_lag_gauge{__$labels__} >= 0))`;
