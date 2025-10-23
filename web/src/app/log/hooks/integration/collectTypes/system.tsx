import { useMetricbeatConfig } from '../collectors/metricbeat/system';

export const useSystemConfig = () => {
  const metricbeat = useMetricbeatConfig();
  const plugins = {
    Metricbeat: metricbeat,
  };

  return {
    type: 'system',
    plugins,
  };
};
