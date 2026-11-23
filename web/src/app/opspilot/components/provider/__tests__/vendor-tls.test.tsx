import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import VendorModal from '../vendorModal';
import VendorBasicInfo from '../vendorBasicInfo';
import type { ModelVendor } from '@/app/opspilot/types/provider';

const api = vi.hoisted(() => ({
  fetchVendorDetail: vi.fn(), updateVendor: vi.fn(), testVendorConnection: vi.fn(),
}));
const group = { id: '1' };
const t = (key: string) => key;
vi.mock('@/app/opspilot/api/provider', () => ({ useProviderApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t }) }));
vi.mock('@/context/userInfo', () => ({ useUserInfoContext: () => ({ selectedGroup: group }) }));
vi.mock('@/components/group-tree-select', () => ({ default: () => null }));
vi.mock('@/components/password', () => ({
  default: ({ value, onChange }: { value?: string; onChange: (value: string) => void }) =>
    <input aria-label="API key" value={value ?? ''} onChange={(event) => onChange(event.target.value)} />,
}));
vi.mock('@/components/operate-modal', () => ({
  default: ({ children, footer }: React.PropsWithChildren<{ footer: React.ReactNode }>) => <>{children}{footer}</>,
}));

const vendor: ModelVendor = {
  id: 12, name: 'Private model', vendor_type: 'other', api_base: 'https://model.example',
  team: [1], skip_ssl_verify: true,
};

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addListener: vi.fn(), removeListener: vi.fn() });
  api.fetchVendorDetail.mockResolvedValue(vendor);
  api.testVendorConnection.mockResolvedValue({ success: true });
  api.updateVendor.mockResolvedValue(vendor);
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('starts with verification enabled and saves the selected setting on a new vendor', async () => {
  const save = vi.fn();
  render(<VendorModal visible mode="add" confirmLoading={false} onOk={save} onCancel={vi.fn()} />);
  const toggle = screen.getByRole('switch', { name: 'provider.vendor.skipSslVerify' });
  expect(toggle.getAttribute('aria-checked')).toBe('false');
  fireEvent.click(toggle);
  fireEvent.change(screen.getByLabelText('common.name'), { target: { value: 'Private vendor' } });
  fireEvent.change(screen.getByLabelText('API key'), { target: { value: 'mock-key' } });
  fireEvent.click(screen.getByRole('button', { name: 'provider.vendor.testConnection' }));
  await waitFor(() => expect(api.testVendorConnection).toHaveBeenCalledWith(expect.objectContaining({ skip_ssl_verify: true })));
  fireEvent.click(screen.getByRole('button', { name: 'common.save' }));
  await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ skip_ssl_verify: true })));
});

it.each(['modal', 'detail'])('tests and saves the edited TLS setting from the %s form', async (entry) => {
  const save = vi.fn();
  if (entry === 'modal') {
    render(<VendorModal visible mode="edit" vendor={vendor} confirmLoading={false} onOk={save} onCancel={vi.fn()} />);
  } else {
    render(<VendorBasicInfo vendorId={vendor.id} onUpdated={vi.fn()} />);
  }
  const toggle = await screen.findByRole('switch', { name: 'provider.vendor.skipSslVerify' });
  expect(toggle.getAttribute('aria-checked')).toBe('true');
  fireEvent.click(toggle);
  fireEvent.click(screen.getAllByRole('button', { name: 'provider.vendor.testConnection' })[0]);
  await waitFor(() => expect(api.testVendorConnection).toHaveBeenCalledWith(expect.objectContaining({
    original_id: 12, password_changed: false, skip_ssl_verify: false,
  })));
  fireEvent.click(screen.getByRole('button', { name: 'common.save' }));
  const payload = expect.objectContaining({ skip_ssl_verify: false });
  await waitFor(() => entry === 'modal'
    ? expect(save).toHaveBeenCalledWith(payload)
    : expect(api.updateVendor).toHaveBeenCalledWith(vendor.id, payload));
});
