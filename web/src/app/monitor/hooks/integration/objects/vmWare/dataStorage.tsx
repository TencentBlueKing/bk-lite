export const useDataStorageConfig = () => {
  return {
    instance_type: 'vmware',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'data_storage_disk_used_average_gauge' },
      { type: 'enum', key: 'data_storage_store_accessible_gauge' },
    ],
    groupIds: {},
    plugins: {},
  };
};
