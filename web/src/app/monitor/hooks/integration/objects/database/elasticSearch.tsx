export const useElasticSearchConfig = () => {
  return {
    instance_type: 'elasticsearch',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'progress', key: 'elasticsearch_jvm_mem_heap_used_percent' },
      { type: 'value', key: 'elasticsearch_fs_data_0_available_in_bytes' },
      { type: 'progress', key: 'elasticsearch_process_cpu_percent' }
    ],
    groupIds: {},
    collectTypes: {
      'ElasticSearch-Exporter': 'exporter',
      ElasticSearch: 'database'
    }
  };
};
