import { useOpenGaussExporter } from '../../plugins/database/openGaussExporter';

export const useOpenGaussConfig = () => {
  const openGaussExporterPlugin = useOpenGaussExporter();
  const plugins = {
    'OpenGauss-Exporter': openGaussExporterPlugin,
  };

  return {
    instance_type: 'opengauss',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
