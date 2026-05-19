export const useDmConfig = () => {
  return {
    instance_type: 'dameng',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'dm_exporter_connections_gauge' },
      { type: 'progress', key: 'dm_exporter_session_used_ratio_gauge' },
      { type: 'progress', key: 'dm_exporter_tablespace_used_ratio_gauge' },
      { type: 'value', key: 'dm_exporter_lock_blocks_gauge' },
      { type: 'value', key: 'dm_exporter_slow_query_gauge' },
    ],
    groupIds: {},
    collectTypes: {
      'DM-Exporter': 'exporter',
    },
  };
};
