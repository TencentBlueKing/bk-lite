import { usePacketbeatDashboard } from './packetbeatDashboard';
import { useHttpDashboard } from './httpDashboard';
import { useDockerDashboard } from './dockerDashboard';
import { useMysqlDashboard } from './mysqlDashboard';
import { useRedisDashboard } from './redisDashboard';

const useBuildInDashBoards = () => {
  // 获取各个仪表盘配置
  const packetbeatDashboard = usePacketbeatDashboard();
  const httpDashboard = useHttpDashboard();
  const dockerDashboard = useDockerDashboard();
  const mysqlDashboard = useMysqlDashboard();
  const redisDashboard = useRedisDashboard();

  // 统一返回所有仪表盘配置
  return [
    httpDashboard,
    packetbeatDashboard,
    dockerDashboard,
    mysqlDashboard,
    redisDashboard
  ];
};
export { useBuildInDashBoards };
