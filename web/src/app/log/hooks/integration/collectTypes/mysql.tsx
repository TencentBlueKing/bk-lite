import { useMysqlFilebeatConfig } from '../collectors/filebeat/mysql';

export const useMysqlConfig = () => {
  const filebeat = useMysqlFilebeatConfig();
  const plugins = {
    Filebeat: filebeat
  };

  return {
    type: 'mysql',
    plugins
  };
};
