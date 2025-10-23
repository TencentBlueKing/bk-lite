import { usePacketbeatConfig } from '../collectors/packetbeat/icmp';

export const useIcmpConfig = () => {
  const packetbeat = usePacketbeatConfig();
  const plugins = {
    Packetbeat: packetbeat,
  };

  return {
    type: 'icmp',
    plugins,
  };
};
