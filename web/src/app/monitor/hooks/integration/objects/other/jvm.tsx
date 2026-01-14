export const useJvmConfig = () => {
  return {
    instance_type: 'jvm',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'jvm_memory_usage_used_value' },
      { type: 'value', key: 'jvm_threads_count_value' },
      { type: 'value', key: 'jvm_gc_collectiontime_seconds_value' },
    ],
    groupIds: {},
    collectTypes: {
      JVM: 'jmx',
    },
  };
};
