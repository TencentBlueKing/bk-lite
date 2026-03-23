import { useElasticsearchFilebeatConfig } from '../collectors/filebeat/elasticsearch';

export const useElasticsearchConfig = () => {
  const filebeat = useElasticsearchFilebeatConfig();
  const plugins = {
    Filebeat: filebeat
  };

  return {
    type: 'elasticsearch',
    plugins
  };
};
