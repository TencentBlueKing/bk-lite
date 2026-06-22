export const useInfluxDBConfig = () => {
  return {
    instance_type: 'influxdb',
    dashboardDisplay: [
      {
        indexId: 'influxdb_database_numSeries',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'influxdb_httpd_writeReq_rate',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'influxdb_httpd_pointsWrittenFail_rate',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'influxdb_runtime_HeapAlloc',
        displayType: 'lineChart',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
    ],
    groupIds: {},
    collectTypes: {
      InfluxDB: 'database',
    },
  };
};
