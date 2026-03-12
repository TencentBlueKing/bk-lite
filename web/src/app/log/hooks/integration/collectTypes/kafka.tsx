import { useKafkaFilebeatConfig } from '../collectors/filebeat/kafka';

export const useKafkaConfig = () => {
  const filebeat = useKafkaFilebeatConfig();
  const plugins = {
    Filebeat: filebeat
  };

  return {
    type: 'kafka',
    plugins
  };
};
