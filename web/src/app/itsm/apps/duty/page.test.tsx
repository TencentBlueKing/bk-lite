import { renderItsm as render } from '../../test-utils';
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react';
import dayjs from 'dayjs';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import DutyPage from './page';

const api = vi.hoisted(() => ({
  ready: true, listResources: vi.fn(), createResource: vi.fn(), updateResource: vi.fn(), deleteResource: vi.fn(),
}));

vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/context/userInfo', async () => {
  const { createContext } = await import('react');
  return { UserInfoContext: createContext({ username: 'alice', loading: false }) };
});
vi.mock('../../components/user-selector', () => ({
  UserSelector: ({ ariaLabel, value, onChange }: { ariaLabel: string; value: string[]; onChange: (value: string[]) => void }) => (
    <input aria-label={ariaLabel} value={value.join(',')} onChange={event => onChange(event.target.value.split(','))} />
  ),
}));

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }),
});

afterEach(cleanup);
beforeEach(() => vi.resetAllMocks());

const today = dayjs().format('YYYY-MM-DD');
const shifts = [
  { id: 1, name: '一线白班', day: today, members: ['alice'] },
  { id: 2, name: '平台夜班', day: today, members: ['bob'] },
];

function openPage(canEdit = true) {
  api.listResources.mockResolvedValue({ items: shifts, can_add: canEdit, can_edit: canEdit, can_delete: canEdit });
  render(<DutyPage />);
}

it('我的值班使用登录人过滤，月历与列表同步', async () => {
  openPage(false);
  await screen.findByText('一线白班');
  fireEvent.click(screen.getByRole('tab', { name: '我的值班' }));
  expect(screen.getByText('一线白班')).toBeTruthy();
  expect(screen.queryByText('平台夜班')).toBeNull();
  fireEvent.click(screen.getByText('月历', { exact: true }));
  fireEvent.click(screen.getByRole('button', { name: `${today}，1 个排班` }));
  const detail = within(screen.getByRole('region', { name: `${today} 值班` }));
  expect(detail.getByText('一线白班')).toBeTruthy();
  expect(detail.getByText('alice')).toBeTruthy();
  expect(detail.queryByText('平台夜班')).toBeNull();
  expect(detail.queryByRole('button', { name: '新建当日排班' })).toBeNull();
  expect(detail.queryByRole('button', { name: '一线白班' })).toBeNull();
});

it('管理员从月历选中日期后新建排班，保存当天日期', async () => {
  openPage();
  await screen.findByText('平台夜班');
  fireEvent.click(screen.getByText('月历', { exact: true }));
  const date = dayjs().date(5).format('YYYY-MM-DD');
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`^${date}，`) }));
  const detail = within(screen.getByRole('region', { name: `${date} 值班` }));
  fireEvent.click(detail.getByRole('button', { name: '新建当日排班' }));
  expect(screen.getByLabelText('值班日期')).toHaveProperty('value', date);
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '值守' } });
  fireEvent.change(screen.getByLabelText('值班人员'), { target: { value: 'alice,bob' } });
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(api.createResource).toHaveBeenCalledWith('duties', { name: '值守', day: date, members: ['alice', 'bob'] }));
});

it('值班月历加载排班时不会同时显示空状态', async () => {
  api.listResources.mockReturnValue(new Promise(() => undefined));
  render(<DutyPage />);
  fireEvent.click(screen.getByText('月历', { exact: true }));
  expect(screen.getByRole('status', { name: '正在加载排班' })).toBeTruthy();
  expect(screen.queryByText('当日暂无排班')).toBeNull();
});
