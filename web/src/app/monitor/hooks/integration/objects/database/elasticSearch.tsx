export const useElasticSearchConfig = () => {
  return {
    instance_type: 'elasticsearch',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'elasticsearch_cluster_health_status_code' },
      { type: 'value', key: 'elasticsearch_cluster_health_unassigned_shards' },
      { type: 'progress', key: 'elasticsearch_jvm_mem_heap_used_percent' },
    ],
    groupIds: {},
    collectTypes: {
      'ElasticSearch-Exporter': 'exporter',
      ElasticSearch: 'database',
    },
  };
};
