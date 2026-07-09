import { CredentialListItem } from '@/app/cmdb/types/assetManage';
export const BUILD_IN_MODEL: Array<{
  key: string;
  icon: string;
}> = [
  // ↓↓↓ 与后端 model_config.xlsx 的 model_id 对齐的内置模型图标映射 ↓↓↓
  // 网络/计算核心（修正历史 bk_ 前缀错配）
  { key: 'switch', icon: 'cc-switch2' },
  { key: 'router', icon: 'cc-router' },
  { key: 'firewall', icon: 'cc-firewall' },
  { key: 'loadbalance', icon: 'cc-balance' },
  { key: 'k8s_node', icon: 'cc-node' },
  { key: 'system', icon: 'cc-business' },
  { key: 'physcial_server', icon: 'cc-hard-server' },
  { key: 'interface', icon: 'cc-ip' },
  // 复用现有图标
  { key: 'ssl_cer', icon: 'cc-certificate' },
  { key: 'es', icon: 'cc-elasticsearch' },
  { key: 'hbase', icon: 'cc-hbase' },
  { key: 'datacenter', icon: 'cc-datacenter-dc' },
  { key: 'rack', icon: 'cc-datacenter-rack' },
  { key: 'server_room', icon: 'cc-datacenter-room' },
  { key: 'haproxy', icon: 'cc-haproxy' },
  { key: 'ceph', icon: 'cc-storage' },
  { key: 'disk', icon: 'cc-storage' },
  { key: 'peripherals', icon: 'cc-equipment' },
  { key: 'office', icon: 'cc-equipment' },
  { key: 'pc', icon: 'cc-host' },
  // 新增专属图标（中间件 + 硬件部件）
  { key: 'activemq', icon: 'cc-activemq' },
  { key: 'rocketmq', icon: 'cc-rocketmq' },
  { key: 'jetty', icon: 'cc-jetty' },
  { key: 'jboss', icon: 'cc-jboss' },
  { key: 'memcached', icon: 'cc-memcached' },
  { key: 'spark', icon: 'cc-spark' },
  { key: 'etcd', icon: 'cc-etcd' },
  { key: 'squid', icon: 'cc-squid' },
  { key: 'keepalive', icon: 'cc-keepalive' },
  { key: 'tongweb', icon: 'cc-tongweb' },
  { key: 'tuxedo', icon: 'cc-tuxedo' },
  { key: 'openresty', icon: 'cc-openresty' },
  { key: 'memory', icon: 'cc-memory' },
  { key: 'nic', icon: 'cc-nic' },
  { key: 'gpu', icon: 'cc-gpu' },
  // 云厂商资源（复用云/对应技术图标）
  { key: 'aws_cf', icon: 'cc-cloud' },
  { key: 'aws_docdb', icon: 'cc-mongodb' },
  { key: 'aws_ec2', icon: 'cc-cloud-server' },
  { key: 'aws_eks', icon: 'cc-k8s-cluster' },
  { key: 'aws_elasticache', icon: 'cc-redis' },
  { key: 'aws_elb', icon: 'cc-cloud-elb' },
  { key: 'aws_memdb', icon: 'cc-redis' },
  { key: 'aws_msk', icon: 'cc-kafka' },
  { key: 'aws_rds', icon: 'cc-mysql' },
  { key: 'aws_s3_bucket', icon: 'cc-cloud-sp' },
  { key: 'hwcloud', icon: 'cc-cloud-huawei' },
  { key: 'hwcloud_ecs', icon: 'cc-cloud-server' },
  { key: 'manageone', icon: 'cc-cloud-manageone' },
  { key: 'manageone_cloud', icon: 'cc-cloud-manageone' },
  { key: 'manageone_ds', icon: 'cc-datastorage' },
  { key: 'manageone_host', icon: 'cc-cloud-host' },
  { key: 'manageone_server', icon: 'cc-cloud-server' },
  { key: 'openstack', icon: 'cc-cloud-openstack' },
  { key: 'qcloud', icon: 'cc-cloud-qcloud' },
  { key: 'qcloud_bucket', icon: 'cc-cloud-sp' },
  { key: 'qcloud_clb', icon: 'cc-cloud-elb' },
  { key: 'qcloud_cmq', icon: 'cc-kafka' },
  { key: 'qcloud_cmq_topic', icon: 'cc-kafka' },
  { key: 'qcloud_domain', icon: 'cc-cloud' },
  { key: 'qcloud_eip', icon: 'cc-ip' },
  { key: 'qcloud_filesystem', icon: 'cc-datastorage' },
  { key: 'qcloud_mongodb', icon: 'cc-mongodb' },
  { key: 'qcloud_mysql', icon: 'cc-mysql' },
  { key: 'qcloud_pgsql', icon: 'cc-postgresql' },
  { key: 'qcloud_plusar_cluster', icon: 'cc-kafka' },
  { key: 'qcloud_redis', icon: 'cc-redis' },
  { key: 'qcloud_rocketmq', icon: 'cc-rocketmq' },
  { key: 'smartx', icon: 'cc-cloud-smartx' },
  { key: 'fusioninsight', icon: 'cc-cloud-fusioninsight' },
  // ↑↑↑ 补充结束 ↑↑↑
  {
    key: 'active_directory',
    icon: 'cc-active-directory',
  },
  {
    key: 'apache',
    icon: 'cc-apache',
  },
  {
    key: 'application',
    icon: 'cc-application',
  },
  {
    key: 'bk_loadbalance',
    icon: 'cc-balance',
  },
  {
    key: 'biz',
    icon: 'cc-business',
  },
  {
    key: 'certificate',
    icon: 'cc-certificate',
  },
  {
    key: 'aliyun_domain',
    icon: 'cc-cloud',
  },
  {
    key: 'aliyun_parsing',
    icon: 'cc-cloud',
  },
  {
    key: 'aliyun_cdn',
    icon: 'cc-cloud',
  },
  {
    key: 'aliyun_firewall',
    icon: 'cc-cloud',
  },
  {
    key: 'aliyun_ssl',
    icon: 'cc-cloud',
  },
  {
    key: 'aliyun_mysql',
    icon: 'cc-cloud',
  },
  {
    key: 'aliyun_redis',
    icon: 'cc-cloud',
  },
  {
    key: 'mo_host',
    icon: 'cc-cloud',
  },
  {
    key: 'mo_ip',
    icon: 'cc-cloud',
  },
  {
    key: 'nutanixhci_sc',
    icon: 'cc-cloud',
  },
  {
    key: 'nutanixhci_vd',
    icon: 'cc-cloud',
  },
  {
    key: 'nutanixhci_disk',
    icon: 'cc-cloud',
  },
  {
    key: 'fusioninsight_cluster',
    icon: 'cc-cloud',
  },
  {
    key: 'openstack_node',
    icon: 'cc-cloud',
  },
  {
    key: 'smartx_cluster',
    icon: 'cc-cloud',
  },
  {
    key: 'mo_elb',
    icon: 'cc-cloud-elb',
  },
  {
    key: 'nutanixhci_host',
    icon: 'cc-cloud-host',
  },
  {
    key: 'smartx_host',
    icon: 'cc-cloud-host',
  },
  {
    key: 'vmware_vc',
    icon: 'cc-cloud-plat',
  },
  {
    key: 'aliyun_account',
    icon: 'cc-cloud-aliyun',
  },
  {
    key: 'qcloud_account',
    icon: 'cc-cloud-qcloud',
  },
  {
    key: 'mo_cloud',
    icon: 'cc-cloud-plat',
  },
  {
    key: 'huaweicloud_account',
    icon: 'cc-cloud-huawei',
  },
  {
    key: 'sangforhci_account',
    icon: 'cc-cloud-sangfor',
  },
  {
    key: 'nutanixhci_account',
    icon: 'cc-cloud-nutanix',
  },
  {
    key: 'fusioninsight_account',
    icon: 'cc-cloud-fusioninsight',
  },
  {
    key: 'openstack_account',
    icon: 'cc-cloud-openstack',
  },
  {
    key: 'smartx_account',
    icon: 'cc-cloud-smartx',
  },
  {
    key: 'vmware_vm',
    icon: 'cc-cloud-server',
  },
  {
    key: 'aliyun_ecs',
    icon: 'cc-cloud-server',
  },
  {
    key: 'qcloud_cvm',
    icon: 'cc-cloud-server',
  },
  {
    key: 'mo_server',
    icon: 'cc-cloud-server',
  },
  {
    key: 'huaweicloud_ecs',
    icon: 'cc-cloud-server',
  },
  {
    key: 'sangforhci_vm',
    icon: 'cc-cloud-server',
  },
  {
    key: 'nutanixhci_vm',
    icon: 'cc-cloud-server',
  },
  {
    key: 'fusioninsight_host',
    icon: 'cc-cloud-server',
  },
  {
    key: 'openstack_vm',
    icon: 'cc-cloud-server',
  },
  {
    key: 'smartx_vm',
    icon: 'cc-cloud-server',
  },
  {
    key: 'mo_ds',
    icon: 'cc-datastorage',
  },
  {
    key: 'nutanixhci_sp',
    icon: 'cc-cloud-sp',
  },
  {
    key: 'openstack_sp',
    icon: 'cc-cloud-sp',
  },
  {
    key: 'nutanixhci_vg',
    icon: 'cc-cloud-volume',
  },
  {
    key: 'openstack_vg',
    icon: 'cc-cloud-volume',
  },
  {
    key: 'smartx_vmvolume',
    icon: 'cc-cloud-volume',
  },
  {
    key: 'dameng',
    icon: 'cc-dameng',
  },
  {
    key: 'datacenter_dc',
    icon: 'cc-datacenter-dc',
  },
  {
    key: 'datacenter_rack',
    icon: 'cc-datacenter-rack',
  },
  {
    key: 'datacenter_room',
    icon: 'cc-datacenter-room',
  },
  {
    key: 'db2',
    icon: 'cc-db2',
  },
  {
    key: 'db_cluster',
    icon: 'cc-db-cluster',
  },
  {
    key: 'docker',
    icon: 'cc-docker',
  },
  {
    key: 'docker_container',
    icon: 'cc-docker-container',
  },
  {
    key: 'docker_image',
    icon: 'cc-docker-image',
  },
  {
    key: 'docker_network',
    icon: 'cc-docker-network',
  },
  {
    key: 'docker_volume',
    icon: 'cc-docker-volume',
  },
  {
    key: 'elasticsearch',
    icon: 'cc-elasticsearch',
  },
  {
    key: 'vmware_esxi',
    icon: 'cc-esxi-host',
  },
  {
    key: 'bk_firewall',
    icon: 'cc-firewall',
  },
  {
    key: 'hard_server',
    icon: 'cc-hard-server',
  },
  {
    key: 'host',
    icon: 'cc-host',
  },
  {
    key: 'ibmmq',
    icon: 'cc-ibmmq',
  },
  {
    key: 'iis',
    icon: 'cc-iis',
  },
  {
    key: 'ip',
    icon: 'cc-ip',
  },
  {
    key: 'k8s_cluster',
    icon: 'cc-k8s-cluster',
  },
  {
    key: 'k8s_namespace',
    icon: 'cc-k8s-namespace',
  },
  {
    key: 'k8s_workload',
    icon: 'cc-k8s-workload',
  },
  {
    key: 'kafka',
    icon: 'cc-kafka',
  },
  {
    key: 'exchange_server',
    icon: 'cc-mail-server',
  },
  {
    key: 'minio',
    icon: 'cc-minio',
  },
  {
    key: 'module',
    icon: 'cc-module',
  },
  {
    key: 'mongodb',
    icon: 'cc-mongodb',
  },
  {
    key: 'mysql',
    icon: 'cc-mysql',
  },
  {
    key: 'nacos',
    icon: 'cc-nacos',
  },
  {
    key: 'nginx',
    icon: 'cc-nginx',
  },
  {
    key: 'bk_node',
    icon: 'cc-node',
  },
  {
    key: 'oracle',
    icon: 'cc-oracle',
  },
  {
    key: 'k8s_pod',
    icon: 'cc-pod',
  },
  {
    key: 'postgresql',
    icon: 'cc-postgresql',
  },
  {
    key: 'profile',
    icon: 'cc-profile',
  },
  {
    key: 'rabbitmq',
    icon: 'cc-rabbitmq',
  },
  {
    key: 'redis',
    icon: 'cc-redis',
  },
  {
    key: 'bk_router',
    icon: 'cc-router',
  },
  {
    key: 'security_equipment',
    icon: 'cc-security-equipment',
  },
  {
    key: 'set',
    icon: 'cc-set',
  },
  {
    key: 'mssql',
    icon: 'cc-sql-server',
  },
  {
    key: 'vmware_ds',
    icon: 'cc-datastorage',
  },
  {
    key: 'aliyun_bucket',
    icon: 'cc-storage',
  },
  {
    key: 'storage',
    icon: 'cc-storage',
  },
  {
    key: 'subnet',
    icon: 'cc-subnet',
  },
  {
    key: 'bk_switch',
    icon: 'cc-switch2',
  },
  {
    key: 'tidb',
    icon: 'cc-tidb',
  },
  {
    key: 'tomcat',
    icon: 'cc-tomcat',
  },
  {
    key: 'weblogic',
    icon: 'cc-weblogic',
  },
  {
    key: 'websphere',
    icon: 'cc-websphere',
  },
  {
    key: 'zookeeper',
    icon: 'cc-zookeeper',
  },
  // ↑↑↑ 补缺第一批：2026-07-06 自主巡航补齐的中间件/数据库图标 ↓↓↓
  {
    key: 'influxdb',
    icon: 'cc-influxdb',
  },
  {
    key: 'consul',
    icon: 'cc-consul',
  },
  {
    key: 'network_config_file',
    icon: 'cc-network-config',
  },
  // ↑↑↑ 国产数据库：2026-07-07 用户反馈 OceanBase/高斯/人大金仓缺失 ↓↓↓
  {
    key: 'oceanbase',
    icon: 'cc-oceanbase',
  },
  {
    key: 'oceanbase_zone',
    icon: 'cc-oceanbase_zone',
  },
  {
    key: 'oceanbase_server',
    icon: 'cc-oceanbase_server',
  },
  {
    key: 'oceanbase_tenant',
    icon: 'cc-oceanbase_tenant',
  },
  {
    key: 'opengauss',
    icon: 'cc-opengauss',
  },
  {
    key: 'gaussdb',
    icon: 'cc-gaussdb',
  },
  {
    key: 'kingbase',
    icon: 'cc-kingbase',
  },
  {
    key: 'vastbase',
    icon: 'cc-vastbase',
  },
  {
    key: 'greenplum',
    icon: 'cc-greenplum',
  },
  {
    key: 'storage_disk',
    icon: 'cc-storage',
  },
  {
    key: 'storage_volume',
    icon: 'cc-cloud-volume',
  },
  {
    key: 'fusioncompute',
    icon: 'cc-cloud-plat',
  },
  {
    key: 'highgo',
    icon: 'cc-highgo',
  },
  // ↑↑↑ 2026-07-07 用户反馈 Storm/YARN/HDFS 等大数据组件图标缺失 ↓↓↓
  {
    key: 'storm',
    icon: 'cc-storm',
  },
  {
    key: 'yarn',
    icon: 'cc-yarn',
  },
  {
    key: 'hdfs',
    icon: 'cc-hdfs',
  },
  {
    key: 'ambari',
    icon: 'cc-ambari',
  },
  // 东方通 Tong 系列
  {
    key: 'tonglinkq',
    icon: 'cc-tonglinkq',
  },
  {
    key: 'tonggtp',
    icon: 'cc-tonggtp',
  },
  {
    key: 'bes',
    icon: 'cc-bes',
  },
  {
    key: 'apusic',
    icon: 'cc-apusic',
  },
  {
    key: 'inforsuite_as',
    icon: 'cc-inforsuite_as',
  },
  // IBM 中间件
  {
    key: 'ihs',
    icon: 'cc-ihs',
  },
  {
    key: 'cics',
    icon: 'cc-cics',
  },
  // 数据库
  {
    key: 'informix',
    icon: 'cc-informix',
  },
  {
    key: 'sybase',
    icon: 'cc-sybase',
  },
  {
    key: 'couchbase',
    icon: 'cc-couchbase',
  },
  {
    key: 'mycat',
    icon: 'cc-mycat',
  },
  {
    key: 'sap_hana',
    icon: 'cc-sap_hana',
  },
  {
    key: 'iris',
    icon: 'cc-iris',
  },
  {
    key: 'gbase8s',
    icon: 'cc-gbase8s',
  },
  {
    key: 'oscar',
    icon: 'cc-oscar',
  },
  {
    key: 'tongrds',
    icon: 'cc-tongrds',
  },
  {
    key: 'tdsql',
    icon: 'cc-tdsql',
  },
  {
    key: 'redis_sentinel',
    icon: 'cc-redis_sentinel',
  },
  // 存储硬件
  {
    key: 'ibm_storwize',
    icon: 'cc-ibm_storwize',
  },
  {
    key: 'ibm_ds',
    icon: 'cc-ibm_ds',
  },
  {
    key: 'emc_symmetrix',
    icon: 'cc-emc_symmetrix',
  },
  {
    key: 'hds_vsp',
    icon: 'cc-hds_vsp',
  },
  {
    key: 'macrosan',
    icon: 'cc-macrosan',
  },
  {
    key: 'pure_array',
    icon: 'cc-pure_array',
  },
  {
    key: 'netapp_cluster',
    icon: 'cc-netapp_cluster',
  },
  {
    key: 'oraclezfs',
    icon: 'cc-oraclezfs',
  },
  {
    key: 'infinidat',
    icon: 'cc-infinidat',
  },
  {
    key: 'tape_library',
    icon: 'cc-tape_library',
  },
  {
    key: 'xsky',
    icon: 'cc-xsky',
  },
  // 网络硬件
  {
    key: 'brocade_fc',
    icon: 'cc-brocade_fc',
  },
  {
    key: 'cisco_fc',
    icon: 'cc-cisco_fc',
  },
  {
    key: 'f5',
    icon: 'cc-f5',
  },
  // 操作系统
  {
    key: 'aix',
    icon: 'cc-aix',
  },
  {
    key: 'hpux',
    icon: 'cc-hpux',
  },
  {
    key: 'hmc',
    icon: 'cc-hmc',
  },
  {
    key: 'domestic_linux',
    icon: 'cc-domestic_linux',
  },
  // 其他
  {
    key: 'security_device',
    icon: 'cc-security_device',
  },
  {
    key: 'zstack',
    icon: 'cc-zstack',
  },
  {
    key: 'h3c_cas',
    icon: 'cc-h3c_cas',
  },
];

// 值类型
export const ATTR_TYPE_LIST = [
  {
    id: 'str',
    name: 'string',
  },
  {
    id: 'int',
    name: 'number',
  },
  {
    id: 'enum',
    name: 'enumeration',
  },
  {
    id: 'tag',
    name: 'tag',
  },
  {
    id: 'time',
    name: 'time',
  },
  {
    id: 'user',
    name: 'user',
  },
  {
    id: 'pwd',
    name: 'password',
  },
  {
    id: 'bool',
    name: 'boolean',
  },
  {
    id: 'organization',
    name: 'organization',
  },
  {
    id: 'table',
    name: 'table',
  },
  {
    id: 'attachment',
    name: 'attachment',
  },
  {
    id: 'image',
    name: 'image',
  },
];

export const CONSTRAINT_List = [
  {
    id: 'n:n',
    name: 'N-N',
  },
  {
    id: 'n:1',
    name: 'N-1',
  },
  {
    id: '1:n',
    name: '1-N',
  },
  {
    id: '1:1',
    name: '1-1',
  },
];

export const CREDENTIAL_LIST: CredentialListItem[] = [
  {
    classification_name: 'OS',
    classification_id: 'os',
    list: [
      {
        model_id: 'host',
        model_name: 'Host',
        assoModelIds: [
          'host',
          'vmware_vm',
          'alibabacloud_ecs',
          'tencentcloud_cvm',
          'huaweicloud_ecs',
        ],
        attrs: [
          {
            attr_id: 'name',
            attr_name: 'Name',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'port',
            attr_name: 'Port',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'username',
            attr_name: 'Username',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'password',
            attr_name: 'Password',
            attr_type: 'pwd',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'remark',
            attr_name: 'Remark',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: false,
          },
        ],
      },
    ],
  },
  {
    classification_name: 'Database',
    classification_id: 'database',
    list: [
      {
        model_id: 'mysql',
        model_name: 'MySQL',
        assoModelIds: ['mysql'],
        attrs: [
          {
            attr_id: 'name',
            attr_name: 'Name',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'port',
            attr_name: 'Port',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'username',
            attr_name: 'Username',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'password',
            attr_name: 'Password',
            attr_type: 'pwd',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'remark',
            attr_name: 'Remark',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: false,
          },
        ],
      },
      {
        model_id: 'oracle',
        model_name: 'Oracle',
        assoModelIds: ['oracle'],
        attrs: [
          {
            attr_id: 'name',
            attr_name: 'Name',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'port',
            attr_name: 'Port',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'username',
            attr_name: 'Username',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'password',
            attr_name: 'Password',
            attr_type: 'pwd',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'remark',
            attr_name: 'Remark',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: false,
          },
        ],
      },
    ],
  },
  {
    classification_name: 'Device',
    classification_id: 'device',
    list: [
      {
        model_id: 'snmp',
        model_name: 'SNMP',
        assoModelIds: [
          'switch',
          'router',
          'loadbalance',
          'firewall',
          'hard_server',
          'storage',
          'security_equipment',
        ],
        attrs: [
          {
            attr_id: 'name',
            attr_name: 'Name',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'version',
            attr_name: 'SNMP Version',
            attr_type: 'enum',
            option: [
              {
                name: 'SNMP_V2',
                id: 0,
              },
              {
                name: 'SNMP_V2C',
                id: 1,
              },
              {
                name: 'SNMP_V3',
                id: 2,
              },
            ],
            editable: true,
            is_required: true,
            children: [
              {
                parent_id: 0,
                attr_id: 'port1',
                attr_name: 'Port',
                attr_type: 'str',
                option: [],
                editable: true,
                is_required: true,
              },
              {
                parent_id: 0,
                attr_id: 'community',
                attr_name: 'Community',
                attr_type: 'str',
                option: [],
                editable: true,
                is_required: true,
              },
              {
                parent_id: 1,
                attr_id: 'port1',
                attr_name: 'Port',
                attr_type: 'str',
                option: [],
                editable: true,
                is_required: true,
              },
              {
                parent_id: 1,
                attr_id: 'community',
                attr_name: 'Community',
                attr_type: 'str',
                option: [],
                editable: true,
                is_required: true,
              },
              {
                parent_id: 2,
                attr_id: 'port2',
                attr_name: 'Port',
                attr_type: 'str',
                option: [],
                editable: true,
                is_required: true,
              },
              {
                parent_id: 2,
                attr_id: 'username',
                attr_name: 'Username',
                attr_type: 'str',
                option: [],
                editable: true,
                is_required: true,
              },
              {
                parent_id: 2,
                attr_id: 'secret_key',
                attr_name: 'Secret Key',
                attr_type: 'pwd',
                option: [],
                editable: true,
                is_required: true,
              },
              {
                parent_id: 2,
                attr_id: 'hash_algorithm',
                attr_name: 'Hash Algorithm',
                attr_type: 'enum',
                option: [
                  {
                    name: 'MD5',
                    id: 0,
                  },
                  {
                    name: 'SHA',
                    id: 1,
                  },
                ],
                editable: true,
                is_required: true,
              },
              {
                parent_id: 2,
                attr_id: 'security_level',
                attr_name: 'Security Level',
                attr_type: 'enum',
                option: [
                  {
                    name: 'authNoPriv',
                    id: 0,
                  },
                  {
                    name: 'authPriv',
                    id: 1,
                  },
                ],
                editable: true,
                is_required: true,
                children: [
                  {
                    parent_id: 1,
                    attr_id: 'encryption_algorithm',
                    attr_name: 'Encryption Algorithm',
                    attr_type: 'enum',
                    option: [
                      {
                        name: 'AES',
                        id: 0,
                      },
                      {
                        name: 'DES',
                        id: 1,
                      },
                    ],
                    editable: true,
                    is_required: true,
                  },
                  {
                    parent_id: 1,
                    attr_id: 'encryption_key',
                    attr_name: 'Encryption Key',
                    attr_type: 'pwd',
                    option: [],
                    editable: true,
                    is_required: true,
                  },
                ],
              },
            ],
          },
          {
            attr_id: 'remark',
            attr_name: 'Remark',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: false,
          },
        ],
      },
    ],
  },
  {
    classification_name: 'Cloud',
    classification_id: 'cloud',
    list: [
      {
        model_id: 'alibabacloud',
        model_name: 'Alibaba Cloud',
        assoModelIds: ['tencentcloud_platform'],
        attrs: [
          {
            attr_id: 'name',
            attr_name: 'Name',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'access_key',
            attr_name: 'Access key',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'access_secret',
            attr_name: 'Access secret',
            attr_type: 'pwd',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'remarks',
            attr_name: 'Remarks',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: false,
          },
        ],
      },
      {
        model_id: 'tencentcloud',
        model_name: 'Tencent Cloud',
        assoModelIds: ['alibabacloud_platform'],
        attrs: [
          {
            attr_id: 'name',
            attr_name: 'Name',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'access_key',
            attr_name: 'Access key',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'access_secret',
            attr_name: 'Access secret',
            attr_type: 'pwd',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'remarks',
            attr_name: 'Remarks',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: false,
          },
        ],
      },
      {
        model_id: 'azure',
        model_name: 'Azure',
        assoModelIds: ['azure_platform'],
        attrs: [
          {
            attr_id: 'name',
            attr_name: 'Name',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'username',
            attr_name: 'Username',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'password',
            attr_name: 'Password',
            attr_type: 'pwd',
            option: [],
            editable: true,
            is_required: true,
          },
          {
            attr_id: 'remarks',
            attr_name: 'Remarks',
            attr_type: 'str',
            option: [],
            editable: true,
            is_required: false,
          },
        ],
      },
    ],
  },
];
