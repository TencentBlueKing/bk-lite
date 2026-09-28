import React, { createRef } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import type { ModelItem } from '@/app/cmdb/types/autoDiscovery';
import BaseTaskForm, { BaseTaskRef } from '../baseTask';
import HostTask from '../hostTask';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import type { CollectTask, TreeNode } from '@/app/cmdb/types/autoDiscovery';

const api = vi.hoisted(() => ({
  getCollectDetail: vi.fn(),
  updateCollect: vi.fn<(id: string, payload: Record<string, unknown>) => Promise<void>>().mockResolvedValue(undefined),
  createCollect: vi.fn<(payload: Record<string, unknown>) => Promise<void>>().mockResolvedValue(undefined),
  searchInstances: vi.fn(async (params: { page: number }) => ({
    insts: [{ inst_uuid: `uuid-${params.page}`, inst_name: `host-${params.page}`, ip_addr: `10.0.0.${params.page}`, cloud: 2 }], count: 20,
  })),
  getCollectNodes: vi.fn(async () => ({ nodes: [{ id: 'proxy-1', name: 'Proxy', node_type: 'container', cloud_region: 2 }, { id: 'proxy-2', name: 'Proxy 2', node_type: 'container', cloud_region: 2 }] })),
}));
vi.mock('@/app/cmdb/api', () => ({ useInstanceApi: () => api, useCollectApi: () => api, useModelApi: () => ({}) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/cmdb/context/common', () => ({ useCmdbUserList: () => [] }));
vi.mock('@/context/userInfo', () => ({ useUserInfoContext: () => ({ selectedGroup: { id: 1 } }) }));
vi.mock('@/app/cmdb/store', async () => ({ useAssetManageStore: (await import('@/app/cmdb/store/useAssetManage')).default }));
vi.mock('@/context/locale', () => ({ useLocale: () => ({ locale: 'zh' }) }));
vi.mock('../credentialPoolEditor', () => ({ default: () => null }));
vi.mock('@/hooks/useUnsavedConfirm', () => ({ default: () => (_dirty: boolean, close: () => void) => close() }));
vi.mock('@/app/cmdb/(pages)/assetData/list/fieldModal', () => ({ default: React.forwardRef(function FieldModalStub() { return null; }) }));
vi.mock('@/components/group-tree-select', () => ({
  default: ({ onChange }: { onChange?: (value: number[]) => void }) =>
    <button type="button" onClick={() => onChange?.([2])}>Change organization</button>,
}));
vi.mock('@/components/custom-table', async () => ({ default: (await import('antd')).Table }));

beforeAll(() => {
  window.matchMedia = vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }));
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
});
afterEach(() => { cleanup(); useAssetManageStore.setState({ copyTaskData: null, editingId: null, scan_cycle_type: null }); vi.clearAllMocks(); });

function renderForm(supportsHostDiscovery = true) {
  const ref = createRef<BaseTaskRef>();
  render(<Form initialValues={{ organization: [1], accessPointId: 'proxy-1' }}>
    <BaseTaskForm ref={ref} modelItem={{ model_id: 'nginx', task_type: 'middleware', type: 'job', supports_host_discovery: supportsHostDiscovery } as ModelItem}
      onClose={() => undefined} showAdvanced={false} />
  </Form>);
  return ref;
}

it('从主机发现时跨页保留选择，翻页查询仍限定 host、任务组织和云区域', async () => {
  const ref = renderForm();
  fireEvent.click(screen.getByLabelText('Collection.chooseHost'));
  const select = screen.getByRole('button', { name: 'common.select' });
  await waitFor(() => expect((select as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(select);
  const dialog = await screen.findByRole('dialog');
  await within(dialog).findByText('host-1');
  fireEvent.click(within(dialog).getAllByRole('checkbox')[1]);
  fireEvent.click(within(dialog).getByTitle('2'));
  await within(dialog).findByText('host-2');
  fireEvent.click(within(dialog).getAllByRole('checkbox')[1]);
  fireEvent.click(within(dialog).getByRole('button', { name: 'Collection.confirm' }));
  expect(ref.current?.selectedData.map(row => row.inst_uuid)).toEqual(['uuid-1', 'uuid-2']);
  expect(api.searchInstances).toHaveBeenLastCalledWith(expect.objectContaining({
    model_id: 'host', page: 2,
    query_list: [{ field: 'cloud', type: 'int=', value: 2 }, { field: 'organization', type: 'list[]', value: [1] }],
  }));
  fireEvent.click(screen.getByRole('button', { name: 'common.select' }));
  const reopened = await screen.findByRole('dialog');
  await within(reopened).findByText('host-1');
  fireEvent.click(within(reopened).getAllByRole('checkbox')[1]);
  fireEvent.click(within(reopened).getByRole('button', { name: 'Collection.confirm' }));
  expect(ref.current?.selectedData.map(row => row.inst_uuid)).toEqual(['uuid-2']);
  fireEvent.click(screen.getByLabelText('Collection.chooseIp'));
  expect(ref.current?.selectedData).toEqual([]);
});

it('目录未开放主机发现时保留原选择方式', async () => {
  renderForm(false);
  expect(screen.queryByLabelText('Collection.chooseHost')).toBeNull();
  expect(screen.getByLabelText('Collection.chooseIp')).toBeTruthy();
  await act(async () => {});
});


const savedHostTask = {
  id: 42, name: 'Nginx discovery', model_id: 'nginx', driver_type: 'job', task_type: 'middleware',
  team: [1], timeout: 60, cycle_value_type: 'cycle', cycle_value: '30', ip_range: '',
  access_point: [{ id: 'proxy-1' }], credential: [],
  instances: [{ inst_uuid: 'uuid-1', inst_name: 'saved-host', ip_addr: '10.0.0.1', cloud: 2 }],
  params: { target_source: 'host', target_cloud_region_id: 2, ip_precheck: true, custom_option: 'kept' },
} as unknown as CollectTask;

it.each(['edit', 'copy'])('%s 主机任务回显来源，保存仅提交 UUID 并保留其他参数', async (mode) => {
  api.getCollectDetail.mockResolvedValue(savedHostTask);
  if (mode === 'copy') useAssetManageStore.setState({ copyTaskData: savedHostTask });
  render(<HostTask onClose={() => undefined}
    editId={mode === 'edit' ? 42 : undefined}
    selectedNode={{ id: 'middleware' } as TreeNode}
    modelItem={{ name: 'Nginx', model_id: 'nginx', task_type: 'middleware', type: 'job', supports_host_discovery: true } as ModelItem}
  />);
  await screen.findByText('saved-host');
  expect((screen.getByLabelText('Collection.chooseHost') as HTMLInputElement).checked).toBe(true);
  fireEvent.change(screen.getByLabelText('Collection.taskNameLabel'), { target: { value: 'Saved discovery' } });
  await waitFor(() => expect(api.getCollectNodes).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: 'Collection.confirm' }));
  const save = mode === 'edit' ? api.updateCollect : api.createCollect;
  await waitFor(() => expect(save).toHaveBeenCalled());
  const payload = mode === 'edit' ? api.updateCollect.mock.calls[0][1] : api.createCollect.mock.calls[0][0];
  expect(payload).toMatchObject({
    model_id: 'nginx', ip_range: '', instances: [{ inst_uuid: 'uuid-1' }],
    params: { target_source: 'host', ip_precheck: true, custom_option: 'kept' },
  });
  expect(payload.instances).toEqual([{ inst_uuid: 'uuid-1' }]);
});

it('变更组织后清空已保存的来源主机', async () => {
  const ref = renderForm();
  await act(async () => {
    ref.current?.initCollectionType(savedHostTask.instances, 'host');
  });
  expect(ref.current?.selectedData).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: 'Change organization' }));
  expect(ref.current?.selectedData).toEqual([]);
});


it('变更接入点后即使云区域相同也清空主机', async () => {
  const ref = renderForm();
  await act(async () => {
    ref.current?.initCollectionType(savedHostTask.instances, 'host');
  });
  fireEvent.mouseDown(screen.getByLabelText('Collection.accessPoint'));
  fireEvent.click(await screen.findByText('Proxy 2'));
  expect(ref.current?.selectedData).toEqual([]);
});
