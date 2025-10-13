import { useConsulTelegraf } from '../../plugins/middleware/consulTelegraf';

export const useConsulConfig = () => {
  const consulTelegraf = useConsulTelegraf();

  const plugins = {
    Consul: consulTelegraf,
  };

  return {
    instance_type: 'consul',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'consul_health_checks_status' },
      { type: 'value', key: 'consul_health_checks_passing' },
    ],
    groupIds: {},
    plugins,
  };
};
