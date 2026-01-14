export const useConsulConfig = () => {
  return {
    instance_type: 'consul',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'consul_health_checks_passing' },
      { type: 'enum', key: 'consul_health_checks_critical' },
      { type: 'enum', key: 'consul_health_checks_status' },
    ],
    groupIds: {},
    collectTypes: {
      Consul: 'middleware',
    },
  };
};
