export const usePostgresConfig = () => {
  return {
    instance_type: 'postgres',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'postgresql_numbackends' },
      { type: 'value', key: 'postgresql_blks_read_rate' },
      { type: 'value', key: 'postgresql_temp_files_rate' },
    ],
    groupIds: {},
    collectTypes: {
      'Postgres-Exporter': 'exporter',
      Postgres: 'database',
    },
  };
};
