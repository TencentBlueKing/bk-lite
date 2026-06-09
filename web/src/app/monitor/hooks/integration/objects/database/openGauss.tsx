export const useOpenGaussConfig = () => {
  return {
    instance_type: 'opengauss',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'OpenGauss-Exporter': 'exporter',
    },
  };
};
