import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { VmwareDeliveryAssets } from './vmware-delivery-assets';

const getAssets = vi.fn();
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => ({ getTicketVmwareAssets: getAssets }) }));
afterEach(() => { cleanup(); getAssets.mockReset(); });

it('仅在用户查询时加载资产，未匹配的回执可重新核对', async () => {
  const entry = { delivery_id: 'itsm-3-1', hostname: 'vm-test', url: null };
  const url = '/cmdb/assetData/detail/baseInfo?model_id=vmware_vm&inst_uuid=8';
  getAssets.mockResolvedValueOnce({ items: [entry] }).mockResolvedValueOnce({ items: [{ ...entry, url }] });
  render(<VmwareDeliveryAssets ticketId={3} />);
  expect(getAssets).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '查询 CMDB 资产' }));
  expect(await screen.findByText('待关联')).toBeTruthy();
  fireEvent.click(await screen.findByRole('button', { name: '查询 CMDB 资产' }));
  expect((await screen.findByRole('link', { name: 'vm-test' })).getAttribute('href')).toBe(url);
  expect(getAssets.mock.calls).toEqual([[3], [3]]);
});
