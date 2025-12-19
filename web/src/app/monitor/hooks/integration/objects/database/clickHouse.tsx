export const useClickHouseConfig = () => {
  return {
    instance_type: 'clickhouse',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'clickhouse_events_query' },
      { type: 'value', key: 'clickhouse_events_inserted_rows' },
      { type: 'value', key: 'clickhouse_asynchronous_metrics_load_average1' },
    ],
    groupIds: {},
    collectTypes: {
      ClickHouse: 'database',
      'ClickHouse-Exporter': 'exporter',
    },
  };
};
