export const useTcpConfig = () => {
  return {
    instance_type: 'qcloud',
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'enum', key: 'ConnectStatus' }],
    groupIds: {},
    collectTypes: {
      'Tencent Cloud': 'http'
    }
  };
};
