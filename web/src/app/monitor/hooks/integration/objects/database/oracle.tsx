export const useOracleConfig = () => {
  return {
    instance_type: 'oracle',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'oracledb_up_gauge' },
      { type: 'value', key: 'oracledb_uptime_seconds_gauge' },
    ],
    groupIds: {},
    collectTypes: {
      'Oracle-Exporter': 'exporter',
    },
  };
};
