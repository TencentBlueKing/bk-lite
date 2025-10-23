import { useVectorConfig } from '../collectors/vector/syslog';

export const useSyslogConfig = () => {
  const vector = useVectorConfig();
  const plugins = {
    Vector: vector,
  };

  return {
    type: 'syslog',
    plugins,
  };
};
