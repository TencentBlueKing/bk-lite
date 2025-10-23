import { useVectorConfig } from '../collectors/vector/docker';
import { useMetricbeatConfig } from '../collectors/metricbeat/docker';

export const useDockerConfig = () => {
  const vector = useVectorConfig();
  const metricbeat = useMetricbeatConfig();
  const plugins = {
    Vector: vector,
    Metricbeat: metricbeat,
  };

  return {
    type: 'docker',
    plugins,
  };
};
