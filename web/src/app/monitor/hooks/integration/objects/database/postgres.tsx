export const usePostgresConfig = () => {
  return {
    instance_type: 'postgres',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'postgresql_active_time' },
      { type: 'value', key: 'postgresql_blks_hit' },
    ],
    groupIds: {},
    collectTypes: {
      'Postgres-Exporter': 'exporter',
      Postgres: 'database',
    },
  };
};
