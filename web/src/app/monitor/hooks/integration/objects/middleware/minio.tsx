export const useMinioBkpullConfig = () => {
  return {
    instance_type: 'minio',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'minio_cluster_capacity_usable_free_bytes_gauge' },
      { type: 'value', key: 'minio_cluster_drive_online_total_gauge' },
      { type: 'enum', key: 'minio_cluster_health_status_gauge' },
    ],
    groupIds: {},
    collectTypes: {
      Minio: 'bkpull',
    },
  };
};
