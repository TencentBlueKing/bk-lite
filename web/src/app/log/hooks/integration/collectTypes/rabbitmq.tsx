import { useRabbitmqFilebeatConfig } from '../collectors/filebeat/rabbitmq';

export const useRabbitmqConfig = () => {
  const filebeat = useRabbitmqFilebeatConfig();
  const plugins = {
    Filebeat: filebeat
  };

  return {
    type: 'rabbitmq',
    plugins
  };
};
