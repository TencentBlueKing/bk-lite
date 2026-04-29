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
    tableDiaplay: [
      { type: 'value', key: 'influxdb_database_numSeries' },
      { type: 'value', key: 'influxdb_httpd_writeReq_rate' },
      { type: 'value', key: 'influxdb_httpd_pointsWrittenFail_rate' },
      { type: 'value', key: 'influxdb_httpd_pointsWrittenDropped_rate' },
      { type: 'value', key: 'influxdb_runtime_HeapAlloc' },
    ],
    groupIds: {},
    collectTypes: {
      InfluxDB: 'database',
    },
  };
};
