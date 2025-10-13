export const useNodeConfig = () => {
  return {
    instance_type: 'k8s',
    dashboardDisplay: [
      {
        indexId: 'node_status_condition',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'node_cpu_load1',
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
        indexId: 'node_cpu_load5',
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
        indexId: 'node_cpu_utilization',
        displayType: 'lineChart',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'node_app_memory_utilization',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'node_io_current',
        displayType: 'lineChart',
        sortIndex: 5,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'node_network_receive',
        displayType: 'lineChart',
        sortIndex: 6,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'node_network_transmit',
        displayType: 'lineChart',
        sortIndex: 7,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'enum', key: 'node_status_condition' },
      { type: 'progress', key: 'node_cpu_utilization' },
      { type: 'progress', key: 'node_memory_utilization' },
    ],
    groupIds: {
      list: ['node'],
      default: ['node'],
    },
    plugins: {},
  };
};
