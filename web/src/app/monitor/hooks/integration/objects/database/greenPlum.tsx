export const useGreenPlumConfig = () => {
  return {
    instance_type: 'greenplum',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    collectTypes: {
      'GreenPlum-Exporter': 'exporter',
    },
  };
};
