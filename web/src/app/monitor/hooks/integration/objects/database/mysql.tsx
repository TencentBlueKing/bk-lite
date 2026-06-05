export const useMysqlConfig = () => {
  return {
    instance_type: 'mysql',
    dashboardDisplay: [
      {
        indexId: 'mysql_connection_utilization',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'mysql_queries_rate',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'mysql_slow_queries_rate',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'mysql_buffer_pool_hit_ratio',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'mysql_threads_connected',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '260px',
          width: '48%'
        }
      },
      {
        indexId: 'mysql_threads_running',
        displayType: 'lineChart',
        sortIndex: 5,
        displayDimension: [],
        style: {
          height: '260px',
          width: '48%'
        }
      },
      {
        indexId: 'mysql_queries_rate',
        displayType: 'lineChart',
        sortIndex: 6,
        displayDimension: [],
        style: {
          height: '260px',
          width: '48%'
        }
      },
      {
        indexId: 'mysql_bytes_sent_rate',
        displayType: 'lineChart',
        sortIndex: 7,
        displayDimension: [],
        style: {
          height: '260px',
          width: '48%'
        }
      }
    ],
    groupIds: {},
    collectTypes: {
      'Mysql-Exporter': 'exporter',
      Mysql: 'database'
    }
  };
};
