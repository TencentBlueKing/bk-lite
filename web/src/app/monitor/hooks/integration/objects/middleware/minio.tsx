export const useMinioBkpullConfig = () => {
  return {
    instance_type: 'minio',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      Minio: 'bkpull',
    },
  };
};
