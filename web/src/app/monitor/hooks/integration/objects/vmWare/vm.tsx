export const useVmConfig = () => {
  return {
    instance_type: 'vmware',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'vm_cpu_usage_average_gauge' },
      { type: 'value', key: 'vm_mem_usage_average_gauge' },
      { type: 'value', key: 'vm_disk_io_usage_gauge' },
    ],
    groupIds: {},
    plugins: {},
  };
};
