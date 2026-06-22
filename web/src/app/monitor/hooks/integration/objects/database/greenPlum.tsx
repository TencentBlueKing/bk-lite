export const useGreenPlumConfig = () => {
  return {
    instance_type: 'greenplum',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'GreenPlum-Exporter': 'exporter',
    },
  };
};
