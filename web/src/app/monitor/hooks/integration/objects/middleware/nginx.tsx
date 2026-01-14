export const useNginxConfig = () => {
  return {
    instance_type: 'nginx',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'nginx_active' },
      { type: 'value', key: 'nginx_requests_rate' },
      { type: 'value', key: 'nginx_handled_rate' },
    ],
    groupIds: {},
    collectTypes: {
      'Nginx-Exporter': 'exporter',
      Nginx: 'middleware',
    },
  };
};
