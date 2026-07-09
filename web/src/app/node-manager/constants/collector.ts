// 采集器显示插件列表
const DISPLAY_PLUGINS: string[] = [
  'Telegraf',
  'Vector',
  'Beat',
  'Export',
  'JMX',
];

// 采集器标签映射
const COLLECTOR_LABEL: Record<string, string[]> = {
  Telegraf: ['Telegraf'],
  Vector: ['Vector'],
  Beat: ['Auditbeat', 'Metricbeat', 'Winlogbeat', 'Packetbeat', 'Filebeat'],
  JMX: [
    'Tomcat-JMX',
    'ActiveMQ-JMX',
    'JVM-JMX',
  ],
  Export: [
    'RabbitMQ-Exporter',
    'Nginx-Exporter',
    'Apache-Exporter',
    'Zookeeper-Exporter',
    'Kafka-Exporter',
    'IIS-Exporter',
    'ElasticSearch-Exporter',
    'Mongodb-Exporter',
    'Mysql-Exporter',
    'Postgres-Exporter',
    'Redis-Exporter',
    'MSSQL-Exporter',
    'Oracle-Exporter',
    'DaMeng-Exporter',
    'openGauss-Exporter',
    'Gbase8a-Exporter',
    'HANA-Exporter',
    'GrenPlum-Exporter',
    'DB2-Exporter',
    'Excahnge-Exporter',
    'AD-Exporter',
    'DM-Exporter',
    'GreenPlum-Exporter',
    'ClickHouse-Exporter',
    'GBase8a-Exporter',
    'OpenGauss-Exporter',
    'KingBase-Exporter',
    'VastBase-Exporter',
  ],
  'BK-pull': [
    'MinIO-Bk-pull',
    'etcd-Bk-pull',
    'TiDB-BK-pull',
  ],
};

export { COLLECTOR_LABEL, DISPLAY_PLUGINS };
