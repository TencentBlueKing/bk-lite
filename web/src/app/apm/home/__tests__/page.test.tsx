import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmHomePage from '../page';
import type { ApmDashboard } from '@/app/apm/types';

const api = {
  getDashboard: vi.fn(),
  isLoading: false,
};

vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('next/link', () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children: React.ReactNode;
    href: string;
    [key: string]: unknown;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const emptyDashboard: ApmDashboard = {
  empty: true,
  window: '1h',
  kpis: { status: 'empty' },
  health: { status: 'empty' },
  slos: { status: 'empty' },
  alerts: { status: 'empty' },
  top_error_rate: { status: 'empty' },
  top_p95: { status: 'empty' },
  releases: { status: 'empty', data: { items: [] } },
};

const loadedDashboard: ApmDashboard = {
  empty: false,
  window: '1h',
  kpis: {
    status: 'ok',
    data: {
      application_count: 2,
      service_count: 5,
      active_alert_count: 1,
      request_rate: 12.5,
      error_request_rate: 0.4,
      p95_ms: 210,
      sparklines: {
        application_count: [1, 2],
        service_count: [3, 5],
        active_alert_count: [0, 1],
        request_rate: [10, 12.5],
        error_request_rate: [0.2, 0.4],
        p95_ms: [180, 210],
      },
    },
  },
  health: {
    status: 'ok',
    data: {
      total: 5,
      buckets: [
        { key: 'healthy', label: '健康', count: 3 },
        { key: 'warning', label: '警告', count: 1 },
        { key: 'critical', label: '严重', count: 1 },
        { key: 'unknown', label: '未知', count: 0 },
      ],
    },
  },
  slos: { status: 'empty', data: { items: [] } },
  alerts: { status: 'empty', data: { items: [] } },
  top_error_rate: { status: 'empty', data: { items: [] } },
  top_p95: { status: 'empty', data: { items: [] } },
  releases: { status: 'empty', data: { items: [] } },
};

const failedAlertsDashboard: ApmDashboard = {
  ...loadedDashboard,
  alerts: { status: 'failed', error: 'alerts down' },
};

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  api.getDashboard.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('ApmHomePage', () => {
  it('shows empty state CTA to integration', async () => {
    api.getDashboard.mockResolvedValue(emptyDashboard);
    render(<ApmHomePage />);

    expect(await screen.findByText('还没有接入任何应用')).not.toBeNull();
    const cta = screen.getByText('前往集成菜单').closest('a');
    expect(cta).not.toBeNull();
    expect(cta?.getAttribute('href')).toBe('/apm/integration/add');
  });

  it('renders KPI labels when data loaded', async () => {
    api.getDashboard.mockResolvedValue(loadedDashboard);
    render(<ApmHomePage />);

    await waitFor(() => expect(screen.getByText('应用数量')).not.toBeNull());
    expect(screen.getByText('服务数量')).not.toBeNull();
    expect(screen.getByText('活跃告警数')).not.toBeNull();
    expect(screen.getByText('请求量')).not.toBeNull();
    expect(screen.getByText('错误请求数')).not.toBeNull();
    expect(screen.getByText('P95 延迟')).not.toBeNull();
  });

  it('shows retry when a section failed', async () => {
    api.getDashboard.mockResolvedValue(failedAlertsDashboard);
    render(<ApmHomePage />);

    await waitFor(() => expect(screen.getByText('实时告警')).not.toBeNull());
    expect(screen.getByText('加载失败，点击重试')).not.toBeNull();

    api.getDashboard.mockResolvedValue(loadedDashboard);
    await userEvent.click(screen.getByText('加载失败，点击重试'));
    await waitFor(() => expect(api.getDashboard).toHaveBeenCalledTimes(2));
  });

  it('always shows releases empty copy', async () => {
    api.getDashboard.mockResolvedValue(loadedDashboard);
    render(<ApmHomePage />);

    expect(await screen.findByText('近 7 天无发布')).not.toBeNull();
  });
});
