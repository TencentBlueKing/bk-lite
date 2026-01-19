export const useTcpConfig = () => {
  return {
    instance_type: 'qcloud',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'progress', key: 'CPUUsage_gauge' },
      { type: 'progress', key: 'MemUsage_gauge' },
    ],
    groupIds: {},
    collectTypes: {
      'Tencent Cloud': 'http',
    },
  };
};
