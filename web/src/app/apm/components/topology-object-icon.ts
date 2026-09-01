export const DEFAULT_TOPOLOGY_OBJECT_ICON = 'cc-default_默认';

export interface TopologyObjectIconRef {
  file: string;
  kind: string;
}

const SYSTEM_ICONS: Record<string, TopologyObjectIconRef> = {
  activemq: { file: 'cc-activemq_ActiveMQ', kind: 'activemq' },
  consul: { file: 'cc-consul_Consul', kind: 'consul' },
  elasticsearch: { file: 'cc-elasticsearch_ElasticSearch', kind: 'elasticsearch' },
  es: { file: 'cc-elasticsearch_ElasticSearch', kind: 'elasticsearch' },
  etcd: { file: 'cc-etcd_Etcd', kind: 'etcd' },
  haproxy: { file: 'cc-haproxy_HAProxy', kind: 'haproxy' },
  hbase: { file: 'cc-hbase_HBase', kind: 'hbase' },
  influxdb: { file: 'cc-influxdb_InfluxDB', kind: 'influxdb' },
  kafka: { file: 'cc-kafka_Kafka', kind: 'kafka' },
  mariadb: { file: 'cc-mysql_MySQL', kind: 'mysql' },
  memcached: { file: 'cc-memcached_Memcached', kind: 'memcached' },
  'microsoft.sql_server': { file: 'cc-sql-server_MSSQL', kind: 'mssql' },
  minio: { file: 'cc-minio_Minio', kind: 'minio' },
  mongo: { file: 'cc-mongodb_MongoDB', kind: 'mongodb' },
  mongodb: { file: 'cc-mongodb_MongoDB', kind: 'mongodb' },
  mssql: { file: 'cc-sql-server_MSSQL', kind: 'mssql' },
  mysql: { file: 'cc-mysql_MySQL', kind: 'mysql' },
  nacos: { file: 'cc-nacos_Nacos', kind: 'nacos' },
  nginx: { file: 'cc-nginx_Nginx', kind: 'nginx' },
  openresty: { file: 'cc-openresty_OpenResty', kind: 'openresty' },
  oracle: { file: 'cc-oracle_Oracle', kind: 'oracle' },
  pgsql: { file: 'cc-postgresql_PostgreSQL', kind: 'postgresql' },
  postgres: { file: 'cc-postgresql_PostgreSQL', kind: 'postgresql' },
  postgresql: { file: 'cc-postgresql_PostgreSQL', kind: 'postgresql' },
  rabbitmq: { file: 'cc-rabbitmq_RabbitMQ', kind: 'rabbitmq' },
  redis: { file: 'cc-redis_REDIS', kind: 'redis' },
  rocketmq: { file: 'cc-rocketmq_RocketMQ', kind: 'rocketmq' },
  sqlserver: { file: 'cc-sql-server_MSSQL', kind: 'mssql' },
  tidb: { file: 'cc-tidb_TiDB', kind: 'tidb' },
  tomcat: { file: 'cc-tomcat_Tomcat', kind: 'tomcat' },
  zookeeper: { file: 'cc-zookeeper_ZooKeeper', kind: 'zookeeper' },
};

const NAME_HINTS: Array<{ pattern: RegExp; icon: TopologyObjectIconRef }> = [
  { pattern: /postgres|pgsql/, icon: SYSTEM_ICONS.postgresql },
  { pattern: /redis/, icon: SYSTEM_ICONS.redis },
  { pattern: /mysql|mariadb/, icon: SYSTEM_ICONS.mysql },
  { pattern: /mongo/, icon: SYSTEM_ICONS.mongodb },
  { pattern: /kafka/, icon: SYSTEM_ICONS.kafka },
  { pattern: /rabbit/, icon: SYSTEM_ICONS.rabbitmq },
  { pattern: /rocketmq/, icon: SYSTEM_ICONS.rocketmq },
  { pattern: /elastic/, icon: SYSTEM_ICONS.elasticsearch },
  { pattern: /memcache/, icon: SYSTEM_ICONS.memcached },
  { pattern: /oracle/, icon: SYSTEM_ICONS.oracle },
  { pattern: /mssql|sqlserver|sql-server/, icon: SYSTEM_ICONS.mssql },
  { pattern: /nginx/, icon: SYSTEM_ICONS.nginx },
  { pattern: /openresty/, icon: SYSTEM_ICONS.openresty },
  { pattern: /haproxy/, icon: SYSTEM_ICONS.haproxy },
  { pattern: /tomcat/, icon: SYSTEM_ICONS.tomcat },
  { pattern: /nacos/, icon: SYSTEM_ICONS.nacos },
  { pattern: /consul/, icon: SYSTEM_ICONS.consul },
  { pattern: /etcd/, icon: SYSTEM_ICONS.etcd },
  { pattern: /zookeeper|\bzk\b/, icon: SYSTEM_ICONS.zookeeper },
  { pattern: /influx/, icon: SYSTEM_ICONS.influxdb },
  { pattern: /minio/, icon: SYSTEM_ICONS.minio },
  { pattern: /gateway|kong|apisix|envoy|traefik/, icon: { file: 'cc-nginx_Nginx', kind: 'gateway' } },
];

const DEFAULT_ICON: TopologyObjectIconRef = {
  file: DEFAULT_TOPOLOGY_OBJECT_ICON,
  kind: 'default',
};

export function resolveTopologyObjectIcon(system?: string, name?: string): TopologyObjectIconRef {
  const normalizedSystem = system?.trim().toLowerCase() ?? '';
  if (normalizedSystem && SYSTEM_ICONS[normalizedSystem]) return SYSTEM_ICONS[normalizedSystem];
  const haystack = `${normalizedSystem} ${name?.trim().toLowerCase() ?? ''}`;
  const hinted = NAME_HINTS.find((item) => item.pattern.test(haystack));
  return hinted?.icon ?? DEFAULT_ICON;
}

export function topologyObjectIconSrc(system?: string, name?: string) {
  return `/assets/icons/${resolveTopologyObjectIcon(system, name).file}.svg`;
}
