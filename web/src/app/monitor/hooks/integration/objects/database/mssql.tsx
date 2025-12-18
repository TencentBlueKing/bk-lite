export const useMssqlConfig = () => {
  return {
    instance_type: 'mssql',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'sqlserver_uptime' },
      { type: 'value', key: 'volume_available_gb' },
      { type: 'progress', key: 'memory_usage' },
    ],
    groupIds: {},
    collectTypes: {
      'MSSQL-Exporter': 'exporter',
      MSSQL: 'database',
    },
  };
};
