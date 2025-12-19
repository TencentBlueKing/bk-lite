export const useJettyJmxConfig = () => {
  return {
    instance_type: 'jetty',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'progress', key: 'jetty_queuedthreadpool_utilizationrate_value' },
      { type: 'value', key: 'jvm_memory_heap_usage_used_rate' },
      { type: 'value', key: 'jvm_memory_heap_usage_max_value' },
      { type: 'enum', key: 'jmx_scrape_error_gauge' },
    ],
    groupIds: {},
    collectTypes: {
      'Jetty-JMX': 'jmx',
    },
  };
};
