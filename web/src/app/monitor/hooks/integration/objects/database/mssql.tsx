export const useMssqlConfig = () => {
  return {
    instance_type: 'mssql',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'MSSQL-Exporter': 'exporter',
      MSSQL: 'database',
    },
  };
};
