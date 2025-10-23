import { usePostgresTelegraf } from '../../plugins/database/postgresTelegraf';
import { usePostgresExporter } from '../../plugins/database/postgresExporter';

export const usePostgresConfig = () => {
  const postgresPlugin = usePostgresTelegraf();
  const postgresExporterPlugin = usePostgresExporter();
  const plugins = {
    Postgres: postgresPlugin,
    'Postgres-Exporter': postgresExporterPlugin,
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
