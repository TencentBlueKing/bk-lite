import { usePostgresTelegraf } from '../../plugins/database/postgresTelegraf';

export const usePostgresConfig = () => {
  const postgresPlugin = usePostgresTelegraf();
  const plugins = {
    Postgres: postgresPlugin,
  };

  return {
    instance_type: 'postgres',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'postgresql_active_time' },
      { type: 'value', key: 'postgresql_blks_hit' },
    ],
    groupIds: {},
    plugins,
  };
};
