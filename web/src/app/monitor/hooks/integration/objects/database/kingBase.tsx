import { useKingBaseExporter } from '../../plugins/database/kingBaseExporter';

export const useKingBaseConfig = () => {
  const kingBaseExporter = useKingBaseExporter();
  const plugins = {
    'KingBase-Exporter': kingBaseExporter,
  };

  return {
    instance_type: 'kingbase',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
