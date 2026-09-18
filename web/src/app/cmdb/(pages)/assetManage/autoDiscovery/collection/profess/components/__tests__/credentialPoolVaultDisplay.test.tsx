import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import CredentialPoolEditor, { type CredentialPoolEditorProps } from '../credentialPoolEditor';
import type { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback || _key }),
}));
vi.mock('@/components/credential-picker', () => ({
  default: ({ type, value, sshAuthMethod, onChange }: { type?: string; value?: string; sshAuthMethod?: string; onChange?: (id: string) => void }) => <div data-testid="picker" data-type={type} data-value={value} data-auth-method={sshAuthMethod}><button onClick={() => onChange?.('selected-credential')}>凭据选择</button></div>,
}));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: () => undefined, removeListener: () => undefined,
      addEventListener: () => undefined, removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

afterEach(cleanup);

it.each<{ shape: CredentialPoolEditorProps['credentialShape']; type: string; extras: CredentialPoolItem }>([
  { shape: 'network_config_file', type: 'ssh', extras: { port: 23, transport_protocol: 'telnet', enable_password: 'task-extra-secret' } },
  { shape: 'sql', type: 'sql', extras: { port: 3307, database: 'orders', namespace: 'USER', bucket: 'inventory' } },
  { shape: 'snmp', type: 'snmp', extras: { snmp_port: 1161 } },
  { shape: 'vm', type: 'platform_api', extras: { port: 8443, ssl: true } },
  { shape: 'cloud', type: 'access_key', extras: { regionId: 'cn-test-1', projectId: 'test-project' } },
  { shape: 'influxdb', type: 'api_token', extras: { port: 8087, scheme: 'https', verify_tls: false } },
  { shape: 'winrm', type: 'winrm', extras: { port: 5986, scheme: 'https', certValidation: true } },
])('$shape 切换、选用和编辑额外字段后仍保留任务参数', ({ shape, type, extras }) => {
  const onChange = vi.fn();
  function Editor() {
    const [value, setValue] = React.useState<CredentialPoolItem[]>([{ ...extras, username: 'manual-user', password: 'manual-secret' }]);
    return <CredentialPoolEditor credentialShape={shape} vaultCategory="test" vaultTypeKeys={[type]}
      showDatabase value={value} onChange={(next) => { setValue(next); onChange(next); }} />;
  }
  render(<Editor />);
  expect(screen.queryByTestId('picker')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '使用已有凭据' }));
  expect(onChange.mock.lastCall?.[0][0]).toMatchObject({ ...extras, credential_source: 'vault', vault_type_key: type });
  expect(onChange.mock.lastCall?.[0][0].password).toBeUndefined();
  fireEvent.click(screen.getByRole('button', { name: '凭据选择' }));
  expect(onChange.mock.lastCall?.[0][0]).toMatchObject({ ...extras, vault_credential_id: 'selected-credential' });
  if (shape === 'network_config_file') {
    fireEvent.change(screen.getByDisplayValue('task-extra-secret'), { target: { value: 'updated-task-extra' } });
  }
  fireEvent.click(screen.getByRole('button', { name: '改用手动录入' }));
  expect(onChange.mock.lastCall?.[0][0]).toMatchObject({
    ...extras, ...(shape === 'network_config_file' ? { enable_password: 'updated-task-extra' } : {}), credential_source: 'inline',
  });
  expect(onChange.mock.lastCall?.[0][0].vault_credential_id).toBeUndefined();
  expect(screen.queryByTestId('picker')).toBeNull();
});

it('云平台已有凭据不展示端口，区域与手动录入一样查询后下拉选择', () => {
  const onRefresh = vi.fn();
  render(<CredentialPoolEditor
    credentialShape="cloud"
    vaultCategory="cloud"
    vaultTypeKeys={['access_key']}
    cloudRegionOptions={[{ label: '华北1', value: 'cn-north-1' }]}
    onCloudRegionRefresh={onRefresh}
    value={[{
      credential_source: 'vault', vault_type_key: 'access_key', vault_credential_id: 'crd-aliyun',
      regionId: 'cn-north-1', regionName: '华北1',
    }]}
  />);
  expect(screen.queryByText('端口')).toBeNull();
  expect(screen.queryByRole('spinbutton')).toBeNull();
  expect(screen.getByText('区域')).toBeTruthy();
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(screen.getByRole('combobox')).toBeTruthy();
  expect(screen.getByText('华北1')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'common.refresh' }));
  expect(onRefresh).toHaveBeenCalled();
});

it('华为云已有凭据仍可填写项目 ID，区域同样为下拉', () => {
  render(<CredentialPoolEditor
    credentialShape="cloud"
    vaultCategory="cloud"
    vaultTypeKeys={['access_key']}
    cloudRegionOptions={[{ label: '华北-北京一', value: 'cn-north-1' }]}
    cloudCredentialLabels={{ accessKey: 'AK', accessSecret: 'SK', projectId: '项目 ID' }}
    value={[{
      credential_source: 'vault', vault_type_key: 'access_key', vault_credential_id: 'crd-hw',
      projectId: 'proj-1', regionId: 'cn-north-1',
    }]}
  />);
  expect(screen.queryByText('端口')).toBeNull();
  expect(screen.getByText('项目 ID')).toBeTruthy();
  expect(screen.getByDisplayValue('proj-1')).toBeTruthy();
  expect(screen.getByRole('combobox')).toBeTruthy();
});

it('已有 SNMP 凭据的额外表单只展示动态端口', () => {
  render(<CredentialPoolEditor
    credentialShape="snmp"
    vaultCategory="network"
    vaultTypeKeys={['snmp']}
    value={[{
      credential_source: 'vault', vault_type_key: 'snmp', vault_credential_id: 'crd-snmp-1',
      version: 'v2', snmp_port: 1161, community: 'stale-page-secret',
    }]}
  />);
  expect(screen.getByText('端口')).toBeTruthy();
  expect(screen.getByRole('spinbutton')).toHaveProperty('value', '1161');
  expect(screen.queryByText('版本')).toBeNull();
  expect(screen.queryByText('stale-page-secret')).toBeNull();
  expect(screen.queryByText('crd-snmp-1')).toBeNull();
});

it('网络配置使用平台账户时仍可填写额外特权密码', () => {
  const { container } = render(<CredentialPoolEditor
    credentialShape="network_config_file" collectModelId="network_config_file"
    vaultCategory="network" vaultTypeKeys={['platform_api']}
    value={[{ credential_source: 'vault', vault_type_key: 'platform_api', vault_credential_id: 'platform-1',
      transport_protocol: 'ssh', port: 22 }]}
  />);
  expect(screen.getByText('特权密码')).toBeTruthy();
  expect(container.querySelector('input[type="password"]')).toBeTruthy();
});

it.each(['inline', 'vault'] as const)('SQL 原始可选参数在 %s 模式保留显示', (source) => {
  const { container } = render(<CredentialPoolEditor
    credentialShape="sql" collectModelId="iris" vaultCategory="database" vaultTypeKeys={['sql']}
    value={[{ credential_source: source, vault_type_key: 'sql', vault_credential_id: 'database-id',
      user: 'db-user', namespace: 'CUSTOM_NAMESPACE', bucket: 'inventory-bucket', port: 1972 }]}
  />);
  const values = Array.from(container.querySelectorAll('input')).map((input) => input.value);
  expect(values).toContain('CUSTOM_NAMESPACE');
  expect(values).toContain('inventory-bucket');
});


it.each(['sql', undefined])('旧 JOB 引用（类型 %s）可回显并主动更换 SSH', (oldType) => {
  const onChange = vi.fn();
  render(<CredentialPoolEditor credentialShape="ssh" vaultCategory="database" vaultTypeKeys={['ssh']}
    editMode onChange={onChange} value={[{ credential_source: 'vault', vault_type_key: oldType,
      vault_credential_id: 'old-sql-id', port: 2222 }]} />);
  expect(screen.getByTestId('picker').getAttribute('data-type')).toBe('sql');
  expect(screen.getByTestId('picker').getAttribute('data-value')).toBe('old-sql-id');
  fireEvent.click(screen.getByRole('button', { name: '改用 SSH 凭据' }));
  expect(onChange.mock.lastCall?.[0][0]).toMatchObject({ vault_type_key: 'ssh', port: 2222 });
  expect(onChange.mock.lastCall?.[0][0].vault_credential_id).toBeUndefined();
});
it('新 JOB 已有凭据只查询 SSH 类型', () => {
  render(<CredentialPoolEditor credentialShape="ssh" vaultCategory="middleware" vaultTypeKeys={['ssh']}
    value={[{ credential_source: 'vault', port: 22 }]} />);
  expect(screen.getByTestId('picker').getAttribute('data-type')).toBe('ssh');
  expect(screen.queryByRole('button', { name: '改用 SSH 凭据' })).toBeNull();
});
it('PC macOS 不套用旧 JOB 用户名密码兼容', () => {
  render(<CredentialPoolEditor credentialShape="macos_ssh" vaultCategory="host" vaultTypeKeys={['ssh']}
    editMode value={[{ credential_source: 'vault', vault_credential_id: 'mac-id', port: 22 }]} />);
  expect(screen.getByTestId('picker').getAttribute('data-type')).toBe('ssh');
});

it('网络配置已有凭据查询 SSH 类型，并保留连接协议、端口及特权密码', () => {
  render(<CredentialPoolEditor credentialShape="network_config_file" collectModelId="network_config_file"
    vaultCategory="network" vaultTypeKeys={['ssh']}
    value={[{ credential_source: 'vault', transport_protocol: 'telnet', port: 23 }]} />);
  expect(screen.getByTestId('picker').getAttribute('data-type')).toBe('ssh');
  expect(screen.getByTestId('picker').getAttribute('data-auth-method')).toBeNull();
  expect(screen.queryByText('仅支持 SSH 密码凭据，可用于 SSH 或 Telnet 登录；特权密码在下方填写。')).toBeNull();
  expect(screen.getByText('连接协议')).toBeTruthy();
  expect(screen.getByText('特权密码')).toBeTruthy();
  expect(screen.getByRole('spinbutton')).toHaveProperty('value', '23');
});

it('网络配置切到已有凭据时补齐连接协议，不按 SSH/Telnet 拆凭据类型', () => {
  const onChange = vi.fn();
  function Editor() {
    const [value, setValue] = React.useState<CredentialPoolItem[]>([{ port: 22 }]);
    return <CredentialPoolEditor credentialShape="network_config_file" vaultCategory="network" vaultTypeKeys={['ssh']}
      value={value} onChange={(next) => { setValue(next); onChange(next); }} />;
  }
  render(<Editor />);
  fireEvent.click(screen.getByRole('button', { name: '使用已有凭据' }));
  expect(onChange.mock.lastCall?.[0][0]).toMatchObject({
    credential_source: 'vault', vault_type_key: 'ssh', transport_protocol: 'ssh', port: 22,
  });
  expect(screen.getByTestId('picker').getAttribute('data-type')).toBe('ssh');
  expect(screen.getByText('连接协议')).toBeTruthy();
  expect(screen.queryByText('仅支持 SSH 密码凭据，可用于 SSH 或 Telnet 登录；特权密码在下方填写。')).toBeNull();
});
it.each(['platform_api', undefined])('网络配置旧平台引用 %s 支持主动换选 SSH', (oldType) => {
  const onChange = vi.fn();
  render(<CredentialPoolEditor credentialShape="network_config_file" vaultCategory="network" vaultTypeKeys={['ssh']}
    onChange={onChange} value={[{ credential_source: 'vault', vault_type_key: oldType,
      vault_credential_id: 'old-platform-id', port: 23, transport_protocol: 'telnet', enable_password: 'extra-secret' }]} />);
  expect(screen.getByTestId('picker').getAttribute('data-type')).toBe('platform_api');
  fireEvent.click(screen.getByRole('button', { name: '改用 SSH 凭据' }));
  expect(onChange.mock.lastCall?.[0][0]).toMatchObject({ vault_type_key: 'ssh', port: 23,
    transport_protocol: 'telnet', enable_password: 'extra-secret' });
  expect(onChange.mock.lastCall?.[0][0].vault_credential_id).toBeUndefined();
});
