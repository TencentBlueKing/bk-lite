export const useNginxConfig = () => {
  return {
    instance_type: 'nginx',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'Nginx-Exporter': 'exporter',
      Nginx: 'middleware',
    },
  };
};
