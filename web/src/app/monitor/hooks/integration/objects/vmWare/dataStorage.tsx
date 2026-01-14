export const useDataStorageConfig = () => {
  return {
    instance_type: 'vmware',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'progress', key: 'disk_used_average_gauge' },
      { type: 'enum', key: 'store_accessible_gauge' },
    ],
    groupIds: {},
    collectTypes: {
      VMWare: 'http',
    },
  };
};
