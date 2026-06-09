export const useConsulConfig = () => {
  return {
    instance_type: 'consul',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      Consul: 'middleware',
    },
  };
};
