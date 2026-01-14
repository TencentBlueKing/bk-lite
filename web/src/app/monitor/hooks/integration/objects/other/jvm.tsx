export const useJvmConfig = () => {
  return {
    instance_type: 'jvm',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'jmx_scrape_error_gauge' },
      { type: 'value', key: 'jvm_sqlserver_volume_space_available_space_bytes_used_value' },
      { type: 'value', key: 'jvm_sqlserver_volume_space_available_space_bytes_max_value' },
      { type: 'value', key: 'jvm_os_memory_physical_free_value' },
      { type: 'value', key: 'jvm_gc_collectiontime_seconds_value' },
    ],
    groupIds: {},
    collectTypes: {
      JVM: 'jmx',
    },
  };
};
