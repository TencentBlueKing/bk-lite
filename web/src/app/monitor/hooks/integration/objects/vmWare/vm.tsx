export const useVmConfig = () => {
  return {
    instance_type: 'vmware',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'progress', key: 'mem_usage_average_gauge' },
      { type: 'enum', key: 'power_state_gauge' },
    ],
    groupIds: {},
    collectTypes: {
      VMWare: 'http',
    },
  };
};
