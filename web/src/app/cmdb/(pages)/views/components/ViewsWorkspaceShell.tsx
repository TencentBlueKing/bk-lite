'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Empty, Segmented, Spin } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi } from '@/app/cmdb/api';
import { useCommon } from '@/app/cmdb/context/common';
import { useUserInfoContext } from '@/context/userInfo';
import type { ModelItem } from '@/app/cmdb/types/assetManage';
import type { RackRoomMode, ViewFocus, ViewType } from '../viewTypes';
import { eligibleModelIdsForView, resolveRackRoomMode } from '../viewEligibility';
import {
  buildBaseInfoPath,
  buildViewsPathPreserving,
  parseViewsSearch,
} from '../viewUrls';
import {
  clearViewFocus,
  pushViewRecent,
  readViewFocus,
  writeViewFocus,
} from '../viewMemory';
import ViewInstancePicker from './ViewInstancePicker';
import ViewCanvasHost from './ViewCanvasHost';

export interface ViewsWorkspaceShellProps {
  viewType: ViewType;
  children?: React.ReactNode;
}

const focusKey = (focus: ViewFocus | null): string =>
  focus ? `${focus.model_id}:${focus.inst_id}:${focus.mode ?? ''}` : '';

const ViewsWorkspaceShell: React.FC<ViewsWorkspaceShellProps> = ({
  viewType,
  children,
}) => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { userId } = useUserInfoContext();
  const common = useCommon();
  const { getTopoThemes } = useInstanceApi();
  const modelList: ModelItem[] = common?.modelList ?? [];

  const [focus, setFocus] = useState<ViewFocus | null>(null);
  const [mode, setMode] = useState<RackRoomMode>('room');
  const [ready, setReady] = useState(false);
  const [networkModelIds, setNetworkModelIds] = useState<string[]>([]);
  const [networkDiscovering, setNetworkDiscovering] = useState(false);
  // Static views are ready immediately; network waits for theme discovery to finish.
  const [networkDiscoveryDone, setNetworkDiscoveryDone] = useState(
    () => viewType !== 'network'
  );

  const hydratedRef = useRef(false);
  const lastSyncedKeyRef = useRef('');
  /** Last searchParams string we observed; null until first post-ready seed. */
  const lastSeenQueryRef = useRef<string | null>(null);
  const themeCacheRef = useRef<Map<string, string[]>>(new Map());
  // API helpers from useInstanceApi are new each render — use refs in effects.
  const getTopoThemesRef = useRef(getTopoThemes);
  getTopoThemesRef.current = getTopoThemes;
  const searchParamsRef = useRef(searchParams);
  searchParamsRef.current = searchParams;

  const modelsReady = viewType === 'network' ? networkDiscoveryDone : true;
  const modelIdsKey = useMemo(
    () => modelList.map((item) => item.model_id).join(','),
    [modelList]
  );

  const enrichFocus = useCallback(
    (raw: ViewFocus): ViewFocus => {
      const model = modelList.find((item) => item.model_id === raw.model_id);
      const resolvedMode =
        viewType === 'rack-room'
          ? resolveRackRoomMode(raw.model_id, raw.mode) ?? raw.mode
          : undefined;
      return {
        ...raw,
        model_name: raw.model_name || model?.model_name,
        icn: raw.icn || model?.icn,
        ...(resolvedMode ? { mode: resolvedMode } : {}),
      };
    },
    [modelList, viewType]
  );

  const focusFromParsed = useCallback(
    (parsed: ReturnType<typeof parseViewsSearch>): ViewFocus | null => {
      if (!parsed.model_id || !parsed.inst_id) return null;
      let next = enrichFocus({
        model_id: parsed.model_id,
        inst_id: parsed.inst_id,
        inst_name: parsed.inst_name,
        model_name: parsed.model_name,
        icn: parsed.icn,
        mode: parsed.mode,
      });
      if (viewType === 'rack-room') {
        const nextMode =
          resolveRackRoomMode(next.model_id, next.mode) ?? parsed.mode ?? 'room';
        next = { ...next, mode: nextMode };
      }
      return next;
    },
    [enrichFocus, viewType]
  );

  // Hydrate focus from URL, then localStorage memory. Never auto-pick first instance.
  // Parent remounts this shell with key={viewType} so view switches start clean.
  useEffect(() => {
    if (hydratedRef.current) return;
    if (!userId) return;

    const parsed = parseViewsSearch(searchParams);
    let next: ViewFocus | null = null;

    if (parsed.model_id && parsed.inst_id) {
      next = focusFromParsed(parsed);
    } else {
      const remembered = readViewFocus(window.localStorage, userId, viewType);
      if (remembered) {
        next = enrichFocus(remembered);
        if (viewType === 'rack-room') {
          const nextMode =
            resolveRackRoomMode(next.model_id, next.mode) ?? 'room';
          next = { ...next, mode: nextMode };
        }
      }
    }

    if (next && viewType === 'rack-room' && next.mode) {
      setMode(next.mode);
    } else if (viewType === 'rack-room' && parsed.mode) {
      setMode(parsed.mode);
    }

    setFocus(next);
    hydratedRef.current = true;
    setReady(true);
  }, [userId, viewType, searchParams, enrichFocus, focusFromParsed]);

  // Discover network-capable models via topo themes (cached).
  useEffect(() => {
    if (viewType !== 'network') {
      setNetworkModelIds([]);
      setNetworkDiscoveryDone(true);
      setNetworkDiscovering(false);
      return;
    }
    if (!modelIdsKey) {
      setNetworkModelIds([]);
      setNetworkDiscoveryDone(true);
      setNetworkDiscovering(false);
      return;
    }

    const modelIds = modelIdsKey.split(',').filter(Boolean);
    let cancelled = false;
    const discover = async () => {
      setNetworkDiscovering(true);
      setNetworkDiscoveryDone(false);
      try {
        const ids: string[] = [];
        await Promise.all(
          modelIds.map(async (modelId) => {
            let themes = themeCacheRef.current.get(modelId);
            if (!themes) {
              try {
                const res = await getTopoThemesRef.current(modelId);
                themes = Array.isArray(res?.themes) ? res.themes : [];
              } catch {
                themes = [];
              }
              themeCacheRef.current.set(modelId, themes);
            }
            if (themes.includes('network')) {
              ids.push(modelId);
            }
          })
        );
        if (!cancelled) {
          setNetworkModelIds((prev) =>
            (prev.length === ids.length && prev.every((id, i) => id === ids[i])
              ? prev
              : ids)
          );
        }
      } finally {
        if (!cancelled) {
          setNetworkDiscovering(false);
          setNetworkDiscoveryDone(true);
        }
      }
    };

    void discover();
    return () => {
      cancelled = true;
    };
  }, [viewType, modelIdsKey]);

  const eligibleModelIds = useMemo(() => {
    if (viewType === 'network') return networkModelIds;
    return eligibleModelIdsForView(
      viewType,
      viewType === 'rack-room' ? mode : undefined
    );
  }, [viewType, mode, networkModelIds]);

  // I1: after eligible models are ready, drop focus that is no longer valid.
  useEffect(() => {
    if (!ready || !modelsReady || !focus) return;
    if (!eligibleModelIds.includes(focus.model_id)) {
      setFocus(null);
    }
  }, [ready, modelsReady, eligibleModelIds, focus]);

  // I2: after hydrate, follow external URL changes (back/forward / shared links).
  // Seed once without applying so memory hydrate is not wiped by an empty URL.
  useEffect(() => {
    if (!ready) return;
    const query = searchParams.toString();
    if (lastSeenQueryRef.current === null) {
      lastSeenQueryRef.current = query;
      return;
    }
    if (query === lastSeenQueryRef.current) return;
    lastSeenQueryRef.current = query;

    const parsed = parseViewsSearch(searchParams);
    const urlFocus = focusFromParsed(parsed);

    if (viewType === 'rack-room') {
      if (urlFocus?.mode) {
        setMode(urlFocus.mode);
      } else if (parsed.mode) {
        setMode(parsed.mode);
      }
    }

    setFocus((prev) =>
      (focusKey(prev) === focusKey(urlFocus) ? prev : urlFocus)
    );
  }, [ready, searchParams, focusFromParsed, viewType]);

  const persistAndSync = useCallback(
    (next: ViewFocus | null) => {
      if (!userId) return;
      const currentParams = searchParamsRef.current;
      const key = focusKey(next);
      if (next) {
        writeViewFocus(window.localStorage, userId, viewType, next);
        if (key !== lastSyncedKeyRef.current) {
          pushViewRecent(window.localStorage, userId, viewType, next);
        }
        const targetPath = buildViewsPathPreserving(viewType, next, currentParams);
        const targetQuery = targetPath.includes('?')
          ? targetPath.slice(targetPath.indexOf('?') + 1)
          : '';
        if (currentParams.toString() !== targetQuery) {
          // Keep I2 from treating our own replace as an external URL change.
          lastSeenQueryRef.current = targetQuery;
          router.replace(targetPath);
        }
        lastSyncedKeyRef.current = key;
      } else {
        if (lastSyncedKeyRef.current !== '' || currentParams.toString()) {
          clearViewFocus(window.localStorage, userId, viewType);
        }
        lastSyncedKeyRef.current = '';
        if (currentParams.toString()) {
          lastSeenQueryRef.current = '';
          router.replace(`/cmdb/views/${viewType}`);
        }
      }
    },
    [userId, viewType, router]
  );

  useEffect(() => {
    if (!ready) return;
    persistAndSync(focus);
  }, [focus, ready, persistAndSync]);

  const handleFocusChange = useCallback((next: ViewFocus | null) => {
    if (!next) {
      setFocus(null);
      return;
    }
    const enriched = enrichFocus(next);
    // Keep Segmented `mode` in sync with focus.mode so rack-room eligibility
    // (I1) does not clear a rack focus that arrived while mode was still `room`.
    if (viewType === 'rack-room' && enriched.mode) {
      setMode(enriched.mode);
    }
    setFocus((prev) => {
      if (focusKey(prev) === focusKey(enriched)) {
        // Same identity — avoid a new object so persist/URL effects do not re-fire.
        const mergedName = enriched.inst_name || prev?.inst_name;
        const mergedModelName = enriched.model_name || prev?.model_name;
        const mergedIcn = enriched.icn || prev?.icn;
        if (
          prev
          && prev.inst_name === mergedName
          && prev.model_name === mergedModelName
          && prev.icn === mergedIcn
        ) {
          return prev;
        }
        return {
          ...enriched,
          inst_name: mergedName,
          model_name: mergedModelName,
          icn: mergedIcn,
        };
      }
      return enriched;
    });
  }, [enrichFocus, viewType]);

  const handleModeChange = (nextMode: RackRoomMode) => {
    setMode(nextMode);
    const allowed = eligibleModelIdsForView('rack-room', nextMode);
    if (focus && !allowed.includes(focus.model_id)) {
      setFocus(null);
      return;
    }
    if (focus) {
      setFocus({ ...focus, mode: nextMode });
    }
  };

  const handleViewDetail = () => {
    if (!focus) return;
    window.open(buildBaseInfoPath(focus), '_blank', 'noopener,noreferrer');
  };

  if (!ready) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="shrink-0 flex items-center gap-3 px-4 py-2 border-b border-[var(--color-border-1)] bg-[var(--color-bg-1)]">
        {viewType === 'rack-room' && (
          <Segmented
            value={mode}
            options={[
              { label: t('ViewsHub.modeRoom'), value: 'room' },
              { label: t('ViewsHub.modeRack'), value: 'rack' },
            ]}
            onChange={(value) => handleModeChange(value as RackRoomMode)}
          />
        )}
        <ViewInstancePicker
          viewType={viewType}
          mode={viewType === 'rack-room' ? mode : undefined}
          eligibleModelIds={eligibleModelIds}
          focus={focus}
          onFocusChange={handleFocusChange}
        />
        {networkDiscovering && viewType === 'network' && (
          <Spin size="small" />
        )}
        <div className="ml-auto shrink-0">
          {focus && (
            <Button type="default" onClick={handleViewDetail}>
              {t('ViewsHub.viewDetail')}
            </Button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 p-4">
        {!focus ? (
          <div className="h-full flex items-center justify-center">
            <Empty description={t('ViewsHub.emptyHint')} />
          </div>
        ) : (
          <ViewCanvasHost
            viewType={viewType}
            focus={focus}
            onFocusChange={handleFocusChange}
          >
            {children}
          </ViewCanvasHost>
        )}
      </div>
    </div>
  );
};

export default ViewsWorkspaceShell;
