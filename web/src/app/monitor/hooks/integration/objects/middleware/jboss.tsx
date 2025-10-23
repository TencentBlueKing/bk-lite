import { useJbossJmx } from '../../plugins/middleware/jbossJmx';

export const useJbossConfig = () => {
  const plugin = useJbossJmx();

  const plugins = {
    'JBoss-JMX': plugin,
  };

  return {
    instance_type: 'jboss',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
