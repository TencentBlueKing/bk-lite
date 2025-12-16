import { useNginxTelegraf } from '../../plugins/middleware/nginxTelegraf';

export const useNginxConfig = () => {
  const nginxTelegraf = useNginxTelegraf();

  const plugins = {
    Nginx: nginxTelegraf,
  };

  return {
    instance_type: 'nginx',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'nginx_requests' },
      { type: 'value', key: 'nginx_active' },
    ],
    groupIds: {},
    plugins,
  };
};
