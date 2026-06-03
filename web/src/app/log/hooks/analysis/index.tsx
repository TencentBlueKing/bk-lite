import { usePacketbeatDashboard } from './packetbeatDashboard';
import { useHttpDashboard } from './httpDashboard';
import { useDockerDashboard } from './dockerDashboard';
import { useMysqlDashboard } from './mysqlDashboard';
import { useRedisDashboard } from './redisDashboard';
import { useKafkaDashboard } from './kafkaDashboard';
import { useMongodbDashboard } from './mongodbDashboard';
import { useElasticsearchDashboard } from './elasticsearchDashboard';
import { useSyslogDashboard } from './syslogDashboard';
import { useApacheDashboard } from './apacheDashboard';
import { useNginxDashboard } from './nginxDashboard';
import { usePostgresqlDashboard } from './postgresqlDashboard';
import { useFileIntegrityDashboard } from './fileIntegrityDashboard';
import { useRabbitmqDashboard } from './rabbitmqDashboard';
import { useWindowsEventDashboard } from './windowsEventDashboard';

const useBuildInDashBoards = () => {
  // 获取各个仪表盘配置
  const packetbeatDashboard = usePacketbeatDashboard();
  const httpDashboard = useHttpDashboard();
  const dockerDashboard = useDockerDashboard();
  const mysqlDashboard = useMysqlDashboard();
  const redisDashboard = useRedisDashboard();
  const elasticsearchDashboard = useElasticsearchDashboard();
  const postgresqlDashboard = usePostgresqlDashboard();
  const kafkaDashboard = useKafkaDashboard();
  const apacheDashboard = useApacheDashboard();
  const nginxDashboard = useNginxDashboard();
  const rabbitmqDashboard = useRabbitmqDashboard();
  const syslogDashboard = useSyslogDashboard();
  const windowsEventDashboard = useWindowsEventDashboard();
  const fileIntegrityDashboard = useFileIntegrityDashboard();
  const mongodbDashboard = useMongodbDashboard();

  // 统一返回所有仪表盘配置
  return [
    elasticsearchDashboard,
    postgresqlDashboard,
    kafkaDashboard,
    apacheDashboard,
    nginxDashboard,
    rabbitmqDashboard,
    syslogDashboard,
    windowsEventDashboard,
    fileIntegrityDashboard,
    mongodbDashboard,
    httpDashboard,
    packetbeatDashboard,
    dockerDashboard,
    mysqlDashboard,
    redisDashboard
  ];
};
export { useBuildInDashBoards };
