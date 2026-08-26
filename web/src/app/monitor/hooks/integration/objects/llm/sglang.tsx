export const useSglangBkpullConfig = () => {
  return {
    instance_type: 'sglang',
    dashboardDisplay: [
      {
        indexId: 'sglang:num_running_reqs_gauge',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: { height: '200px', width: '15%' },
      },
      {
        indexId: 'sglang:num_queue_reqs_gauge',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: { height: '200px', width: '15%' },
      },
      {
        indexId: 'sglang:token_usage_gauge',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: { height: '200px', width: '15%' },
      },
      {
        indexId: 'sglang:generation_tokens_total_counter_rate',
        displayType: 'lineChart',
        sortIndex: 3,
        displayDimension: [],
        style: { height: '200px', width: '32%' },
      },
    ],
    groupIds: {},
    collectTypes: {
      SGLang: 'bkpull',
    },
  };
};
