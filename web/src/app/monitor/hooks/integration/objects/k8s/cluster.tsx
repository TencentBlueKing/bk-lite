export const useClusterConfig = () => {
  return {
    instance_type: 'k8s',
    dashboardDisplay: [
      {
        indexId: 'cluster_pod_count',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'cluster_node_count',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'k8s_cluster',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'cluster_pod_count' },
      { type: 'value', key: 'cluster_node_count' },
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id'],
    },
    plugins: {},
  };
};
