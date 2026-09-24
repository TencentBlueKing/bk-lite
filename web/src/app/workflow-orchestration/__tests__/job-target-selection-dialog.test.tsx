import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { vi } from 'vitest';

import { JobTargetSelectionDialog } from '../components/job-target-selection-dialog';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('@/utils/request', () => ({
  default: () => ({ get: mocks.get }),
}));

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
      if (url.includes('source=job_mgmt')) return Promise.resolve({ source: 'job_mgmt', count: 1, items: [jobTarget] });
      return Promise.resolve({ source: 'job_mgmt', count: 0, items: [] });
    });
  });

  it('仅从作业平台选择主机并回填稳定目标引用', async () => {
    const confirm = vi.fn();
    render(<App><JobTargetSelectionDialog open value={[]} onCancel={vi.fn()} onConfirm={confirm} /></App>);

    expect(await screen.findByText('选择作业平台主机')).not.toBeNull();
    expect(screen.queryByRole('tab', { name: /节点管理/ })).toBeNull();

    const row = (await screen.findByText(jobTarget.name)).closest('tr');
    expect(row).not.toBeNull();
    expect(mocks.get).toHaveBeenCalledWith(
      expect.stringContaining('source=job_mgmt'),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    fireEvent.click(within(row!).getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '确认选择' }));

    await waitFor(() => expect(confirm).toHaveBeenCalledWith(
      ['manual:11'],
      [expect.objectContaining({ id: 'manual:11', name: 'job-linux-01' })],
    ));
  });
});
