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
  { key: 'snmpAuthAlgorithm', defaultValue: 'SHA' },
  { key: 'snmpAuthPassword' },
  { key: 'snmpPrivacyAlgorithm', defaultValue: 'AES' },
  { key: 'snmpPrivacyKey' },
  { key: 'snmpPort', defaultValue: '161' },
] as const;

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
    storage: {
      formKind: 'platform_api',
      protocolKey: 'httpsApi',
      credentialKindKey: 'oceanStorAccount',
      instructionKey: 'oceanStor',
      defaultPort: 8088,
      fields: [
        { key: 'platformUsername' },
        { key: 'platformPassword' },
        { key: 'platformPort', defaultValue: '8088' },
        {
          key: 'tlsVerify',
          defaultValueKey: 'enabled',
          recommendedValueKey: 'enabled',
        },
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
      protocolKey: 'ssh',
      credentialKindKey: 'networkDeviceAccount',
      instructionKey: 'networkConfig',
      defaultPort: 22,
      fields: [
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

type CredentialModel = Partial<
  Pick<
    ModelItem,
    'model_id' | 'type' | 'credential_protocol' | 'credential_default_port'
  >
>;

export function getCredentialDescriptor(
  model: CredentialModel,
): CredentialDescriptor | null {
  if (model.model_id === 'physcial_server' && model.type !== 'protocol') {
    return CREDENTIAL_DESCRIPTORS.protocols.ssh;
  }
  const modelDescriptor = CREDENTIAL_DESCRIPTORS.models[
    model.model_id as keyof typeof CREDENTIAL_DESCRIPTORS.models
  ];
  if (modelDescriptor) {
    return modelDescriptor;
  }
  if (!model.credential_protocol) {
    return null;
  }
  return CREDENTIAL_DESCRIPTORS.protocols[
    model.credential_protocol as keyof typeof CREDENTIAL_DESCRIPTORS.protocols
  ] || null;
}

export function getCredentialDefaultPort(model: CredentialModel): number | undefined {
  return model.credential_default_port ?? getCredentialDescriptor(model)?.defaultPort;
}
