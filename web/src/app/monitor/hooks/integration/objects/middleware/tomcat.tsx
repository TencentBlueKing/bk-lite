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
    ],
    groupIds: {},
    plugins,
  };
};
