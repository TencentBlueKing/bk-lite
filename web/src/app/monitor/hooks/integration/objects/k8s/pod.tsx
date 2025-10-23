export const usePodConfig = () => {
  return {
    instance_type: 'k8s',
    dashboardDisplay: [
      {
        indexId: 'pod_status',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'pod_cpu_utilization',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'pod_memory_utilization',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'pod_io_writes',
        displayType: 'lineChart',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'pod_io_read',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'enum', key: 'pod_status' },
      { type: 'progress', key: 'pod_cpu_utilization' },
      { type: 'progress', key: 'pod_memory_utilization' },
    ],
    groupIds: {
      list: ['uid'],
      default: ['uid'],
    },
    plugins: {},
  };
};
