import { useMysqlTelegraf } from '../../plugins/database/mysqlTelegraf ';

export const useMysqlConfig = () => {
  const mysqlPlugin = useMysqlTelegraf();
  const plugins = {
    Mysql: mysqlPlugin,
  };

  return {
    instance_type: 'mysql',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'mysql_bytes_received' },
      { type: 'value', key: 'mysql_bytes_sent' },
      { type: 'value', key: 'mysql_connections_total' },
    ],
    groupIds: {},
    plugins,
  };
};
