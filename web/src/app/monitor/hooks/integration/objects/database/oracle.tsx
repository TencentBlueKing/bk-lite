import { useOracleExporter } from '../../plugins/database/oracleExporter';

export const useOracleConfig = () => {
  const oraclePlugin = useOracleExporter();
  const plugins = {
    'Oracle-Exporter': oraclePlugin,
  };

  return {
    instance_type: 'oracle',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'oracledb_up_gauge' },
      { type: 'value', key: 'oracledb_uptime_seconds_gauge' },
    ],
    groupIds: {},
    plugins,
  };
};
