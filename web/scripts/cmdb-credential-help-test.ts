/**
 * CMDB 专业采集凭据描述契约。
 *
 * Run: pnpm exec tsx scripts/cmdb-credential-help-test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  CREDENTIAL_DESCRIPTORS,
  getCredentialDefaultPort,
  getCredentialDescriptor,
} from '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialDescriptors';
import {
  buildPCCredentialHelp,
  buildSnmpCredentialHelp,
  resolveCredentialHelp,
  type CredentialHelpTranslator,
} from '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialHelp';

const localePath = (locale: 'zh' | 'en') =>
  resolve(process.cwd(), `src/app/cmdb/locales/${locale}.json`);
const locales = {
  zh: JSON.parse(readFileSync(localePath('zh'), 'utf8')),
  en: JSON.parse(readFileSync(localePath('en'), 'utf8')),
};
const t: CredentialHelpTranslator = (key) => {
  const value = key.split('.').reduce<unknown>(
    (current, part) => (
      current && typeof current === 'object'
        ? (current as Record<string, unknown>)[part]
        : undefined
    ),
    locales.zh,
  );
  return typeof value === 'string' ? value : key;
};

const ssh = resolveCredentialHelp(
  {
    model_id: 'host',
    credential_protocol: 'ssh',
    credential_default_port: 2222,
  },
  t,
);
assert.equal(ssh.protocol, 'SSH');
assert.equal(ssh.defaultPort, '2222');
assert.equal(
  ssh.fields?.find((field) => field.name === '端口')?.defaultValue,
  '2222',
);

const postgresModel = {
  model_id: 'postgresql',
  credential_protocol: 'postgresql',
} as const;
assert.equal(getCredentialDefaultPort(postgresModel), 5432);
assert.equal(getCredentialDescriptor(postgresModel)?.formKind, 'sql');
assert.equal(
  resolveCredentialHelp(postgresModel, t).fields
    ?.find((field) => field.name === '端口')?.defaultValue,
  '5432',
);

assert.equal(
  getCredentialDescriptor({
    model_id: 'enterprise-plugin',
  }),
  null,
  '未知插件不能仅凭 task_type 猜测认证表单',
);
assert.equal(
  resolveCredentialHelp({ model_id: 'enterprise-plugin' }, t).protocol,
  '此插件尚未提供协议说明，请以插件文档为准。',
);

assert.equal(
  getCredentialDescriptor({ model_id: 'hwcloud' })?.formKind,
  'cloud',
);
assert.equal(
  getCredentialDescriptor({ model_id: 'fusioninsight' })?.defaultPort,
  443,
);
assert.equal(
  getCredentialDescriptor({ model_id: 'storage' })?.defaultPort,
  8088,
);
assert.equal(
  getCredentialDescriptor({ model_id: 'winsphere' })?.defaultPort,
  443,
);
assert.equal(
  getCredentialDescriptor({ model_id: 'vmware_vc' })?.formKind,
  'vmware',
);
assert.equal(
  getCredentialDescriptor({
    model_id: 'physcial_server',
    type: 'protocol',
  })?.defaultPort,
  623,
);
assert.equal(
  getCredentialDescriptor({
    model_id: 'physcial_server',
    type: 'job',
  })?.formKind,
  'ssh',
);
assert.equal(
  getCredentialDescriptor({ model_id: 'network_config_file' })?.formKind,
  'network_config_file',
);
assert.equal(
  getCredentialDescriptor({ model_id: 'config_file' })?.formKind,
  'ssh',
);

const snmp = buildSnmpCredentialHelp(t);
assert.deepEqual(
  snmp.fields?.map((field) => field.name),
  [
    '版本',
    '团体字',
    '用户名',
    '安全级别',
    '认证算法',
    '认证密码',
    '加密算法',
    '加密密钥',
    '端口',
  ],
);
assert.equal(
  snmp.fields?.find((field) => field.name === '认证算法')?.defaultValue,
  'SHA',
);
assert.equal(
  snmp.fields?.find((field) => field.name === '加密算法')?.defaultValue,
  'AES',
);

const windows = buildPCCredentialHelp('windows', t);
assert.equal(windows.defaultPort, 'HTTPS 5986 / HTTP 5985');
assert.equal(
  windows.fields?.find((field) => field.name === '协议')?.recommendedValue,
  'HTTPS',
);
const macos = buildPCCredentialHelp('macos', t);
assert.equal(
  macos.fields?.find((field) => field.name === '认证方式')
    ?.recommendedValue,
  'PEM 私钥',
);

assert.equal(
  CREDENTIAL_DESCRIPTORS.models.influxdb.fields
    .find((field) => field.key === 'influxToken')?.defaultValue,
  undefined,
  'Operator Token 必须保持选填',
);

for (const messages of Object.values(locales)) {
  const help = messages.Collection.credentialHelp;
  assert.ok(help.labels.protocol);
  assert.ok(help.labels.fieldDetails);
  assert.ok(help.unsupportedTitle);
  assert.ok(help.unsupportedDescription);
  for (const fieldKey of [
    'snmpAuthAlgorithm',
    'snmpAuthPassword',
    'snmpPrivacyAlgorithm',
    'snmpPrivacyKey',
  ]) {
    assert.ok(help.fieldNames[fieldKey]);
    assert.ok(help.fields[fieldKey]);
  }
  const descriptors = [
    ...Object.values(CREDENTIAL_DESCRIPTORS.protocols),
    ...Object.values(CREDENTIAL_DESCRIPTORS.models),
    ...Object.values(CREDENTIAL_DESCRIPTORS.pc),
  ];
  for (const descriptor of descriptors) {
    assert.ok(help.protocol[descriptor.protocolKey]);
    assert.ok(help.kind[descriptor.credentialKindKey]);
    assert.ok(help.instruction[descriptor.instructionKey]);
    for (const field of descriptor.fields) {
      assert.ok(help.fieldNames[field.key], `missing field name: ${field.key}`);
      assert.ok(help.fields[field.key], `missing field help: ${field.key}`);
    }
  }
}

const professStyles = readFileSync(
  resolve(
    process.cwd(),
    'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/index.module.scss',
  ),
  'utf8',
);
assert.match(
  professStyles,
  /\.credentialPoolHelpButton\s*\{[\s\S]*?height:\s*40px;[\s\S]*?min-width:\s*40px;/,
  '凭据帮助按钮的桌面点击区域不得小于 40×40px',
);
assert.match(
  professStyles,
  /@media\s*\(pointer:\s*coarse\)[\s\S]*?\.credentialPoolHelpButton\s*\{[\s\S]*?height:\s*44px;[\s\S]*?min-width:\s*44px;/,
  '触摸设备上的凭据帮助按钮不得小于 44×44px',
);

console.log('CMDB credential descriptor contract passed');
