export const useKafkaConfig = () => {
  return {
    instance_type: 'kafka',
    dashboardDisplay: [
      'kafka_up_gauge',
      'kafka_topic_partition_under_replicated_partition',
      'kafka_consumergroup_lag',
    ],
    groupIds: {},
    collectTypes: {
      'Kafka-Exporter': 'exporter',
    },
  };
};
