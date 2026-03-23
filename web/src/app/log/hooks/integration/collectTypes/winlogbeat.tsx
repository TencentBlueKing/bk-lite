import { useWinlogbeatConfig as useWinlogbeatCollectorConfig } from '../collectors/winlogbeat/winlogbeat';

export const useWinlogbeatConfig = () => {
  const winlogbeat = useWinlogbeatCollectorConfig();
  const plugins = {
    Winlogbeat: winlogbeat
  };

  return {
    type: 'winlogbeat',
    plugins
  };
};
