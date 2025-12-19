export const useElasticSearchConfig = () => {
  return {
    instance_type: 'elasticsearch',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'elasticsearch_fs_total_available_in_bytes' },
      { type: 'value', key: 'elasticsearch_http_current_open' },
      { type: 'value', key: 'elasticsearch_indices_docs_count' },
    ],
    groupIds: {},
    collectTypes: {
      'ElasticSearch-Exporter': 'exporter',
      ElasticSearch: 'database',
    },
  };
};
