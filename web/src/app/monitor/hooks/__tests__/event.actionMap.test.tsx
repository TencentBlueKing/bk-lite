import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import zh from '@/app/monitor/locales/zh.json';
import { useEventActionMap } from '../event';

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
  it('用语言包展示触发、升级、认领、分派、恢复和关闭', () => {
    const { result } = renderHook(() => useEventActionMap());
    expect(result.current).toEqual({
      triggered: '触发',
      escalated: '级别升级',
      claimed: '认领',
      assigned: '分派',
      recovered: '自动恢复',
      closed: '关闭'
    });
  });
});
