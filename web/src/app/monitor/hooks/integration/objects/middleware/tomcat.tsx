export const useTomcatConfig = () => {
  return {
    instance_type: 'tomcat',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'tomcat_connector_current_threads_busy' },
      { type: 'value', key: 'tomcat_jvm_memorypool_used' },
      { type: 'value', key: 'tomcat_connector_error_count_rate' },
    ],
    groupIds: {},
    collectTypes: {
      'Tomcat-JMX': 'jmx',
      Tomcat: 'middleware',
    },
  };
};
