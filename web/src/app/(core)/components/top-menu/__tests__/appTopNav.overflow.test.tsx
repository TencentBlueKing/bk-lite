import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverStub);

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/components/icon', () => ({
  default: ({ type }: { type: string }) => <span data-testid={`icon-${type}`} />,
}));

import AppTopNav from '../appTopNav';
import type { ClientData } from '@/types/index';

const apps = [
  { name: 'opspilot', display_name: 'OpsPilot', url: '/opspilot', icon: 'opspilot', is_build_in: true },
  { name: 'cmdb', display_name: 'CMDB', url: '/cmdb', icon: 'cmdb', is_build_in: true },
  { name: 'monitor', display_name: '监控中心', url: '/monitor', icon: 'monitor', is_build_in: true },
  { name: 'alarm', display_name: '告警中心', url: '/alarm', icon: 'alarm', is_build_in: true },
] as ClientData[];

const setStripOverflow = (
  strip: HTMLElement,
  { scrollLeft, clientWidth, scrollWidth }: { scrollLeft: number; clientWidth: number; scrollWidth: number },
) => {
  Object.defineProperty(strip, 'scrollLeft', { configurable: true, value: scrollLeft });
  Object.defineProperty(strip, 'clientWidth', { configurable: true, value: clientWidth });
  Object.defineProperty(strip, 'scrollWidth', { configurable: true, value: scrollWidth });
  act(() => {
    strip.dispatchEvent(new Event('scroll'));
  });
};

afterEach(() => {
  cleanup();
});

describe('AppTopNav overflow arrows', () => {
  it('hides arrows when the strip does not overflow', () => {
    render(<AppTopNav apps={apps} pathname="/cmdb" />);
    expect(screen.queryByRole('button', { name: 'common.scrollAppsLeft' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'common.scrollAppsRight' })).toBeNull();
    expect(screen.queryByText('common.more')).toBeNull();
    expect(screen.queryByText('详情')).toBeNull();
  });

  it('shows a right arrow when more apps sit past the visible edge', async () => {
    const { container } = render(<AppTopNav apps={apps} pathname="/cmdb" />);
    const strip = container.querySelector('[data-app-strip]') as HTMLElement;
    setStripOverflow(strip, { scrollLeft: 0, clientWidth: 320, scrollWidth: 900 });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'common.scrollAppsRight' })).toBeTruthy();
    });
    expect(screen.queryByRole('button', { name: 'common.scrollAppsLeft' })).toBeNull();
    expect(screen.getByText('告警中心')).toBeTruthy();
  });

  it('scrolls the strip when the right arrow is clicked', async () => {
    const { container } = render(<AppTopNav apps={apps} pathname="/cmdb" />);
    const strip = container.querySelector('[data-app-strip]') as HTMLElement;
    const scrollBy = vi.fn();
    strip.scrollBy = scrollBy;
    setStripOverflow(strip, { scrollLeft: 0, clientWidth: 320, scrollWidth: 900 });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'common.scrollAppsRight' })).toBeTruthy();
    });
    fireEvent.click(screen.getByRole('button', { name: 'common.scrollAppsRight' }));
    expect(scrollBy).toHaveBeenCalledWith({ left: 224, behavior: 'smooth' });
  });
});
