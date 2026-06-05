export const useApacheConfig = () => {
  return {
    instance_type: 'apache',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'Apache-Exporter': 'exporter',
      Apache: 'middleware',
    },
  };
};
