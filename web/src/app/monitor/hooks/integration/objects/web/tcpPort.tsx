export const useTcpPortConfig = () => {
  return {
    instance_type: 'tcp',
    dashboardDisplay: [
      {
        indexId: 'net_response_response_time',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'net_response_result_code',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
    ],
    groupIds: {},
    collectTypes: {
      TCPPort: 'tcp',
    },
  };
};
