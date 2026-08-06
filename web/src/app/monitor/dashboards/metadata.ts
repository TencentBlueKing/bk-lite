import type { ProfessionalDashboardMetaItem } from './shared/types';
import { ENTERPRISE_PROFESSIONAL_DASHBOARD_METADATA } from './objects/(enterprise)-metadata';
import { normalizeDashboardKey } from './shared/utils';

export const PROFESSIONAL_DASHBOARD_GROUPS = {
  hardware: { label: '硬件设备', order: 10 },
  container: { label: '容器', order: 15 },
  os: { label: '操作系统', order: 20 },
  network: { label: '网络', order: 30 },
  database: { label: '数据库', order: 40 },
  middleware: { label: '中间件', order: 50 }
} as const;

const COMMUNITY_DASHBOARD_METADATA: ProfessionalDashboardMetaItem[] = [
  { key: 'jvm', groupKey: 'middleware', objectName: 'JVM', objectDisplayName: 'JVM', inheritedPermissionPath: '/monitor/view' },
  { key: 'mysql', groupKey: 'database', objectName: 'Mysql', objectDisplayName: 'MySQL', inheritedPermissionPath: '/monitor/view' },
  { key: 'redis', groupKey: 'database', objectName: 'Redis', objectDisplayName: 'Redis', inheritedPermissionPath: '/monitor/view' },
  { key: 'mongodb', groupKey: 'database', objectName: 'Mongodb', objectDisplayName: 'MongoDB', inheritedPermissionPath: '/monitor/view' },
  { key: 'mssql', groupKey: 'database', objectName: 'MSSQL', objectDisplayName: 'MSSQL', inheritedPermissionPath: '/monitor/view' },
  { key: 'nginx', groupKey: 'middleware', objectName: 'nginx', objectDisplayName: 'Nginx', inheritedPermissionPath: '/monitor/view' },
  { key: 'docker', groupKey: 'middleware', objectName: 'Docker', objectDisplayName: 'Docker', inheritedPermissionPath: '/monitor/view' },
  { key: 'activemq', aliases: ['active_mq'], groupKey: 'middleware', objectName: 'ActiveMQ', objectDisplayName: 'ActiveMQ', inheritedPermissionPath: '/monitor/view' },
  { key: 'apache', groupKey: 'middleware', objectName: 'Apache', objectDisplayName: 'Apache', inheritedPermissionPath: '/monitor/view' },
  { key: 'consul', groupKey: 'middleware', objectName: 'Consul', objectDisplayName: 'Consul', inheritedPermissionPath: '/monitor/view' },
  { key: 'rabbitmq', aliases: ['rabbit_mq'], groupKey: 'middleware', objectName: 'RabbitMQ', objectDisplayName: 'RabbitMQ', inheritedPermissionPath: '/monitor/view' },
  { key: 'tomcat', groupKey: 'middleware', objectName: 'Tomcat', objectDisplayName: 'Tomcat', inheritedPermissionPath: '/monitor/view' },
  { key: 'zookeeper', aliases: ['zk'], groupKey: 'middleware', objectName: 'Zookeeper', objectDisplayName: 'Zookeeper', inheritedPermissionPath: '/monitor/view' },
  { key: 'kafka', groupKey: 'middleware', objectName: 'Kafka', objectDisplayName: 'Kafka', inheritedPermissionPath: '/monitor/view' },
  { key: 'postgres', aliases: ['postgresql'], groupKey: 'database', objectName: 'Postgres', objectDisplayName: 'PostgreSQL', inheritedPermissionPath: '/monitor/view' },
  { key: 'elasticsearch', groupKey: 'database', objectName: 'ElasticSearch', objectDisplayName: 'Elasticsearch', inheritedPermissionPath: '/monitor/view' },
  { key: 'host', aliases: ['os', '主机'], groupKey: 'os', objectName: 'Host', objectDisplayName: '主机', inheritedPermissionPath: '/monitor/view' },
  { key: 'process', aliases: ['进程'], groupKey: 'os', objectName: 'Process', objectDisplayName: '进程', inheritedPermissionPath: '/monitor/view' },
  { key: 'website', aliases: ['web', '网站'], groupKey: 'network', objectName: 'Website', objectDisplayName: '网站', inheritedPermissionPath: '/monitor/view' },
  { key: 'ping', groupKey: 'network', objectName: 'Ping', objectDisplayName: 'Ping', inheritedPermissionPath: '/monitor/view' },
  { key: 'tcp', aliases: ['TCPPort', 'TCP端口'], groupKey: 'network', objectName: 'TCPPort', objectDisplayName: 'TCP', inheritedPermissionPath: '/monitor/view' },
  { key: 'switch', aliases: ['交换机'], groupKey: 'network', objectName: 'Switch', objectDisplayName: '交换机', inheritedPermissionPath: '/monitor/view' },
  { key: 'firewall', aliases: ['防火墙'], groupKey: 'network', objectName: 'Firewall', objectDisplayName: '防火墙', inheritedPermissionPath: '/monitor/view' },
  { key: 'loadbalance', aliases: ['负载均衡'], groupKey: 'network', objectName: 'Loadbalance', objectDisplayName: '负载均衡', inheritedPermissionPath: '/monitor/view' },
  { key: 'router', aliases: ['路由器'], groupKey: 'network', objectName: 'Router', objectDisplayName: '路由器', inheritedPermissionPath: '/monitor/view' },
  { key: 'wireless', aliases: ['无线设备'], groupKey: 'network', objectName: 'Wireless', objectDisplayName: '无线设备', inheritedPermissionPath: '/monitor/view' },
  { key: 'transmission', aliases: ['传输设备'], groupKey: 'network', objectName: 'Transmission', objectDisplayName: '传输设备', inheritedPermissionPath: '/monitor/view' },
  { key: 'access', aliases: ['接入设备'], groupKey: 'network', objectName: 'Access', objectDisplayName: '接入设备', inheritedPermissionPath: '/monitor/view' },
  { key: 'network_service', aliases: ['网络服务'], groupKey: 'network', objectName: 'NetworkService', objectDisplayName: '网络服务', inheritedPermissionPath: '/monitor/view' },
  { key: 'console_server', aliases: ['控制台服务器'], groupKey: 'network', objectName: 'ConsoleServer', objectDisplayName: '控制台服务器', inheritedPermissionPath: '/monitor/view' },
  { key: 'voice_gateway', aliases: ['语音网关'], groupKey: 'network', objectName: 'VoiceGateway', objectDisplayName: '语音网关', inheritedPermissionPath: '/monitor/view' },
  { key: 'k8s-cluster', aliases: ['cluster'], groupKey: 'container', objectName: 'Cluster', objectDisplayName: '集群', inheritedPermissionPath: '/monitor/view' },
  { key: 'k8s-node', aliases: ['node'], groupKey: 'container', objectName: 'Node', objectDisplayName: '节点', inheritedPermissionPath: '/monitor/view' },
  { key: 'k8s-pod', aliases: ['pod'], groupKey: 'container', objectName: 'Pod', objectDisplayName: 'Pod', inheritedPermissionPath: '/monitor/view' },
  { key: 'k3s-cluster', groupKey: 'container', objectName: 'K3SCluster', objectDisplayName: 'K3S 集群', inheritedPermissionPath: '/monitor/view' },
  { key: 'k3s-node', groupKey: 'container', objectName: 'K3SNode', objectDisplayName: 'K3S 节点', inheritedPermissionPath: '/monitor/view' },
  { key: 'k3s-pod', groupKey: 'container', objectName: 'K3SPod', objectDisplayName: 'K3S Pod', inheritedPermissionPath: '/monitor/view' }
];

export const PROFESSIONAL_DASHBOARD_METADATA: ProfessionalDashboardMetaItem[] = [
  ...COMMUNITY_DASHBOARD_METADATA,
  ...ENTERPRISE_PROFESSIONAL_DASHBOARD_METADATA
];

/** @deprecated 使用 PROFESSIONAL_DASHBOARD_METADATA；保留别名兼容旧引用。 */
export const PROFESSIONAL_DASHBOARDS = PROFESSIONAL_DASHBOARD_METADATA;

const getDashboardCandidates = (item: ProfessionalDashboardMetaItem) =>
  [item.key, ...(item.aliases || []), item.objectName, item.objectDisplayName]
    .filter(Boolean)
    .map((value) => normalizeDashboardKey(value));

export const findProfessionalDashboardMeta = (
  objectName?: string | null,
  objectDisplayName?: string | null
) => {
  const objectCandidates = [objectName, objectDisplayName].map((value) => normalizeDashboardKey(value));
  return PROFESSIONAL_DASHBOARD_METADATA.find((item) => {
    const candidates = getDashboardCandidates(item);
    return objectCandidates.some((candidate) => candidate && candidates.includes(candidate));
  });
};

export const findProfessionalDashboardMetaByKey = (objectKey?: string | null) => {
  const normalizedKey = normalizeDashboardKey(objectKey);
  if (!normalizedKey) return undefined;
  return PROFESSIONAL_DASHBOARD_METADATA.find((item) =>
    getDashboardCandidates(item).includes(normalizedKey)
  );
};

export const getProfessionalDashboardKey = (objectName?: string | null, objectDisplayName?: string | null) => {
  return findProfessionalDashboardMeta(objectName, objectDisplayName)?.key || '';
};

/** 侧栏/列表展示名：优先 API display_name；TCPPort 等技术名回退到注册表 objectDisplayName（→ TCP）。 */
export const getProfessionalObjectDisplayName = (objectName?: string | null, objectDisplayName?: string | null) => {
  const matched = findProfessionalDashboardMeta(objectName, objectDisplayName);
  const apiName = String(objectDisplayName || '').trim();
  const technicalName = String(objectName || '').trim();
  const apiKey = normalizeDashboardKey(apiName);
  const techKey = normalizeDashboardKey(technicalName);

  if (techKey === 'tcpport' || apiKey === 'tcpport') {
    return matched?.objectDisplayName || 'TCP';
  }
  if (apiName && apiName !== technicalName) return apiName;
  return matched?.objectDisplayName || apiName || technicalName || '';
};

export const getProfessionalDashboardUrl = (
  objectName?: string | null,
  objectDisplayName?: string | null,
  queryString?: string
) => {
  const key = getProfessionalDashboardKey(objectName, objectDisplayName);
  if (!key) return '';
  return `/monitor/view/dashboard/${key}${queryString ? `?${queryString}` : ''}`;
};

export const getProfessionalDashboardPermissionPath = (url?: string | null) => {
  const normalizedUrl = String(url || '').replace(/\/$/, '').toLowerCase();
  const matched = PROFESSIONAL_DASHBOARD_METADATA.find((item) => {
    return getDashboardCandidates(item).some((candidate) => {
      const dashboardPath = `/monitor/view/dashboard/${candidate}`;
      return normalizedUrl === dashboardPath || normalizedUrl.startsWith(`${dashboardPath}/`);
    });
  });
  return matched?.inheritedPermissionPath || '';
};
