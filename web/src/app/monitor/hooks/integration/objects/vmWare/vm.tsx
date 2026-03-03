export const useVmConfig = () => {
  return {
    instance_type: 'vmware',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'progress', key: 'cpu_usage_average_gauge' },
      { type: 'progress', key: 'mem_usage_average_gauge' },
      { type: 'progress', key: 'disk_io_usage_gauge' },
    ],
    groupIds: {},
    collectTypes: {
      VMWare: 'http',
    },
  };
};
