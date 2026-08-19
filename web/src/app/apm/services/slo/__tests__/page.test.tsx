import React from 'react';
import { cleanup, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
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
  it('统一左对齐表头与正文，并保留自适应主信息列', async () => {
    const { container } = renderWithApmIntl(<ApmSloPage />);

    expect(await screen.findByText('结算接口 500ms 时延目标')).not.toBeNull();
    expect(screen.getByText('1 项')).not.toBeNull();

    const currentHeader = screen.getByRole('columnheader', { name: /当前表现.*达标率/ });
    const enabledHeader = screen.getByRole('columnheader', { name: /启用.*状态/ });
    const actionHeader = screen.getByRole('columnheader', { name: '操作' });
    expect(getComputedStyle(currentHeader).textAlign).toBe('left');
    expect(getComputedStyle(enabledHeader).textAlign).toBe('left');
    expect(getComputedStyle(actionHeader).textAlign).toBe('left');
    expect(actionHeader.classList.contains('ant-table-cell-fix-right')).toBe(true);
    expect(screen.getByRole('button', { name: '编辑' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '删除' })).not.toBeNull();
    expect(getComputedStyle(screen.getByText('78.74%').closest('td')!)).toMatchObject({
      textAlign: 'left',
    });

    const explicitColumnWidths = Array.from(container.querySelectorAll('col'))
      .map((column) => column.getAttribute('style'))
      .filter(Boolean);
    expect(explicitColumnWidths).not.toContain('width: 220px;');
    expect(explicitColumnWidths).not.toContain('width: 210px;');
  }, 10_000);

  it('编辑归档服务的 SLO 时展示服务名称而不是 UUID', async () => {
    const user = userEvent.setup();
    api.getServices.mockResolvedValue([]);
    api.getSlos.mockResolvedValue([
      {
        id: 'slo-legacy',
        name: '旧服务可用性',
        service_id: 'service-archived',
        environment: 'legacy',
        endpoint: '',
        sli_type: 'availability',
        objective: '99.90',
        evaluation_window: 'rolling30d',
        is_enabled: false,
        service_namespace: 'legacy-shop',
        service_name: 'legacy-api',
        latency_threshold_ms: null,
        current_rate: null,
        budget_remaining: null,
        data_state: 'no_data',
      },
    ]);

    renderWithApmIntl(<ApmSloPage />);
    await user.click(await screen.findByRole('button', { name: '编辑' }));

    expect(await screen.findByText('legacy-shop / legacy-api（已归档）')).not.toBeNull();
    expect(screen.queryByText('service-archived')).toBeNull();
    expect(api.getServices).toHaveBeenCalledWith({ include_archived: true });
  });
});
