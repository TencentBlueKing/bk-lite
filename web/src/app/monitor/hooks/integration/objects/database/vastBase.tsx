import { useVastBaseExporter } from '../../plugins/database/vastBaseExporter';

export const useVastBaseConfig = () => {
  const vastBaseExporter = useVastBaseExporter();
  const plugins = {
    'VastBase-Exporter': vastBaseExporter,
  };

  return {
    instance_type: 'vastbase',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
