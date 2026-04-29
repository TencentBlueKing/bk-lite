import { usePacketbeatDashboard } from './packetbeatDashboard';
import { useHttpDashboard } from './httpDashboard';
import { useDockerDashboard } from './dockerDashboard';

const useBuildInDashBoards = () => {
  // 获取各个仪表盘配置
  const packetbeatDashboard = usePacketbeatDashboard();
  const httpDashboard = useHttpDashboard();
  const dockerDashboard = useDockerDashboard();

  // 统一返回所有仪表盘配置
  return [httpDashboard, packetbeatDashboard, dockerDashboard];
};
export { useBuildInDashBoards };
