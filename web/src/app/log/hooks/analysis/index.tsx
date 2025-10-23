import { usePacketbeatDashboard } from './packetbeatDashboard';

const useBuildInDashBoards = () => {
  // 获取各个仪表盘配置
  const packetbeatDashboard = usePacketbeatDashboard();

  // 统一返回所有仪表盘配置
  return [packetbeatDashboard];
};
export { useBuildInDashBoards };
