import { useElasticSearchTelegraf } from '../../plugins/database/elasticSearchTelegraf';
import { useElasticSearchExporter } from '../../plugins/database/elasticSearchExporter';

export const useElasticSearchConfig = () => {
  const ElasticSearchTelegraf = useElasticSearchTelegraf();
  const ElasticSearchExporter = useElasticSearchExporter();
  const plugins = {
    ElasticSearch: ElasticSearchTelegraf,
    'ElasticSearch-Exporter': ElasticSearchExporter,
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
