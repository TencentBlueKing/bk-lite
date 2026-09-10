import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApplicationCard from '../application-card';

vi.mock('next/link', () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children: React.ReactNode;
    href: string;
    [key: string]: unknown;
  }) => <a href={href} {...rest}>{children}</a>,
}));

const baseProps = {
  status: 'warning' as const,
  requestRate: 6.5,
  errorRate: 0.112,
  requestRateTrend: [4, 5, 6.5],
  errorRateTrend: [0.08, 0.1, 0.112],
  metricUnavailable: false,
  alertCount: 1,
  timeWindow: '1h',
  servicesHref: '/apm/services?perspective=service',
  eventsHref: '/apm/events/alerts',
  href: '/apm/services/applications/demo',
};

describe('ApplicationCard 分区对齐', () => {
  it('头 / 指标 / 底栏用固定三行模板，底栏高度不随服务数量变化', () => {
    const { container } = renderWithApmIntl(
      <div className="grid grid-cols-2">
        <ApplicationCard
          {...baseProps}
          label="少服务"
          services={[{ name: 'demo-catalog', silent: false }]}
        />
        <ApplicationCard
          {...baseProps}
          label="多服务"
          services={[
            { name: 'demo-catalog', silent: false },
            { name: 'demo-inventory', silent: false },
            { name: 'demo-orders', silent: false },
            { name: 'demo-payment', silent: false },
            { name: 'demo-storefront', silent: false },
            { name: 'ingest-verify-django', silent: false },
          ]}
        />
      </div>,
    );

    const bodies = [...container.querySelectorAll('article > div.grid')];
    expect(bodies).toHaveLength(2);
    for (const body of bodies) {
      expect(body.className).toContain('grid-rows-[auto_minmax(0,1fr)_auto]');
      expect(body.className).not.toContain('mt-auto');
    }

    const footers = bodies.map((body) => body.lastElementChild);
    expect(footers[0]?.className).toBe(footers[1]?.className);
    for (const footer of footers) {
      expect(footer?.className).toContain('min-w-0');
      expect(footer?.className).toContain('overflow-hidden');
    }
    expect(screen.getByText('少服务')).not.toBeNull();
    expect(screen.getByText('多服务')).not.toBeNull();
  });
});
