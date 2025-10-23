import { useWebLogicJmx } from '../../plugins/middleware/webLogicJmx';

export const useWebLogicConfig = () => {
  const webLogicPlugin = useWebLogicJmx();

  const plugins = {
    'WebLogic-JMX': webLogicPlugin,
  };

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
      { type: 'enum', key: 'jmx_scrape_error_gauge' },
    ],
    groupIds: {},
    plugins,
  };
};
