export const useDb2Config = () => {
  return {
    instance_type: 'db2',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    collectTypes: {
      'DB2-Exporter': 'database',
    },
  };
};
