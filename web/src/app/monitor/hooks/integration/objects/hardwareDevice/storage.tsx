export const useStorageConfig = () => {
  return {
    instance_type: 'storage',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'Storage IPMI': 'ipmi',
      OceanStor: 'oceanstor',
    },
  };
};
