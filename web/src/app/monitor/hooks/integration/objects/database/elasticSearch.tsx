import { useElasticSearchTelegraf } from '../../plugins/database/elasticSearchTelegraf';

export const useElasticSearchConfig = () => {
  const ElasticSearchTelegraf = useElasticSearchTelegraf();
  const plugins = {
    ElasticSearch: ElasticSearchTelegraf,
  };

  return {
    instance_type: 'elasticsearch',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'elasticsearch_fs_total_available_in_bytes' },
      { type: 'value', key: 'elasticsearch_http_current_open' },
      { type: 'value', key: 'elasticsearch_indices_docs_count' },
    ],
    groupIds: {},
    plugins,
  };
};
