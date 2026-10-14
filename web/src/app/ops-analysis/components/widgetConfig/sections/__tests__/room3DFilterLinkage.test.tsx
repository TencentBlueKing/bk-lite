import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import Room3DFilterLinkage from '@/app/ops-analysis/components/widgetConfig/sections/room3DFilterLinkage';
import { ROOM3D_FILTER_ID } from '@/app/ops-analysis/utils/room3DScreenFilter';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';

const translate = (key: string) => {
  const messages: Record<string, string> = {
    'dashboard.room3DFilterName': '机房',
    'dashboard.string': '字符串',
    'dashboard.filterLinked': '已联动',
    'dashboard.filterUnlinked': '未联动',
    'dashboard.filterDisabled': '已停用',
    'dashboard.noUnifiedFilters': '暂无全局筛选项',
  };
  return messages[key] ?? key;
};

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: translate,
  }),
}));

const savedRoom = (
  overrides: Partial<UnifiedFilterDefinition> = {},
): UnifiedFilterDefinition => ({
  id: ROOM3D_FILTER_ID,
  key: 'server_room_id',
  name: '园区机房',
  type: 'string',
  enabled: false,
  order: 1,
  ...overrides,
});

describe('Room3DFilterLinkage', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('shows the room filter linked and keeps the switch on and disabled', () => {
    render(<Room3DFilterLinkage definitions={[savedRoom()]} />);

    expect(screen.getByText('园区机房')).not.toBeNull();
    expect(screen.getByText('已联动')).not.toBeNull();
    const toggle = screen.getByRole('switch');
    expect(toggle.getAttribute('aria-checked')).toBe('true');
    expect(toggle).toHaveProperty('disabled', true);
  });

  it('uses the translated room name when the screen has no saved filter', () => {
    render(<Room3DFilterLinkage definitions={[]} />);

    expect(screen.getByText('机房')).not.toBeNull();
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true');
  });
});