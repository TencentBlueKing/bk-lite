export const useWebsiteConfig = () => {
  return {
    instance_type: 'web',
    dashboardDisplay: [
      {
        indexId: 'http_node_success_rate',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'http_response_response_time',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'http_ssl',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'http_status_code',
        displayType: 'lineChart',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '48%',
        },
      },
      {
        indexId: 'http_dns.lookup.time',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '48%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'progress', key: 'http_node_success_rate' },
      { type: 'value', key: 'http_response_response_time' },
      { type: 'value', key: 'http_response_http_response_code' },
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id'],
    },
    collectTypes: {
      Website: 'web',
    },
  };
};
