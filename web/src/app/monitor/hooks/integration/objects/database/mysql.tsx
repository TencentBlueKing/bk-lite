export const useMysqlConfig = () => {
  return {
    instance_type: 'mysql',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'mysql_threads_running' },
      { type: 'value', key: 'mysql_slow_queries_rate' },
      { type: 'value', key: 'mysql_innodb_buffer_pool_reads_rate' }
    ],
    groupIds: {},
    collectTypes: {
      'Mysql-Exporter': 'exporter',
      Mysql: 'database'
    }
  };
};
