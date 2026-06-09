export const useEtcdBkpullConfig = () => {
  return {
    instance_type: 'etcd',
    dashboardDisplay: [
      {
        indexId: 'etcd_server_has_leader_gauge',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'etcd_backend_allocated_usage_percent',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'etcd_server_proposals_apply_lag',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
      {
        indexId: 'etcd_disk_wal_fsync_p99_seconds',
        displayType: 'lineChart',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '32%',
        },
      },
    ],
    groupIds: {},
    collectTypes: {
      Etcd: 'bkpull',
    },
  };
};
