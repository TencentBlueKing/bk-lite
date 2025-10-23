import { useVectorConfig } from '../collectors/vector/exec';

export const useExecConfig = () => {
  const vector = useVectorConfig();
  const plugins = {
    Vector: vector,
  };

  return {
    type: 'exec',
    plugins,
  };
};
