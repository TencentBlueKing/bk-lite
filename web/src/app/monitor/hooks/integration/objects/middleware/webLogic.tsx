export const useWebLogicConfig = () => {
  return {
    instance_type: 'weblogic',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'weblogic_threadpool_stuck_thread_count_value' },
      { type: 'value', key: 'weblogic_threadpool_load_ratio' },
      {
        type: 'enum',
        key: 'weblogic_application_overallhealthstatejmx_is_critical_value',
      },
      { type: 'enum', key: 'jvm_memory_usage_used_value' },
    ],
    groupIds: {},
    collectTypes: {
      'WebLogic-JMX': 'jmx',
    },
  };
};
