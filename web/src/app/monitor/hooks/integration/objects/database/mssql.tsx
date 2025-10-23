import { useMssqlTelegraf } from '../../plugins/database/mssqlTelegraf';
import { useMssqlExporter } from '../../plugins/database/mssqlExporter';

export const useMssqlConfig = () => {
  const mssqlTelegraf = useMssqlTelegraf();
  const mssqlExporter = useMssqlExporter();
  const plugins = {
    MSSQL: mssqlTelegraf,
    'MSSQL-Exporter': mssqlExporter,
  };

  return {
    instance_type: 'mssql',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
