import { useMemo } from 'react';
import { TableDataItem } from '@/app/monitor/types';
import { useHardwareConfig } from './objects/hardwareDevice/hardware';
import { useOracleConfig } from './objects/database/oracle';
import { useElasticSearchConfig } from './objects/database/elasticSearch';
import { useMongoDBConfig } from './objects/database/mongoDB';
import { useMysqlConfig } from './objects/database/mysql';
import { useRedisConfig } from './objects/database/redis';
import { usePostgresConfig } from './objects/database/postgres';
import { useZookeeperConfig } from './objects/middleware/zookeeper';
import { useActiveMQConfig } from './objects/middleware/activeMQ';
import { useWebLogicConfig } from './objects/middleware/webLogic';
import { useNginxConfig } from './objects/middleware/nginx';
import { useApacheConfig } from './objects/middleware/apache';
import { useConsulConfig } from './objects/middleware/consul';
import { useClickHouseConfig } from './objects/database/clickHouse';
import { useTomcatConfig } from './objects/middleware/tomcat';
import { useMinioBkpullConfig } from './objects/middleware/minio';
import { useJettyJmxConfig } from './objects/middleware/jetty';
import { useRabbitMQConfig } from './objects/middleware/rabbitMQ';
import { useRouterConfig } from './objects/networkDevice/router';
import { useScanningDeviceConfig } from './objects/networkDevice/scanningDevice';
import { useLoadbalanceConfig } from './objects/networkDevice/loadbalance';
import { useDetectionDeviceConfig } from './objects/networkDevice/detectionDevice';
import { useSwitchConfig } from './objects/networkDevice/switch';
import { useFirewallConfig } from './objects/networkDevice/firewall';
import { useVCenterConfig } from './objects/vmWare/vCenter';
import { useDataStorageConfig } from './objects/vmWare/dataStorage';
import { useEsxiConfig } from './objects/vmWare/esxi';
import { useVmConfig } from './objects/vmWare/vm';
import { useDockerConfig } from './objects/containerManagement/docker';
import { useBastionHostConfig } from './objects/hardwareDevice/bastionHost';
import { useStorageConfig } from './objects/hardwareDevice/storage';
import { useHostConfig } from './objects/os/host';
import { useWebsiteConfig } from './objects/web/website';
import { usePingConfig } from './objects/web/ping';
import { useSnmpTrapConfig } from './objects/other/snmpTrap';
import { useJvmConfig } from './objects/other/jvm';
import { useTcpConfig } from './objects/tencentCloud/tcp';
import { useCvmConfig } from './objects/tencentCloud/cvm';
import { useTongWebConfig } from './objects/middleware/tongWeb';
import { useJbossConfig } from './objects/middleware/jboss';
import { useKafkaConfig } from './objects/middleware/kafka';
import { useMssqlConfig } from './objects/database/mssql';
import { useClusterConfig } from './objects/k8s/cluster';
import { useNodeConfig } from './objects/k8s/node';
import { usePodConfig } from './objects/k8s/pod';
import { useDockerContainerConfig } from './objects/containerManagement/dockerContainer';
import { useDmConfig } from './objects/database/dm';
import { useDb2Config } from './objects/database/db2';
import { useGreenPlumConfig } from './objects/database/greenPlum';

export const useMonitorConfig = () => {
  const hardwareConfig = useHardwareConfig();
  const oracleConfig = useOracleConfig();
  const elasticSearchConfig = useElasticSearchConfig();
  const mongoDBConfig = useMongoDBConfig();
  const mysqlDBConfig = useMysqlConfig();
  const redisConfig = useRedisConfig();
  const postgresConfig = usePostgresConfig();
  const zookeeperConfig = useZookeeperConfig();
  const activeMQConfig = useActiveMQConfig();
  const webLogicConfig = useWebLogicConfig();
  const nginxConfig = useNginxConfig();
  const apacheConfig = useApacheConfig();
  const consulConfig = useConsulConfig();
  const clickHouseConfig = useClickHouseConfig();
  const tomcatConfig = useTomcatConfig();
  const minioBkpullConfig = useMinioBkpullConfig();
  const jettyJmxConfig = useJettyJmxConfig();
  const rabbitMQConfig = useRabbitMQConfig();
  const routerConfig = useRouterConfig();
  const scanningDeviceConfig = useScanningDeviceConfig();
  const loadbalanceConfig = useLoadbalanceConfig();
  const detectionDeviceConfig = useDetectionDeviceConfig();
  const switchConfig = useSwitchConfig();
  const firewallConfig = useFirewallConfig();
  const dataStorageConfig = useDataStorageConfig();
  const vCenterConfig = useVCenterConfig();
  const esxiConfig = useEsxiConfig();
  const vmConfig = useVmConfig();
  const dockerConfig = useDockerConfig();
  const bastionHostConfig = useBastionHostConfig();
  const storageConfig = useStorageConfig();
  const hostConfig = useHostConfig();
  const websiteConfig = useWebsiteConfig();
  const pingConfig = usePingConfig();
  const snmpTrapConfig = useSnmpTrapConfig();
  const jvmConfig = useJvmConfig();
  const tcpConfig = useTcpConfig();
  const cvmConfig = useCvmConfig();
  const tongWebConfig = useTongWebConfig();
  const jbossConfig = useJbossConfig();
  const kafkaConfig = useKafkaConfig();
  const mssqlConfig = useMssqlConfig();
  const clusterConfig = useClusterConfig();
  const podConfig = usePodConfig();
  const nodeConfig = useNodeConfig();
  const dockerContainerConfig = useDockerContainerConfig();
  const dmConfig = useDmConfig();
  const db2Config = useDb2Config();
  const greenPlumConfig = useGreenPlumConfig();

  const config: any = useMemo(
    () => ({
      'Hardware Server': hardwareConfig,
      Oracle: oracleConfig,
      ElasticSearch: elasticSearchConfig,
      MongoDB: mongoDBConfig,
      Mysql: mysqlDBConfig,
      Redis: redisConfig,
      Postgres: postgresConfig,
      Zookeeper: zookeeperConfig,
      ActiveMQ: activeMQConfig,
      WebLogic: webLogicConfig,
      Nginx: nginxConfig,
      Apache: apacheConfig,
      Consul: consulConfig,
      ClickHouse: clickHouseConfig,
      Tomcat: tomcatConfig,
      Minio: minioBkpullConfig,
      Jetty: jettyJmxConfig,
      RabbitMQ: rabbitMQConfig,
      Router: routerConfig,
      'Scanning Device': scanningDeviceConfig,
      Loadbalance: loadbalanceConfig,
      'Detection Device': detectionDeviceConfig,
      Switch: switchConfig,
      Firewall: firewallConfig,
      vCenter: vCenterConfig,
      Docker: dockerConfig,
      'Bastion Host': bastionHostConfig,
      Storage: storageConfig,
      Host: hostConfig,
      Website: websiteConfig,
      Ping: pingConfig,
      'SNMP Trap': snmpTrapConfig,
      JVM: jvmConfig,
      TCP: tcpConfig,
      TongWeb: tongWebConfig,
      JBoss: jbossConfig,
      Kafka: kafkaConfig,
      MSSQL: mssqlConfig,
      Cluster: clusterConfig,
      Pod: podConfig,
      Node: nodeConfig,
      'Docker Container': dockerContainerConfig,
      CVM: cvmConfig,
      DataStorage: dataStorageConfig,
      ESXI: esxiConfig,
      VM: vmConfig,
      DM: dmConfig,
      DB2: db2Config,
      GreenPlum: greenPlumConfig,
    }),
    []
  );

  // 获取指定插件的手动/自动配置模式
  const getPlugin = (data: {
    objectName: string;
    mode: 'manual' | 'auto' | 'edit';
    pluginName: string;
    dataSource?: TableDataItem[];
    onTableDataChange?: (data: TableDataItem[]) => void;
  }) => {
    const objectConfig = config[data.objectName];
    const pluginCfg =
      objectConfig?.plugins?.[data.pluginName]?.getPluginCfg(data);
    const commonConfig = {
      collect_type: '',
      config_type: [],
      collector: '',
      instance_type: '',
      object_name: '',
    };
    let defaultPluginCfg: any = {
      getParams: () => ({
        instance_id: '',
        instance_name: '',
      }),
      getFormItems: () => null,
      configText: '',
    };
    if (data.mode === 'auto') {
      defaultPluginCfg = {
        formItems: null,
        initTableItems: {},
        defaultForm: {},
        columns: [],
        getParams: () => ({}),
      };
    }
    return pluginCfg || { ...commonConfig, ...defaultPluginCfg };
  };

  return {
    config,
    getPlugin,
  };
};
