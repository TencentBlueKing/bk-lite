import { useGBase8aExporter } from '../../plugins/database/gBase8aExporter';

export const useGBase8aConfig = () => {
  const gBase8aExporter = useGBase8aExporter();
  const plugins = {
    'GBase8a-Exporter': gBase8aExporter,
  };

  return {
    instance_type: 'gbase8a',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
