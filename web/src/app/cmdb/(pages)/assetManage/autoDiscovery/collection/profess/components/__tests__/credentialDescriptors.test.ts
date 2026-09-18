import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { getCredentialDescriptor } from '../credentialDescriptors';


describe('network config file credential descriptors', () => {
  it('declares SSH/Telnet protocol and default ports', () => {
    const descriptor = getCredentialDescriptor({
      model_id: 'network_config_file',
    });

    expect(descriptor?.formKind).toBe('network_config_file');
    expect(descriptor?.protocolKey).toBe('sshOrTelnet');
    expect(descriptor?.defaultPort).toBe(22);
    expect(descriptor?.defaultPortLabel).toBe('SSH 22 / Telnet 23');
    expect(descriptor?.fields.map((field) => field.key)).toContain('transportProtocol');
  });
});

describe('physical server credential descriptors', () => {
  it('uses the explicit Redfish protocol instead of the legacy IPMI model default', () => {
    const descriptor = getCredentialDescriptor({
      model_id: 'physcial_server',
      type: 'protocol',
      credential_protocol: 'redfish',
      credential_default_port: 443,
    });

    expect(descriptor?.formKind).toBe('redfish');
    expect(descriptor?.protocolKey).toBe('redfish');
    expect(descriptor?.defaultPort).toBe(443);
  });

  it('keeps historical protocol tasks on the IPMI descriptor', () => {
    const descriptor = getCredentialDescriptor({
      model_id: 'physcial_server',
      type: 'protocol',
    });

    expect(descriptor?.formKind).toBe('ipmi');
    expect(descriptor?.defaultPort).toBe(623);
  });
});

describe('企业版按 Stargazer 复核后的认证入口', () => {
  it.each([
    ['zstack', 'platform_api'],
    ['f5', 'snmp'], ['security_device', 'snmp'], ['tape_library', 'snmp'],
    ['couchbase', 'sql'], ['sap_hana', 'sql'], ['iris', 'sql'], ['tongrds', 'sql'], ['tdsql', 'sql'],
    ['ibm_storwize', 'platform_api'], ['ibm_ds', 'cloud'], ['emc_symmetrix', 'platform_api'],
    ['macrosan', 'snmp'], ['netapp_cluster', 'platform_api'], ['oraclezfs', 'platform_api'],
    ['infinidat', 'platform_api'], ['xsky', 'cloud'], ['ambari', 'platform_api'],
  ] as const)('%s 有对应的有效采集表单', (modelId, formKind) => {
    expect(getCredentialDescriptor({ model_id: modelId })?.formKind).toBe(formKind);
  });
});

// FC 历史路由为 SNMP，但实际插件声明 SSHPlugin；按用户要求以脚本修正。
describe('原始一次性表单不受凭据绑定影响', () => {
  it.each(['brocade_fc', 'cisco_fc'])('%s 按实际脚本使用 SSH 账号密码表单', (modelId) => {
    const model = { model_id: modelId, task_type: 'snmp', type: 'job', credential_protocol: 'ssh' };
    expect(getCredentialDescriptor({ ...model, credential_binding: 'network/snmp' })?.formKind).toBe('ssh');
    expect(getCredentialDescriptor(model)?.formKind).toBe('ssh');
  });
});

interface OriginalEntry {
  id: string;
  model_id: string;
  type: string;
  task_type: string;
  credential_protocol?: string;
  credential_default_port?: number;
  original_form: string;
  effective_form?: string;
  binding: string | null;
}
const originalEntries: OriginalEntry[] = JSON.parse(readFileSync(
  resolve(process.cwd(), '../server/apps/cmdb/tests/fixtures/collection_original_forms.json'), 'utf8',
));
describe('118 个原始入口的认证表单逐项回归', () => {
  it.each(originalEntries.filter((row) => !['none', 'winrm'].includes(row.original_form)))(
    '$id 保留原组件且不受已有凭据类型影响', (row) => {
      const expected = row.effective_form || (row.original_form === 'config_file' ? 'ssh' : row.original_form);
      expect(getCredentialDescriptor(row)?.formKind).toBe(expected);
      expect(getCredentialDescriptor({ ...row, credential_binding: row.binding })?.formKind).toBe(expected);
      expect(getCredentialDescriptor({ ...row, credential_binding: 'host/ssh' })?.formKind).toBe(expected);
    },
  );
});

it.each([
  ['oceanbase', 'sql', 'mysql', 2881],
  ['highgo', 'sql', 'postgresql', 5432],
  ['greenplum', 'sql', 'postgresql', 5432],
  ['kingbase', 'sql', 'postgresql', 5432],
  ['opengauss', 'sql', 'postgresql', 5432],
  ['vastbase', 'sql', 'postgresql', 5432],
  ['server_bmc', 'redfish', 'redfish', 443],
  ['nacos', 'platform_api', 'httpApi', 8848],
  ...['dell_unity', 'netapp_ontap', 'hds_vsp', 'pure_array', 'dell_powerstore', 'hp_3par']
    .map((id) => [id, 'platform_api', 'httpsApi', 443]),
])('%s 的表单和缺省端口匹配真实采集器', (modelId, formKind, protocolKey, defaultPort) => {
  const descriptor = getCredentialDescriptor({ model_id: String(modelId) });
  expect(descriptor?.formKind).toBe(formKind);
  expect(descriptor?.protocolKey).toBe(protocolKey);
  expect(descriptor?.defaultPort).toBe(defaultPort);
});

describe('Stargazer 原始参数默认值', () => {
  it.each([
    ['sap_hana', 30015], ['iris', 1972], ['ambari', 8080], ['ibm_storwize', 7443],
    ['emc_symmetrix', 8443], ['netapp_cluster', 443], ['oraclezfs', 215], ['infinidat', 443],
    ['macrosan', 161], ['f5', 161], ['security_device', 161], ['tape_library', 161],
  ] as const)('%s 显示脚本对应端口', (model_id, port) => {
    expect(getCredentialDescriptor({ model_id })?.defaultPort).toBe(port);
  });
  it.each([['couchbase',8091], ['tongrds',6379]] as const)('%s 使用 Stargazer 插件清单的端口', (model_id, port) => {
    expect(getCredentialDescriptor({ model_id })?.defaultPort).toBe(port);
  });
});
