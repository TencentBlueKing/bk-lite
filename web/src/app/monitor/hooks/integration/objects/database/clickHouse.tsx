import { useClickHouseTelegraf } from '../../plugins/database/clickHouseTelegraf';
import { useClickHouseExporter } from '../../plugins/database/clickHouseExporter';

export const useClickHouseConfig = () => {
  const clickHouseTelegraf = useClickHouseTelegraf();
  const clickHouseExporter = useClickHouseExporter();

  const plugins = {
    ClickHouse: clickHouseTelegraf,
    'ClickHouse-Exporter': clickHouseExporter,
  };

  return {
    instance_type: 'clickhouse',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'clickhouse_events_query' },
      { type: 'value', key: 'clickhouse_events_inserted_rows' },
      { type: 'value', key: 'clickhouse_asynchronous_metrics_load_average1' },
    ],
    groupIds: {},
    plugins,
  };
};
