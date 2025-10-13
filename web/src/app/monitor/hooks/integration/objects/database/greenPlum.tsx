import { useGreenPlumExporter } from '../../plugins/database/greenPlumExporter';

export const useGreenPlumConfig = () => {
  const greenPlumExporter = useGreenPlumExporter();
  const plugins = {
    'GreenPlum-Exporter': greenPlumExporter,
  };

  return {
    instance_type: 'greenplum',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
