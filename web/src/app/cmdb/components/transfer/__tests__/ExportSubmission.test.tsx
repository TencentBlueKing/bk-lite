import React, { createRef } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import ExportModal from '@/app/cmdb/(pages)/assetData/components/exportModal';
import type { ExportModalRef } from '@/app/cmdb/types/assetData';

const exportFile = vi.hoisted(() => vi.fn());
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/cmdb/api', () => ({ useModelApi: () => ({ getModelAssociations: async () => [] }) }));
vi.mock('@/app/cmdb/api/transfer', () => ({ useTransferApi: () => ({ exportFile }) }));
Object.defineProperty(window, 'matchMedia', { value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }), writable: true });

it('submits current-page UUIDs and fields, then reports acceptance rather than downloading', async () => {
  const accepted = { task_id: 'one', status: 'queued', type: 'export' };
  exportFile.mockResolvedValue(accepted);
  const onSubmitted = vi.fn();
  const ref = createRef<ExportModalRef>();
  render(<ExportModal ref={ref} models={[]} userList={[]} assoTypes={[]} canSubmit onSubmitted={onSubmitted} />);
  await act(async () => {
    ref.current?.showModal({ title: '导出', modelId: 'host', selectedKeys: ['other-row'], exportType: 'currentPage',
      columns: [{ key: 'inst_name', title: '实例名', dataIndex: 'inst_name' }], tableData: [{ inst_uuid: 'page-row' }] });
  });
  fireEvent.click(screen.getByText('Transfer.submitExport'));
  await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith(accepted));
  expect(exportFile.mock.calls[0][0]).toEqual({ model_id: 'host', scope: 'currentPage', inst_uuids: ['page-row'], attr_list: ['inst_name'], association_list: [] });
  expect(exportFile.mock.calls[0][1]).toMatch(/^[0-9a-f-]{36}$/);
});

it('opens task records immediately while export acceptance is still pending', async () => {
  let accept!: (value: { task_id: string; status: string; type: string }) => void;
  exportFile.mockImplementation(() => new Promise(resolve => { accept = resolve; }));
  const onSubmitStart = vi.fn();
  const onSubmitted = vi.fn();
  const ref = createRef<ExportModalRef>();
  render(<ExportModal ref={ref} models={[]} userList={[]} assoTypes={[]} canSubmit onSubmitStart={onSubmitStart} onSubmitted={onSubmitted} />);
  await act(async () => {
    ref.current?.showModal({ title: '导出', modelId: 'host', selectedKeys: [], exportType: 'all',
      columns: [{ key: 'inst_name', title: '实例名', dataIndex: 'inst_name' }], tableData: [] });
  });
  fireEvent.click(screen.getByText('Transfer.submitExport'));
  expect(onSubmitStart).toHaveBeenCalledTimes(1);
  expect(onSubmitted).not.toHaveBeenCalled();
  const task = { task_id: 'pending', status: 'queued', type: 'export' };
  await act(async () => accept(task));
  expect(onSubmitted).toHaveBeenCalledWith(task);
});

it('restores export settings after a failed submission and reuses the request key', async () => {
  exportFile.mockClear();
  exportFile.mockRejectedValueOnce(new Error('提交失败'));
  exportFile.mockResolvedValueOnce({ task_id: 'retry', status: 'queued', type: 'export' });
  const onSubmitted = vi.fn();
  const ref = createRef<ExportModalRef>();
  render(<ExportModal ref={ref} models={[]} userList={[]} assoTypes={[]} canSubmit onSubmitStart={vi.fn()} onSubmitted={onSubmitted} />);
  await act(async () => {
    ref.current?.showModal({ title: '导出配置', modelId: 'host', selectedKeys: ['selected-host'], exportType: 'selected',
      columns: [{ key: 'inst_name', title: '实例名', dataIndex: 'inst_name' }] });
  });
  await act(async () => fireEvent.click(screen.getByText('Transfer.submitExport')));
  const retryButton = screen.getByText('Transfer.submitExport').closest('button')!;
  expect(retryButton.disabled).toBe(false);
  expect(screen.getByText('导出配置').closest('[role="dialog"]')?.getAttribute('style')).not.toContain('display: none');
  expect(onSubmitted).not.toHaveBeenCalled();
  fireEvent.click(retryButton);
  await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1));
  expect(exportFile.mock.calls[1]).toEqual(exportFile.mock.calls[0]);
});
