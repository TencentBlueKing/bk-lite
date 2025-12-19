export const useConsulConfig = () => {
  return {
    instance_type: 'consul',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'consul_health_checks_status' },
      { type: 'value', key: 'consul_health_checks_passing' },
    ],
    groupIds: {},
    collectTypes: {
      Consul: 'middleware',
    },
  };
};
