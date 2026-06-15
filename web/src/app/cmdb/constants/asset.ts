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
  { key: 'haproxy', icon: 'cc-balance' },
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
  { key: 'hwcloud', icon: 'cc-cloud-plat' },
  { key: 'hwcloud_ecs', icon: 'cc-cloud-server' },
  { key: 'manageone', icon: 'cc-cloud-plat' },
  { key: 'manageone_cloud', icon: 'cc-cloud-plat' },
  { key: 'manageone_ds', icon: 'cc-storage' },
  { key: 'manageone_host', icon: 'cc-cloud-host' },
  { key: 'manageone_server', icon: 'cc-cloud-server' },
  { key: 'openstack', icon: 'cc-cloud-plat' },
  { key: 'qcloud', icon: 'cc-cloud-plat' },
  { key: 'qcloud_bucket', icon: 'cc-cloud-sp' },
  { key: 'qcloud_clb', icon: 'cc-cloud-elb' },
  { key: 'qcloud_cmq', icon: 'cc-kafka' },
  { key: 'qcloud_cmq_topic', icon: 'cc-kafka' },
  { key: 'qcloud_domain', icon: 'cc-cloud' },
  { key: 'qcloud_eip', icon: 'cc-ip' },
  { key: 'qcloud_filesystem', icon: 'cc-storage' },
  { key: 'qcloud_mongodb', icon: 'cc-mongodb' },
  { key: 'qcloud_mysql', icon: 'cc-mysql' },
  { key: 'qcloud_pgsql', icon: 'cc-postgresql' },
  { key: 'qcloud_plusar_cluster', icon: 'cc-kafka' },
  { key: 'qcloud_redis', icon: 'cc-redis' },
  { key: 'qcloud_rocketmq', icon: 'cc-rocketmq' },
  { key: 'smartx', icon: 'cc-cloud-plat' },
  { key: 'fusioninsight', icon: 'cc-cloud-plat' },
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
    icon: 'cc-cloud-plat',
  },
  {
    key: 'qcloud_account',
    icon: 'cc-cloud-plat',
  },
  {
    key: 'mo_cloud',
    icon: 'cc-cloud-plat',
  },
  {
    key: 'huaweicloud_account',
    icon: 'cc-cloud-plat',
  },
  {
    key: 'sangforhci_account',
    icon: 'cc-cloud-plat',
  },
  {
    key: 'nutanixhci_account',
    icon: 'cc-cloud-plat',
  },
  {
    key: 'fusioninsight_account',
    icon: 'cc-cloud-plat',
  },
  {
    key: 'openstack_account',
    icon: 'cc-cloud-plat',
  },
  {
    key: 'smartx_account',
    icon: 'cc-cloud-plat',
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
    icon: 'cc-cloud-sp',
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
    icon: 'cc-storage',
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
