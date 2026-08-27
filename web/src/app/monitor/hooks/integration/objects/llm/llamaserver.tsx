export const useLlamaServerBkpullConfig = () => {
  return {
    instance_type: 'llamaserver',
    dashboardDisplay: [
      {
        indexId: 'llamacpp:requests_processing_gauge',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: { height: '200px', width: '15%' },
      },
      {
        indexId: 'llamacpp:requests_deferred_gauge',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: { height: '200px', width: '15%' },
      },
      {
        indexId: 'llamacpp:kv_cache_usage_ratio_gauge',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: { height: '200px', width: '15%' },
      },
      {
        indexId: 'llamacpp:predicted_tokens_seconds_gauge',
        displayType: 'lineChart',
        sortIndex: 3,
        displayDimension: [],
        style: { height: '200px', width: '32%' },
      },
    ],
    groupIds: {},
    collectTypes: {
      LlamaServer: 'bkpull',
    },
  };
};
