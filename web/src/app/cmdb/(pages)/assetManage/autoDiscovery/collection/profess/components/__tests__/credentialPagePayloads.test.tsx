import React from 'react';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { act, cleanup, render } from '@testing-library/react';
import { afterAll, afterEach, expect, it, vi } from 'vitest';
import type { CredentialPoolItem, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import { getCredentialDescriptor } from '../credentialDescriptors';
import HostTask from '../hostTask';
import SQLTask from '../sqlTask';
import PlatformApiTask from '../platformApiTask';
import CloudTask from '../cloudTask';
import SnmpTask from '../snmpTask';
import VMTask from '../vmTask';
import WinSphereTask from '../winsphereTask';
import InfluxdbTask from '../influxdbTask';
import IPMITask from '../ipmiTask';
import RedfishTask from '../redfishTask';
import PCTask from '../pcTask';
import ConfigFileTask from '../configFileTask';
import NetworkConfigFileTask from '../networkConfigFileTask';

type Values = Record<string, unknown>;
interface Entry extends ModelItem { original_form: string; effective_form?: string; binding: string | null }
const state = vi.hoisted(() => ({
  setCopyTaskData: () => {},
  values: {} as Values,
  saved: null as Values | null,
  format: null as null | ((values: Values) => Values),
  target: {} as Values,
  rules: new Map<string, Array<{ validator?: (rule: unknown, value: unknown) => Promise<void> }>>(),
}));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string, fallback?: string) => fallback || key }) }));
vi.mock('@/app/cmdb/store/useAssetManage', () => ({ default: (selector?: (value: unknown) => unknown) => {
  const store = { copyTaskData: null, setCopyTaskData: state.setCopyTaskData };
  return selector ? selector(store) : store;
} }));
vi.mock('@/context/userInfo', () => ({ useUserInfoContext: () => ({ selectedGroup: null }) }));
vi.mock('@/app/cmdb/api', () => ({ useCollectApi: () => ({ getCollectRegions: async () => [], getNetworkConfigBrands: async () => [] }) }));
vi.mock('../../hooks/useCollectionFormLayout', () => ({ useCollectionFormLayout: () => ({}) }));
vi.mock('../credentialPoolEditor', () => ({ default: () => null }));
vi.mock('antd', () => {
  const Container = ({ children }: { children?: React.ReactNode }) => children;
  const Form = Object.assign(Container, {
    Item: ({ name, rules, children }: { name?: string; rules?: Array<{ validator?: (r: unknown, v: unknown) => Promise<void> }>; children?: React.ReactNode }) => {
      if (name && rules) state.rules.set(name, rules);
      return typeof children === 'function' ? null : children;
    },
    useWatch: (name: string) => state.values[name],
  });
  return { Form, Spin: Container, Tooltip: Container, Alert: () => null, Select: () => null,
    Input: Object.assign(() => null, { TextArea: () => null }), InputNumber: () => null,
    Switch: () => null, Radio: Object.assign(() => null, { Group: Container }), message: { success: vi.fn(), error: vi.fn() } };
});
vi.mock('../baseTask', async () => {
  const { forwardRef, useImperativeHandle } = await import('react');
  return { default: forwardRef(function Base({ children }: { children?: React.ReactNode }, ref) {
    useImperativeHandle(ref, () => ({
      collectionType: 'asset', selectedData: [state.target],
      accessPoints: [{ value: 'test-node', origin: { id: 'test-node' } }],
      instOptions: [{ value: state.target.inst_uuid, origin: state.target }],
      initCollectionType: vi.fn(),
    }));
    return children;
  }) };
});
vi.mock('../../hooks/useTaskForm', () => ({
  getCleanupFormValues: () => ({ cleanupStrategy: 'no_cleanup', cleanupDays: 0 }),
  getCycleFormValues: () => ({ cycle: 'cycle', intervalValue: 30 }),
  useTaskForm: ({ formatValues }: { formatValues: (values: Values) => Values }) => {
    state.format = formatValues;
    return {
      form: {
        setFieldsValue: (values: Values) => Object.assign(state.values, values),
        getFieldValue: (key: string) => state.values[key],
        getFieldsValue: () => state.values,
        setFieldValue: (key: string, value: unknown) => { state.values[key] = value; },
      },
      fetchTaskDetail: async () => state.saved,
      formatCycleValue: () => ({ value_type: 'cycle', value: 30 }),
      onFinish: vi.fn(), loading: false, submitLoading: false,
    };
  },
}));

const entries: Entry[] = JSON.parse(readFileSync(process.env.CMDB_PAGE_TREE || resolve(process.cwd(), '../server/apps/cmdb/tests/fixtures/collection_original_forms.json'), 'utf8'));
const components = { ssh: HostTask, sql: SQLTask, platform_api: PlatformApiTask, cloud: CloudTask,
  snmp: SnmpTask, vmware: VMTask, winsphere: WinSphereTask, influxdb: InfluxdbTask, ipmi: IPMITask,
  redfish: RedfishTask, winrm: PCTask, config_file: ConfigFileTask, network_config_file: NetworkConfigFileTask };
const artifacts: Values[] = [];
afterEach(cleanup);
afterAll(() => {
  if (process.env.CMDB_PAGE_PAYLOADS) writeFileSync(process.env.CMDB_PAGE_PAYLOADS, JSON.stringify(artifacts, null, 2));
});

const schema = { schema_version: 1, allow_multiple: false, allow_unknown_fields: false, encrypted_fields: ['password'], fields: [
  { key: 'user', type: 'string' as const, label: '账号', required: true },
  { key: 'password', type: 'password' as const, label: '密码', required: true },
  { key: 'https_port', type: 'integer' as const, label: '端口', required: true, default: 443, min: 1, max: 65535 },
  { key: 'verify_tls', type: 'boolean' as const, label: '校验证书', required: true, default: true },
] };

function credentialFor(form: keyof typeof components, entry: Entry): CredentialPoolItem {
  const port = getCredentialDescriptor(entry)?.defaultPort || 443;
  const credentials: Record<keyof typeof components, CredentialPoolItem> = {
    ssh: { username: 'page-reader', password: 'page-secret', port: 2222 },
    sql: { user: 'page-reader', password: 'page-secret', port },
    platform_api: { username: 'page-reader', password: 'page-secret', port, verify_tls: false },
    cloud: { accessKey: 'page-key', accessSecret: 'page-secret', regionId: 'region-test', projectId: 'project-test' },
    snmp: { version: 'v3', username: 'page-reader', level: 'authPriv', integrity: 'sha', authkey: 'page-auth', privacy: 'aes', privkey: 'page-priv', snmp_port: 1161 },
    vmware: { username: 'page-reader', password: 'page-secret', port: 8443, ssl: false },
    winsphere: { user: 'page-reader', password: 'page-secret', https_port: 8443, verify_tls: false },
    influxdb: { token: 'page-token', scheme: 'https', port: 8087, verify_tls: false },
    ipmi: { username: 'page-reader', password: 'page-secret', port: 6623, privilege: 'operator' },
    redfish: { username: 'page-reader', password: 'page-secret', port: 8443, verify_tls: false },
    winrm: { username: 'page-reader', password: 'page-secret', port: 5985, scheme: 'http', certValidation: false, transport: 'ntlm' },
    config_file: { username: 'page-reader', password: 'page-secret', port: 2222 },
    network_config_file: { username: 'page-reader', password: 'page-secret', port: 2323, transport_protocol: 'telnet', enable_password: 'page-enable' },
  };
  const result = credentials[form];
  if (entry.model_id === 'mssql') result.database = 'app';
  if (entry.model_id === 'iris') result.namespace = 'APP';
  if (entry.model_id === 'couchbase') result.bucket = 'sample';
  if (entry.model_id === 'azure') Object.assign(result, { tenant_id: 'tenant-test', subscription_id: 'subscription-test' });
  if (entry.model_id === 'openstack') Object.assign(result, { user_domain_name: 'Internal', project_id: 'project-test' });
  if (entry.model_id === 'nacos') result.scheme = 'https';
  if (entry.model_id === 'smartx') Object.assign(result, { source: 'LDAP', verify_tls: true });
  if (entry.model_id === 'azure') { delete result.port; delete result.verify_tls; }
  if (entry.model_id === 'manageone') Object.assign(result, { region: 'region-1', api_version: '8.2.0' });
  if (entry.model_id === 'fusioncompute') result.user_type = '1';
  return result;
}

it.each(entries.filter((entry) => entry.binding))('$id 页面手动与已有凭据生成可回放的创建、编辑请求', async (entry) => {
  const formKind = (entry.id === 'pc' ? 'winrm' : entry.id === 'config_file' ? 'config_file' : getCredentialDescriptor(entry)?.formKind) as keyof typeof components;
  const Component = components[formKind];
  expect(Component).toBeTruthy();
  const modelItem = { ...entry, credential_category: entry.binding!.split('/')[0], credential_type_keys: [entry.binding!.split('/')[1]], credential_schema: schema };
  state.target = { inst_uuid: '63e4a531-b6bb-43cc-9eae-8eb8a09f795e', model_id: entry.model_id, inst_name: 'page-target',
    ip_addr: '192.0.2.10', endpoint: 'platform.example.com', management_address: 'platform.example.com', brand: 'Cisco' };
  for (const source of ['inline', 'vault'] as const) {
    state.values = {};
    state.saved = null;
    state.rules.clear();
    await act(async () => { render(<Component onClose={() => {}} modelItem={modelItem} selectedNode={{ id: entry.id } as never} />); });
    const raw = { ...credentialFor(formKind, entry), credential_source: source };
    if (source === 'vault') Object.assign(raw, { vault_credential_id: 'test-vault', vault_type_key: entry.binding!.split('/')[1] });
    Object.assign(state.values, { credentialPool: [raw], taskName: `page-${entry.id}`, timeout: entry.id === 'pc' ? 120 : 600,
      accessPointId: 'test-node', instUuid: state.target.inst_uuid, organization: [1], cleanupStrategy: 'no_cleanup',
      configName: 'running-config', commands: 'show version', configFilePath: '/etc/hosts', osType: 'windows' });
    for (const rule of state.rules.get('credentialPool') || []) await rule.validator?.({}, [raw]);
    const create = JSON.parse(JSON.stringify(state.format!(state.values))) as Values;
    const pool = (Array.isArray(create.credential) ? create.credential : [create.credential]) as CredentialPoolItem[];
    expect(pool[0].credential_source).toBe(source);
    if (source === 'vault') {
      expect(pool[0].vault_credential_id).toBe('test-vault');
      expect(JSON.stringify(pool)).not.toMatch(/page-secret|page-token|page-auth|page-priv/);
    }
    cleanup();
    const masked = pool.map((item) => {
      const result = { ...item, credential_id: 'test-candidate', credential_version: 3 };
      for (const key of ['password', 'accessSecret', 'token', 'authkey', 'privkey', 'community', 'enable_password']) {
        if (result[key]) result[key] = '******';
      }
      return result;
    });
    state.values = {};
    state.saved = { ...create, credential: masked, name: create.name, taskName: create.name,
      instUuid: state.target.inst_uuid, cycle: 'cycle', intervalValue: 30 };
    await act(async () => { render(<Component onClose={() => {}} modelItem={modelItem} selectedNode={{ id: entry.id } as never} editId={99} />); });
    const edit = JSON.parse(JSON.stringify(state.format!(state.values))) as Values;
    artifacts.push({ id: entry.id, formKind, binding: entry.binding, source, raw, create, edit });
    cleanup();
  }
});
