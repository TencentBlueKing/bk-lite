import { useHostTelegraf } from '../../plugins/os/hostTelegraf';

export const useHostConfig = () => {
  const plugin = useHostTelegraf();

  // 所有插件配置
  const plugins = {
    Host: plugin,
  };

  return {
    instance_type: 'os',
    dashboardDisplay: [
      {
        indexId: 'env.procs',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'load1',
        displayType: 'dashboard',
        sortIndex: 1,
        displayDimension: [],
        segments: [
          { value: 1, color: '#27C274' }, // 绿色区域
          { value: 2, color: '#FF9214' }, // 黄色区域
          { value: 4, color: '#D97007' }, // 黄色区域
          { value: 20, color: '#F43B2C' }, // 红色区域
        ],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'load5',
        displayType: 'dashboard',
        sortIndex: 2,
        displayDimension: [],
        segments: [
          { value: 1.5, color: '#27C274' }, // 绿色区域
          { value: 3, color: '#FF9214' }, // 黄色区域
          { value: 5, color: '#D97007' }, // 黄色区域
          { value: 20, color: '#F43B2C' }, // 红色区域
        ],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'disk.used',
        displayType: 'table',
        sortIndex: 3,
        displayDimension: ['Device', 'Value'],
        style: {
          height: '200px',
          width: '48%',
        },
      },
      {
        indexId: 'cpu_summary.usage',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: ['cpu'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'disk.is_use',
        displayType: 'lineChart',
        sortIndex: 5,
        displayDimension: ['device'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'mem.pct_used',
        displayType: 'lineChart',
        sortIndex: 6,
        displayDimension: ['device'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'io.util',
        displayType: 'lineChart',
        sortIndex: 7,
        displayDimension: ['device'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'net.speed_sent',
        displayType: 'lineChart',
        sortIndex: 8,
        displayDimension: ['device'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'net.speed_recv',
        displayType: 'lineChart',
        sortIndex: 9,
        displayDimension: ['device'],
        style: {
          height: '200px',
          width: '32%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'progress', key: 'cpu_summary.usage' },
      { type: 'progress', key: 'mem.pct_used' },
      { type: 'value', key: 'load5' },
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id'],
    },
    plugins,
  };
};
