export const useVCenterConfig = () => {
  return {
    instance_type: 'vmware',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'vmware_esxi_count' },
      { type: 'value', key: 'vmware_datastore_count' },
      { type: 'value', key: 'vmware_vm_count' },
    ],
    groupIds: {},
    collectTypes: {
      VMWare: 'http',
    },
  };
};
