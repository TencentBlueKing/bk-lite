import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.fn();
const post = vi.fn();
const put = vi.fn();
const patch = vi.fn();
const del = vi.fn();

vi.mock('@/utils/request', () => ({
  default: () => ({ get, post, put, patch, del, isLoading: false }),
}));

import { useRumQueries } from '@/app/rum/api';

describe('useRumQueries domain calls', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    put.mockReset();
    patch.mockReset();
    del.mockReset();
  });

  it('lists and mutates applications with normalization', async () => {
    get.mockResolvedValueOnce([
      {
        application: 'store',
        enabled: true,
        origins: null,
        browserKeys: null,
        browserKeyDigests: null,
        lastAcceptedAt: 1_700_000_000,
        lastStoredAt: 1_700_000_030,
      },
    ]);
    post.mockResolvedValueOnce({
      application: 'store',
      enabled: true,
      origins: ['https://a.test'],
      browserKeys: [],
      browserKeyDigests: [],
    });
    put.mockResolvedValueOnce({
      application: 'store',
      enabled: false,
      origins: [],
      browserKeys: [],
      browserKeyDigests: [],
    });

    const { result } = renderHook(() => useRumQueries());
    const listed = await result.current.listApplications();
    expect(get).toHaveBeenCalledWith('/rum/applications', undefined);
    expect(listed[0].origins).toEqual([]);
    expect(listed[0].lastAcceptedAt).toBe(1_700_000_000);
    expect(listed[0].lastStoredAt).toBe(1_700_000_030);

    const created = await result.current.createApplication({
      application: 'store',
      origins: ['https://a.test'],
    });
    expect(post).toHaveBeenCalledWith(
      '/rum/applications',
      { application: 'store', origins: ['https://a.test'] },
      undefined,
    );
    expect(created.origins).toEqual(['https://a.test']);

    const updated = await result.current.updateApplication('store', { enabled: false });
    expect(put).toHaveBeenCalledWith('/rum/applications/store', { enabled: false }, undefined);
    expect(updated.enabled).toBe(false);
  });

  it('loads sessions/views/errors with degradation defaults', async () => {
    get
      .mockResolvedValueOnce({ sessions: null, summary: null, analyticsUnavailable: true })
      .mockResolvedValueOnce({
        rows: [{ route: '/', views: '3', dist: null, mom: null, deviceMix: null }],
      })
      .mockResolvedValueOnce({ issues: [{ fingerprint: 'abc' }], controlUnavailable: true });

    const { result } = renderHook(() => useRumQueries());
    const sessions = await result.current.listSessions({ range: '24h' });
    expect(get).toHaveBeenCalledWith(
      '/rum/sessions',
      expect.objectContaining({
        params: { range: '24h' },
      }),
    );
    expect(
      get.mock.calls.find(([url]) => url === '/rum/sessions')?.[1]?.suppressErrorNotification,
    ).toBeFalsy();
    expect(sessions.sessions).toEqual([]);
    expect(sessions.summary.total).toBe(0);
    expect(sessions.analyticsUnavailable).toBe(true);

    const views = await result.current.listViews({ range: '24h' });
    expect(views.rows[0].views).toBe(3);
    expect(views.rows[0].dist).toEqual({ good: 0, needsImprove: 0, poor: 0, missing: 0 });
    expect(views.rows[0].deviceMix).toEqual({ mobile: 0, desktop: 0 });

    const errors = await result.current.listErrors({ range: '24h' });
    expect(errors.issues).toHaveLength(1);
    expect(errors.controlUnavailable).toBe(true);
  });

  it('covers replay, funnels, monitors, releases, alerts, compliance, saved views', async () => {
    get
      .mockResolvedValueOnce({ state: 'ready', recordings: [{ recordingId: 'r1', segments: [] }] })
      .mockResolvedValueOnce([{ id: 'f1', name: 'signup' }])
      .mockResolvedValueOnce([{ id: 'm1', name: 'error-spike' }])
      .mockResolvedValueOnce({ releases: [{ version: '1.0.0' }] })
      .mockResolvedValueOnce({ items: [{ id: 'a1' }], total: 1, page: 1, limit: 20 })
      .mockResolvedValueOnce([{ id: 'e1', status: 'done' }])
      .mockResolvedValueOnce([{ id: 'sv1', name: 'mine' }]);
    post
      .mockResolvedValueOnce({ targetIncluded: true, segments: [{ ref: 'seg-1', url: '/x' }] })
      .mockResolvedValueOnce({ id: 'f2' })
      .mockResolvedValueOnce({ id: 'm2' })
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({ id: 'sv2' });
    put.mockResolvedValueOnce({ id: 'f2' }).mockResolvedValueOnce({ id: 'm2' });
    del.mockResolvedValue(undefined);

    const { result } = renderHook(() => useRumQueries());

    const manifest = await result.current.getReplayManifest('store', 's1');
    expect(get).toHaveBeenCalledWith(
      '/rum/replay/manifest',
      expect.objectContaining({ params: { application: 'store', session: 's1' } }),
    );
    expect(manifest.recordings).toHaveLength(1);

    const grant = await result.current.createReplayGrant('store', 's1', 'seg-1');
    expect(post).toHaveBeenCalledWith(
      '/rum/replay/grants',
      { application: 'store', session: 's1', targetRef: 'seg-1' },
      undefined,
    );
    expect(grant.targetIncluded).toBe(true);

    expect(await result.current.listFunnels()).toEqual([{ id: 'f1', name: 'signup' }]);
    await result.current.createFunnel({ name: 'signup', steps: ['/a'] });
    await result.current.updateFunnel('f2', { name: 'signup2', steps: ['/a'] });
    await result.current.deleteFunnel('f2');

    expect(await result.current.listMonitors()).toEqual([{ id: 'm1', name: 'error-spike' }]);
    await result.current.createMonitor({ name: 'n' });
    await result.current.updateMonitor('m2', { name: 'n2' });
    await result.current.deleteMonitor('m2');

    const releases = await result.current.listReleases({ application: 'store' });
    expect(releases.releases[0].version).toBe('1.0.0');

    const alerts = await result.current.listAlertEvents(1, 20);
    expect(alerts.items[0].id).toBe('a1');
    expect(alerts.total).toBe(1);

    expect(await result.current.listEraseJobs()).toEqual([{ id: 'e1', status: 'done' }]);
    await result.current.eraseCompliance({ application: 'store', endUserId: 'u1' });

    expect(await result.current.listSavedViews('sessions')).toEqual([{ id: 'sv1', name: 'mine' }]);
    await result.current.createSavedView({
      screen: 'sessions',
      name: 'mine',
      contextJson: '{}',
      shared: false,
    });
    await result.current.deleteSavedView('sv1');

    expect(del).toHaveBeenCalled();
  });
});
