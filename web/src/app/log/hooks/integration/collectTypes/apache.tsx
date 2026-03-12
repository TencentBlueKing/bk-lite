import { useFilebeatConfig } from '../collectors/filebeat/apache';

export const useApacheConfig = () => {
  const filebeat = useFilebeatConfig();
  const plugins = {
    Filebeat: filebeat
  };

  return {
    type: 'apache',
    plugins
  };
};
