import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TableDataItem } from '@/app/log/types';
import zh from '@/app/log/locales/zh.json';
import AlertHandlerActions from '../alertHandlerActions';

vi.mock('@/components/permission', () => ({
  default: ({ children }: React.PropsWithChildren) => <>{children}</>
}));

vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ userId: '7', username: 'testuser' })
}));

vi.mock('@/app/log/api', () => ({
  default: () => ({ getAllUsers: vi.fn().mockResolvedValue([]) })
}));

vi.mock('@/app/log/api/event', () => ({
  default: () => ({
    patchLogAlert: vi.fn(),
    claimLogAlert: vi.fn(),
    assignLogAlert: vi.fn(),
    reassignLogAlert: vi.fn()
  })
}));

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

afterEach(cleanup);

const renderActions = (record: Partial<TableDataItem>) =>
  render(
    <AlertHandlerActions
      record={
        {
          id: 'alert-1',
          status: 'new',
          handlers: [],
          permission: ['Operate'],
          ...record
        } as TableDataItem
      }
      closeText="关闭"
      onSuccess={vi.fn()}
    />
  );

describe('日志告警处理人按钮', () => {
  it('空处理人的活跃告警展示认领、分派和关闭，不展示转派', () => {
    renderActions({ handlers: [] });
    expect(screen.getByRole('button', { name: /^认\s*领$/ })).not.toBeNull();
    expect(screen.getByRole('button', { name: /^分\s*派$/ })).not.toBeNull();
    expect(screen.getByRole('button', { name: /^关\s*闭$/ })).not.toBeNull();
    expect(screen.queryByRole('button', { name: /^转\s*派$/ })).toBeNull();
  });

  it('当前处理人的活跃告警展示转派和关闭，不展示认领和分派', () => {
    renderActions({ handlers: [7], handlers_display: ['Bob(bob)'] });
    expect(screen.getByRole('button', { name: /^转\s*派$/ })).not.toBeNull();
    expect(screen.getByRole('button', { name: /^关\s*闭$/ })).not.toBeNull();
    expect(screen.queryByRole('button', { name: /^认\s*领$/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^分\s*派$/ })).toBeNull();
  });

  it('不是当前处理人时不展示关闭', () => {
    renderActions({ handlers: [8], handlers_display: ['Alice(alice)'] });
    expect(screen.queryByRole('button', { name: /^关\s*闭$/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^转\s*派$/ })).toBeNull();
  });
});
