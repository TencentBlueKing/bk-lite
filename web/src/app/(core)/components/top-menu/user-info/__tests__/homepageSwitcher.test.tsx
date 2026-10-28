import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { HomepagePreferenceState } from '@/app/ops-analysis/utils/homepageDirectoryActions';

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  pathname: '/ops-analysis/view',
  search: '',
  messageSuccess: vi.fn(),
  refreshLogo: vi.fn(async () => {}),
  preferenceState: null as HomepagePreferenceState | null,
  preferenceLoading: false,
  reloadPreference: vi.fn(async () => {}),
  getAccess: vi.fn(),
  applyPersonal: vi.fn(),
  requestGet: vi.fn(),
  clientLoading: false,
  clientData: [{ name: 'ops-analysis' }] as Array<{ name: string }>,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
  usePathname: () => mocks.pathname,
  useSearchParams: () => new URLSearchParams(mocks.search.replace(/^\?/, '')),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: {
      ...actual.message,
      success: mocks.messageSuccess,
      error: vi.fn(),
    },
  };
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, _fallback?: string, values?: { name?: string }) => (
      values?.name ? `${key}:${values.name}` : key
    ),
  }),
}));

vi.mock('@/utils/request', () => ({
  default: () => ({ get: mocks.requestGet }),
}));

vi.mock('@/app/ops-analysis/api/homepage', () => ({
  useHomepageApi: () => ({
    getAccess: mocks.getAccess,
  }),
}));

vi.mock('@/app/ops-analysis/context/homepagePreference', () => ({
  useHomepagePreference: () => ({
    state: mocks.preferenceState,
    status: mocks.preferenceLoading ? 'loading' : (mocks.preferenceState ? 'ready' : 'idle'),
    isLoading: mocks.preferenceLoading,
    reload: mocks.reloadPreference,
    applyPersonal: mocks.applyPersonal,
    applyGlobal: vi.fn(),
  }),
}));

vi.mock('@/context/client', () => ({
  useClientData: () => ({
    clientData: mocks.clientData,
    loading: mocks.clientLoading,
  }),
}));

import {
  HomepageSwitcherPanel,
  HomepageSwitcherRow,
  useHomepageMenu,
} from '../homepageSwitcher';

const dashboardState: HomepagePreferenceState = {
  is_platform_admin: false,
  personal_mode: 'dashboard',
  personal_dashboard_id: 3,
  global_mode: 'dashboard',
  global_dashboard_id: 9,
};

const viewMenus = [
  {
    name: 'Operations Analysis',
    children: [{ name: 'view', operation: ['View', 'AddCatalogue'] }],
  },
];

const resetMocks = () => {
  mocks.push.mockReset();
  mocks.replace.mockReset();
  mocks.pathname = '/ops-analysis/view';
  mocks.search = '';
  mocks.messageSuccess.mockReset();
  mocks.refreshLogo.mockReset();
  mocks.refreshLogo.mockResolvedValue(undefined);
  mocks.reloadPreference.mockReset();
  mocks.reloadPreference.mockImplementation(async () => {});
  mocks.getAccess.mockReset();
  mocks.applyPersonal.mockReset();
  mocks.requestGet.mockReset();
  mocks.clientLoading = false;
  mocks.clientData = [{ name: 'ops-analysis' }];
  mocks.preferenceLoading = false;
  mocks.preferenceState = dashboardState;
  mocks.getAccess.mockImplementation(async (id: number) => {
    if (Number(id) === 9) {
      return { status: 'ok', name: '运维总览', desc: '', is_build_in: false };
    }
    if (Number(id) === 3) {
      return { status: 'ok', name: '业务大盘', desc: '', is_build_in: false };
    }
    return { status: 'missing', name: '', desc: '', is_build_in: false };
  });
  mocks.requestGet.mockResolvedValue(viewMenus);
};

const Harness = () => {
  const menu = useHomepageMenu('group-1');
  return (
    <>
      <button type="button" data-testid="reload-homepage-state" onClick={() => { void menu.reloadState(); }}>
        reload
      </button>
      <HomepageSwitcherRow mode={menu.personalMode} dashboardName={menu.personalDashboardCaption} />
      <HomepageSwitcherPanel
        personalMode={menu.personalMode}
        adminDashboardName={menu.adminDashboardName}
        personalDashboardCaption={menu.personalDashboardCaption}
        showSettingsLink={menu.showSettingsLink}
        applying={menu.applying}
        onFollow={() => {
          void menu.followGlobal();
        }}
        onPinWorkbench={() => {
          void menu.pinWorkbench();
        }}
        onOpenSettings={menu.openDashboardSettings}
      />
    </>
  );
};

const workbenchState: HomepagePreferenceState = {
  ...dashboardState,
  personal_mode: 'workbench',
  personal_dashboard_id: null,
};

const followRadio = () => screen.getByRole('radio', { name: 'common.homepageFollowGlobal' });

afterEach(() => {
  cleanup();
});

describe('HomepageSwitcher', () => {
  it('shows the current choice on the parent row and opens from a click', () => {
    const onToggle = vi.fn();
    render(<HomepageSwitcherRow mode="dashboard" dashboardName="运维总览" onToggle={onToggle} />);
    const row = screen.getByTestId('homepage-switcher-row');
    expect(row.textContent).toContain('common.homepage');
    expect(row.textContent).toContain('运维总览');
    expect(row.textContent).not.toContain('common.homepageFollowGlobal');
    expect(row.textContent).not.toContain('common.homepagePanelTitle');
    fireEvent.mouseEnter(row);
    expect(onToggle).not.toHaveBeenCalled();
    fireEvent.click(row);
    expect(onToggle).toHaveBeenCalledTimes(1);

    cleanup();
    render(<HomepageSwitcherRow mode="workbench" />);
    expect(screen.getByTestId('homepage-switcher-row').textContent).toContain('common.homepagePinWorkbench');
    expect(screen.getByTestId('homepage-switcher-row').textContent).toContain('common.homepage');

    cleanup();
    render(<HomepageSwitcherRow mode="follow" />);
    expect(screen.getByTestId('homepage-switcher-row').textContent).toContain('common.homepageFollowGlobal');
  });

  it('leaves both radios clear for a personal dashboard and keeps the name off a third option', () => {
    render(
      <HomepageSwitcherPanel
        personalMode="dashboard"
        adminDashboardName="运维总览"
        personalDashboardCaption="业务大盘"
        showSettingsLink
        applying={false}
        onFollow={vi.fn()}
        onPinWorkbench={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );
    expect(screen.getByTestId('homepage-panel-title').textContent).toBe('common.homepagePanelTitle');
    expect(screen.getByTestId('homepage-option-icon-follow')).toBeTruthy();
    expect(screen.getByTestId('homepage-option-icon-workbench')).toBeTruthy();
    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(2);
    expect(radios.every((radio) => radio.getAttribute('aria-checked') === 'false')).toBe(true);
    expect(screen.getByTestId('homepage-dashboard-settings').getAttribute('role')).toBeNull();
    expect(screen.getByTestId('homepage-dashboard-settings').getAttribute('data-selected')).toBe('true');
    expect(screen.getByTestId('homepage-dashboard-settings').innerHTML).toContain('text-[var(--color-primary)]');
    expect(screen.getByTestId('homepage-personal-dashboard-caption').textContent).toBe('common.homepageCurrentHomepage:业务大盘');
    expect(screen.getByRole('radio', { name: 'common.homepageFollowGlobal' }).textContent)
      .toContain('common.homepageFollowGlobalCurrent:运维总览');
  });

  it('keeps the dashboard settings link unhighlighted while following default or console', () => {
    const { rerender } = render(
      <HomepageSwitcherPanel
        personalMode="follow"
        adminDashboardName="运维总览"
        personalDashboardCaption={null}
        showSettingsLink
        applying={false}
        onFollow={vi.fn()}
        onPinWorkbench={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );
    const followLink = screen.getByTestId('homepage-dashboard-settings');
    expect(followLink.getAttribute('data-selected')).toBe('false');
    expect(followLink.innerHTML).not.toContain('text-[var(--color-primary)]');
    expect(followLink.innerHTML).toContain('text-[var(--color-text-1)]');
    expect(screen.getByTestId('homepage-personal-dashboard-caption').textContent).toBe(
      'common.homepageDashboardSettingsHint',
    );

    rerender(
      <HomepageSwitcherPanel
        personalMode="workbench"
        adminDashboardName={null}
        personalDashboardCaption={null}
        showSettingsLink
        applying={false}
        onFollow={vi.fn()}
        onPinWorkbench={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );
    const workbenchLink = screen.getByTestId('homepage-dashboard-settings');
    expect(workbenchLink.getAttribute('data-selected')).toBe('false');
    expect(workbenchLink.innerHTML).not.toContain('text-[var(--color-primary)]');
  });

  it('checks follow global and omits the settings link when it must stay hidden', () => {
    const parentClick = vi.fn();
    render(
      <div onClick={parentClick}>
        <HomepageSwitcherPanel
          personalMode="follow"
          adminDashboardName={null}
          personalDashboardCaption={null}
          showSettingsLink={false}
          applying={false}
          onFollow={vi.fn()}
          onPinWorkbench={vi.fn()}
          onOpenSettings={vi.fn()}
        />
      </div>,
    );
    expect(screen.getByRole('radio', { name: 'common.homepageFollowGlobal' }).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByRole('radio', { name: 'common.homepageFollowGlobal' }).getAttribute('data-selected')).toBe('true');
    expect(screen.getByRole('radio', { name: 'common.homepageFollowGlobal' }).className).toContain('bg-[var(--color-primary-bg-active)]');
    expect(screen.getByRole('radio', { name: 'common.homepagePinWorkbench' }).getAttribute('aria-checked')).toBe('false');
    expect(screen.queryByTestId('homepage-dashboard-settings')).toBeNull();
    expect(screen.getAllByRole('radio')).toHaveLength(2);
    fireEvent.click(screen.getByTestId('homepage-switcher-panel'));
    expect(parentClick).not.toHaveBeenCalled();
  });
});

describe('useHomepageMenu', () => {
  afterEach(() => {
    cleanup();
  });

  it('follows the default homepage preference without navigating away', async () => {
    resetMocks();
    render(<Harness />);

    await waitFor(() => {
      expect(screen.getByTestId('homepage-personal-dashboard-caption').textContent).toBe('common.homepageCurrentHomepage:业务大盘');
      expect(screen.getByRole('radio', { name: 'common.homepageFollowGlobal' }).textContent)
        .toContain('common.homepageFollowGlobalCurrent:运维总览');
    });
    expect(mocks.preferenceState?.personal_dashboard_id).toBe(3);
    expect(screen.getByTestId('homepage-dashboard-settings')).toBeTruthy();
    expect(screen.getAllByRole('radio').every((radio) => radio.getAttribute('aria-checked') === 'false')).toBe(true);
    expect(screen.getByTestId('homepage-switcher-row').textContent).toContain('common.homepage');
    expect(mocks.requestGet).toHaveBeenCalledWith('/core/api/get_user_menus/', {
      params: { name: 'ops-analysis' },
      suppressErrorNotification: true,
    });

    mocks.applyPersonal.mockResolvedValue({
      ...dashboardState,
      personal_mode: 'follow',
      personal_dashboard_id: null,
    });
    fireEvent.click(screen.getByRole('radio', { name: 'common.homepageFollowGlobal' }));

    await waitFor(() => {
      expect(mocks.applyPersonal).toHaveBeenCalledWith({ action: 'clear' });
      expect(mocks.messageSuccess).toHaveBeenCalledWith('common.homepageFollowGlobalSuccess');
    });
    expect(mocks.push).not.toHaveBeenCalled();
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it('pins the console preference without navigating away', async () => {
    resetMocks();
    mocks.applyPersonal.mockResolvedValue({
      ...dashboardState,
      personal_mode: 'workbench',
      personal_dashboard_id: null,
    });
    render(<Harness />);
    await waitFor(() => {
      expect(screen.getByRole('radio', { name: 'common.homepagePinWorkbench' })).toBeTruthy();
    });
    fireEvent.click(screen.getByRole('radio', { name: 'common.homepagePinWorkbench' }));
    await waitFor(() => {
      expect(mocks.applyPersonal).toHaveBeenCalledWith({ action: 'pin_workbench' });
      expect(mocks.messageSuccess).toHaveBeenCalledWith('common.homepagePinWorkbenchSuccess');
    });
    expect(mocks.push).not.toHaveBeenCalled();
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it('opens the operations analysis directory from the settings link', async () => {
    resetMocks();
    render(<Harness />);
    fireEvent.click(await screen.findByTestId('homepage-dashboard-settings'));
    expect(mocks.push).toHaveBeenCalledWith('/ops-analysis/view');
  });

  it('uses the fallback caption when the personal dashboard name cannot be loaded', async () => {
    resetMocks();
    mocks.getAccess.mockResolvedValue({ status: 'permission', name: '', desc: '', is_build_in: false });
    render(<Harness />);
    expect((await screen.findByTestId('homepage-personal-dashboard-caption')).textContent).toBe(
      'common.homepageCurrentHomepage:common.homepagePersonalDashboardFallback',
    );
    expect(screen.getByRole('radio', { name: 'common.homepageFollowGlobal' }).textContent)
      .not.toContain('common.homepageFollowGlobalCurrent');
  });

  it('keeps follow and pin visible without the operations analysis module', async () => {
    resetMocks();
    mocks.clientData = [];
    render(<Harness />);
    await waitFor(() => {
      expect(screen.getAllByRole('radio')).toHaveLength(2);
    });
    expect(screen.queryByTestId('homepage-dashboard-settings')).toBeNull();
    expect(mocks.requestGet).not.toHaveBeenCalled();
  });

  it('keeps follow and pin visible without the view permission', async () => {
    resetMocks();
    mocks.requestGet.mockResolvedValue([
      { name: 'Operations Analysis', children: [{ name: 'view', operation: ['AddCatalogue'] }] },
    ]);
    render(<Harness />);
    await waitFor(() => {
      expect(mocks.requestGet).toHaveBeenCalled();
    });
    expect(screen.getAllByRole('radio')).toHaveLength(2);
    expect(screen.queryByTestId('homepage-dashboard-settings')).toBeNull();
  });

  it('does not draw the settings link while client data is still loading', async () => {
    resetMocks();
    let resolveMenus: (value: unknown) => void = () => {};
    mocks.requestGet.mockImplementation(
      () => new Promise((resolve) => {
        resolveMenus = resolve;
      }),
    );
    mocks.clientLoading = true;
    const { rerender } = render(<Harness />);
    expect(screen.getAllByRole('radio')).toHaveLength(2);
    expect(screen.queryByTestId('homepage-dashboard-settings')).toBeNull();
    expect(mocks.requestGet).not.toHaveBeenCalled();

    mocks.clientLoading = false;
    rerender(<Harness />);
    await waitFor(() => {
      expect(mocks.requestGet).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('homepage-dashboard-settings')).toBeNull();
    await act(async () => {
      resolveMenus(viewMenus);
    });
    expect(await screen.findByTestId('homepage-dashboard-settings')).toBeTruthy();
  });

  it('keeps the administrator name while reloading the same dashboard', async () => {
    resetMocks();
    mocks.preferenceState = workbenchState;
    const { rerender } = render(<Harness />);

    await waitFor(() => {
      expect(followRadio().textContent).toContain('common.homepageFollowGlobalCurrent:运维总览');
    });
    expect(screen.getByTestId('homepage-dashboard-settings')).toBeTruthy();

    let resolveAccess: (value: unknown) => void = () => {};
    mocks.getAccess.mockImplementation(
      () => new Promise((resolve) => {
        resolveAccess = resolve;
      }),
    );
    mocks.preferenceState = { ...workbenchState };
    rerender(<Harness />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('reload-homepage-state'));
    });

    expect(followRadio().textContent).toContain('common.homepageFollowGlobalCurrent:运维总览');
    expect(screen.getByTestId('homepage-personal-dashboard-caption').textContent).toBe(
      'common.homepageDashboardSettingsHint',
    );
    expect(mocks.reloadPreference).toHaveBeenCalled();
    expect(mocks.getAccess).toHaveBeenCalledWith(9);

    await act(async () => {
      resolveAccess({ status: 'ok', name: 'WeOpsX 平台使用', desc: '', is_build_in: false });
    });
    expect(followRadio().textContent).toContain('common.homepageFollowGlobalCurrent:WeOpsX 平台使用');
  });

  it('clears the administrator name when the bound dashboard changes', async () => {
    resetMocks();
    mocks.preferenceState = workbenchState;
    const { rerender } = render(<Harness />);
    await waitFor(() => {
      expect(followRadio().textContent).toContain('common.homepageFollowGlobalCurrent:运维总览');
    });

    let resolveAccess: (value: unknown) => void = () => {};
    mocks.getAccess.mockImplementation(
      () => new Promise((resolve) => {
        resolveAccess = resolve;
      }),
    );
    mocks.preferenceState = {
      ...workbenchState,
      global_dashboard_id: 10,
    };
    rerender(<Harness />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('reload-homepage-state'));
    });

    expect(followRadio().textContent).not.toContain('运维总览');
    expect(followRadio().textContent).not.toContain('common.homepageFollowGlobalCurrent');

    await act(async () => {
      resolveAccess({ status: 'ok', name: '新盘', desc: '', is_build_in: false });
    });
    expect(followRadio().textContent).toContain('common.homepageFollowGlobalCurrent:新盘');
  });

  it('stays on the menu when saving the preference fails', async () => {
    resetMocks();
    mocks.applyPersonal.mockRejectedValue(new Error('save failed'));
    render(<Harness />);
    fireEvent.click(await screen.findByRole('radio', { name: 'common.homepageFollowGlobal' }));
    await waitFor(() => {
      expect(mocks.applyPersonal).toHaveBeenCalledWith({ action: 'clear' });
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(mocks.push).not.toHaveBeenCalled();
    expect(mocks.messageSuccess).not.toHaveBeenCalled();
  });


  it('finishes the preference save without navigating or waiting on logo refresh', async () => {
    resetMocks();
    let resolvePersonal: (value: HomepagePreferenceState) => void = () => {};
    mocks.applyPersonal.mockImplementation(
      () => new Promise<HomepagePreferenceState>((resolve) => {
        resolvePersonal = resolve;
      }),
    );
    render(<Harness />);
    await waitFor(() => {
      expect(screen.getByRole('radio', { name: 'common.homepageFollowGlobal' })).toBeTruthy();
    });
    fireEvent.click(screen.getByRole('radio', { name: 'common.homepageFollowGlobal' }));
    expect(mocks.push).not.toHaveBeenCalled();
    expect(mocks.messageSuccess).not.toHaveBeenCalled();
    await act(async () => {
      resolvePersonal({
        ...dashboardState,
        personal_mode: 'follow',
        personal_dashboard_id: null,
      });
    });
    await waitFor(() => {
      expect(mocks.applyPersonal).toHaveBeenCalledWith({ action: 'clear' });
      expect(mocks.messageSuccess).toHaveBeenCalledWith('common.homepageFollowGlobalSuccess');
    });
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it('clears onto a global workbench preference without navigating', async () => {
    resetMocks();
    mocks.preferenceState = {
      ...dashboardState,
      global_mode: 'workbench',
      global_dashboard_id: null,
    };
    mocks.applyPersonal.mockResolvedValue({
      ...dashboardState,
      personal_mode: 'follow',
      personal_dashboard_id: null,
      global_mode: 'workbench',
      global_dashboard_id: null,
    });
    render(<Harness />);
    fireEvent.click(await screen.findByRole('radio', { name: 'common.homepageFollowGlobal' }));
    await waitFor(() => {
      expect(mocks.applyPersonal).toHaveBeenCalledWith({ action: 'clear' });
      expect(mocks.messageSuccess).toHaveBeenCalledWith('common.homepageFollowGlobalSuccess');
    });
    expect(mocks.push).not.toHaveBeenCalled();
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it('stays put when pinning workbench off the portal home route', async () => {
    resetMocks();
    mocks.pathname = '/cmdb/resource';
    mocks.applyPersonal.mockResolvedValue({
      ...dashboardState,
      personal_mode: 'workbench',
      personal_dashboard_id: null,
    });
    render(<Harness />);
    fireEvent.click(await screen.findByRole('radio', { name: 'common.homepagePinWorkbench' }));
    await waitFor(() => {
      expect(mocks.applyPersonal).toHaveBeenCalledWith({ action: 'pin_workbench' });
      expect(mocks.messageSuccess).toHaveBeenCalledWith('common.homepagePinWorkbenchSuccess');
    });
    expect(mocks.replace).not.toHaveBeenCalled();
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it('replaces onto bare console home when pinning workbench on a dashboard homepage', async () => {
    resetMocks();
    mocks.pathname = '/ops-console/home';
    mocks.search = 'dashboard_id=105';
    mocks.applyPersonal.mockResolvedValue({
      ...dashboardState,
      personal_mode: 'workbench',
      personal_dashboard_id: null,
    });
    render(<Harness />);
    fireEvent.click(await screen.findByRole('radio', { name: 'common.homepagePinWorkbench' }));
    await waitFor(() => {
      expect(mocks.applyPersonal).toHaveBeenCalledWith({ action: 'pin_workbench' });
      expect(mocks.messageSuccess).toHaveBeenCalledWith('common.homepagePinWorkbenchSuccess');
      expect(mocks.replace).toHaveBeenCalledWith('/ops-console/home');
    });
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it('replaces onto the default dashboard when following while already on portal home', async () => {
    resetMocks();
    mocks.pathname = '/ops-console/home';
    mocks.search = '';
    mocks.applyPersonal.mockResolvedValue({
      ...dashboardState,
      personal_mode: 'follow',
      personal_dashboard_id: null,
      global_mode: 'dashboard',
      global_dashboard_id: 9,
    });
    render(<Harness />);
    fireEvent.click(await screen.findByRole('radio', { name: 'common.homepageFollowGlobal' }));
    await waitFor(() => {
      expect(mocks.applyPersonal).toHaveBeenCalledWith({ action: 'clear' });
      expect(mocks.replace).toHaveBeenCalledWith('/ops-console/home?dashboard_id=9');
    });
  });
});
