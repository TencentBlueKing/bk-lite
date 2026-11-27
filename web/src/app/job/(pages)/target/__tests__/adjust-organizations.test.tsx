import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import AdjustOrganizationsModal from '@/app/job/components/adjust-organizations-modal';

const adjust = vi.hoisted(() => vi.fn());
vi.mock('antd', async (importOriginal) => ({
  ...await importOriginal<typeof import('antd')>(),
  message: { success: vi.fn() },
}));
vi.mock('@/app/job/api', () => ({ default: () => ({ adjustOrganizations: adjust }) }));
vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ flatGroups: [{ id: 2, name: '研发' }, { id: 3, name: '运维' }] }),
}));
vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('@/components/group-tree-select', () => ({
  default: ({ onChange }: { onChange: (ids: number[]) => void }) => (
    <select aria-label="组织" defaultValue="" onChange={e => onChange([Number(e.target.value)])}>
      <option value="">选择组织</option><option value="2">研发</option><option value="3">运维</option>
    </select>
  ),
}));

const ids = [10, 20, 30];
const preview = {
  changed: 1, unchanged: 1, blocked: [{ id: 30, name: 'db-single' }],
  preview_token: 'confirmed-selection', groups: [
    { before: [2, 3], after: [3], count: 1 }, { before: [3], after: [3], count: 1 },
    { before: [2], after: [], count: 1 },
  ],
};
const key = (suffix: string) => 'job.targetOrganizations.' + suffix;
const pick = (value: number) => fireEvent.change(screen.getByRole('combobox', { name: '组织' }), { target: { value } });

beforeAll(() => {
  window.matchMedia = (query) => ({
    matches: false, media: query, onchange: null, addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false,
  });
});
beforeEach(() => adjust.mockReset());
afterEach(cleanup);

describe('作业资源批量调整组织', () => {
  it.each(['target', 'script', 'playbook'] as const)('%s 移除最后一个组织时须显式排除，确认使用同类资源和同一份预览', async resource => {
    adjust.mockResolvedValue(preview);
    const onSuccess = vi.fn();
    render(<AdjustOrganizationsModal resource={resource} ids={ids} onCancel={vi.fn()} onSuccess={onSuccess} />);
    fireEvent.click(screen.getByText(key('remove')));
    pick(2);
    await waitFor(() => expect(adjust).toHaveBeenCalledWith(resource, { ids, operation: 'remove', organization: 2 }));
    const exclude = await screen.findByRole('checkbox');
    const confirm = screen.getByRole('button', { name: key('applyRemove') }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.click(exclude);
    fireEvent.click(confirm);
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(adjust).toHaveBeenLastCalledWith(resource, {
      ids, operation: 'remove', organization: 2, exclude_blocked: true, preview_token: preview.preview_token,
    });
  });

  it('服务端拒绝过期预览后，重新预览并显式确认才提交', async () => {
    const onSuccess = vi.fn();
    const valid = { ...preview, blocked: [], preview_token: 'first' };
    const refreshed = { ...valid, changed: 2, preview_token: 'fresh' };
    adjust.mockResolvedValueOnce(valid).mockRejectedValueOnce(new Error('stale preview'))
      .mockResolvedValueOnce(refreshed).mockResolvedValueOnce(refreshed);
    render(<AdjustOrganizationsModal resource="target" ids={ids} onCancel={vi.fn()} onSuccess={onSuccess} />);
    pick(2);
    fireEvent.click(await screen.findByRole('button', { name: /job\.targetOrganizations\.applyAdd/ }));
    const retry = await screen.findByRole('button', { name: key('retry') });
    expect(onSuccess).not.toHaveBeenCalled();
    fireEvent.click(retry);
    const confirm = await screen.findByRole('button', { name: /job\.targetOrganizations\.applyAdd/ });
    expect(adjust.mock.lastCall?.[1]).not.toHaveProperty('preview_token');
    fireEvent.click(confirm);
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(adjust.mock.lastCall?.[1]).toMatchObject({ preview_token: 'fresh' });
  });

  it('后返回的旧组织预览不能覆盖当前组织的预览', async () => {
    let finishFirst!: (value: typeof preview) => void;
    adjust.mockReturnValueOnce(new Promise<typeof preview>(resolve => { finishFirst = resolve; }));
    const current = { ...preview, changed: 3, unchanged: 0, blocked: [], preview_token: 'current' };
    adjust.mockResolvedValue(current);
    render(<AdjustOrganizationsModal resource="target" ids={ids} onCancel={vi.fn()} onSuccess={vi.fn()} />);
    pick(2);
    await waitFor(() => expect(adjust).toHaveBeenCalledTimes(1));
    pick(3);
    await waitFor(() => expect(adjust).toHaveBeenCalledTimes(2));
    await act(async () => finishFirst(preview));
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: /job\.targetOrganizations\.applyAdd/ }));
    await waitFor(() => expect(adjust).toHaveBeenCalledTimes(3));
    expect(adjust.mock.lastCall?.[1]).toMatchObject({ ids, organization: 3, operation: 'add', preview_token: 'current' });
  });
});
