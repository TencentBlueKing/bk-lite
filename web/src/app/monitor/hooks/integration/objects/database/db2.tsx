import { useDb2Exporter } from '../../plugins/database/db2Exporter';

export const useDb2Config = () => {
  const db2ExporterPlugin = useDb2Exporter();
  const plugins = {
    'DB2-Exporter': db2ExporterPlugin,
  };

  return {
    instance_type: 'db2',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
