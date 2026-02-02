export const useOracleConfig = () => {
  return {
    instance_type: 'oracle',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'oracledb_up_gauge' },
      { type: 'value', key: 'oracledb_wait_time_user_io_gauge' },
      { type: 'progress', key: 'oracledb_tablespace_used_percent_gauge' },
    ],
    groupIds: {},
    collectTypes: {
      'Oracle-Exporter': 'exporter',
    },
  };
};
