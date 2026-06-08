export const useClickHouseConfig = () => {
  return {
    instance_type: 'clickhouse',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      ClickHouse: 'database',
      'ClickHouse-Exporter': 'exporter',
    },
  };
};
