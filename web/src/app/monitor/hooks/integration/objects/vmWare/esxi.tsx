export const useEsxiConfig = () => {
  return {
    instance_type: 'vmware',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'esxi_cpu_usage_average_gauge' },
      { type: 'value', key: 'esxi_mem_usage_average_gauge' },
      { type: 'value', key: 'esxi_disk_read_average_gauge' },
    ],
    groupIds: {},
    plugins: {},
  };
};
