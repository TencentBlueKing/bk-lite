import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { vi } from 'vitest';

import { JobTargetSelectionDialog } from '../components/job-target-selection-dialog';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('@/utils/request', () => ({
  default: () => ({ get: mocks.get }),
}));

const nodeTarget = {
  id: 'node:n1',
  source: 'node_mgmt' as const,
  source_id: 'n1',
  name: 'node-linux-01',
  ip: '10.0.0.8',
  operating_system: 'linux' as const,
  connected: true,
};

const jobTarget = {
  id: 'manual:11',
  source: 'job_mgmt' as const,
  source_id: 11,
  name: 'job-linux-01',
  ip: '10.10.41.101',
  operating_system: 'linux' as const,
  connected: true,
};

describe('作业目标选择弹窗', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() })),
    });
  });

  beforeEach(() => {
    mocks.get.mockReset();
    mocks.get.mockImplementation((url: string) => {
      if (url.includes('source=node_mgmt')) return Promise.resolve({ source: 'node_mgmt', count: 1, items: [nodeTarget] });
      if (url.includes('source=job_mgmt')) return Promise.resolve({ source: 'job_mgmt', count: 1, items: [jobTarget] });
      return Promise.resolve({ source: 'job_mgmt', count: 0, items: [] });
    });
  });

  it('可从节点管理选择主机并回填稳定目标引用', async () => {
    const confirm = vi.fn();
    render(<App><JobTargetSelectionDialog open value={[]} onCancel={vi.fn()} onConfirm={confirm} /></App>);

    expect(await screen.findByText('选择主机 · 目标主机')).not.toBeNull();
    expect(screen.getByRole('tab', { name: /节点管理/ })).not.toBeNull();
    expect(screen.getByRole('tab', { name: /作业平台/ })).not.toBeNull();
    expect(screen.getByText(/节点管理与作业平台不能混选/)).not.toBeNull();

    const row = (await screen.findByText(nodeTarget.name)).closest('tr');
    expect(row).not.toBeNull();
    expect(mocks.get).toHaveBeenCalledWith(
      expect.stringContaining('source=node_mgmt'),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    fireEvent.click(within(row!).getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '确认选择' }));

    await waitFor(() => expect(confirm).toHaveBeenCalledWith(
      ['node:n1'],
      [expect.objectContaining({ id: 'node:n1', name: 'node-linux-01' })],
    ));
  });

  it('切换来源会清空已选，并回填作业平台目标', async () => {
    const confirm = vi.fn();
    render(<App><JobTargetSelectionDialog open value={['node:n1']} onCancel={vi.fn()} onConfirm={confirm} /></App>);

    expect(await screen.findByText(/已选 1 台/)).not.toBeNull();
    fireEvent.click(screen.getByRole('tab', { name: '作业平台' }));

    await waitFor(() => {
      expect(screen.getByText(/已选 0 台/)).not.toBeNull();
    });
    expect(screen.getByRole('button', { name: '确认选择' })).toHaveProperty('disabled', true);

    const row = (await screen.findByText(jobTarget.name)).closest('tr');
    expect(row).not.toBeNull();
    fireEvent.click(within(row!).getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '确认选择' }));

    await waitFor(() => expect(confirm).toHaveBeenCalledWith(
      ['manual:11'],
      [expect.objectContaining({ id: 'manual:11', name: 'job-linux-01' })],
    ));
  });
});
