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
      { type: 'enum', key: 'nginx_up' },
      { type: 'value', key: 'nginx_connections_active' },
      { type: 'value', key: 'nginx_http_requests_total' },
      { type: 'value', key: 'nginx_vts_server_requestMsec' },
    ],
    groupIds: {},
    plugins,
  };
};
