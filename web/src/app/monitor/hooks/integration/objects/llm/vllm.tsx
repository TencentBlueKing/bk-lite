export const useVllmBkpullConfig = () => {
  return {
    instance_type: 'vllm',
    dashboardDisplay: [
      {
        indexId: 'vllm:num_requests_running_gauge',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'vllm:num_requests_waiting_gauge',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'vllm:kv_cache_usage_perc_gauge',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'vllm:generation_tokens_total_counter_rate',
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
      VLLM: 'bkpull',
    },
  };
};
