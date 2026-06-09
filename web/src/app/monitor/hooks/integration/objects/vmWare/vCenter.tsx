export const useVCenterConfig = () => {
  return {
    instance_type: 'vmware',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      VMWare: 'http',
    },
  };
};
