import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import zh from '@/app/alarm/locales/zh.json';
import ShieldStrategy from '../page';

const api = vi.hoisted(() => ({
  getShieldList: vi.fn(),
  deleteShield: vi.fn(),
  patchShield: vi.fn(),
  createShield: vi.fn(),
  updateShield: vi.fn(),
}));

function translate(key: string): string {
  const value = key.split('.').reduce<unknown>((current, part) => {
    if (current && typeof current === 'object' && part in current) {
      return (current as Record<string, unknown>)[part];
    }
    return undefined;
  }, zh);
  return typeof value === 'string' ? value : key;
}

vi.mock('@/app/alarm/api/settings', () => ({ useSettingApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: translate }) }));
vi.mock('@/app/alarm/context/common', () => ({
  useCommon: () => ({
    userList: [
      { id: '1', username: 'alice', display_name: '陈永' },
      { id: '2', username: 'bob', display_name: '鲍勃' },
    ],
  }),
}));
vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({ convertToLocalizedTime: (value: string) => value }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  default: () => ({ hasPermission: () => true }),
}));

const rows = [
  {
    id: 1,
    name: 'fdsda',
    created_by: 'alice',
    created_at: '2026-10-01T02:00:00Z',
    is_active: true,
    runtime_status: 'outside',
    match_type: 'all',
    match_rules: [],
    suppression_time: {
      type: 'month',
      week_month: [1, 3, 6, 5, 2, 28, 30, 31, 26, 24],
      start_time: '02:00:00',
      end_time: '23:59:59',
    },
  },
  {
    id: 2,
    name: 'assa',
    created_by: 'alice',
    created_at: '2026-10-01T02:00:00Z',
    is_active: true,
    runtime_status: 'outside',
    match_type: 'all',
    match_rules: [],
    suppression_time: {
      type: 'week',
      week_month: [5, 3],
      start_time: '03:00:02',
      end_time: '23:59:59',
    },
  },
  {
    id: 3,
    name: 'ces2',
    created_by: 'bob',
    created_at: '2026-10-01T02:00:00Z',
    is_active: true,
    runtime_status: 'shielding',
    match_type: 'all',
    match_rules: [],
    suppression_time: {
      type: 'one',
      start_time: '2026-10-21 00:00:00',
      end_time: '2026-11-21 23:59:59',
    },
  },
  {
    id: 4,
    name: '测试11',
    created_by: 'alice',
    created_at: '2026-10-01T02:00:00Z',
    is_active: true,
    runtime_status: 'shielding',
    match_type: 'all',
    match_rules: [],
    suppression_time: { type: 'day', start_time: '00:00:00', end_time: '23:57:59' },
  },
  {
    id: 5,
    name: '已停用',
    created_by: 'carol',
    created_at: '2026-10-01T02:00:00Z',
    is_active: false,
    runtime_status: 'disabled',
    match_type: 'all',
    match_rules: [],
    suppression_time: { type: 'day', start_time: '00:00:00', end_time: '23:59:59' },
  },
  {
    id: 6,
    name: '未开始策略',
    created_by: 'bob',
    created_at: '2026-10-01T02:00:00Z',
    is_active: true,
    runtime_status: 'not_started',
    match_type: 'all',
    match_rules: [],
    suppression_time: {
      type: 'one',
      start_time: '2026-12-01 00:00:00',
      end_time: '2026-12-02 00:00:00',
    },
  },
  {
    id: 7,
    name: '已结束策略',
    created_by: 'bob',
    created_at: '2026-10-01T02:00:00Z',
    is_active: true,
    runtime_status: 'expired',
    match_type: 'all',
    match_rules: [],
    suppression_time: {
      type: 'one',
      start_time: '2020-01-01 00:00:00',
      end_time: '2020-01-02 00:00:00',
    },
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  api.getShieldList.mockResolvedValue({ items: rows, count: rows.length });
});

afterEach(cleanup);

describe('屏蔽策略列表和详情', () => {
  it('把创建人、启用状态、当前结果和生效时间分开显示', async () => {
    render(<ShieldStrategy />);

    expect(await screen.findByText('每月 1日,2日,3日,5日,6日,24日,26日,28日,30日,31日 02:00:00 - 23:59:59')).toBeTruthy();
    expect(screen.getByText('每周 星期三,星期五 03:00:02 - 23:59:59')).toBeTruthy();
    expect(screen.getByText('单次 2026-10-21 00:00:00-2026-11-21 23:59:59')).toBeTruthy();
    expect(screen.getByText('每天 00:00:00 - 23:57:59')).toBeTruthy();
    expect(screen.getAllByText('陈永(alice)').length).toBeGreaterThan(0);
    expect(screen.getAllByText('鲍勃(bob)').length).toBeGreaterThan(0);
    expect(screen.getByText('carol')).toBeTruthy();
    expect(screen.getAllByText('屏蔽中').length).toBeGreaterThan(0);
    expect(screen.getAllByText('时段外').length).toBeGreaterThan(0);
    expect(screen.getAllByText('未启用').length).toBeGreaterThan(0);
    expect(screen.getAllByText('已启用').length).toBeGreaterThan(0);
    expect(screen.getByText('未开始')).toBeTruthy();
    expect(screen.getByText('已结束')).toBeTruthy();
    expect(screen.queryByText('生效')).toBeNull();
  });

  it('编辑抽屉展示这条策略的创建人和当前结果', async () => {
    render(<ShieldStrategy />);
    await screen.findByText('ces2');

    const row = screen.getByText('ces2').closest('tr');
    expect(row).toBeTruthy();
    fireEvent.click(within(row as HTMLElement).getByText('common.edit'));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('编辑屏蔽策略 - ces2')).toBeTruthy();
    expect(within(dialog).getByText('创建人')).toBeTruthy();
    expect(within(dialog).getByText('鲍勃(bob)')).toBeTruthy();
    expect(within(dialog).getByText('当前结果')).toBeTruthy();
    expect(within(dialog).getByText('屏蔽中')).toBeTruthy();
    expect(within(dialog).getByText('启用状态')).toBeTruthy();
    expect(within(dialog).getByText('已启用')).toBeTruthy();
  });
});
