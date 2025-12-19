export const useNginxConfig = () => {
  return {
    instance_type: 'nginx',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'nginx_requests' },
      { type: 'value', key: 'nginx_active' },
    ],
    groupIds: {},
    collectTypes: {
      'Nginx-Exporter': 'exporter',
      Nginx: 'middleware',
    },
  };
};
