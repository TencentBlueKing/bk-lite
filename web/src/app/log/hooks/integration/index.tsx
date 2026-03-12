import { useMemo } from 'react';
import { TableDataItem } from '@/app/log/types';
import { useFileConfig } from './collectTypes/file';
import { useSyslogConfig } from './collectTypes/syslog';
import { useDockerConfig } from './collectTypes/docker';
import { useApacheConfig } from './collectTypes/apache';
import { useNginxConfig } from './collectTypes/nginx';
import { useMysqlConfig } from './collectTypes/mysql';
import { usePostgresqlConfig } from './collectTypes/postgresql';
import { useRedisConfig } from './collectTypes/redis';
import { useMongodbConfig } from './collectTypes/mongodb';
import { useKafkaConfig } from './collectTypes/kafka';
import { useRabbitmqConfig } from './collectTypes/rabbitmq';
import { useElasticsearchConfig } from './collectTypes/elasticsearch';
import { useWinlogbeatConfig } from './collectTypes/winlogbeat';
import { useAuditdConfig } from './collectTypes/auditd';
import { useHttpConfig } from './collectTypes/http';
import { useFileIntegrityConfig } from './collectTypes/fileIntegrity';
import { useIcmpConfig } from './collectTypes/icmp';
import { useFlowsConfig } from './collectTypes/flows';

export const useCollectTypeConfig = () => {
  const fileConfig = useFileConfig();
  const syslogConfig = useSyslogConfig();
  const dockerConfig = useDockerConfig();
  const apacheConfig = useApacheConfig();
  const nginxConfig = useNginxConfig();
  const mysqlConfig = useMysqlConfig();
  const postgresqlConfig = usePostgresqlConfig();
  const redisConfig = useRedisConfig();
  const mongodbConfig = useMongodbConfig();
  const kafkaConfig = useKafkaConfig();
  const rabbitmqConfig = useRabbitmqConfig();
  const elasticsearchConfig = useElasticsearchConfig();
  const winlogbeatConfig = useWinlogbeatConfig();
  const auditdConfig = useAuditdConfig();
  const httpConfig = useHttpConfig();
  const fileIntegrityConfig = useFileIntegrityConfig();
  const icmpConfig = useIcmpConfig();
  const flowsConfig = useFlowsConfig();

  const configs: any = useMemo(
    () => ({
      file: fileConfig,
      syslog: syslogConfig,
      docker: dockerConfig,
      apache: apacheConfig,
      nginx: nginxConfig,
      mysql: mysqlConfig,
      postgresql: postgresqlConfig,
      redis: redisConfig,
      mongodb: mongodbConfig,
      kafka: kafkaConfig,
      rabbitmq: rabbitmqConfig,
      elasticsearch: elasticsearchConfig,
      winlogbeat: winlogbeatConfig,
      auditd: auditdConfig,
      http: httpConfig,
      file_integrity: fileIntegrityConfig,
      icmp: icmpConfig,
      flows: flowsConfig
    }),
    []
  );

  // 获取指定插件的手动/自动/编辑配置模式
  const getCollectTypeConfig = (data: {
    mode: 'manual' | 'auto' | 'edit';
    type: string;
    collector: string;
    dataSource?: TableDataItem[];
    onTableDataChange?: (data: TableDataItem[]) => void;
  }) => {
    const collectTypeCfg =
      configs[data.type]?.plugins?.[data.collector]?.getConfig(data);
    const config = {
      collector: '',
      icon: ''
    };
    let defaultCollectTypeCfg: any = {
      getParams: () => ({
        instance_id: '',
        instance_name: ''
      }),
      getFormItems: () => null,
      configText: ''
    };
    if (data.mode === 'auto') {
      defaultCollectTypeCfg = {
        formItems: null,
        initTableItems: {},
        defaultForm: {},
        columns: [],
        getParams: () => ({})
      };
    }
    return (
      collectTypeCfg || {
        ...config,
        ...defaultCollectTypeCfg
      }
    );
  };

  return {
    configs,
    getCollectTypeConfig
  };
};
