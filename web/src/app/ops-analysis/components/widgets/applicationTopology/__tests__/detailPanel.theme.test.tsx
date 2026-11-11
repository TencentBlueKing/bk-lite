import React, { act } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render } from '@testing-library/react';
import { theme as antdTheme } from 'antd';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import ScreenWidgetThemeProvider from '@/app/ops-analysis/components/screenWidgetThemeProvider';
import { SCREEN_ANTD_CSS_VAR_KEY } from '@/app/ops-analysis/utils/screenWidgetTokens';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { APP_VIEW_FULLSCREEN_EVENT } from '@/components/app-view-fullscreen';
import { defaultTheme, ThemeProvider } from '@/theme';
import type { ApplicationTopologyBandNode } from '../bandModel';
import ApplicationTopologyDetailPanel, {
  readScreenDetailPresentation,
  resolveApplicationTopologyDetailChrome,
  screenDetailFollowsScreenTheme,
} from '../detailPanel';
import panelStyles from '../detailPanel.module.scss';

vi.mock('@/context/appCapabilities', () => ({
  useAppWidget: () => ({
    status: 'unavailable',
    declared: false,
    loadWidget: null,
  }),
  useLazyAppWidget: () => ({ Widget: null, loadFailed: false }),
}));

const SCREEN_DARK_SURFACE = '#14243a';
const SCREEN_DARK_BORDER = 'rgba(112, 147, 195, 0.24)';

const node: ApplicationTopologyBandNode = {
  id: 'node-1',
  name: 'bj-pay-worker-01',
  modelId: 'host',
  layer: 'host',
  tone: 'normal',
  alertCount: 0,
  maxLevel: null,
  monitorId: '',
  badge: null,
  category: 'host',
  x: 0,
  y: 0,
};

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute('data-app-view-fullscreen');
  document.documentElement.classList.remove('dark', 'light');
  window.localStorage.removeItem('theme');
  delete window.__BK_LITE_THEME_MODE__;
  Object.defineProperty(document, 'fullscreenElement', {
    configurable: true,
    get: () => null,
  });
});

const renderPanel = ({
  mode,
  shareMode = false,
  chartThemeMode = 'screen-dark',
  withScreenProvider = true,
}: {
  mode: 'light' | 'dark';
  shareMode?: boolean;
  chartThemeMode?: OpsChartThemeMode;
  withScreenProvider?: boolean;
}) => {
  window.__BK_LITE_THEME_MODE__ = mode;
  window.localStorage.removeItem('theme');
  const panel = (
    <ApplicationTopologyDetailPanel
      node={node}
      statusLabel="正常"
      shareMode={shareMode}
      chartThemeMode={chartThemeMode}
      onClose={() => undefined}
    />
  );
  return render(
    <IntlProvider locale="zh" messages={{}}>
      <ThemeProvider>
        {withScreenProvider ? (
          <ScreenWidgetThemeProvider mode={chartThemeMode}>
            {panel}
          </ScreenWidgetThemeProvider>
        ) : panel}
      </ThemeProvider>
    </IntlProvider>,
  );
};

const drawerRoot = () => document.querySelector<HTMLElement>('.ant-drawer');

const drawerSurface = () => {
  const styled = Array.from(document.querySelectorAll<HTMLElement>('*')).find((element) => (
    element.style.getPropertyValue('--ops-topology-drawer-surface')
  ));
  return styled?.style.getPropertyValue('--ops-topology-drawer-surface').trim() ?? '';
};

const drawerRewritesScreenTokens = () => {
  const drawer = drawerRoot();
  if (!drawer) return false;
  return Array.from(drawer.querySelectorAll<HTMLElement>('*')).some((element) => (
    element.style.getPropertyValue('--color-text-1') === '#e8eef7'
  ));
};

const drawerAntdVar = (name: string) => {
  const names = drawerRoot()?.className.split(' ') ?? [];
  const themeClass = names.find((item) => item.includes('ops-screen'))
    ?? names.find((item) => item.startsWith('css-var-'));
  if (!themeClass) return '';
  const matched = Array.from(document.querySelectorAll('style'))
    .map((node) => node.textContent || '')
    .filter((text) => text.includes(themeClass))
    .join('\n');
  return matched.match(new RegExp(`${name}:([^;]+)`))?.[1] ?? '';
};

describe('application topology detail chrome', () => {
  it('follows the system theme inside an embedded preview', () => {
    const light = resolveApplicationTopologyDetailChrome({
      chartThemeMode: 'screen-dark',
      presentedAlone: false,
      systemMode: 'light',
      systemTokens: defaultTheme.light,
    });
    expect(light.surface).toBeUndefined();
    expect(light.contentStyle).toBeUndefined();
    expect(light.theme?.inherit).toBe(false);
    expect(light.theme?.algorithm).toBe(antdTheme.defaultAlgorithm);
    expect(light.theme?.cssVar).toBe(true);
    expect(light.theme?.token?.colorBgContainer).toBe(defaultTheme.light.surfaceContainer);
    expect(light.theme?.token?.colorText).toBe(defaultTheme.light.textPrimary);
    expect(light.theme?.cssVar).not.toEqual({ key: SCREEN_ANTD_CSS_VAR_KEY['screen-dark'] });

    const dark = resolveApplicationTopologyDetailChrome({
      chartThemeMode: 'screen-dark',
      presentedAlone: false,
      systemMode: 'dark',
      systemTokens: defaultTheme.dark,
    });
    expect(dark.surface).toBeUndefined();
    expect(dark.contentStyle).toBeUndefined();
    expect(dark.theme?.inherit).toBe(false);
    expect(dark.theme?.algorithm).toBe(antdTheme.darkAlgorithm);
    expect(dark.theme?.token?.colorBgContainer).toBe(defaultTheme.dark.surfaceContainer);
    expect(dark.theme?.token?.colorText).toBe(defaultTheme.dark.textPrimary);
    expect(dark.theme?.token?.colorBgContainer).not.toBe(SCREEN_DARK_SURFACE);
  });

  it('keeps the screen theme for fullscreen or share', () => {
    expect(screenDetailFollowsScreenTheme({
      shareMode: true,
      appViewFullscreen: false,
      browserFullscreen: false,
    })).toBe(true);
    expect(screenDetailFollowsScreenTheme({
      shareMode: false,
      appViewFullscreen: true,
      browserFullscreen: false,
    })).toBe(true);
    expect(screenDetailFollowsScreenTheme({
      shareMode: false,
      appViewFullscreen: false,
      browserFullscreen: true,
    })).toBe(true);
    expect(screenDetailFollowsScreenTheme({
      shareMode: false,
      appViewFullscreen: false,
      browserFullscreen: false,
    })).toBe(false);

    const screen = resolveApplicationTopologyDetailChrome({
      chartThemeMode: 'screen-dark',
      presentedAlone: true,
      systemMode: 'light',
      systemTokens: defaultTheme.light,
    });
    expect(screen.surface).toBe(SCREEN_DARK_SURFACE);
    expect(screen.theme?.inherit).toBe(false);
    expect(screen.theme?.algorithm).toBe(antdTheme.darkAlgorithm);
    expect(screen.theme?.cssVar).toEqual({ key: SCREEN_ANTD_CSS_VAR_KEY['screen-dark'] });
    expect(screen.theme?.token?.colorBgContainer).toBe(SCREEN_DARK_SURFACE);
    expect(screen.contentStyle).toMatchObject({
      '--color-text-1': '#e8eef7',
      '--color-border-1': SCREEN_DARK_BORDER,
    });
  });

  it('leaves a normal dashboard drawer on the surrounding theme', () => {
    const dashboard = resolveApplicationTopologyDetailChrome({
      chartThemeMode: 'default',
      presentedAlone: false,
      systemMode: 'dark',
      systemTokens: defaultTheme.dark,
    });
    expect(dashboard.theme).toBeUndefined();
    expect(dashboard.surface).toBeUndefined();
    expect(dashboard.contentStyle).toBeUndefined();

    const sharedDashboard = resolveApplicationTopologyDetailChrome({
      chartThemeMode: undefined,
      presentedAlone: true,
      systemMode: 'light',
      systemTokens: defaultTheme.light,
    });
    expect(sharedDashboard.theme).toBeUndefined();
    expect(sharedDashboard.surface).toBeUndefined();
  });
});

describe('application topology detail drawer presentation', () => {
  it('reads share, app-view fullscreen, and browser fullscreen as shell-less', () => {
    expect(readScreenDetailPresentation(false)).toBe(false);
    expect(readScreenDetailPresentation(true)).toBe(true);

    document.documentElement.setAttribute('data-app-view-fullscreen', '');
    expect(readScreenDetailPresentation(false)).toBe(true);
    document.documentElement.removeAttribute('data-app-view-fullscreen');

    const stage = document.createElement('div');
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => stage,
    });
    expect(readScreenDetailPresentation(false)).toBe(true);
  });

  it('uses the system surface for an embedded screen while the system is light', () => {
    renderPanel({ mode: 'light', chartThemeMode: 'screen-dark' });

    expect(document.documentElement.classList.contains('light')).toBe(true);
    expect(drawerSurface()).toBe('');
    expect(drawerRoot()?.classList.contains(panelStyles.shell)).toBe(false);
    expect(drawerRewritesScreenTokens()).toBe(false);
    expect(drawerRoot()?.className ?? '').not.toContain(SCREEN_ANTD_CSS_VAR_KEY['screen-dark']);
    expect(drawerAntdVar('--ant-color-text')).toBe(defaultTheme.light.textPrimary);
    expect(drawerAntdVar('--ant-color-bg-container')).toBe(defaultTheme.light.surfaceContainer);
    expect(document.querySelector('[data-screen-widget-theme="screen-dark"]')).toBeTruthy();
  });

  it('uses the system surface for an embedded screen while the system is dark', () => {
    renderPanel({ mode: 'dark', chartThemeMode: 'screen-dark' });

    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(drawerSurface()).toBe('');
    expect(drawerRoot()?.classList.contains(panelStyles.shell)).toBe(false);
    expect(drawerRewritesScreenTokens()).toBe(false);
    expect(drawerRoot()?.className ?? '').not.toContain(SCREEN_ANTD_CSS_VAR_KEY['screen-dark']);
    expect(drawerAntdVar('--ant-color-text')).toBe(defaultTheme.dark.textPrimary);
    expect(drawerAntdVar('--ant-color-bg-container')).toBe(defaultTheme.dark.surfaceContainer);
  });

  it('uses the screen-dark surface when the screen is shared or fullscreen', () => {
    renderPanel({ mode: 'light', shareMode: true, chartThemeMode: 'screen-dark' });

    expect(drawerSurface()).toBe(SCREEN_DARK_SURFACE);
    expect(drawerRoot()?.classList.contains(panelStyles.shell)).toBe(true);
    expect(document.querySelector('.ant-drawer-content')?.style.getPropertyValue('--color-border-1')).toBe(SCREEN_DARK_BORDER);
    expect(document.querySelector('.ant-drawer-content')?.contains(document.querySelector('.ant-drawer-header'))).toBe(true);
    expect(drawerRewritesScreenTokens()).toBe(true);
    expect(drawerRoot()?.className ?? '').toContain(SCREEN_ANTD_CSS_VAR_KEY['screen-dark']);
    expect(drawerAntdVar('--ant-color-bg-container')).toBe(SCREEN_DARK_SURFACE);
    expect(drawerAntdVar('--ant-color-text')).toBe('#e8eef7');

    cleanup();
    document.documentElement.classList.remove('dark', 'light');

    renderPanel({ mode: 'light', chartThemeMode: 'screen-dark' });
    expect(drawerSurface()).toBe('');

    act(() => {
      document.documentElement.setAttribute('data-app-view-fullscreen', '');
      window.dispatchEvent(new Event(APP_VIEW_FULLSCREEN_EVENT));
    });
    expect(drawerSurface()).toBe(SCREEN_DARK_SURFACE);
    expect(drawerRoot()?.className ?? '').toContain(SCREEN_ANTD_CSS_VAR_KEY['screen-dark']);
  });
});
