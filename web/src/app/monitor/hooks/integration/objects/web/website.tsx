import { useWebsiteTelegraf } from '../../plugins/web/websiteTelegraf';

export const useWebsiteConfig = () => {
  const plugin = useWebsiteTelegraf();

  // 所有插件配置
  const plugins = {
    Website: plugin,
  };

  return {
    instance_type: 'web',
    dashboardDisplay: [
      {
        indexId: 'http_success.rate',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'http_duration',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'http_ssl',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'http_status_code',
        displayType: 'lineChart',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '48%',
        },
      },
      {
        indexId: 'http_dns.lookup.time',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '48%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'enum', key: 'http_success.rate' },
      { type: 'value', key: 'http_duration' },
      { type: 'enum', key: 'http_code' },
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id'],
    },
    plugins,
  };
};
