export const useDmConfig = () => {
  return {
    instance_type: 'dameng',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'progress', key: 'dm_exporter_session_used_ratio_gauge' },
      { type: 'progress', key: 'dm_exporter_tablespace_used_ratio_gauge' },
    ],
    groupIds: {},
    collectTypes: {
      'DM-Exporter': 'exporter',
    },
  };
};
