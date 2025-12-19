export const useTcpConfig = () => {
  return {
    instance_type: 'qcloud',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'cvm_CPU_Usage' },
      { type: 'value', key: 'cvm_MemUsage' },
      { type: 'value', key: 'cvm_LanOuttraffic' },
      { type: 'value', key: 'cvm_WanOuttraffic' },
    ],
    groupIds: {},
    collectTypes: {
      'Tencent Cloud': 'http',
    },
  };
};
