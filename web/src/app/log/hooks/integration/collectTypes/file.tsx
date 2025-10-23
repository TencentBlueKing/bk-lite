import { useVectorConfig } from '../collectors/vector/file';

export const useFileConfig = () => {
  const vector = useVectorConfig();
  const plugins = {
    Vector: vector,
  };

  return {
    type: 'file',
    plugins,
  };
};
