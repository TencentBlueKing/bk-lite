import { useTcpTelegraf } from '../../plugins/tencentCloud/tcpTelegraf';

export const useTcpConfig = () => {
  const tcp = useTcpTelegraf();
  const plugins = {
    'Tencent Cloud': tcp,
  };

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
    plugins,
  };
};
