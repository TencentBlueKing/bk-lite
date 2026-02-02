export const usePingConfig = () => {
  return {
    instance_type: 'ping',
    dashboardDisplay: [
      {
        indexId: 'ping_average_response_ms',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'ping_result_code',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'ping_average_response_ms' },
      { type: 'progress', key: 'ping_percent_packet_loss' },
      { type: 'enum', key: 'ping_result_code' },
    ],
    groupIds: {},
    collectTypes: {
      Ping: 'ping',
    },
  };
};
