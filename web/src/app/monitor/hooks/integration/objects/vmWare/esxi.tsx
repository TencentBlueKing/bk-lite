export const useEsxiConfig = () => {
  return {
    instance_type: 'vmware',
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'progress', key: 'mem_usage_average_gauge' }],
    groupIds: {},
    collectTypes: {
      VMWare: 'http',
    },
  };
};
