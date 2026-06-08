export const useKafkaConfig = () => {
  return {
    instance_type: 'kafka',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'Kafka-Exporter': 'exporter',
    },
  };
};
