import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { HomepagePreferenceState } from '@/app/ops-analysis/utils/homepageDirectoryActions';

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  refresh: vi.fn(async () => {}),
  getState: vi.fn(),
  getAccess: vi.fn(),
  applyPersonal: vi.fn(),
  requestGet: vi.fn(),
  clientLoading: false,
  clientData: [{ name: 'ops-analysis' }] as Array<{ name: string }>,
  shortcutEntry: { dashboardId: 99 } as { dashboardId: number } | null,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push }),
}));

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
    getState: mocks.getState,
    getAccess: mocks.getAccess,
    applyPersonal: mocks.applyPersonal,
  }),
}));

vi.mock('@/app/ops-analysis/context/effectiveHomepage', () => ({
  useEffectiveHomepage: () => ({
    entry: mocks.shortcutEntry,
    refresh: mocks.refresh,
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
  mocks.refresh.mockReset();
  mocks.refresh.mockResolvedValue(undefined);
  mocks.getState.mockReset();
  mocks.getAccess.mockReset();
  mocks.applyPersonal.mockReset();
  mocks.requestGet.mockReset();
  mocks.clientLoading = false;
  mocks.clientData = [{ name: 'ops-analysis' }];
  mocks.shortcutEntry = { dashboardId: 99 };
  mocks.getState.mockResolvedValue(dashboardState);
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
      <HomepageSwitcherRow mode={menu.personalMode} />
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
    render(<HomepageSwitcherRow mode="dashboard" onToggle={onToggle} />);
    const row = screen.getByTestId('homepage-switcher-row');
    expect(row.textContent).toContain('common.homepage');
    expect(row.textContent).not.toContain('common.homepageFollowGlobal');
    fireEvent.mouseEnter(row);
    expect(onToggle).not.toHaveBeenCalled();
    fireEvent.click(row);
    expect(onToggle).toHaveBeenCalledTimes(1);

    cleanup();
    render(<HomepageSwitcherRow mode="workbench" />);
    expect(screen.getByTestId('homepage-switcher-row').textContent).toContain('common.homepagePinWorkbench');
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
    expect(screen.getByTestId('homepage-panel-title').textContent).toBe('common.homepage');
    expect(screen.getByTestId('homepage-option-icon-follow')).toBeTruthy();
    expect(screen.getByTestId('homepage-option-icon-workbench')).toBeTruthy();
    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(2);
    expect(radios.every((radio) => radio.getAttribute('aria-checked') === 'false')).toBe(true);
    expect(screen.getByTestId('homepage-dashboard-settings').getAttribute('role')).toBeNull();
    expect(screen.getByTestId('homepage-personal-dashboard-caption').textContent).toBe('业务大盘');
    expect(screen.getByRole('radio', { name: 'common.homepageFollowGlobal' }).textContent)
      .toContain('common.homepageFollowGlobalCurrent:运维总览');
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

  it('follows the administrator dashboard from homepage state, not the logo shortcut', async () => {
    resetMocks();
    render(<Harness />);

    await waitFor(() => {
      expect(screen.getByTestId('homepage-personal-dashboard-caption').textContent).toBe('业务大盘');
      expect(screen.getByRole('radio', { name: 'common.homepageFollowGlobal' }).textContent)
        .toContain('common.homepageFollowGlobalCurrent:运维总览');
    });
    expect(mocks.getState).toHaveBeenCalledWith({ suppressErrorNotification: true });
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
      expect(mocks.push).toHaveBeenCalledWith('/ops-console/home?dashboard_id=9');
    });
    expect(mocks.applyPersonal).toHaveBeenCalledWith({ action: 'clear' });
    expect(mocks.refresh).toHaveBeenCalled();
    expect(mocks.push).not.toHaveBeenCalledWith('/ops-console/home?dashboard_id=3');
    expect(mocks.push).not.toHaveBeenCalledWith('/ops-console/home?dashboard_id=99');
  });

  it('returns to the workbench immediately after pinning the console', async () => {
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
      expect(mocks.push).toHaveBeenCalledWith('/ops-console/home');
    });
    expect(mocks.applyPersonal).toHaveBeenCalledWith({ action: 'pin_workbench' });
    expect(mocks.push.mock.calls.some((call) => String(call[0]).includes('dashboard_id'))).toBe(false);
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
      'common.homepagePersonalDashboardFallback',
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
    mocks.getState.mockResolvedValue(workbenchState);
    render(<Harness />);

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
    mocks.getState.mockResolvedValue({ ...workbenchState });

    await act(async () => {
      fireEvent.click(screen.getByTestId('reload-homepage-state'));
    });

    expect(followRadio().textContent).toContain('common.homepageFollowGlobalCurrent:运维总览');
    expect(screen.getByTestId('homepage-personal-dashboard-caption').textContent).toBe(
      'common.homepageDashboardSettingsHint',
    );
    expect(mocks.getAccess).toHaveBeenCalledWith(9);

    await act(async () => {
      resolveAccess({ status: 'ok', name: 'WeOpsX 平台使用', desc: '', is_build_in: false });
    });
    expect(followRadio().textContent).toContain('common.homepageFollowGlobalCurrent:WeOpsX 平台使用');
  });

  it('clears the administrator name when the bound dashboard changes', async () => {
    resetMocks();
    mocks.getState.mockResolvedValue(workbenchState);
    render(<Harness />);
    await waitFor(() => {
      expect(followRadio().textContent).toContain('common.homepageFollowGlobalCurrent:运维总览');
    });

    let resolveAccess: (value: unknown) => void = () => {};
    mocks.getAccess.mockImplementation(
      () => new Promise((resolve) => {
        resolveAccess = resolve;
      }),
    );
    mocks.getState.mockResolvedValue({
      ...workbenchState,
      global_dashboard_id: 10,
    });

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
  });

  it('sends the workbench when follow clears onto a global workbench', async () => {
    resetMocks();
    mocks.getState.mockResolvedValue({
      ...dashboardState,
      global_mode: 'workbench',
      global_dashboard_id: null,
    });
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
      expect(mocks.push).toHaveBeenCalledWith('/ops-console/home');
    });
  });
});
