import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RouteScopedLayout } from '@/app/routeScopedLayout';

const providerCalls = {
  userInfo: vi.fn(),
  client: vi.fn(),
  menus: vi.fn(),
  permissions: vi.fn(),
};

let pathname = '/ops-analysis/render/execution/7';
let sessionStatus: 'loading' | 'authenticated' | 'unauthenticated' = 'authenticated';

vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ status: sessionStatus }),
}));

vi.mock('@ant-design/nextjs-registry', () => ({
  AntdRegistry: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('@/components/spin', () => ({
  default: () => <div data-testid="route-loader" />,
}));

vi.mock('@/context/userInfo', () => ({
  UserInfoProvider: ({ children }: { children: React.ReactNode }) => {
    providerCalls.userInfo();
    return children;
  },
}));

vi.mock('@/context/client', () => ({
  ClientProvider: ({ children }: { children: React.ReactNode }) => {
    providerCalls.client();
    return children;
  },
}));

vi.mock('@/context/menus', () => ({
  MenusProvider: ({ children }: { children: React.ReactNode }) => {
    providerCalls.menus();
    return children;
  },
}));

vi.mock('@/context/permissions', () => ({
  PermissionsProvider: ({ children }: { children: React.ReactNode }) => {
    providerCalls.permissions();
    return children;
  },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  pathname = '/ops-analysis/render/execution/7';
  sessionStatus = 'authenticated';
});

describe('RouteScopedLayout', () => {
  it('mounts the render page without ordinary user/menu/permission providers', () => {
    const StandardLayout = vi.fn(({ children }: { children: React.ReactNode }) => children);

    render(
      <RouteScopedLayout StandardLayout={StandardLayout}>
        <div>render-page-mounted</div>
      </RouteScopedLayout>,
    );

    expect(screen.getByText('render-page-mounted')).toBeTruthy();
    expect(StandardLayout).not.toHaveBeenCalled();
    expect(providerCalls.userInfo).not.toHaveBeenCalled();
    expect(providerCalls.client).not.toHaveBeenCalled();
    expect(providerCalls.menus).not.toHaveBeenCalled();
    expect(providerCalls.permissions).not.toHaveBeenCalled();
  });

  it('keeps ordinary routes behind the standard provider chain', () => {
    pathname = '/ops-analysis/dashboard';
    const StandardLayout = vi.fn(({ children }: { children: React.ReactNode }) => children);

    render(
      <RouteScopedLayout StandardLayout={StandardLayout}>
        <div>ordinary-page</div>
      </RouteScopedLayout>,
    );

    expect(screen.getByText('ordinary-page')).toBeTruthy();
    expect(StandardLayout).toHaveBeenCalledOnce();
    expect(providerCalls.userInfo).toHaveBeenCalledOnce();
    expect(providerCalls.client).toHaveBeenCalledOnce();
    expect(providerCalls.menus).toHaveBeenCalledOnce();
    expect(providerCalls.permissions).toHaveBeenCalledOnce();
  });

  it('does not treat lookalike paths as privileged render routes', () => {
    pathname = '/ops-analysis/render/execution/not-an-id';
    const StandardLayout = vi.fn(({ children }: { children: React.ReactNode }) => children);

    render(
      <RouteScopedLayout StandardLayout={StandardLayout}>
        <div>lookalike-page</div>
      </RouteScopedLayout>,
    );

    expect(screen.getByText('lookalike-page')).toBeTruthy();
    expect(StandardLayout).toHaveBeenCalledOnce();
    expect(providerCalls.permissions).toHaveBeenCalledOnce();
  });

  it('waits only for render session resolution before mounting the render page', () => {
    sessionStatus = 'loading';

    render(
      <RouteScopedLayout StandardLayout={({ children }) => children}>
        <div>render-page-mounted</div>
      </RouteScopedLayout>,
    );

    expect(screen.getByTestId('route-loader')).toBeTruthy();
    expect(screen.queryByText('render-page-mounted')).toBeNull();
  });
});
