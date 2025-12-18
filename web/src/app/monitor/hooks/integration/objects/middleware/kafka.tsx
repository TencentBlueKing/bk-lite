export const useKafkaConfig = () => {
  return {
    instance_type: 'kafka',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    collectTypes: {
      'Kafka-Exporter': 'exporter',
    },
  };
};
