import { useRedisFilebeatConfig } from '../collectors/filebeat/redis';

export const useRedisConfig = () => {
  const filebeat = useRedisFilebeatConfig();
  const plugins = {
    Filebeat: filebeat
  };

  return {
    type: 'redis',
    plugins
  };
};
