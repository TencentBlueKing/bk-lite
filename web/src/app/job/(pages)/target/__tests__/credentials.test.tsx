import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Target } from '@/app/job/types';
import type { CredentialPickerProps } from '@/components/credential-picker';
import TargetPage from '../page';

const job = vi.hoisted(() => ({
  getTargetList: vi.fn(),
  createTarget: vi.fn(),
  updateTarget: vi.fn(),
  testTargetConnection: vi.fn(),
  testSavedTargetConnection: vi.fn(),
}));

vi.mock('@/app/job/api', () => ({ default: () => job }));
vi.mock('@/context/userInfo', () => ({ useUserInfoContext: () => ({ selectedGroup: { id: '4' }, userId: '1' }) }));
vi.mock('@/hooks/usePermissions', () => ({ default: () => ({ hasPermission: () => true }) }));
vi.mock('@/utils/request', () => ({ default: () => ({ isLoading: false }) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (id: string) => id }) }));
vi.mock('@/app/node-manager/api/useCloudRegionApi', () => ({
  default: () => ({ getCloudList: async () => [{ id: 2, name: 'Region A' }] }),
}));
vi.mock('@/components/top-section', () => ({ default: () => null }));
vi.mock('@/components/search-action-bar', () => ({
  default: ({ actions }: { actions: React.ReactNode }) => actions,
}));
vi.mock('@/components/permission', () => ({
  default: ({ children }: React.PropsWithChildren) => children,
}));
vi.mock('@/components/operate-modal', () => ({
  default: ({ open, children, footer }: React.PropsWithChildren<{ open: boolean; footer: React.ReactNode }>) => (
    <div hidden={!open}>{children}{footer}</div>
  ),
}));
vi.mock('@/components/custom-table', () => ({
  default: ({ columns, dataSource }: {
    columns: { key: string; render?: (_: unknown, row: Target) => React.ReactNode }[];
    dataSource: Target[];
  }) => dataSource.map((row) => (
    <div key={row.id}>
      {columns.find((column) => column.key === 'credential')?.render?.(undefined, row)}
      {columns.find((column) => column.key === 'action')?.render?.(undefined, row)}
    </div>
  )),
}));
vi.mock('@/components/group-tree-select', () => ({
  default: ({ onChange }: { onChange?: (ids: number[]) => void }) => (
    <button type="button" onClick={() => onChange?.([4])}>select team</button>
  ),
}));
vi.mock('@/components/credential-picker', () => ({
  default: ({ value, onChange, type, category, boundOption, manualOption }: CredentialPickerProps) => (
    <select aria-label={`${category}/${type}`} value={value || ''} onChange={(e) => onChange?.(e.target.value)}>
      <option value={manualOption?.value}>{manualOption?.label}</option>
      {boundOption && <option value={boundOption.credentialId} disabled={boundOption.unavailable}>{boundOption.name}</option>}
      <option value={`new-${type}`}>new {type}</option>
    </select>
  ),
}));

const target: Target = {
  id: 1, name: 'Target A', ip: '192.0.2.5', os_type: 'linux', os_type_display: 'Linux',
  driver: 'ansible', driver_display: 'Ansible', cloud_region_id: 2, node_id: '',
  source: 'manual', source_display: '', source_id: '', team: [4], team_name: ['A'],
  credential_source: 'credential', credential_source_display: '', credential_id: 'bound',
  credential_name: 'Linux account', credential_available: true,
  ssh_credential_type: 'password', ssh_credential_type_display: '', ssh_port: 2222, ssh_user: '',
  ssh_key_file: null, ssh_key_file_name: '', has_ssh_key: false, has_ssh_password: false,
  has_winrm_password: false, winrm_port: 5986, winrm_scheme: 'https', winrm_scheme_display: 'HTTPS',
  winrm_user: '', winrm_cert_validation: false, winrm_transport: 'kerberos', created_by: '', updated_by: '',
};

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  window.matchMedia = (query) => ({
    matches: false, media: query, onchange: null, addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false,
  });
});

beforeEach(() => {
  vi.resetAllMocks();
  job.getTargetList.mockResolvedValue({ items: [], count: 0 });
  job.testTargetConnection.mockResolvedValue({ success: true });
  job.testSavedTargetConnection.mockResolvedValue({ success: true });
});
afterEach(cleanup);

async function edit(overrides: Partial<Target> = {}) {
  job.getTargetList.mockResolvedValue({ items: [{ ...target, ...overrides }], count: 1 });
  render(<TargetPage />);
  fireEvent.click(await screen.findByText('job.editRule'));
}

describe('Job target credential binding', () => {
  it('saves and tests a new vault target using exactly the selected binding and connection settings', async () => {
    render(<TargetPage />);
    fireEvent.click(screen.getByText('common.new'));
    fireEvent.change(screen.getByPlaceholderText('job.targetNamePlaceholder'), { target: { value: 'New target' } });
    fireEvent.change(screen.getByPlaceholderText('job.ipPlaceholder'), { target: { value: '192.0.2.7' } });
    fireEvent.mouseDown(screen.getByLabelText('job.cloudRegion'));
    fireEvent.click(await screen.findByText('Region A'));
    fireEvent.click(screen.getByText('select team'));
    fireEvent.change(screen.getByPlaceholderText('job.sshPasswordPlaceholder'), { target: { value: 'unsaved-manual-password' } });
    fireEvent.change(screen.getByLabelText('host/ssh'), { target: { value: 'new-ssh' } });
    expect(screen.queryByPlaceholderText('job.sshPasswordPlaceholder')).toBeNull();
    fireEvent.click(screen.getByText('job.testConnection'));
    await waitFor(() => expect(job.testTargetConnection).toHaveBeenCalledOnce());
    const expected = {
      credential_source: 'credential', credential_id: 'new-ssh', ip: '192.0.2.7',
      cloud_region_id: '2', os_type: 'linux', driver: 'ansible', ssh_port: '22',
    };
    expect(Object.fromEntries(job.testTargetConnection.mock.calls[0][0])).toEqual(expected);
    fireEvent.click(screen.getByText('job.save'));
    await waitFor(() => expect(job.createTarget).toHaveBeenCalledOnce());
    expect(Object.fromEntries(job.createTarget.mock.calls[0][0])).toEqual({ ...expected, name: 'New target', team: '[4]' });
  });

  it('tests the edited binding and discards the SSH choice when switching to WinRM', async () => {
    await edit();
    expect((screen.getByLabelText('host/ssh') as HTMLSelectElement).value).toBe('bound');
    fireEvent.click(screen.getByRole('radio', { name: 'job.windows' }));
    const winrm = await screen.findByLabelText('host/winrm');
    expect((winrm as HTMLSelectElement).value).toBe('manual');
    fireEvent.change(winrm, { target: { value: 'new-winrm' } });
    fireEvent.click(screen.getByText('job.testConnection'));
    await waitFor(() => expect(job.testSavedTargetConnection).toHaveBeenCalledOnce());
    const [id, body] = job.testSavedTargetConnection.mock.calls[0];
    expect(id).toBe(1);
    expect(Object.fromEntries(body)).toEqual({
      credential_id: 'new-winrm', credential_source: 'credential', driver: 'ansible',
      ip: target.ip, cloud_region_id: '2', os_type: 'windows', winrm_scheme: 'https',
      winrm_transport: 'kerberos', winrm_cert_validation: 'false', winrm_port: '5986',
    });
  });

  it('requires replacement of an unavailable binding; switching to manual requires a new password', async () => {
    await edit({ credential_available: false, credential_name: null });
    expect(screen.getAllByText('job.credentialUnavailable').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText('job.save'));
    await waitFor(() => expect(document.querySelector('.ant-form-item-has-error')).toBeTruthy());
    expect(job.updateTarget).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('host/ssh'), { target: { value: 'manual' } });
    fireEvent.click(screen.getByText('job.testConnection'));
    await screen.findByText('job.sshPasswordPlaceholder');
    expect(job.testSavedTargetConnection).not.toHaveBeenCalled();
    fireEvent.change(screen.getByPlaceholderText('job.sshPasswordPlaceholder'), { target: { value: 'typed-again' } });
    fireEvent.click(screen.getByText('job.save'));
    await waitFor(() => expect(job.updateTarget).toHaveBeenCalledOnce());
    const body = job.updateTarget.mock.calls[0][1];
    expect(body.get('credential_source')).toBe('manual');
    expect(body.get('credential_id')).toBe('');
    expect(body.get('ssh_password')).toBe('typed-again');
  });

  it('keeps the original manual private key until a replacement is uploaded', async () => {
    await edit({
      credential_source: 'manual', credential_id: '', credential_name: null, credential_available: null,
      ssh_credential_type: 'key', has_ssh_key: true, ssh_key_file_name: 'old.pem', ssh_user: 'operator',
    });
    fireEvent.click(screen.getByText('job.testConnection'));
    await waitFor(() => expect(job.testSavedTargetConnection).toHaveBeenCalledOnce());
    expect(job.testSavedTargetConnection.mock.calls[0][1].get('ssh_key_file')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'job.replaceKey' }));
    const upload = document.querySelector<HTMLInputElement>('input[type=file]');
    if (!upload) throw new Error('Expected a private key upload input');
    fireEvent.change(upload, { target: { files: [new File(['test fixture'], 'replacement.pem')] } });
    await screen.findByText('replacement.pem');
    fireEvent.click(screen.getByText('job.save'));
    await waitFor(() => expect(job.updateTarget).toHaveBeenCalledOnce());
    const body: FormData = job.updateTarget.mock.calls[0][1];
    const file = body.get('ssh_key_file');
    expect(file instanceof File && file.name).toBe('replacement.pem');
    expect(body.has('ssh_password')).toBe(false);
  });

  it('continues using the stored manual WinRM password without sending a placeholder', async () => {
    await edit({
      os_type: 'windows', credential_source: 'manual', credential_id: '', credential_name: null,
      credential_available: null, winrm_user: 'local-user', has_winrm_password: true,
    });
    fireEvent.click(screen.getByText('job.testConnection'));
    await waitFor(() => expect(job.testSavedTargetConnection).toHaveBeenCalledOnce());
    const body = job.testSavedTargetConnection.mock.calls[0][1];
    expect(body.get('winrm_user')).toBe('local-user');
    expect(body.get('winrm_password')).toBeNull();
    expect(body.get('credential_source')).toBe('manual');
  });
});
