import { useVCenterTelegraf } from '../../plugins/vmWare/vCenterTelegraf';

export const useVCenterConfig = () => {
  const vCenter = useVCenterTelegraf();
  const plugins = {
    VMWare: vCenter,
  };

  return {
    instance_type: 'vmware',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'vmware_esxi_count' },
      { type: 'value', key: 'vmware_datastore_count' },
      { type: 'value', key: 'vmware_vm_count' },
    ],
    groupIds: {},
    plugins,
  };
};
