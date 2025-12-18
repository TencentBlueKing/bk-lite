export const useApacheConfig = () => {
  return {
    instance_type: 'apache',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'apache_uptime' },
      { type: 'value', key: 'apache_req_per_sec' },
      { type: 'progress', key: 'apache_cpu_load' },
    ],
    groupIds: {},
    collectTypes: {
      'Apache-Exporter': 'exporter',
      Apache: 'middleware',
    },
  };
};
