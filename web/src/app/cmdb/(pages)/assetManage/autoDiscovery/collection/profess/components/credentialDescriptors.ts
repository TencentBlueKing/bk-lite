import type { ModelItem } from '@/app/cmdb/types/autoDiscovery';

export type CredentialFormKind =
  | 'ssh'
  | 'sql'
  | 'snmp'
  | 'influxdb'
  | 'cloud'
  | 'platform_api'
  | 'winrm'
  | 'macos_ssh'
  | 'winsphere'
  | 'vmware'
  | 'ipmi'
  | 'redfish'
  | 'network_config_file';

export interface CredentialFieldDescriptor {
  key: string;
  formLabelKey?: string;
  defaultValue?: string;
  defaultValueKey?: string;
  recommendedValue?: string;
  recommendedValueKey?: string;
}

export interface CredentialDescriptor {
  formKind: CredentialFormKind;
  protocolKey: string;
  credentialKindKey: string;
  instructionKey: string;
  defaultPort?: number;
  defaultPortLabel?: string;
  fields: readonly CredentialFieldDescriptor[];
}

const ACCOUNT_FIELDS = [
  { key: 'databaseAccount' },
  { key: 'databasePassword' },
] as const;

const PLATFORM_API_FIELDS = (defaultPort: string) => [
  { key: 'platformUsername' },
  { key: 'platformPassword' },
  { key: 'platformPort', defaultValue: defaultPort },
  {
    key: 'tlsVerify',
    defaultValueKey: 'enabled',
    recommendedValueKey: 'enabled',
  },
] as const;

const platformApiDescriptor = (
  defaultPort: number,
): CredentialDescriptor => ({
  formKind: 'platform_api',
  protocolKey: 'httpsApi',
  credentialKindKey: 'platformAccount',
  instructionKey: 'platformApi',
  defaultPort,
  fields: PLATFORM_API_FIELDS(String(defaultPort)),
});

const legacySqlDescriptor = (defaultPort: number): CredentialDescriptor => ({
  formKind: 'sql', protocolKey: 'mysql', credentialKindKey: 'databaseAccount',
  instructionKey: 'database', defaultPort,
  fields: [...ACCOUNT_FIELDS, { key: 'databasePort', defaultValue: String(defaultPort) }],
});

const legacyAkSkDescriptor = (defaultPort: number): CredentialDescriptor => ({
  formKind: 'cloud', protocolKey: 'httpsApi', credentialKindKey: 'platformAccount',
  instructionKey: 'database', defaultPort,
  fields: [
    { key: 'storageAccessKey', formLabelKey: 'Collection.cloudTask.accessKey' },
    { key: 'storageAccessSecret', formLabelKey: 'Collection.cloudTask.accessSecret' },
    { key: 'cloudRegion' },
  ],
});

const SNMP_FIELDS = [
  {
    key: 'snmpVersion',
    defaultValue: 'V2',
    recommendedValueKey: 'snmpV3Recommended',
  },
  { key: 'snmpCommunity' },
  { key: 'snmpUsername' },
  {
    key: 'snmpSecurityLevel',
    defaultValue: 'authNoPriv',
    recommendedValue: 'authPriv',
  },
  { key: 'snmpAuthAlgorithm', defaultValue: 'SHA-1' },
  { key: 'snmpAuthPassword' },
  { key: 'snmpPrivacyAlgorithm', defaultValue: 'AES-128' },
  { key: 'snmpPrivacyKey' },
  { key: 'snmpPort', defaultValue: '161' },
] as const;

const legacySnmpDescriptor = (): CredentialDescriptor => ({
  formKind: 'snmp', protocolKey: 'snmp', credentialKindKey: 'snmpParameters',
  instructionKey: 'snmp', defaultPort: 161, defaultPortLabel: 'UDP 161',
  fields: SNMP_FIELDS,
});

const legacySshDescriptor = (): CredentialDescriptor => ({
  formKind: 'ssh', protocolKey: 'ssh', credentialKindKey: 'hostAccount',
  instructionKey: 'ssh', defaultPort: 22,
  fields: [{ key: 'sshAccount' }, { key: 'sshPassword' }, { key: 'sshPort', defaultValue: '22' }],
});

export const CREDENTIAL_DESCRIPTORS = {
  protocols: {
    ssh: {
      formKind: 'ssh',
      protocolKey: 'ssh',
      credentialKindKey: 'hostAccount',
      instructionKey: 'ssh',
      defaultPort: 22,
      fields: [
        { key: 'sshAccount' },
        { key: 'sshPassword' },
        { key: 'sshPort', defaultValue: '22' },
      ],
    },
    mysql: {
      formKind: 'sql',
      protocolKey: 'mysql',
      credentialKindKey: 'databaseAccount',
      instructionKey: 'database',
      defaultPort: 3306,
      fields: [
        ...ACCOUNT_FIELDS,
        { key: 'databasePort', defaultValue: '3306' },
      ],
    },
    postgresql: {
      formKind: 'sql',
      protocolKey: 'postgresql',
      credentialKindKey: 'databaseAccount',
      instructionKey: 'database',
      defaultPort: 5432,
      fields: [
        ...ACCOUNT_FIELDS,
        { key: 'databasePort', defaultValue: '5432' },
      ],
    },
    sql_server: {
      formKind: 'sql',
      protocolKey: 'sqlServer',
      credentialKindKey: 'databaseAccount',
      instructionKey: 'database',
      defaultPort: 1433,
      fields: [
        ...ACCOUNT_FIELDS,
        { key: 'databasePort', defaultValue: '1433' },
        { key: 'databaseName', defaultValue: 'master' },
      ],
    },
    snmp: {
      formKind: 'snmp',
      protocolKey: 'snmp',
      credentialKindKey: 'snmpParameters',
      instructionKey: 'snmp',
      defaultPort: 161,
      defaultPortLabel: 'UDP 161',
      fields: SNMP_FIELDS,
    },
    redfish: {
      formKind: 'redfish',
      protocolKey: 'redfish',
      credentialKindKey: 'bmcAccount',
      instructionKey: 'redfish',
      defaultPort: 443,
      defaultPortLabel: 'HTTPS 443',
      fields: [
        { key: 'platformUsername' },
        { key: 'platformPassword' },
        { key: 'platformPort', defaultValue: '443' },
        {
          key: 'tlsVerify',
          defaultValueKey: 'enabled',
          recommendedValueKey: 'enabled',
        },
      ],
    },
  },
  models: {
    influxdb: {
      formKind: 'influxdb',
      protocolKey: 'influxdb',
      credentialKindKey: 'influxdbToken',
      instructionKey: 'influxdb',
      defaultPort: 8086,
      fields: [
        {
          key: 'influxProtocol',
          defaultValue: 'HTTP',
          recommendedValue: 'HTTPS',
        },
        { key: 'influxPort', defaultValue: '8086' },
        { key: 'influxToken' },
        {
          key: 'tlsVerify',
          defaultValueKey: 'enabled',
          recommendedValueKey: 'enabled',
        },
      ],
    },
    aliyun_account: {
      formKind: 'cloud',
      protocolKey: 'aliyun',
      credentialKindKey: 'aliyun',
      instructionKey: 'aliyun',
      fields: [
        {
          key: 'aliyunAccessKey',
          formLabelKey: 'Collection.cloudTask.aliyunAccessKeyId',
        },
        {
          key: 'aliyunAccessSecret',
          formLabelKey: 'Collection.cloudTask.aliyunAccessKeySecret',
        },
        { key: 'cloudRegion' },
      ],
    },
    qcloud: {
      formKind: 'cloud',
      protocolKey: 'tencent',
      credentialKindKey: 'tencent',
      instructionKey: 'tencent',
      fields: [
        {
          key: 'tencentAccessKey',
          formLabelKey: 'Collection.cloudTask.tencentSecretId',
        },
        {
          key: 'tencentAccessSecret',
          formLabelKey: 'Collection.cloudTask.tencentSecretKey',
        },
        { key: 'cloudRegion' },
      ],
    },
    hwcloud: {
      formKind: 'cloud',
      protocolKey: 'huawei',
      credentialKindKey: 'huawei',
      instructionKey: 'huawei',
      fields: [
        {
          key: 'huaweiAccessKey',
          formLabelKey: 'Collection.cloudTask.huaweiAk',
        },
        {
          key: 'huaweiAccessSecret',
          formLabelKey: 'Collection.cloudTask.huaweiSk',
        },
        { key: 'huaweiProjectId' },
        { key: 'cloudRegion' },
      ],
    },
    fusioninsight: {
      formKind: 'platform_api',
      protocolKey: 'httpsApi',
      credentialKindKey: 'fusionInsightBasic',
      instructionKey: 'fusionInsight',
      defaultPort: 443,
      fields: PLATFORM_API_FIELDS('443'),
    },
    storage: {
      formKind: 'platform_api',
      protocolKey: 'httpsApi',
      credentialKindKey: 'oceanStorAccount',
      instructionKey: 'oceanStor',
      defaultPort: 8088,
      fields: PLATFORM_API_FIELDS('8088'),
    },
    // 企业版云平台：HTTPS 平台账户（username/password[/port]）
    h3c_cas: platformApiDescriptor(443),
    fusioncompute: platformApiDescriptor(7443),
    nutanixhci: platformApiDescriptor(443),
    sangforhci: platformApiDescriptor(443),
    sangforscp: platformApiDescriptor(443),
    inspurincloudrail: platformApiDescriptor(443),
    zstack: platformApiDescriptor(8080),
    openstack: platformApiDescriptor(5000),
    smartx: platformApiDescriptor(443),
    manageone: platformApiDescriptor(443),
    // OAuth 身份来自凭据管理；订阅范围由采集任务设置。
    azure: {
      ...platformApiDescriptor(443),
      defaultPort: undefined,
      credentialKindKey: 'azureOAuth',
      instructionKey: 'azureOAuth',
      fields: [
        { key: 'azureClientId' }, { key: 'azureClientSecret' },
        { key: 'azureTenantId' }, { key: 'azureSubscriptionId' },
      ],
    },
    aws: {
      formKind: 'cloud',
      protocolKey: 'aws',
      credentialKindKey: 'aws',
      instructionKey: 'aws',
      fields: [
        {
          key: 'awsAccessKey',
          formLabelKey: 'Collection.cloudTask.accessKey',
        },
        {
          key: 'awsAccessSecret',
          formLabelKey: 'Collection.cloudTask.accessSecret',
        },
        { key: 'cloudRegion' },
      ],
    },
    network: {
      formKind: 'snmp',
      protocolKey: 'snmp',
      credentialKindKey: 'snmpParameters',
      instructionKey: 'snmp',
      defaultPort: 161,
      defaultPortLabel: 'UDP 161',
      fields: SNMP_FIELDS,
    },
    winsphere: {
      formKind: 'winsphere',
      protocolKey: 'winsphereApi',
      credentialKindKey: 'winsphereAccount',
      instructionKey: 'winsphere',
      defaultPort: 443,
      fields: [
        { key: 'winsphereUsername' },
        { key: 'winspherePassword' },
        { key: 'winspherePort', defaultValue: '443' },
        {
          key: 'tlsVerify',
          defaultValueKey: 'disabled',
          recommendedValueKey: 'enabled',
        },
      ],
    },
    vmware_vc: {
      formKind: 'vmware',
      protocolKey: 'vsphereApi',
      credentialKindKey: 'vsphereAccount',
      instructionKey: 'vsphere',
      defaultPort: 443,
      fields: [
        { key: 'vmwareUsername' },
        { key: 'vmwarePassword' },
        { key: 'vmwarePort', defaultValue: '443' },
        {
          key: 'vmwareSslVerify',
          defaultValueKey: 'disabled',
          recommendedValueKey: 'enabled',
        },
      ],
    },
    physcial_server: {
      formKind: 'ipmi',
      protocolKey: 'ipmi',
      credentialKindKey: 'bmcAccount',
      instructionKey: 'ipmi',
      defaultPort: 623,
      defaultPortLabel: 'UDP 623',
      fields: [
        { key: 'ipmiUsername' },
        { key: 'ipmiPassword' },
        { key: 'ipmiPort', defaultValue: '623' },
        {
          key: 'ipmiPrivilege',
          defaultValue: 'administrator',
          recommendedValue: 'operator',
        },
      ],
    },
    network_config_file: {
      formKind: 'network_config_file',
      protocolKey: 'sshOrTelnet',
      credentialKindKey: 'networkDeviceAccount',
      instructionKey: 'networkConfig',
      defaultPort: 22,
      defaultPortLabel: 'SSH 22 / Telnet 23',
      fields: [
        { key: 'transportProtocol', defaultValue: 'ssh' },
        { key: 'sshAccount' },
        { key: 'sshPassword' },
        { key: 'sshPort', defaultValue: '22' },
        { key: 'enablePassword' },
      ],
    },
    config_file: {
      formKind: 'ssh',
      protocolKey: 'ssh',
      credentialKindKey: 'hostAccount',
      instructionKey: 'configFile',
      defaultPort: 22,
      fields: [
        { key: 'sshAccount' },
        { key: 'sshPassword' },
        { key: 'sshPort', defaultValue: '22' },
      ],
    },
  },
  pc: {
    windows: {
      formKind: 'winrm',
      protocolKey: 'winrm',
      credentialKindKey: 'windowsAccount',
      instructionKey: 'winrm',
      defaultPortLabel: 'HTTPS 5986 / HTTP 5985',
      fields: [
        { key: 'winrmUsername' },
        { key: 'winrmPassword' },
        {
          key: 'winrmScheme',
          defaultValue: 'HTTPS',
          recommendedValue: 'HTTPS',
        },
        { key: 'winrmPort', defaultValue: '5986' },
        { key: 'winrmTransport', defaultValue: 'NTLM' },
        {
          key: 'winrmCertValidation',
          defaultValueKey: 'disabled',
          recommendedValueKey: 'enabled',
        },
      ],
    },
    macos: {
      formKind: 'macos_ssh',
      protocolKey: 'macosSsh',
      credentialKindKey: 'macosAccount',
      instructionKey: 'macosSsh',
      defaultPort: 22,
      fields: [
        { key: 'macUsername' },
        { key: 'macPort', defaultValue: '22' },
        {
          key: 'macAuthType',
          defaultValueKey: 'passwordAuth',
          recommendedValueKey: 'privateKeyAuth',
        },
        { key: 'macPassword' },
        { key: 'macPrivateKey' },
        { key: 'macPassphrase' },
      ],
    },
  },
} as const satisfies {
  protocols: Record<string, CredentialDescriptor>;
  models: Record<string, CredentialDescriptor>;
  pc: Record<string, CredentialDescriptor>;
};

// 未有专用描述的入口，逐项依据 cae36df3f^ 的 page.tsx / taskMap 恢复。
// 此清单与已有凭据类型无关；FC 两项按已核实的 SSHPlugin 脚本修正为账号密码表单。
const ORIGINAL_FORM_DESCRIPTORS: Record<string, CredentialDescriptor> = {
  sap_hana: { ...legacySqlDescriptor(30015), protocolKey: 'sapHana' },
  iris: { ...legacySqlDescriptor(1972), protocolKey: 'iris' },
  couchbase: { ...legacySqlDescriptor(8091), protocolKey: 'couchbase' },
  tongrds: { ...legacySqlDescriptor(6379), protocolKey: 'tongrds' },
  ambari: { ...platformApiDescriptor(8080), protocolKey: 'httpApi', instructionKey: 'httpApi' },
  ibm_storwize: platformApiDescriptor(7443),
  emc_symmetrix: platformApiDescriptor(8443),
  netapp_cluster: platformApiDescriptor(443),
  oraclezfs: platformApiDescriptor(215),
  infinidat: platformApiDescriptor(443),
  oceanbase: { ...legacySqlDescriptor(2881) },
  highgo: { ...CREDENTIAL_DESCRIPTORS.protocols.postgresql },
  greenplum: { ...CREDENTIAL_DESCRIPTORS.protocols.postgresql },
  kingbase: { ...CREDENTIAL_DESCRIPTORS.protocols.postgresql },
  opengauss: { ...CREDENTIAL_DESCRIPTORS.protocols.postgresql },
  vastbase: { ...CREDENTIAL_DESCRIPTORS.protocols.postgresql },
  server_bmc: { ...CREDENTIAL_DESCRIPTORS.protocols.redfish },
  nacos: { ...platformApiDescriptor(8848), protocolKey: 'httpApi', instructionKey: 'httpApi' },
  ...Object.fromEntries(
    'dell_unity netapp_ontap hds_vsp pure_array dell_powerstore hp_3par'.split(' ').map((id) => [id, platformApiDescriptor(443)]),
  ),
  ...Object.fromEntries(
    "f5 security_device tape_library macrosan".split(' ').map((id) => [id, legacySnmpDescriptor()]),
  ),
  ...Object.fromEntries(
    "tdsql gbase8a".split(' ').map((id) => [id, legacySqlDescriptor(3306)]),
  ),
  ...Object.fromEntries(
    "brocade_fc cisco_fc informix sybase mycat redis_sentinel gbase8s oscar dameng db2 tidb hmc ibmmq tonglinkq tonggtp ihs cics hdfs yarn storm bes apusic inforsuite_as ceph jboss jetty tongweb weblogic websphere".split(' ').map((id) => [id, legacySshDescriptor()]),
  ),
  ...Object.fromEntries(
    "ibm_ds xsky".split(' ').map((id) => [id, legacyAkSkDescriptor(443)]),
  ),
};

type CredentialModel = Partial<
  Pick<
    ModelItem,
    'model_id' | 'type' | 'credential_protocol' | 'credential_default_port' | 'credential_binding'
  >
>;

export function getCredentialDescriptor(
  model: CredentialModel,
): CredentialDescriptor | null {
  if (model.model_id === 'physcial_server' && model.type !== 'protocol') {
    return CREDENTIAL_DESCRIPTORS.protocols.ssh;
  }
  const withPort = (descriptor: CredentialDescriptor): CredentialDescriptor => {
    if (model.credential_default_port == null || descriptor.defaultPort === model.credential_default_port) return descriptor;
    const port = model.credential_default_port;
    return { ...descriptor, defaultPort: port, fields: descriptor.fields.map((field) =>
      field.key.endsWith('Port') ? { ...field, defaultValue: String(port) } : field),
    };
  };
  if (model.credential_protocol) {
    const protocolDescriptor = CREDENTIAL_DESCRIPTORS.protocols[
      model.credential_protocol as keyof typeof CREDENTIAL_DESCRIPTORS.protocols
    ];
    if (protocolDescriptor) {
      return withPort(protocolDescriptor);
    }
  }
  const modelDescriptor = CREDENTIAL_DESCRIPTORS.models[
    model.model_id as keyof typeof CREDENTIAL_DESCRIPTORS.models
  ];
  if (modelDescriptor) {
    return withPort(modelDescriptor);
  }
  // 一次性认证沿用原采集表单；凭据管理绑定只参与已有凭据筛选。
  const original = ORIGINAL_FORM_DESCRIPTORS[model.model_id || ''];
  return original ? withPort(original) : null;
}

export function getCredentialDefaultPort(model: CredentialModel): number | undefined {
  return model.credential_default_port ?? getCredentialDescriptor(model)?.defaultPort;
}
