// @vitest-environment jsdom

import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ClientData } from '@/types/index';

const clientState: {
  clientData: ClientData[];
  loading: boolean;
} = {
  clientData: [],
  loading: true,
};

vi.mock('@/console-layout', () => ({
  useScreenAwareRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/app/system-manager/api/application', () => ({
  useRoleApi: () => ({ deleteApplication: vi.fn() }),
}));

vi.mock('@/context/client', () => ({
  useClientData: () => clientState,
}));

let translate = (id: string, fallback?: string) => fallback ?? id;

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: translate }),
}));

import { applicationListSearchText, useApplicationPage } from '@/app/system-manager/hooks/useApplicationPage';

const monitor: ClientData = {
  id: '1',
  name: 'monitor',
  display_name: 'Monitor',
  description: 'Watch systems',
  url: '/monitor/view',
  is_build_in: true,
  tags: ['tag.monitor'],
};

describe('应用列表跟随上下文数据和当前语言', () => {
  it('数据晚到时补上卡片，语言变化时重算名称且保留原文', () => {
    clientState.clientData = [];
    clientState.loading = true;
    translate = (id: string, fallback?: string) => (
      id === 'apps.monitor' ? '监控中心' : (fallback ?? id)
    );

    const { result, rerender } = renderHook(() => useApplicationPage());

    expect(result.current.loading).toBe(true);
    expect(result.current.dataList).toEqual([]);

    clientState.clientData = [
      monitor,
      { ...monitor, id: '2', name: 'ops-console', display_name: 'Console' },
    ];
    clientState.loading = false;
    rerender();

    expect(result.current.dataList).toHaveLength(1);
    expect(result.current.dataList[0]).toMatchObject({
      name: 'monitor',
      display_name: '监控中心',
      source_display_name: 'Monitor',
      source_description: 'Watch systems',
    });

    translate = (id: string, fallback?: string) => (
      id === 'apps.monitor' ? 'Monitor Center' : (fallback ?? id)
    );
    rerender();

    expect(result.current.dataList[0].display_name).toBe('Monitor Center');
    expect(result.current.dataList[0].source_display_name).toBe('Monitor');
  });

  it('搜索同时匹配当前展示名和应用 id', () => {
    const text = applicationListSearchText({
      id: '1',
      name: 'monitor',
      display_name: '监控中心',
      description: '',
      url: '',
      source_display_name: 'Monitor',
      source_description: '',
      tagList: [],
    }).toLowerCase();

    expect(text.includes('监控中心')).toBe(true);
    expect(text.includes('monitor')).toBe(true);
  });
});
