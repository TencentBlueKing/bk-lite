import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback || _key }),
}));

vi.mock('antd', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@ant-design/icons', () => ({
  DesktopOutlined: () => <span>desk</span>,
  MobileOutlined: () => <span>mob</span>,
}));

vi.mock('@/app/apm/components/home/sparkline', () => ({
  default: ({ data }: { data: number[] }) => <div data-testid="sparkline">{data.join(',')}</div>,
}));

import DeviceMixCell from '@/app/rum/views/ui/device-mix-cell';
import DistributionBar from '@/app/rum/views/ui/distribution-bar';
import MomCell from '@/app/rum/views/ui/mom-cell';

afterEach(() => {
  cleanup();
});

describe('rum views cells', () => {
  it('MomCell shows em dash when spark is empty or all zeros', () => {
    const { unmount } = render(<MomCell mom={{ hasDelta: false, spark: [] }} />);
    expect(screen.getByText('—')).toBeTruthy();
    unmount();
    render(<MomCell mom={{ hasDelta: false, spark: [0, 0, 0] }} />);
    expect(screen.getByText('—')).toBeTruthy();
  });

  it('MomCell renders sparkline for positive values', () => {
    render(<MomCell mom={{ hasDelta: true, viewsDeltaPct: 12, spark: [1, 2, 3] }} />);
    expect(screen.getByTestId('sparkline').textContent).toBe('1,2,3');
  });

  it('DistributionBar shows empty state', () => {
    render(<DistributionBar dist={{ good: 0, needsImprove: 0, poor: 0, missing: 0 }} />);
    expect(screen.getByText('—')).toBeTruthy();
  });

  it('DistributionBar shows good percentage', () => {
    render(<DistributionBar dist={{ good: 75, needsImprove: 15, poor: 5, missing: 5 }} />);
    expect(screen.getByText('75%')).toBeTruthy();
  });

  it('DeviceMixCell computes mobile/desktop percentages', () => {
    const { unmount } = render(<DeviceMixCell mix={{ mobile: 0, desktop: 0 }} />);
    expect(screen.getByText('—')).toBeTruthy();
    unmount();
    render(<DeviceMixCell mix={{ mobile: 25, desktop: 75 }} />);
    expect(screen.getByText('25%')).toBeTruthy();
    expect(screen.getByText('75%')).toBeTruthy();
  });
});
