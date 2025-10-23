import { useDmExporter } from '../../plugins/database/dmExporter';

export const useDmConfig = () => {
  const dmExporterPlugin = useDmExporter();
  const plugins = {
    'DM-Exporter': dmExporterPlugin,
  };

  return {
    instance_type: 'dm',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
