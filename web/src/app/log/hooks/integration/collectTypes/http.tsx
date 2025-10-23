import { usePacketbeatConfig } from '../collectors/packetbeat/http';

export const useHttpConfig = () => {
  const packetbeat = usePacketbeatConfig();
  const plugins = {
    Packetbeat: packetbeat,
  };

  return {
    type: 'http',
    plugins,
  };
};
