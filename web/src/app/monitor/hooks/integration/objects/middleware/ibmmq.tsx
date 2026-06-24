export const useIBMMQConfig = () => {
  return {
    instance_type: 'ibmmq',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'IBM-MQ-Exporter': 'exporter',
    },
  };
};
