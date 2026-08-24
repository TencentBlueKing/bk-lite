import React from 'react';
import { cleanup, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApmDeploymentsPage from '../page';

const api = {
  getDeployments: vi.fn(),
  getServices: vi.fn(),
  isLoading: false,
};

vi.mock('next/navigation', () => ({
  usePathname: () => '/apm/services/deployments',
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
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
      id: 'svc-1',
      namespace: 'shop',
      name: 'checkout',
      environment_views: [{ environment: 'production' }],
    },
  ]);
  api.getDeployments.mockResolvedValue({
    count: 1,
    items: [
      {
        id: 'dep-1',
        service_id: 'svc-1',
        service_namespace: 'shop',
        service_name: 'checkout',
        environment: 'production',
        version: '1.2.0',
        deployed_at: new Date().toISOString(),
        deployed_by: '',
        status: 'success',
        source: 'inferred',
      },
    ],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 部署列表', () => {
  it('渲染服务链接、版本、空部署人、推断来源与状态', async () => {
    renderWithApmIntl(<ApmDeploymentsPage />);

    const serviceLink = await screen.findByRole('link', { name: 'shop / checkout' });
    expect(serviceLink.getAttribute('href')).toBe('/apm/services/svc-1');
    expect(screen.getByText('1.2.0')).not.toBeNull();
    expect(screen.getByText('—')).not.toBeNull();
    expect(screen.getByText('推断')).not.toBeNull();
    expect(screen.getAllByText('成功').length).toBeGreaterThan(1);
  });

  it('无事件时展示空态', async () => {
    api.getDeployments.mockResolvedValue({ count: 0, items: [] });
    renderWithApmIntl(<ApmDeploymentsPage />);

    expect(await screen.findByText('暂无部署事件')).not.toBeNull();
  });
});
