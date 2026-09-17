import React, { useEffect } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { PublicWidgetPane } from '../index';
import { buildAlarmApmReplayWindow } from '@/app/alarm/utils/alarmApmReplayWindow';

const received = vi.hoisted(() => ({
  props: null as null | Record<string, string>,
}));

function SpyApmWidget(props: Record<string, string>) {
  useEffect(() => {
    received.props = props;
  }, [props]);
  return (
    <div data-testid="spy-apm">
      {props.startedAt || 'missing'}|{props.endedAt || 'missing'}
    </div>
  );
}

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
  received.props = null;
});

describe('PublicWidgetPane APM query window forwarding', () => {
  it('forwards host replay window into identifier widget props', async () => {
    const window = buildAlarmApmReplayWindow(
      {
        first_event_time: '2026-09-17 10:49:34',
        last_event_time: '2026-09-17 10:50:34',
        created_at: '2026-09-15 18:32:52',
      },
      new Date('2026-09-17T06:04:38.486Z'),
      'Asia/Shanghai',
    );
    expect(window).toEqual({
      startedAt: '2026-09-17T02:19:34.000Z',
      endedAt: '2026-09-17T03:19:34.000Z',
    });

    const loadWidget = vi.fn(async () => ({ default: SpyApmWidget }));
    render(
      <PublicWidgetPane
        active
        loadWidget={loadWidget}
        identifier="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001"
        identifierProp="serviceId"
        startedAt={window?.startedAt}
        endedAt={window?.endedAt}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('spy-apm').textContent).toBe(
        '2026-09-17T02:19:34.000Z|2026-09-17T03:19:34.000Z',
      );
    });
    expect(received.props).toMatchObject({
      serviceId: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001',
      startedAt: '2026-09-17T02:19:34.000Z',
      endedAt: '2026-09-17T03:19:34.000Z',
    });
  });

  it('omits time props when host has no replay window (widget falls back)', async () => {
    const loadWidget = vi.fn(async () => ({ default: SpyApmWidget }));
    render(
      <PublicWidgetPane
        active
        loadWidget={loadWidget}
        identifier="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001"
        identifierProp="serviceId"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('spy-apm').textContent).toBe('missing|missing');
    });
    expect(received.props).toEqual({
      serviceId: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001',
    });
  });
});
