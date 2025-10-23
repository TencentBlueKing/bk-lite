import { usePacketbeatConfig } from '../collectors/packetbeat/dhcp';

export const useDhcpConfig = () => {
  const packetbeat = usePacketbeatConfig();
  const plugins = {
    Packetbeat: packetbeat,
  };

  return {
    type: 'dhcp',
    plugins,
  };
};
