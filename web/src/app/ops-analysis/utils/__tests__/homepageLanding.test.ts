import { describe, expect, it, vi } from 'vitest';

import {
  effectiveHomepageHref,
  homepageLandingHref,
  homepagePreferenceNavigationTarget,
  hrefAfterOrgInit,
  isBarePortalHomeTarget,
  isDashboardHomepagePath,
  isPortalHomePath,
  preferenceLandingHref,
  resolvePostLoginHref,
} from '../homepageLanding';

const origin = 'https://lite.example';

describe('effective homepage entry', () => {
  it('opens an accessible dashboard and otherwise stays on the workbench', () => {
    expect(effectiveHomepageHref({ dashboardId: 8 })).toBe('/ops-console/home?dashboard_id=8');
    expect(effectiveHomepageHref(null)).toBe('/ops-console/home');
    expect(effectiveHomepageHref({ dashboardId: null })).toBe('/ops-console/home');
  });
});

describe('first login org submit', () => {
  it('opens the saved dashboard once and otherwise leaves the reload to the caller', () => {
    expect(hrefAfterOrgInit({ dashboard_id: 8 })).toBe('/ops-console/home?dashboard_id=8');
    expect(hrefAfterOrgInit({ dashboard_id: null, fallback: 'org' })).toBeNull();
    expect(hrefAfterOrgInit({ dashboard_id: null, fallback: null })).toBeNull();
    expect(hrefAfterOrgInit(null)).toBeNull();
  });
});

describe('homepage landing resolution', () => {
  it('leaves business deep links and existing dashboard urls unchanged', () => {
    expect(homepageLandingHref(
      '/ops-analysis/view?type=dashboard&id=7',
      { dashboard_id: 3 },
      origin,
    )).toBe('/ops-analysis/view?type=dashboard&id=7');
    expect(homepageLandingHref(
      '/ops-console/home?dashboard_id=9',
      { dashboard_id: 3 },
      origin,
    )).toBe('/ops-console/home?dashboard_id=9');
    expect(homepageLandingHref(
      'https://example.test/playground',
      { dashboard_id: 3 },
      origin,
    )).toBe('https://example.test/playground');
  });

  it('sends a bare home to the saved dashboard without screen', () => {
    expect(isBarePortalHomeTarget('/ops-console/home?screen=true', origin)).toBe(true);
    expect(isBarePortalHomeTarget('/ops-console/home?dashboard_id=', origin)).toBe(true);
    expect(homepageLandingHref(
      '/ops-console/home?screen=true',
      { dashboard_id: 12 },
      origin,
    )).toBe('/ops-console/home?dashboard_id=12');
    expect(homepageLandingHref('/', { dashboard_id: 12 }, origin)).toBe(
      '/ops-console/home?dashboard_id=12',
    );
  });

  it('keeps the original workbench target when there is no dashboard', () => {
    expect(homepageLandingHref(
      '/ops-console/home?screen=true',
      { dashboard_id: null, fallback: null },
      origin,
    )).toBe('/ops-console/home?screen=true');
    expect(homepageLandingHref(
      '/ops-console/home',
      { dashboard_id: null, fallback: 'missing' },
      origin,
    )).toBe('/ops-console/home?homepage_fallback=missing');
    expect(homepageLandingHref(
      '/',
      { fallback: 'org' },
      origin,
    )).toBe('/ops-console/home?homepage_fallback=org');
  });

  it('recognizes the dashboard homepage even when screen is also present', () => {
    expect(isDashboardHomepagePath('/ops-console/home', '?dashboard_id=4&screen=true')).toBe(true);
    expect(isDashboardHomepagePath('/ops-console/home/', new URLSearchParams('dashboard_id=4'))).toBe(true);
    expect(isDashboardHomepagePath('/ops-console/home', '?screen=true')).toBe(false);
    expect(isDashboardHomepagePath('/ops-analysis/view', '?dashboard_id=4')).toBe(false);
  });

  it('falls back to the original target when landing cannot be read', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ result: false }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(resolvePostLoginHref('/ops-analysis/view?id=1', 'token', origin)).resolves.toBe(
      '/ops-analysis/view?id=1',
    );
    expect(fetchMock).not.toHaveBeenCalled();

    await expect(resolvePostLoginHref('/ops-console/home', 'token', origin)).resolves.toBe(
      '/ops-console/home',
    );
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      result: true,
      data: { dashboard_id: 8, fallback: null },
    }), { status: 200 }));
    await expect(resolvePostLoginHref('/ops-console/home?screen=true', 'token', origin)).resolves.toBe(
      '/ops-console/home?dashboard_id=8',
    );
    vi.unstubAllGlobals();
  });
});

describe('preference landing after switcher save', () => {
  it('treats portal home paths as homepage routes', () => {
    expect(isPortalHomePath('/ops-console/home')).toBe(true);
    expect(isPortalHomePath('/ops-console/home/')).toBe(true);
    expect(isPortalHomePath('/')).toBe(true);
    expect(isPortalHomePath('/ops-analysis/view')).toBe(false);
  });

  it('builds the landing url from the saved preference', () => {
    expect(preferenceLandingHref({
      personal_mode: 'workbench',
      personal_dashboard_id: null,
      global_mode: 'dashboard',
      global_dashboard_id: 105,
    })).toBe('/ops-console/home');
    expect(preferenceLandingHref({
      personal_mode: 'follow',
      personal_dashboard_id: null,
      global_mode: 'dashboard',
      global_dashboard_id: 105,
    })).toBe('/ops-console/home?dashboard_id=105');
    expect(preferenceLandingHref({
      personal_mode: 'follow',
      personal_dashboard_id: null,
      global_mode: 'workbench',
      global_dashboard_id: null,
    })).toBe('/ops-console/home');
    expect(preferenceLandingHref({
      personal_mode: 'dashboard',
      personal_dashboard_id: 3,
      global_mode: 'workbench',
      global_dashboard_id: null,
    })).toBe('/ops-console/home?dashboard_id=3');
  });

  it('navigates only when already on portal home and the landing changed', () => {
    const workbench = {
      personal_mode: 'workbench' as const,
      personal_dashboard_id: null,
      global_mode: 'dashboard' as const,
      global_dashboard_id: 105,
    };
    expect(homepagePreferenceNavigationTarget(
      '/ops-console/home',
      '?dashboard_id=105',
      workbench,
    )).toBe('/ops-console/home');
    expect(homepagePreferenceNavigationTarget(
      '/ops-console/home',
      '',
      workbench,
    )).toBeNull();
    expect(homepagePreferenceNavigationTarget(
      '/ops-analysis/view',
      '?dashboard_id=105',
      workbench,
    )).toBeNull();
    expect(homepagePreferenceNavigationTarget(
      '/ops-console/home',
      '?dashboard_id=105',
      {
        personal_mode: 'follow',
        personal_dashboard_id: null,
        global_mode: 'dashboard',
        global_dashboard_id: 105,
      },
    )).toBeNull();
    expect(homepagePreferenceNavigationTarget(
      '/ops-console/home',
      '',
      {
        personal_mode: 'follow',
        personal_dashboard_id: null,
        global_mode: 'dashboard',
        global_dashboard_id: 9,
      },
    )).toBe('/ops-console/home?dashboard_id=9');
  });
});
