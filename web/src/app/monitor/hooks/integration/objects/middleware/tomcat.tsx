import { useTomcatTelegraf } from '../../plugins/middleware/tomcatTelegraf';

export const useTomcatConfig = () => {
  const tomcatPlugin = useTomcatTelegraf();

  const plugins = {
    Tomcat: tomcatPlugin,
  };

  return {
    instance_type: 'tomcat',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'tomcat_connector_request_count' },
      { type: 'value', key: 'tomcat_connector_current_threads_busy' },
      { type: 'value', key: 'tomcat_connector_error_count' },
      { type: 'value', key: 'tomcat_errorcount_increase' },
      { type: 'progress', key: 'tomcat_threadpool_utilization' },
      { type: 'progress', key: 'tomcat_session_rejectionrate' },
      { type: 'enum', key: 'jmx_scrape_error_gauge' },
    ],
    groupIds: {},
    plugins,
  };
};
