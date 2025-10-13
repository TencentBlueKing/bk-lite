import { useTomcatTelegraf } from '../../plugins/middleware/tomcatTelegraf';
import { useTomcatJmx } from '../../plugins/middleware/tomcatJmx';

export const useTomcatConfig = () => {
  const tomcatPlugin = useTomcatTelegraf();
  const tomcatJmxPlugin = useTomcatJmx();

  const plugins = {
    Tomcat: tomcatPlugin,
    'Tomcat-JMX': tomcatJmxPlugin,
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
