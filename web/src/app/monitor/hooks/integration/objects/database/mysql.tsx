export const useMysqlConfig = () => {
  return {
    instance_type: 'mysql',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'mysql_bytes_received' },
      { type: 'value', key: 'mysql_bytes_sent' },
      { type: 'value', key: 'mysql_connections_total' },
    ],
    groupIds: {},
    collectTypes: {
      'Mysql-Exporter': 'exporter',
      Mysql: 'database',
    },
  };
};
