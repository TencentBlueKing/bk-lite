export const useKafkaConfig = () => {
  return {
    instance_type: 'kafka',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'kafka_up_gauge' },
      { type: 'enum', key: 'kafka_topic_partition_under_replicated_partition' },
      { type: 'value', key: 'kafka_consumergroup_lag' },
    ],
    groupIds: {},
    collectTypes: {
      'Kafka-Exporter': 'exporter',
    },
  };
};
