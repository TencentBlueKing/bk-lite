import { useVectorConfig } from '../collectors/vector/docker';

export const useDockerConfig = () => {
  const vector = useVectorConfig();
  const plugins = {
    Vector: vector
  };

  return {
    type: 'docker',
    plugins
  };
};
