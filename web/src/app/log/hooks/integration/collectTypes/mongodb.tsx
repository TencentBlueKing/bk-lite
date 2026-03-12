import { useMongodbFilebeatConfig } from '../collectors/filebeat/mongodb';

export const useMongodbConfig = () => {
  const filebeat = useMongodbFilebeatConfig();
  const plugins = {
    Filebeat: filebeat
  };

  return {
    type: 'mongodb',
    plugins
  };
};
