import { usePostgresqlFilebeatConfig } from '../collectors/filebeat/postgresql';

export const usePostgresqlConfig = () => {
  const filebeat = usePostgresqlFilebeatConfig();
  const plugins = {
    Filebeat: filebeat
  };

  return {
    type: 'postgresql',
    plugins
  };
};
