import MysqlDashboard from './objects/mysql';
import MongodbDashboard from './objects/mongodb';
import RedisDashboard from './objects/redis';
import ElasticsearchDashboard from './objects/elasticsearch';
import HostDashboard from './objects/host';
import MssqlDashboard from './objects/mssql';
import NginxDashboard from './objects/nginx';
import DockerDashboard from './objects/docker';
import ActiveMQDashboard from './objects/activemq';
import ApacheDashboard from './objects/apache';
import ConsulDashboard from './objects/consul';
import RabbitMQDashboard from './objects/rabbitmq';
import TomcatDashboard from './objects/tomcat';
import ZookeeperDashboard from './objects/zookeeper';
import PingDashboard from './objects/ping';
import PostgresqlDashboard from './objects/postgresql';
import { ProfessionalDashboardRegistryItem } from './shared/types';
import WebsiteDashboard from './objects/website';
import K8sClusterDashboard from './objects/k8s-cluster';
import K8sNodeDashboard from './objects/k8s-node';
import K8sPodDashboard from './objects/k8s-pod';
import SwitchDashboard from './objects/switch';
import FirewallDashboard from './objects/firewall';
import LoadbalanceDashboard from './objects/loadbalance';
import RouterDashboard from './objects/router';
import { normalizeDashboardKey } from './shared/utils';

export const PROFESSIONAL_DASHBOARD_GROUPS = {
  hardware: { label: '硬件设备', order: 10 },
  container: { label: '容器', order: 15 },
  os: { label: '操作系统', order: 20 },
  network: { label: '网络', order: 30 },
  database: { label: '数据库', order: 40 },
  middleware: { label: '中间件', order: 50 }
} as const;

export const PROFESSIONAL_DASHBOARDS: ProfessionalDashboardRegistryItem[] = [
  {
    key: 'mysql',
    groupKey: 'database',
    objectName: 'Mysql',
    objectDisplayName: 'MySQL',
    inheritedPermissionPath: '/monitor/view',
    component: MysqlDashboard
  },
  {
    key: 'redis',
    groupKey: 'database',
    objectName: 'Redis',
    objectDisplayName: 'Redis',
    inheritedPermissionPath: '/monitor/view',
    component: RedisDashboard
  },
  {
    key: 'mongodb',
    groupKey: 'database',
    objectName: 'Mongodb',
    objectDisplayName: 'MongoDB',
    inheritedPermissionPath: '/monitor/view',
    component: MongodbDashboard
  },
  {
    key: 'mssql',
    groupKey: 'database',
    objectName: 'MSSQL',
    objectDisplayName: 'MSSQL',
    inheritedPermissionPath: '/monitor/view',
    component: MssqlDashboard
  },
  {
    key: 'nginx',
    groupKey: 'middleware',
    objectName: 'nginx',
    objectDisplayName: 'Nginx',
    inheritedPermissionPath: '/monitor/view',
    component: NginxDashboard
  },
  {
    key: 'docker',
    groupKey: 'middleware',
    objectName: 'Docker',
    objectDisplayName: 'Docker',
    inheritedPermissionPath: '/monitor/view',
    component: DockerDashboard
  },
  {
    key: 'activemq',
    aliases: ['active_mq'],
    groupKey: 'middleware',
    objectName: 'ActiveMQ',
    objectDisplayName: 'ActiveMQ',
    inheritedPermissionPath: '/monitor/view',
    component: ActiveMQDashboard
  },
  {
    key: 'apache',
    groupKey: 'middleware',
    objectName: 'Apache',
    objectDisplayName: 'Apache',
    inheritedPermissionPath: '/monitor/view',
    component: ApacheDashboard
  },
  {
    key: 'consul',
    groupKey: 'middleware',
    objectName: 'Consul',
    objectDisplayName: 'Consul',
    inheritedPermissionPath: '/monitor/view',
    component: ConsulDashboard
  },
  {
    key: 'rabbitmq',
    aliases: ['rabbit_mq'],
    groupKey: 'middleware',
    objectName: 'RabbitMQ',
    objectDisplayName: 'RabbitMQ',
    inheritedPermissionPath: '/monitor/view',
    component: RabbitMQDashboard
  },
  {
    key: 'tomcat',
    groupKey: 'middleware',
    objectName: 'Tomcat',
    objectDisplayName: 'Tomcat',
    inheritedPermissionPath: '/monitor/view',
    component: TomcatDashboard
  },
  {
    key: 'zookeeper',
    aliases: ['zk'],
    groupKey: 'middleware',
    objectName: 'Zookeeper',
    objectDisplayName: 'Zookeeper',
    inheritedPermissionPath: '/monitor/view',
    component: ZookeeperDashboard
  },
  {
    key: 'postgres',
    aliases: ['postgresql'],
    groupKey: 'database',
    objectName: 'Postgres',
    objectDisplayName: 'PostgreSQL',
    inheritedPermissionPath: '/monitor/view',
    component: PostgresqlDashboard
  },
  {
    key: 'elasticsearch',
    groupKey: 'database',
    objectName: 'ElasticSearch',
    objectDisplayName: 'Elasticsearch',
    inheritedPermissionPath: '/monitor/view',
    component: ElasticsearchDashboard
  },
  {
    key: 'host',
    aliases: ['os', '主机'],
    groupKey: 'os',
    objectName: 'Host',
    objectDisplayName: '主机',
    inheritedPermissionPath: '/monitor/view',
    component: HostDashboard
  },
  {
    key: 'website',
    aliases: ['web', '网站'],
    groupKey: 'network',
    objectName: 'Website',
    objectDisplayName: '网站',
    inheritedPermissionPath: '/monitor/view',
    component: WebsiteDashboard
  },
  {
    key: 'ping',
    groupKey: 'network',
    objectName: 'Ping',
    objectDisplayName: 'Ping',
    inheritedPermissionPath: '/monitor/view',
    component: PingDashboard
  },
  {
    key: 'switch',
    aliases: ['交换机'],
    groupKey: 'network',
    objectName: 'Switch',
    objectDisplayName: '交换机',
    inheritedPermissionPath: '/monitor/view',
    component: SwitchDashboard
  },
  {
    key: 'firewall',
    aliases: ['防火墙'],
    groupKey: 'network',
    objectName: 'Firewall',
    objectDisplayName: '防火墙',
    inheritedPermissionPath: '/monitor/view',
    component: FirewallDashboard
  },
  {
    key: 'loadbalance',
    aliases: ['负载均衡'],
    groupKey: 'network',
    objectName: 'Loadbalance',
    objectDisplayName: '负载均衡',
    inheritedPermissionPath: '/monitor/view',
    component: LoadbalanceDashboard
  },
  {
    key: 'router',
    aliases: ['路由器'],
    groupKey: 'network',
    objectName: 'Router',
    objectDisplayName: '路由器',
    inheritedPermissionPath: '/monitor/view',
    component: RouterDashboard
  },
  {
    key: 'k8s-cluster',
    aliases: ['cluster'],
    groupKey: 'container',
    objectName: 'Cluster',
    objectDisplayName: '集群',
    inheritedPermissionPath: '/monitor/view',
    component: K8sClusterDashboard
  },
  {
    key: 'k8s-node',
    aliases: ['node'],
    groupKey: 'container',
    objectName: 'Node',
    objectDisplayName: '节点',
    inheritedPermissionPath: '/monitor/view',
    component: K8sNodeDashboard
  },
  {
    key: 'k8s-pod',
    aliases: ['pod'],
    groupKey: 'container',
    objectName: 'Pod',
    objectDisplayName: 'Pod',
    inheritedPermissionPath: '/monitor/view',
    component: K8sPodDashboard
  }
];

export const PROFESSIONAL_DASHBOARD_MAP = new Map(
  PROFESSIONAL_DASHBOARDS.flatMap((item) => {
    const keys = [item.key, ...(item.aliases || []), item.objectName, item.objectDisplayName]
      .filter(Boolean)
      .map((key) => normalizeDashboardKey(key));
    return keys.map((key) => [key, item.component] as const);
  })
);

const getDashboardCandidates = (item: ProfessionalDashboardRegistryItem) =>
  [item.key, ...(item.aliases || []), item.objectName, item.objectDisplayName]
    .filter(Boolean)
    .map((value) => normalizeDashboardKey(value));

export const getProfessionalDashboardKey = (objectName?: string | null, objectDisplayName?: string | null) => {
  const matched = PROFESSIONAL_DASHBOARDS.find((item) => {
    const candidates = getDashboardCandidates(item);
    const objectCandidates = [objectName, objectDisplayName].map((value) => normalizeDashboardKey(value));
    return objectCandidates.some((candidate) => candidate && candidates.includes(candidate));
  });

  return matched?.key || '';
};

export const getProfessionalDashboardUrl = (
  objectName?: string | null,
  objectDisplayName?: string | null,
  queryString?: string
) => {
  const key = getProfessionalDashboardKey(objectName, objectDisplayName);

  if (!key) {
    return '';
  }

  return `/monitor/view/dashboard/${key}${queryString ? `?${queryString}` : ''}`;
};

export const getProfessionalDashboardPermissionPath = (url?: string | null) => {
  const normalizedUrl = String(url || '').replace(/\/$/, '').toLowerCase();
  const matched = PROFESSIONAL_DASHBOARDS.find((item) => {
    return getDashboardCandidates(item).some((candidate) => {
      const dashboardPath = `/monitor/view/dashboard/${candidate}`;
      return normalizedUrl === dashboardPath || normalizedUrl.startsWith(`${dashboardPath}/`);
    });
  });
  return matched?.inheritedPermissionPath || '';
};
