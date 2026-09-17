import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import CredentialPicker, { CredentialPickerChrome } from '../index';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const pickerApi = vi.hoisted(() => ({
  listSelectableCredentials: vi.fn(async () => [
    { credential_id: 'ssh-password', type: 'ssh', name: 'SSH password account', fields: { auth_method: 'password' } },
    { credential_id: 'ssh-key', type: 'ssh', name: 'SSH private key account', fields: { auth_method: 'key' } },
  ]),
  listSelectableTypes: vi.fn(async () => [{ key: 'ssh', name: 'SSH', categories: ['network'], fields: [] }]),
  createCredential: vi.fn(),
  getCredentialPermissions: vi.fn(async () => []),
}));
vi.mock('../api', () => ({ useCredentialPickerApi: () => pickerApi }));
vi.mock('@/hooks/usePermissions', () => ({ default: () => ({ hasPermission: () => false }) }));

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

it('选择项只显示凭据名称，仍以 credential_id 作为选择值', () => {
  const onChange = vi.fn();
  const options = [{ label: '生产 SNMP', value: 'crd-snmp-1' }];
  const { container } = render(
    <CredentialPickerChrome value="crd-snmp-1" options={options}
      canAdd={false} canView={false} onChange={onChange} />,
  );
  expect(screen.getByText('生产 SNMP')).toBeTruthy();
  expect(container.textContent).not.toContain('crd-snmp-1');
  expect(onChange).not.toHaveBeenCalled();
});

it('失效的凭据 ID 不显示在下拉输入框里', () => {
  const { container } = render(
    <CredentialPickerChrome value="crd-disabled" options={[]}
      canAdd={false} canView={false} />,
  );
  expect(container.textContent).not.toContain('crd-disabled');
});

it.each([undefined, 'password'] as const)('SSH 认证方式筛选 %s 不影响其他调用方', async (sshAuthMethod) => {
  render(<CredentialPicker category="network" type="ssh" sshAuthMethod={sshAuthMethod} />);
  await waitFor(() => expect(pickerApi.listSelectableCredentials).toHaveBeenCalledWith({ category: 'network', type: 'ssh' }));
  fireEvent.mouseDown(screen.getByRole('combobox'));
  expect(await screen.findByText('SSH password account')).toBeTruthy();
  if (sshAuthMethod) expect(screen.queryByText('SSH private key account')).toBeNull();
  else expect(screen.getByText('SSH private key account')).toBeTruthy();
});
