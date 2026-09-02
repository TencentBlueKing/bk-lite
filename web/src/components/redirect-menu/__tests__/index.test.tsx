import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';

const replace = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
  usePathname: vi.fn(() => '/'),
}));

vi.mock('@/context/permissions', () => ({
  usePermissions: vi.fn(() => ({ menus: [], loading: false })),
}));

import { usePathname } from 'next/navigation';
import { usePermissions } from '@/context/permissions';
import RedirectToFirstMenu from '../index';
import { PORTAL_HOME_PATH } from '@/utils/route';

describe('RedirectToFirstMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(usePathname).mockReturnValue('/');
    vi.mocked(usePermissions).mockReturnValue({
      menus: [],
      loading: false,
      permissions: {},
      hasPermission: () => false,
    });
  });

  it('redirects the portal root to the console home page', () => {
    render(<RedirectToFirstMenu />);

    expect(replace).toHaveBeenCalledWith(PORTAL_HOME_PATH);
  });

  it('redirects app landing pages to the first accessible menu', () => {
    vi.mocked(usePathname).mockReturnValue('/opspilot');
    vi.mocked(usePermissions).mockReturnValue({
      menus: [{ url: '/opspilot/studio', name: 'studio' } as any],
      loading: false,
      permissions: {},
      hasPermission: () => true,
    });

    render(<RedirectToFirstMenu />);

    expect(replace).toHaveBeenCalledWith('/opspilot/studio');
  });
});
