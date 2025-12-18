export const useOpenGaussConfig = () => {
  return {
    instance_type: 'opengauss',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    collectTypes: {
      'OpenGauss-Exporter': 'exporter',
    },
  };
};
