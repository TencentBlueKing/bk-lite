import { useNginxFilebeatConfig } from '../collectors/filebeat/nginx';

export const useNginxConfig = () => {
  const filebeat = useNginxFilebeatConfig();
  const plugins = {
    Filebeat: filebeat
  };

  return {
    type: 'nginx',
    plugins
  };
};
