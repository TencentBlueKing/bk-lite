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
      { type: 'value', key: 'oracledb_activity_user_rollbacks_rate' },
      { type: 'value', key: 'oracledb_wait_time_user_io_gauge' },
      { type: 'progress', key: 'oracledb_tablespace_used_percent_gauge' },
    ],
    groupIds: {},
    plugins,
  };
};
