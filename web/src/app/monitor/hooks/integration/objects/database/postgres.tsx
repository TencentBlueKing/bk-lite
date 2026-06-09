export const usePostgresConfig = () => {
  return {
    instance_type: 'postgres',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'Postgres-Exporter': 'exporter',
      Postgres: 'database',
    },
  };
};
