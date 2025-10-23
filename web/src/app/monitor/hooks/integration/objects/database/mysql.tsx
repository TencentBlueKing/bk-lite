import { useMysqlTelegraf } from '../../plugins/database/mysqlTelegraf ';
import { useMysqlExporter } from '../../plugins/database/mysqlExporter';

export const useMysqlConfig = () => {
  const mysqlPlugin = useMysqlTelegraf();
  const mysqlExporterExporter = useMysqlExporter();
  const plugins = {
    Mysql: mysqlPlugin,
    'Mysql-Exporter': mysqlExporterExporter,
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
