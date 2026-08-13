import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmSloPage from '../page';

const api = {
  createSlo: vi.fn(),
  deleteSlo: vi.fn(),
  getServices: vi.fn(),
  getSlos: vi.fn(),
  setSloEnabled: vi.fn(),
  updateSlo: vi.fn(),
};

vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: true,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));

  api.getServices.mockResolvedValue([
    {
      id: 'service-checkout',
      namespace: 'apm-demo-shop',
      name: 'demo-storefront',
      environment_views: [{ environment: 'local' }],
    },
  ]);
  api.getSlos.mockResolvedValue([
    {
      id: 'slo-checkout',
      name: '结算接口 500ms 时延目标',
      service_id: 'service-checkout',
      environment: 'local',
      endpoint: 'POST /api/checkout',
      sli_type: 'latency_p95',
      objective: '95.00',
      evaluation_window: 'rolling7d',
      is_enabled: true,
      service_namespace: 'apm-demo-shop',
      service_name: 'demo-storefront',
      latency_threshold_ms: 500,
      current_rate: 78.74,
      budget_remaining: 0,
      data_state: 'available',
    },
  ]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM SLO 列表布局', () => {
  it('按列语义对齐表头与正文，并保留自适应主信息列', async () => {
    const { container } = render(<ApmSloPage />);

    expect(await screen.findByText('结算接口 500ms 时延目标')).not.toBeNull();
    expect(screen.getByText('1 项')).not.toBeNull();

    const currentHeader = screen.getByRole('columnheader', { name: /当前表现.*达标率/ });
    const enabledHeader = screen.getByRole('columnheader', { name: /启用.*状态/ });
    const actionHeader = screen.getByRole('columnheader', { name: /操作.*编辑 · 删除/ });
    expect(getComputedStyle(currentHeader).textAlign).toBe('right');
    expect(getComputedStyle(enabledHeader).textAlign).toBe('center');
    expect(getComputedStyle(actionHeader).textAlign).toBe('right');
    expect(getComputedStyle(screen.getByText('78.74%').closest('td')!)).toMatchObject({
      textAlign: 'right',
    });

    const explicitColumnWidths = Array.from(container.querySelectorAll('col'))
      .map((column) => column.getAttribute('style'))
      .filter(Boolean);
    expect(explicitColumnWidths).not.toContain('width: 220px;');
    expect(explicitColumnWidths).not.toContain('width: 210px;');
  }, 10_000);
});
