import { usePingTelegraf } from '../../plugins/web/pingTelegraf';

export const usePingConfig = () => {
  const plugin = usePingTelegraf();

  // 所有插件配置
  const plugins = {
    Ping: plugin,
  };

  return {
    instance_type: 'ping',
    dashboardDisplay: [
      {
        indexId: 'ping_response_time',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'ping_error_response_code',
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
      { type: 'value', key: 'ping_response_time' },
      { type: 'enum', key: 'ping_error_response_code' },
    ],
    groupIds: {},
    plugins,
  };
};
