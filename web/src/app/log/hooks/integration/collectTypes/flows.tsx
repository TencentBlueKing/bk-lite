import { usePacketbeatConfig } from '../collectors/packetbeat/flows';

export const useFlowsConfig = () => {
  const packetbeat = usePacketbeatConfig();
  const plugins = {
    Packetbeat: packetbeat,
  };

  return {
    type: 'flows',
    plugins,
  };
};
