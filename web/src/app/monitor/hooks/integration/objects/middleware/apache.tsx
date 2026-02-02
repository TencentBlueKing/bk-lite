export const useApacheConfig = () => {
  return {
    instance_type: 'apache',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'apache_ReqPerSec' },
      { type: 'value', key: 'apache_BusyWorkers' },
      { type: 'progress', key: 'apache_CPULoad' },
    ],
    groupIds: {},
    collectTypes: {
      'Apache-Exporter': 'exporter',
      Apache: 'middleware',
    },
  };
};
