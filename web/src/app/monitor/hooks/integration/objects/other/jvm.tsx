import { useJvmJmx } from '../../plugins/other/jvmJmx';

export const useJvmConfig = () => {
  const plugin = useJvmJmx();

  // 所有插件配置
  const plugins = {
    JVM: plugin,
  };

  return {
    instance_type: 'jvm',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'jmx_scrape_error_gauge' },
      { type: 'value', key: 'jvm_memory_usage_used_value' },
      { type: 'value', key: 'jvm_memory_usage_max_value' },
      { type: 'value', key: 'jvm_os_memory_physical_free_value' },
      { type: 'value', key: 'jvm_gc_collectiontime_seconds_value' },
    ],
    groupIds: {},
    plugins,
  };
};
