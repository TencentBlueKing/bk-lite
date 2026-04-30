import type { TreeNode } from '@/app/cmdb/types/autoDiscovery';

const DEFAULT_COLLECTION_ICON = '/assets/icons/cc-default_默认.svg';

const COLLECTION_ICON_MAP: Array<{ keywords: string[]; src: string }> = [
  {
    keywords: ['k8s', 'kubernetes'],
    src: '/assets/icons/cc-k8s-cluster_K8S集群.svg',
  },
  {
    keywords: ['docker'],
    src: '/assets/icons/cc-docker_Docker.svg',
  },
  {
    keywords: ['vcenter', 'vmware', 'esxi'],
    src: '/assets/icons/cc-esxi-host_ESXi.svg',
  },
  {
    keywords: ['network', 'snmp', 'switch', 'router'],
    src: '/assets/icons/cc-router_路由器.svg',
  },
  {
    keywords: ['mssql', 'sql_server', 'sql server'],
    src: '/assets/icons/cc-sql-server_MSSQL.svg',
  },
  {
    keywords: ['mysql'],
    src: '/assets/icons/cc-mysql_MySQL.svg',
  },
  {
    keywords: ['postgresql', 'postgres'],
    src: '/assets/icons/cc-postgresql_PostgreSQL.svg',
  },
  {
    keywords: ['redis'],
    src: '/assets/icons/cc-redis_REDIS.svg',
  },
  {
    keywords: ['mongodb', 'mongo'],
    src: '/assets/icons/cc-mongodb_MongoDB.svg',
  },
  {
    keywords: ['rabbitmq'],
    src: '/assets/icons/cc-rabbitmq_RabbitMQ.svg',
  },
  {
    keywords: ['kafka'],
    src: '/assets/icons/cc-kafka_Kafka.svg',
  },
  {
    keywords: ['nginx'],
    src: '/assets/icons/cc-nginx_Nginx.svg',
  },
  {
    keywords: ['oracle'],
    src: '/assets/icons/cc-oracle_Oracle.svg',
  },
  {
    keywords: ['tidb'],
    src: '/assets/icons/cc-tidb_TiDB.svg',
  },
  {
    keywords: ['cloud'],
    src: '/assets/icons/cc-cloud_云.svg',
  },
  {
    keywords: ['host', 'linux', 'windows'],
    src: '/assets/icons/cc-host_主机.svg',
  },
];

export const getCollectionIconSrc = (tab: TreeNode) => {
  const searchText = [tab.model_id, tab.id, tab.name, tab.type, tab.task_type]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  return (
    COLLECTION_ICON_MAP.find(({ keywords }) =>
      keywords.some((keyword) => searchText.includes(keyword))
    )?.src || DEFAULT_COLLECTION_ICON
  );
};
