import { useFilebeatConfig } from '../collectors/filebeat/filestream';

export const useFilestreamConfig = () => {
  const filebeat = useFilebeatConfig();
  const plugins = {
    Filebeat: filebeat,
  };

  return {
    type: 'filestream',
    plugins,
  };
};
