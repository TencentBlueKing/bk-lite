import { usePacketbeatConfig } from '../collectors/packetbeat/dns';

export const useDnsConfig = () => {
  const packetbeat = usePacketbeatConfig();
  const plugins = {
    Packetbeat: packetbeat,
  };

  return {
    type: 'dns',
    plugins,
  };
};
