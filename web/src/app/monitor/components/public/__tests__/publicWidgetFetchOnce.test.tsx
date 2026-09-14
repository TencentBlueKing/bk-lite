import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

const apis = vi.hoisted(() => ({
  lookupInstance: vi.fn(async () => ({
    monitor_object: {
      id: 11,
      name: 'Host',
      display_name: '主机',
      instance_id_keys: ['instance_id'],
    },
    instance: {
      instance_id: 'mon-1',
      instance_name: 'web-1',
      instance_id_values: ['web-1'],
      instance_id_keys: ['instance_id'],
    },
  })),
  getInstanceList: vi.fn(async () => ({
    count: 0,
    results: [],
  })),
  getEffectivePlugins: vi.fn(async () => [
    { id: 7, name: 'Host', display_name: '主机' },
  ]),
  getMonitorMetrics: vi.fn(async () => ({
    count: 0,
    items: [],
  })),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/monitor/api', () => ({
  default: () => ({
    lookupInstance: async (...args: unknown[]) => apis.lookupInstance(...args),
    getInstanceList: async (...args: unknown[]) => apis.getInstanceList(...args),
    getEffectivePlugins: async (...args: unknown[]) =>
      apis.getEffectivePlugins(...args),
    getMonitorMetrics: async (...args: unknown[]) => apis.getMonitorMetrics(...args),
  }),
}));

vi.mock('@/app/monitor/(pages)/view/monitorView', () => ({
  default: () => <div data-testid="monitor-view" />,
}));

vi.mock('@/app/monitor/(pages)/view/monitorAlarm', () => ({
  default: ({ objects }: { objects?: Array<{ id?: number; display_name?: string }> }) => (
    <div
      data-testid="monitor-alarm"
      data-objects={JSON.stringify(objects || [])}
    />
  ),
}));

import MonitorViewWidget from '../MonitorViewWidget';
import AlertListWidget from '../AlertListWidget';
import { resetMonitorPublicContextCache } from '../resolveMonitorPublicContext';

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
  resetMonitorPublicContextCache();
  vi.clearAllMocks();
});

async function assertNoRetrigger(getCount: () => number) {
  const settled = getCount();
  await new Promise((resolve) => setTimeout(resolve, 80));
  expect(getCount()).toBe(settled);
}

describe('monitor public widgets fetch once', () => {
  it('does not retrigger monitor view bootstrap when API identities change each render', async () => {
    render(<MonitorViewWidget monitorId="mon-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('monitor-view')).toBeTruthy();
    });
    expect(apis.lookupInstance).toHaveBeenCalledTimes(1);
    expect(apis.getInstanceList).not.toHaveBeenCalled();
    await assertNoRetrigger(() => apis.lookupInstance.mock.calls.length);
  });

  it('does not retrigger alert list bootstrap when API identities change each render', async () => {
    render(<AlertListWidget monitorId="mon-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('monitor-alarm')).toBeTruthy();
    });
    expect(apis.lookupInstance).toHaveBeenCalledTimes(1);
    expect(apis.getMonitorMetrics).toHaveBeenCalledTimes(1);
    expect(apis.getInstanceList).not.toHaveBeenCalled();
    expect(JSON.parse(screen.getByTestId('monitor-alarm').getAttribute('data-objects') || '[]')).toEqual([
      {
        id: 11,
        name: 'Host',
        display_name: '主机',
        type: '',
        description: '',
      },
    ]);
    await assertNoRetrigger(() => apis.lookupInstance.mock.calls.length);
  });

  it('does not rescan monitor objects after remounting the same monitorId', async () => {
    const { unmount } = render(<MonitorViewWidget monitorId="mon-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('monitor-view')).toBeTruthy();
    });
    expect(apis.lookupInstance).toHaveBeenCalledTimes(1);
    unmount();

    render(<MonitorViewWidget monitorId="mon-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('monitor-view')).toBeTruthy();
    });
    expect(apis.lookupInstance).toHaveBeenCalledTimes(1);
    expect(apis.getInstanceList).not.toHaveBeenCalled();
  });
});
