import { useKafkaExporter } from '../../plugins/middleware/kafkaExporter';

export const useKafkaConfig = () => {
  const kafkaPlugin = useKafkaExporter();
  const plugins = {
    'Kafka-Exporter': kafkaPlugin,
  };

  return {
    instance_type: 'kafka',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
