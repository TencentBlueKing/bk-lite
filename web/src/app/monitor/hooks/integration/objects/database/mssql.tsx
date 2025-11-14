import { useMssqlTelegraf } from '../../plugins/database/mssqlTelegraf';

export const useMssqlConfig = () => {
  const mssqlTelegraf = useMssqlTelegraf();
  const plugins = {
    MSSQL: mssqlTelegraf,
  };

  return {
    instance_type: 'mssql',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
