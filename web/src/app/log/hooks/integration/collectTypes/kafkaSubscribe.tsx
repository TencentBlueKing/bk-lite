import { useVectorConfig } from '../collectors/vector/kafkaSubscribe';

export const useKafkaSubscribeConfig = () => {
  const vector = useVectorConfig();
  const plugins = {
    Vector: vector
  };

  return {
    type: 'kafka_subscribe',
    plugins
  };
};
