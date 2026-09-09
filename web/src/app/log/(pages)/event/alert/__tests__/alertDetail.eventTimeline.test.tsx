import React, { createRef } from 'react';
import { cleanup, render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ModalRef } from '@/app/log/types';
import zh from '@/app/log/locales/zh.json';
import AlertDetail from '../alertDetail';

vi.mock('@/components/operate-drawer', () => ({
  default: ({
    children,
    visible
  }: {
    children: React.ReactNode;
    visible?: boolean;
  }) => (visible ? <div>{children}</div> : null)
}));

vi.mock('../information', () => ({
  default: () => <div data-testid="information-panel" />
}));

vi.mock('../eventDetail', () => ({
  default: () => <div data-testid="event-detail" />
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({ convertToLocalizedTime: (value: string) => value })
}));

vi.mock('@/components/heat-map', () => ({
  default: ({ data }: { data: Array<{ id?: string }> }) => (
    <div data-testid="event-heat-map">{data.map((item) => item.id).join(',')}</div>
  ),
  getHeatMapCellColor: () => '#000'
}));

const geEventList = vi.fn();
const getEventRaw = vi.fn().mockResolvedValue({});

vi.mock('@/app/log/api/event', () => ({
  default: () => ({
    geEventList,
    getEventRaw
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

beforeEach(() => {
  geEventList.mockResolvedValue([
    {
      id: 'hit-1',
      action: '',
      event_time: '2026-01-01 12:00:00',
      content: 'error keyword'
    },
    {
      id: 'claimed-1',
      action: 'claimed',
      event_time: '2026-01-01 12:05:00',
      content: 'sre 认领，处理人变为 sre'
    },
    {
      id: 'assigned-1',
      action: 'assigned',
      event_time: '2026-01-01 12:06:00',
      content: 'sre 分派给 bob'
    },
    {
      id: 'closed-1',
      action: 'closed',
      event_time: '2026-01-01 12:10:00',
      content: 'sre 关闭'
    }
  ]);
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn()
  });
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('日志告警详情事件序列', () => {
  it(
    '展示认领/分派/关闭动作，且热力图与详情不把生命周期当命中',
    async () => {
      const ref = createRef<ModalRef>();
      render(
      <AlertDetail ref={ref} objects={[]} userList={[]} onSuccess={vi.fn()} />
      );

      await act(async () => {
        ref.current?.showModal({
          type: 'alert',
          title: '告警详情',
          form: {
            id: 'a1',
            status: 'new',
            level: 'warning',
            content: 'error keyword',
            alert_type: 'keyword',
            updated_at: '2026-01-01 12:00:00'
          }
        });
      });

      await userEvent.click(screen.getByText('事件'));
      await waitFor(() => {
        expect(geEventList).toHaveBeenCalled();
      });

      expect(await screen.findByText('认领')).toBeTruthy();
      expect(screen.getByText('分派')).toBeTruthy();
      expect(screen.getByText('关闭')).toBeTruthy();
      expect(screen.getByText('error keyword')).toBeTruthy();
      expect(screen.getByTestId('event-heat-map').textContent).toBe('hit-1');
      expect(screen.getAllByRole('button', { name: '详情' })).toHaveLength(1);
    },
    15000
  );
});
