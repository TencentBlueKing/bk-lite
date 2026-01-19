export const useMssqlConfig = () => {
  return {
    instance_type: 'mssql',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'sqlserver_database_io_read_latency_ms' },
      { type: 'value', key: 'sqlserver_waitstats_wait_time_ms_rate' },
      { type: 'value', key: 'sqlserver_volume_space_available_space_bytes' },
    ],
    groupIds: {},
    collectTypes: {
      'MSSQL-Exporter': 'exporter',
      MSSQL: 'database',
    },
  };
};
