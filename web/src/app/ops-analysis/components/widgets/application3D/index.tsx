'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Empty, Select, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useShareMode } from '@/app/ops-analysis/context/shareMode';
import { useApplication3DApi } from '@/app/ops-analysis/api/application3D';
import type {
  Application3DAlarmDetailData,
  Application3DDetailData,
  Application3DMetricSeriesResult,
  Application3DWallData,
  Application3DWallItem,
} from '@/app/ops-analysis/types/sceneWidget';
import type { ScreenRenderContext } from '@/app/ops-analysis/types/dashBoard';
import type { Application3DFocusChromeLayout, Application3DSceneController } from './application3DScene';
import Application3DDetail from './application3DDetail';

interface Application3DProps {
  refreshKey?: string | number;
  editMode?: boolean;
  screenRenderContext?: ScreenRenderContext;
  onReady?: (ready: boolean) => void;
  onError?: (message: string) => void;
  runtimeActive?: boolean;
}

const getErrorCode = (error: unknown): string | undefined => {
  if (!error || typeof error !== 'object') return undefined;
  if ('code' in error && typeof error.code === 'string') return error.code;
  const response = 'response' in error ? error.response : undefined;
  if (!response || typeof response !== 'object' || !('data' in response)) return undefined;
  const data = response.data;
  if (!data || typeof data !== 'object') return undefined;
  if ('code' in data && typeof data.code === 'string') return data.code;
  if ('data' in data && data.data && typeof data.data === 'object' && 'code' in data.data) {
    return typeof data.data.code === 'string' ? data.data.code : undefined;
  }
  return undefined;
};

export default function Application3D({
  refreshKey,
  editMode = false,
  screenRenderContext,
  onReady,
  onError,
  runtimeActive = true,
}: Application3DProps) {
  const { t } = useTranslation();
  const translateRef = useRef(t);
  translateRef.current = t;
  const shareMode = useShareMode();
  const params = useParams<{ sessionId?: string }>();
  const {
    getWall,
    getApplicationDetail,
    getAlarmDetail,
    getMetric,
  } = useApplication3DApi(shareMode ? params.sessionId : undefined);
  const mountRef = useRef<HTMLDivElement | null>(null);
  const controllerRef = useRef<Application3DSceneController | null>(null);
  const resizeSceneRef = useRef<() => void>(() => undefined);
  const mountedRef = useRef(true);
  const wallGenerationRef = useRef(0);
  const detailGenerationRef = useRef(0);
  const wallAbortRef = useRef<AbortController | null>(null);
  const detailAbortRef = useRef<AbortController | null>(null);
  const metricAbortRef = useRef<AbortController | null>(null);
  const [wall, setWall] = useState<Application3DWallData | null>(null);
  const [appliedFilters, setAppliedFilters] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [refreshWarning, setRefreshWarning] = useState('');
  const [selected, setSelected] = useState<Application3DWallItem | null>(null);
  const [focusReady, setFocusReady] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<Application3DDetailData | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [moreAlarmsLoading, setMoreAlarmsLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [alarmDetail, setAlarmDetail] = useState<Application3DAlarmDetailData | null>(null);
  const [alarmLoading, setAlarmLoading] = useState(false);
  const [alarmError, setAlarmError] = useState('');
  const lastAlarmIdRef = useRef<string | null>(null);
  const [metric, setMetric] = useState<Application3DMetricSeriesResult | null>(null);
  const [metricLoading, setMetricLoading] = useState(false);
  const [toolbarEntered, setToolbarEntered] = useState(false);
  const [focusChromeLayout, setFocusChromeLayout] = useState<Application3DFocusChromeLayout | null>(null);
  const allowedOnSurface = screenRenderContext?.enabled === true;
  const wallMotionRef = useRef<'intro' | 'filter' | 'none'>('intro');
  const wallRef = useRef(wall);
  const selectedRef = useRef(selected);
  const clearSelectionRef = useRef<() => void>(() => undefined);
  wallRef.current = wall;
  selectedRef.current = selected;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      wallGenerationRef.current += 1;
      detailGenerationRef.current += 1;
      wallAbortRef.current?.abort();
      detailAbortRef.current?.abort();
      metricAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    const mountNode = mountRef.current;
    if (!allowedOnSurface) return undefined;
    if (!mountNode) return undefined;
    let cancelled = false;
    void import('./application3DScene').then(({ createApplication3DScene }) => {
      if (cancelled || !mountedRef.current) return;
      const controller = createApplication3DScene(mountNode, {
        interactive: !editMode,
        active: runtimeActive,
        translate: (id, defaultMessage) => translateRef.current(id, defaultMessage),
        onSelect: (item) => {
          if (editMode) return;
          if (selectedRef.current?.id === item.id) {
            return;
          }
          detailGenerationRef.current += 1;
          detailAbortRef.current?.abort();
          metricAbortRef.current?.abort();
          setFocusReady(false);
          setSelected(item);
          setDetailOpen(false);
          setDetail(null);
          setDetailLoading(false);
          setDetailError('');
          setAlarmDetail(null);
          setAlarmLoading(false);
          setAlarmError('');
          setMetric(null);
          setMetricLoading(false);
          controllerRef.current?.focus(item.id);
        },
        onFocusSettled: (item) => {
          if (editMode || selectedRef.current?.id !== item.id) return;
          setFocusReady(true);
        },
        onBackground: () => {
          if (editMode || !selectedRef.current) return;
          clearSelectionRef.current();
        },
      });
      controllerRef.current = controller;
      resizeSceneRef.current = () => controller.resize();
      if (wallRef.current) {
        const motion = wallMotionRef.current;
        controller.reconcile(wallRef.current.items, {
          playIntro: motion === 'intro',
          playFilter: motion === 'filter',
        });
        if (wallRef.current.items.length > 0 && motion !== 'none') {
          wallMotionRef.current = 'none';
        }
      }
      controller.resize();
    });
    return () => {
      cancelled = true;
      resizeSceneRef.current = () => undefined;
      controllerRef.current?.dispose();
      controllerRef.current = null;
    };
  }, [allowedOnSurface, editMode]);

  useEffect(() => {
    controllerRef.current?.setActive(runtimeActive);
    if (runtimeActive) return;
    wallGenerationRef.current += 1;
    detailGenerationRef.current += 1;
    wallAbortRef.current?.abort();
    detailAbortRef.current?.abort();
    metricAbortRef.current?.abort();
    setLoading(false);
    setRefreshing(false);
    setDetailLoading(false);
    setAlarmLoading(false);
    setMetricLoading(false);
    setMoreAlarmsLoading(false);
  }, [runtimeActive]);

  useEffect(() => {
    const controller = controllerRef.current;
    if (!controller) return;
    const motion = wallMotionRef.current;
    controller.reconcile(wall?.items ?? [], {
      playIntro: motion === 'intro',
      playFilter: motion === 'filter',
    });
    if ((wall?.items.length ?? 0) > 0 && motion !== 'none') {
      wallMotionRef.current = 'none';
    }
  }, [wall]);

  useEffect(() => {
    const controller = controllerRef.current;
    const items = wallRef.current?.items;
    if (!controller || !items?.length) return;
    controller.reconcile(items, { forceRepaint: true });
  }, [t]);

  // Screen fitScale is a CSS transform; ResizeObserver content-box does not change.
  useLayoutEffect(() => {
    resizeSceneRef.current();
  }, [screenRenderContext?.fitScale]);

  const clearSelection = useCallback(() => {
    detailGenerationRef.current += 1;
    detailAbortRef.current?.abort();
    metricAbortRef.current?.abort();
    setSelected(null);
    setFocusReady(false);
    setDetailOpen(false);
    setDetail(null);
    setDetailError('');
    setDetailLoading(false);
    setAlarmDetail(null);
    setAlarmLoading(false);
    setAlarmError('');
    lastAlarmIdRef.current = null;
    setMetric(null);
    setMetricLoading(false);
    controllerRef.current?.restoreWall();
  }, []);
  clearSelectionRef.current = clearSelection;

  const fetchWall = useCallback(async (filters: Record<string, string[]>, silent = false) => {
    const generation = ++wallGenerationRef.current;
    wallAbortRef.current?.abort();
    const abortController = new AbortController();
    wallAbortRef.current = abortController;
    const currentWall = wallRef.current;
    if (silent && currentWall) setRefreshing(true);
    else setLoading(true);
    setError('');
    setRefreshWarning('');
    try {
      const result = await getWall(filters, abortController.signal);
      if (!mountedRef.current || generation !== wallGenerationRef.current) return;
      setWall(result);
      setAppliedFilters(result.appliedFilters || filters);
      if (
        selectedRef.current &&
        !result.items.some((item) => item.id === selectedRef.current?.id)
      ) {
        clearSelection();
      }
      onReady?.(result.items.length > 0);
    } catch (requestError) {
      if (abortController.signal.aborted) return;
      if (!mountedRef.current || generation !== wallGenerationRef.current) return;
      const code = getErrorCode(requestError);
      const message = code === 'capacity_exceeded'
        ? t('dashboard.application3DCapacityExceeded')
        : t('dashboard.application3DLoadFailed');
      if (
        currentWall &&
        !['permission_denied', 'scope_changed', 'not_found'].includes(code || '')
      ) {
        setWall({
          ...currentWall,
          items: currentWall.items.map((item) => ({
            ...item,
            health: { ...item.health, stale: true, reason: 'stale_after_refresh_failure' },
          })),
        });
        setRefreshWarning(t('dashboard.application3DStale'));
      } else {
        setWall(null);
        clearSelection();
        setError(message);
        onError?.(message);
      }
    } finally {
      if (mountedRef.current && generation === wallGenerationRef.current) {
        if (wallAbortRef.current === abortController) wallAbortRef.current = null;
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [clearSelection, getWall, onError, onReady, t]);

  useEffect(() => {
    if (!allowedOnSurface || !runtimeActive) return;
    void fetchWall(appliedFilters, Boolean(wall));
  }, [refreshKey, runtimeActive]);

  useEffect(() => {
    if (wall && !loading) setToolbarEntered(true);
  }, [wall, loading]);

  useLayoutEffect(() => {
    if (!focusReady || !selected) {
      setFocusChromeLayout(null);
      return undefined;
    }
    const readLayout = () => {
      setFocusChromeLayout(controllerRef.current?.getFocusChromeLayout?.() ?? null);
    };
    readLayout();
    const frame = window.requestAnimationFrame(readLayout);
    const mountNode = mountRef.current;
    const observer = typeof ResizeObserver !== 'undefined' && mountNode
      ? new ResizeObserver(readLayout)
      : null;
    observer?.observe(mountNode);
    window.addEventListener('resize', readLayout);
    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener('resize', readLayout);
    };
  }, [focusReady, selected, screenRenderContext?.fitScale]);

  const filterDefinitions = wall?.filters ?? [];
  const handleFilterChange = (filterId: string, values: string[]) => {
    const next = { ...appliedFilters, [filterId]: values };
    setAppliedFilters(next);
    clearSelection();
    wallMotionRef.current = 'filter';
    void fetchWall(next);
  };

  const loadDetail = useCallback(async () => {
    if (!selected) return;
    const generation = ++detailGenerationRef.current;
    detailAbortRef.current?.abort();
    metricAbortRef.current?.abort();
    const abortController = new AbortController();
    detailAbortRef.current = abortController;
    setDetailOpen(true);
    setFocusReady(false);
    setDetailLoading(true);
    setDetailError('');
    setAlarmError('');
    setAlarmDetail(null);
    setMetric(null);
    controllerRef.current?.restoreWall();
    try {
      const result = await getApplicationDetail(selected.id, undefined, abortController.signal);
      if (!mountedRef.current || generation !== detailGenerationRef.current) return;
      setDetail(result);
    } catch (requestError) {
      if (abortController.signal.aborted) return;
      if (!mountedRef.current || generation !== detailGenerationRef.current) return;
      if (['permission_denied', 'scope_changed', 'not_found'].includes(getErrorCode(requestError) || '')) {
        clearSelection();
        return;
      }
      setDetail(null);
      setDetailError(t('dashboard.application3DDetailFailed'));
    } finally {
      if (mountedRef.current && generation === detailGenerationRef.current) {
        if (detailAbortRef.current === abortController) detailAbortRef.current = null;
        setDetailLoading(false);
      }
    }
  }, [clearSelection, getApplicationDetail, selected, t]);

  const loadMoreAlarms = useCallback(async () => {
    if (!selected || detail?.alarms.state !== 'available' || !detail.alarms.page.nextCursor) return;
    const generation = detailGenerationRef.current;
    const abortController = new AbortController();
    detailAbortRef.current?.abort();
    detailAbortRef.current = abortController;
    setMoreAlarmsLoading(true);
    try {
      const result = await getApplicationDetail(
        selected.id,
        detail.alarms.page.nextCursor,
        abortController.signal,
      );
      if (!mountedRef.current || generation !== detailGenerationRef.current) return;
      setDetail((current) => {
        if (!current || current.alarms.state !== 'available' || result.alarms.state !== 'available') return current;
        const byId = new Map(current.alarms.items.map((item) => [item.id, item]));
        result.alarms.items.forEach((item) => byId.set(item.id, item));
        return {
          ...current,
          alarms: { ...result.alarms, items: Array.from(byId.values()) },
          refreshedAt: result.refreshedAt,
        };
      });
    } catch (requestError) {
      if (!abortController.signal.aborted && mountedRef.current && generation === detailGenerationRef.current) {
        if (['permission_denied', 'scope_changed', 'not_found'].includes(getErrorCode(requestError) ?? '')) {
          clearSelection();
          return;
        }
        setDetailError(t('dashboard.application3DDetailFailed'));
      }
    } finally {
      if (mountedRef.current && generation === detailGenerationRef.current) setMoreAlarmsLoading(false);
    }
  }, [clearSelection, detail, getApplicationDetail, selected, t]);

  const loadMetric = useCallback(async (applicationId: string, alarmId: string) => {
    const generation = detailGenerationRef.current;
    metricAbortRef.current?.abort();
    const abortController = new AbortController();
    metricAbortRef.current = abortController;
    setMetricLoading(true);
    setMetric(null);
    try {
      const result = await getMetric(applicationId, alarmId, abortController.signal);
      if (!mountedRef.current || generation !== detailGenerationRef.current) return;
      setMetric(result);
    } catch (requestError) {
      if (abortController.signal.aborted) return;
      if (!mountedRef.current || generation !== detailGenerationRef.current) return;
      if (getErrorCode(requestError) === 'permission_denied') {
        setMetric({
          applicationId,
          alarmId,
          state: 'permission_denied',
          series: null,
          thresholds: [],
          alarmMarker: null,
        });
        return;
      }
      setMetric({
        applicationId,
        alarmId,
        state: 'failure',
        series: null,
        thresholds: [],
        alarmMarker: null,
        errorCode: 'metric_source_failure',
      });
    } finally {
      if (mountedRef.current && generation === detailGenerationRef.current) {
        if (metricAbortRef.current === abortController) metricAbortRef.current = null;
        setMetricLoading(false);
      }
    }
  }, [getMetric]);

  const loadAlarm = useCallback(async (alarmId: string) => {
    if (!selected) return;
    const generation = ++detailGenerationRef.current;
    detailAbortRef.current?.abort();
    metricAbortRef.current?.abort();
    const abortController = new AbortController();
    detailAbortRef.current = abortController;
    lastAlarmIdRef.current = alarmId;
    setAlarmLoading(true);
    setAlarmError('');
    setDetailError('');
    setAlarmDetail(null);
    setMetric(null);
    try {
      const result = await getAlarmDetail(selected.id, alarmId, abortController.signal);
      if (!mountedRef.current || generation !== detailGenerationRef.current) return;
      setAlarmDetail(result);
      void loadMetric(selected.id, alarmId);
    } catch (requestError) {
      if (abortController.signal.aborted) return;
      if (!mountedRef.current || generation !== detailGenerationRef.current) return;
      if (['permission_denied', 'scope_changed', 'not_found'].includes(getErrorCode(requestError) || '')) {
        setAlarmDetail(null);
        setMetric(null);
        setAlarmError('');
        return;
      }
      setAlarmError(t('dashboard.application3DAlarmFailed'));
    } finally {
      if (mountedRef.current && generation === detailGenerationRef.current) {
        if (detailAbortRef.current === abortController) detailAbortRef.current = null;
        setAlarmLoading(false);
      }
    }
  }, [getAlarmDetail, loadMetric, selected, t]);

  const filterControls = useMemo(
    () =>
      filterDefinitions.map((definition) => (
        <Select
          key={definition.id}
          mode={definition.type === 'multiple' ? 'multiple' : undefined}
          allowClear
          maxTagCount="responsive"
          value={appliedFilters[definition.id] || []}
          options={definition.options}
          placeholder={definition.label}
          className="min-w-48"
          // Root uses overflow-hidden; keep popup on body so reopen isn't clipped/stuck.
          getPopupContainer={() => document.body}
          popupMatchSelectWidth={false}
          onChange={(value) =>
            handleFilterChange(
              definition.id,
              Array.isArray(value) ? value : value ? [value] : [],
            )
          }
        />
      )),
    [appliedFilters, filterDefinitions],
  );

  return (
    <div className="relative h-full min-h-48 w-full overflow-hidden bg-transparent text-[var(--color-application3d-text)]">
      <div
        ref={mountRef}
        className="absolute inset-0 z-0 [&>canvas]:relative [&>canvas]:z-0 [&>canvas]:block [&>canvas]:h-full [&>canvas]:w-full"
        aria-hidden="true"
      />
      {!allowedOnSurface && (
        <div className="absolute inset-0 z-30 flex items-center justify-center p-6">
          <Alert type="error" showIcon message={t('dashboard.application3DScreenOnly')} />
        </div>
      )}
      {/* Full-screen status layers stay below chrome so filter Select stays clickable. */}
      {loading && (
        <div className="pointer-events-none absolute inset-0 z-[5] flex items-center justify-center bg-[var(--color-application3d-loading-overlay)]">
          <Spin tip={t('dashboard.application3DLoading')} />
        </div>
      )}
      {error && !loading && (
        <div className="absolute inset-0 z-[5] flex items-center justify-center p-6">
          <Alert
            type="error"
            showIcon
            message={error}
            action={<Button onClick={() => void fetchWall(appliedFilters)}>{t('common.retry')}</Button>}
          />
        </div>
      )}
      {!loading && !error && wall?.items.length === 0 && (
        <div className="pointer-events-none absolute inset-0 z-[5] flex items-center justify-center">
          <Empty description={t('dashboard.application3DEmpty')} />
        </div>
      )}
      {!editMode && (
        <div className={`pointer-events-none absolute left-3 right-3 top-3 z-20 flex items-start justify-between gap-3${toolbarEntered ? ' app3d-toolbar-in' : ''}`}>
          <div className="pointer-events-auto flex flex-wrap gap-2">{filterControls}</div>
          <Button
            size="small"
            className="pointer-events-auto border-[var(--color-application3d-refresh-border)] bg-[var(--color-application3d-refresh-bg)] text-[var(--color-application3d-text)]"
            icon={<ReloadOutlined spin={refreshing} />}
            disabled={refreshing}
            onClick={() => void fetchWall(appliedFilters, true)}
            title={t('common.refresh')}
          />
        </div>
      )}
      {refreshWarning && (
        <Alert
          className="absolute bottom-3 left-3 z-20"
          type="warning"
          showIcon
          message={refreshWarning}
        />
      )}
      {selected && focusReady && !editMode && !detailOpen && (
        <div className="pointer-events-none absolute inset-0 z-20">
          <div
            key={selected.id}
            className={
              focusChromeLayout
                ? 'pointer-events-auto absolute flex flex-col items-center gap-3'
                : 'pointer-events-auto absolute left-1/2 top-[58%] flex w-max min-w-[11.5rem] max-w-full -translate-x-1/2 flex-col items-center gap-3'
            }
            style={
              focusChromeLayout
                ? {
                  left: focusChromeLayout.centerX,
                  top: focusChromeLayout.bottom + 22,
                  width: 'max-content',
                  minWidth: focusChromeLayout.width,
                  maxWidth: '100%',
                  transform: 'translateX(-50%)',
                }
                : undefined
            }
          >
            <button
              type="button"
              className="app3d-detail-cta"
              onClick={() => void loadDetail()}
            >
              {t('dashboard.application3DOpenDetail')}
              <span aria-hidden="true" className="ml-2 font-normal opacity-80">→</span>
            </button>
            <button
              type="button"
              className="app3d-back-cta"
              onClick={clearSelection}
              title={t('dashboard.application3DBackWall')}
            >
              <span aria-hidden="true">←</span>
              {t('dashboard.application3DBackWall')}
            </button>
          </div>
        </div>
      )}
      {detailOpen && selected && !editMode && (
        <Application3DDetail
          selected={selected}
          detail={detail}
          alarmDetail={alarmDetail}
          metric={metric}
          loading={detailLoading}
          alarmLoading={alarmLoading}
          metricLoading={metricLoading}
          moreAlarmsLoading={moreAlarmsLoading}
          error={detailError}
          alarmError={alarmError}
          onClose={clearSelection}
          onRetry={() => {
            void loadDetail();
          }}
          onRetryAlarm={() => {
            if (lastAlarmIdRef.current) void loadAlarm(lastAlarmIdRef.current);
          }}
          onOpenAlarm={(alarmId) => void loadAlarm(alarmId)}
          onCloseAlarm={() => {
            detailGenerationRef.current += 1;
            detailAbortRef.current?.abort();
            metricAbortRef.current?.abort();
            setAlarmDetail(null);
            setAlarmLoading(false);
            setAlarmError('');
            setMetric(null);
            setMetricLoading(false);
            setDetailError('');
          }}
          onNavigateAlarm={(alarmId) => void loadAlarm(alarmId)}
          onRetryMetric={() => {
            if (alarmDetail) void loadMetric(alarmDetail.applicationId, alarmDetail.alarm.id);
          }}
          onLoadMoreAlarms={() => void loadMoreAlarms()}
        />
      )}
    </div>
  );
}
