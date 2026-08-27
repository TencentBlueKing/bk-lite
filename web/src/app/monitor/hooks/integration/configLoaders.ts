/**
 * 按监控对象名动态加载配置模块，避免一次静态挂载 50+ 对象配置。
 * 各 use*Config 实际是无 hook 的工厂函数，可安全在异步路径调用。
 */

import type {
  ObjectConfig,
  ObjectConfigFactory
} from './configContracts';

type ObjectConfigLoader = () => Promise<ObjectConfigFactory>;

const COMMUNITY_OBJECT_CONFIG_LOADERS: Record<string, ObjectConfigLoader> = {
  'Hardware Server': () =>
    import('./objects/hardwareDevice/hardware').then((m) => m.useHardwareConfig),
  Oracle: () => import('./objects/database/oracle').then((m) => m.useOracleConfig),
  ElasticSearch: () =>
    import('./objects/database/elasticSearch').then((m) => m.useElasticSearchConfig),
  InfluxDB: () => import('./objects/database/influxdb').then((m) => m.useInfluxDBConfig),
  MongoDB: () => import('./objects/database/mongoDB').then((m) => m.useMongoDBConfig),
  Mysql: () => import('./objects/database/mysql').then((m) => m.useMysqlConfig),
  Redis: () => import('./objects/database/redis').then((m) => m.useRedisConfig),
  Postgres: () => import('./objects/database/postgres').then((m) => m.usePostgresConfig),
  Zookeeper: () =>
    import('./objects/middleware/zookeeper').then((m) => m.useZookeeperConfig),
  ActiveMQ: () => import('./objects/middleware/activeMQ').then((m) => m.useActiveMQConfig),
  Nginx: () => import('./objects/middleware/nginx').then((m) => m.useNginxConfig),
  'Active Directory': () =>
    import('./objects/middleware/activeDirectory').then((m) => m.useActiveDirectoryConfig),
  Apache: () => import('./objects/middleware/apache').then((m) => m.useApacheConfig),
  Haproxy: () => import('./objects/middleware/haproxy').then((m) => m.useHaproxyConfig),
  Consul: () => import('./objects/middleware/consul').then((m) => m.useConsulConfig),
  Etcd: () => import('./objects/middleware/etcd').then((m) => m.useEtcdBkpullConfig),
  VLLM: () => import('./objects/llm/vllm').then((m) => m.useVllmBkpullConfig),
  SGLang: () => import('./objects/llm/sglang').then((m) => m.useSglangBkpullConfig),
  LlamaServer: () => import('./objects/llm/llamaserver').then((m) => m.useLlamaServerBkpullConfig),
  ClickHouse: () =>
    import('./objects/database/clickHouse').then((m) => m.useClickHouseConfig),
  Tomcat: () => import('./objects/middleware/tomcat').then((m) => m.useTomcatConfig),
  Minio: () => import('./objects/middleware/minio').then((m) => m.useMinioBkpullConfig),
  RabbitMQ: () => import('./objects/middleware/rabbitMQ').then((m) => m.useRabbitMQConfig),
  Router: () => import('./objects/networkDevice/router').then((m) => m.useRouterConfig),
  Loadbalance: () =>
    import('./objects/networkDevice/loadbalance').then((m) => m.useLoadbalanceConfig),
  Switch: () => import('./objects/networkDevice/switch').then((m) => m.useSwitchConfig),
  Firewall: () =>
    import('./objects/networkDevice/firewall').then((m) => m.useFirewallConfig),
  Wireless: () =>
    import('./objects/networkDevice/wireless').then((m) => m.useWirelessConfig),
  Transmission: () =>
    import('./objects/networkDevice/transmission').then((m) => m.useTransmissionConfig),
  Access: () => import('./objects/networkDevice/access').then((m) => m.useAccessConfig),
  NetworkService: () =>
    import('./objects/networkDevice/networkService').then((m) => m.useNetworkServiceConfig),
  ConsoleServer: () =>
    import('./objects/networkDevice/consoleServer').then((m) => m.useConsoleServerConfig),
  VoiceGateway: () =>
    import('./objects/networkDevice/voiceGateway').then((m) => m.useVoiceGatewayConfig),
  vCenter: () => import('./objects/vmWare/vCenter').then((m) => m.useVCenterConfig),
  Docker: () =>
    import('./objects/containerManagement/docker').then((m) => m.useDockerConfig),
  Host: () => import('./objects/os/host').then((m) => m.useHostConfig),
  Process: () => import('./objects/os/process').then((m) => m.useProcessConfig),
  Website: () => import('./objects/web/website').then((m) => m.useWebsiteConfig),
  Ping: () => import('./objects/web/ping').then((m) => m.usePingConfig),
  TCPPort: () => import('./objects/web/tcpPort').then((m) => m.useTcpPortConfig),
  'SNMP Trap': () => import('./objects/other/snmpTrap').then((m) => m.useSnmpTrapConfig),
  JVM: () => import('./objects/other/jvm').then((m) => m.useJvmConfig),
  TCP: () => import('./objects/tencentCloud/tcp').then((m) => m.useTcpConfig),
  Kafka: () => import('./objects/middleware/kafka').then((m) => m.useKafkaConfig),
  MSSQL: () => import('./objects/database/mssql').then((m) => m.useMssqlConfig),
  Cluster: () => import('./objects/k8s/cluster').then((m) => m.useClusterConfig),
  Pod: () => import('./objects/k8s/pod').then((m) => m.usePodConfig),
  Node: () => import('./objects/k8s/node').then((m) => m.useNodeConfig),
  K3SCluster: () => import('./objects/k3s/cluster').then((m) => m.useClusterConfig),
  K3SPod: () => import('./objects/k3s/pod').then((m) => m.usePodConfig),
  K3SNode: () => import('./objects/k3s/node').then((m) => m.useNodeConfig),
  'Docker Container': () =>
    import('./objects/containerManagement/dockerContainer').then(
      (m) => m.useDockerContainerConfig
    ),
  CVM: () => import('./objects/tencentCloud/cvm').then((m) => m.useCvmConfig),
  DataStorage: () =>
    import('./objects/vmWare/dataStorage').then((m) => m.useDataStorageConfig),
  ESXI: () => import('./objects/vmWare/esxi').then((m) => m.useEsxiConfig),
  VM: () => import('./objects/vmWare/vm').then((m) => m.useVmConfig),
  DB2: () => import('./objects/database/db2').then((m) => m.useDb2Config),
  GreenPlum: () =>
    import('./objects/database/greenPlum').then((m) => m.useGreenPlumConfig),
  OpenGauss: () =>
    import('./objects/database/openGauss').then((m) => m.useOpenGaussConfig),
  GBase8a: () => import('./objects/database/gBase8a').then((m) => m.useGBase8aConfig),
  VastBase: () => import('./objects/database/vastBase').then((m) => m.useVastBaseConfig),
  KingBase: () => import('./objects/database/kingBase').then((m) => m.useKingBaseConfig)
};

const configCache: Record<string, ObjectConfig> = {};
const inflight = new Map<string, Promise<ObjectConfig | undefined>>();
let enterpriseConfigPromise: Promise<Record<string, ObjectConfig>> | null = null;

const loadEnterpriseConfigMap = async (): Promise<Record<string, ObjectConfig>> => {
  if (!enterpriseConfigPromise) {
    enterpriseConfigPromise = (async () => {
      try {
        const mod = await import('@/app/monitor/(enterprise)/hooks/integration');
        const factory = mod.useEnterpriseConfig;
        const raw = typeof factory === 'function' ? factory() || {} : {};
        return raw as Record<string, ObjectConfig>;
      } catch (error) {
        // 社区构建无企业包时属预期；其它失败也应降级为空映射并留痕。
        console.warn('[monitor] load enterprise object config failed', error);
        return {};
      }
    })();
  }
  return enterpriseConfigPromise;
};

export const getCachedObjectConfig = (objectName?: string | null) => {
  if (!objectName) return undefined;
  return configCache[objectName];
};

export const loadObjectConfig = async (objectName?: string | null) => {
  if (!objectName) return undefined;
  if (configCache[objectName]) return configCache[objectName];

  const pending = inflight.get(objectName);
  if (pending) return pending;

  const task = (async () => {
    const communityLoader = COMMUNITY_OBJECT_CONFIG_LOADERS[objectName];
    if (communityLoader) {
      const factory = await communityLoader();
      const cfg = factory();
      configCache[objectName] = cfg;
      return cfg;
    }

    const enterpriseMap = await loadEnterpriseConfigMap();
    const cfg = enterpriseMap[objectName];
    if (cfg) {
      Object.keys(enterpriseMap).forEach((key) => {
        if (!configCache[key]) configCache[key] = enterpriseMap[key];
      });
      return cfg;
    }
    return undefined;
  })().finally(() => {
    inflight.delete(objectName);
  });

  inflight.set(objectName, task);
  return task;
};
