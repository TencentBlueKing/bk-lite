export const FINGERPRINT_TARGET_TYPE_OPTIONS = [
  { value: 'mysql', label: 'MySQL' },
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mssql', label: 'SQL Server (MSSQL)' },
  { value: 'oracle', label: 'Oracle' },
  { value: 'influxdb', label: 'InfluxDB' },
  { value: 'redis', label: 'Redis' },
  { value: 'mongodb', label: 'MongoDB' },
  { value: 'es', label: 'Elasticsearch' },
  { value: 'nginx', label: 'Nginx' },
  { value: 'apache', label: 'Apache' },
  { value: 'openresty', label: 'OpenResty' },
  { value: 'tomcat', label: 'Tomcat' },
  { value: 'kafka', label: 'Kafka' },
  { value: 'zookeeper', label: 'ZooKeeper' },
  { value: 'rabbitmq', label: 'RabbitMQ' },
  { value: 'consul', label: 'Consul' },
  { value: 'etcd', label: 'Etcd' },
  { value: 'memcached', label: 'Memcached' },
  { value: 'minio', label: 'MinIO' },
  { value: 'haproxy', label: 'HAProxy' },
  { value: 'iis', label: 'IIS' },
  { value: 'activemq', label: 'ActiveMQ' },
  { value: 'rocketmq', label: 'RocketMQ' },
  { value: 'squid', label: 'Squid' },
  { value: 'nacos', label: 'Nacos' },
];

export const getTargetTypeLabel = (value: string) => {
  const found = FINGERPRINT_TARGET_TYPE_OPTIONS.find((item) => item.value === value);
  return found ? found.label : value;
};
