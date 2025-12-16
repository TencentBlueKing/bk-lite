import { useMssqlTelegraf } from '../../plugins/database/mssqlTelegraf';

export const useMssqlConfig = () => {
  const mssqlTelegraf = useMssqlTelegraf();
  const plugins = {
    MSSQL: mssqlTelegraf,
  };

  return {
    instance_type: 'mssql',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'sqlserver_uptime' },
      { type: 'value', key: 'volume_available_gb' },
      { type: 'progress', key: 'memory_usage' },
    ],
    groupIds: {},
    plugins,
  };
};
