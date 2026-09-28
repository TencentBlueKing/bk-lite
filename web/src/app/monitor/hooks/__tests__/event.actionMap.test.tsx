import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import zh from '@/app/monitor/locales/zh.json';
import { useEventActionMap, useGroupMethodList } from '../event';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const value = key
        .split('.')
        .reduce<unknown>((current, segment) => {
          if (!current || typeof current !== 'object') return undefined;
          return (current as Record<string, unknown>)[segment];
        }, zh);
      return typeof value === 'string' ? value : key;
    }
  })
}));

describe('useEventActionMap', () => {
  it('用语言包展示触发、升级、认领、分派、转派、恢复和关闭', () => {
    const { result } = renderHook(() => useEventActionMap());
    expect(result.current).toEqual({
      triggered: '触发',
      escalated: '级别升级',
      claimed: '认领',
      assigned: '分派',
      reassigned: '转派',
      recovered: '自动恢复',
      closed: '关闭'
    });
  });
});

describe('useGroupMethodList', () => {
  it('分组聚合的计数项走语言包，不回显 key', () => {
    const { result } = renderHook(() => useGroupMethodList());
    expect(result.current.find((item) => item.value === 'count')).toMatchObject({
      label: '计数',
      title: '表示选中时间范围内，所有维度的数量。\n count函数用于计数匹配的时间序列数量，适用于统计有多少个维度符合条件，例如有多少个活跃的实例或端口。'
    });
  });
});
