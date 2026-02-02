export const useEsxiConfig = () => {
  return {
    instance_type: 'vmware',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'progress', key: 'cpu_usage_average_gauge' },
      { type: 'progress', key: 'mem_usage_average_gauge' },
      { type: 'value', key: 'disk_read_average_gauge' },
    ],
    groupIds: {},
    collectTypes: {
      VMWare: 'http',
    },
  };
};
