'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button,  Segmented, Spin } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';
import { useCommon } from '@/app/cmdb/context/common';
import { useUserInfoContext } from '@/context/userInfo';
import type { ModelItem } from '@/app/cmdb/types/assetManage';
import type { RackRoomMode, ViewFocus, ViewType } from '../viewTypes';
import { eligibleModelIdsForView, resolveRackRoomMode } from '../viewEligibility';
import {
  filterNetworkModelIdsByCatalog,
  networkModelIdsFromInterfaceAssociations,
} from '../networkModelDiscovery';
import {
  buildBaseInfoPath,
  buildViewsPathPreserving,
  parseViewsSearch,
} from '../viewUrls';
import {
  clearViewFocus,
  pushViewRecent,
  readViewFocus,
  readViewFocusForMode,
  writeViewFocus,
} from '../viewMemory';
import ViewInstancePicker from './ViewInstancePicker';
import ViewCanvasHost from './ViewCanvasHost';
import HopDepthControl from '@/app/cmdb/(pages)/assetData/detail/relationships/networkTopo/HopDepthControl';
import {
  NETWORK_TOPO_DEFAULT_CENTER_HOP,
  type NetworkTopoHop,
} from '@/app/cmdb/(pages)/assetData/detail/relationships/networkTopo/hopDepth';

export interface ViewsWorkspaceShellProps {
  viewType: ViewType;
  children?: React.ReactNode;
}

const focusKey = (focus: ViewFocus | null): string =>
  focus ? `${focus.model_id}:${focus.inst_uuid}:${focus.mode ?? ''}` : '';

const ViewsWorkspaceShell: React.FC<ViewsWorkspaceShellProps> = ({
  viewType,
  children,
}) => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { userId } = useUserInfoContext();
  const common = useCommon();
  const { getModelAssociations } = useModelApi();
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
  /** Room focus to restore after drilling into a rack from the floor plan. */
  const [roomReturn, setRoomReturn] = useState<{
    focus: ViewFocus;
    rackId: string;
  } | null>(null);
  const [highlightRackId, setHighlightRackId] = useState<string | null>(null);
  const [networkHop, setNetworkHop] = useState<NetworkTopoHop>(
    NETWORK_TOPO_DEFAULT_CENTER_HOP
  );

  const hydratedRef = useRef(false);
  const lastSyncedKeyRef = useRef('');
  /** Last searchParams string we observed; null until first post-ready seed. */
  const lastSeenQueryRef = useRef<string | null>(null);
  /** Session cache: interface associations → network model ids (one request). */
  const networkModelsCacheRef = useRef<string[] | null>(null);
  // API helpers from useModelApi are new each render — use refs in effects.
  const getModelAssociationsRef = useRef(getModelAssociations);
  getModelAssociationsRef.current = getModelAssociations;
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
      if (!parsed.model_id || !parsed.inst_uuid) return null;
      let next = enrichFocus({
        model_id: parsed.model_id,
        inst_uuid: parsed.inst_uuid,
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

    if (parsed.model_id && parsed.inst_uuid) {
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

  // Discover network-capable models via one interface association query
  // (same rule as NetworkTopo / backend is_network_device_model). Avoid N× topo_themes.
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

    const catalogModelIds = modelIdsKey.split(',').filter(Boolean);
    let cancelled = false;
    const discover = async () => {
      setNetworkDiscovering(true);
      setNetworkDiscoveryDone(false);
      try {
        let networkIds = networkModelsCacheRef.current;
        if (!networkIds) {
          try {
            const assoc = await getModelAssociationsRef.current('interface');
            networkIds = networkModelIdsFromInterfaceAssociations(assoc);
          } catch {
            networkIds = [];
          }
          networkModelsCacheRef.current = networkIds;
        }
        const ids = filterNetworkModelIdsByCatalog(catalogModelIds, networkIds);
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
      setRoomReturn(null);
      setHighlightRackId(null);
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

    // External URL navigation abandons an in-memory room→rack drill stack.
    setRoomReturn(null);
    setHighlightRackId(null);

    setFocus((prev) => {
      if (viewType === 'network' && prev?.inst_uuid !== urlFocus?.inst_uuid) {
        setNetworkHop(NETWORK_TOPO_DEFAULT_CENTER_HOP);
      }
      return focusKey(prev) === focusKey(urlFocus) ? prev : urlFocus;
    });
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
        // Mode switch / picker clear: do not wipe the other rack-room mode slot.
        if (lastSyncedKeyRef.current !== '' || currentParams.toString()) {
          clearViewFocus(
            window.localStorage,
            userId,
            viewType,
            viewType === 'rack-room' ? mode : undefined
          );
        }
        lastSyncedKeyRef.current = '';
        const emptyPath =
          viewType === 'rack-room'
            ? `/cmdb/views/rack-room?mode=${mode}`
            : `/cmdb/views/${viewType}`;
        const emptyQuery = emptyPath.includes('?')
          ? emptyPath.slice(emptyPath.indexOf('?') + 1)
          : '';
        if (currentParams.toString() !== emptyQuery) {
          lastSeenQueryRef.current = emptyQuery;
          router.replace(emptyPath);
        }
      }
    },
    [userId, viewType, router, mode]
  );

  useEffect(() => {
    if (!ready) return;
    persistAndSync(focus);
  }, [focus, ready, persistAndSync]);

  const handleFocusChange = useCallback((next: ViewFocus | null) => {
    if (!next) {
      setRoomReturn(null);
      setHighlightRackId(null);
      setFocus(null);
      setNetworkHop(NETWORK_TOPO_DEFAULT_CENTER_HOP);
      return;
    }
    const enriched = enrichFocus(next);
    // Leaving the room→rack drill path (picker / other focus) clears Back.
    if (
      roomReturn
      && !(
        enriched.mode === 'rack'
        && enriched.model_id === 'rack'
      )
      && focusKey(enriched) !== focusKey(roomReturn.focus)
    ) {
      setRoomReturn(null);
    }
    // Keep Segmented `mode` in sync with focus.mode so rack-room eligibility
    // (I1) does not clear a rack focus that arrived while mode was still `room`.
    if (viewType === 'rack-room' && enriched.mode) {
      setMode(enriched.mode);
    }
    setFocus((prev) => {
      if (viewType === 'network' && prev?.inst_uuid !== enriched.inst_uuid) {
        setNetworkHop(NETWORK_TOPO_DEFAULT_CENTER_HOP);
      }
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
  }, [enrichFocus, viewType, roomReturn]);

  const handleRoomRackDrill = useCallback(
    (payload: {
      inst_uuid: string;
      inst_name?: string;
      fromRoom: ViewFocus;
    }) => {
      setHighlightRackId(null);
      const roomFocus = enrichFocus({ ...payload.fromRoom, mode: 'room' });
      // Park the room instance before focus flips to rack so Tab-back can restore it.
      if (userId) {
        writeViewFocus(window.localStorage, userId, 'rack-room', roomFocus);
      }
      setRoomReturn({
        focus: roomFocus,
        rackId: payload.inst_uuid,
      });
    },
    [enrichFocus, userId]
  );

  const handleBackToRoom = useCallback(() => {
    if (!roomReturn) return;
    const target = enrichFocus({ ...roomReturn.focus, mode: 'room' });
    const rackId = roomReturn.rackId;
    setRoomReturn(null);
    setMode('room');
    setFocus(target);
    // Clear first so returning to the same rack can re-trigger highlight.
    setHighlightRackId(null);
    window.setTimeout(() => {
      setHighlightRackId(rackId);
      window.setTimeout(() => {
        setHighlightRackId((current) => (current === rackId ? null : current));
      }, 2000);
    }, 0);
  }, [roomReturn, enrichFocus]);

  const handleModeChange = (nextMode: RackRoomMode) => {
    if (nextMode === mode) return;

    // Segmented "机房" while we still have a drill return target → same as Back.
    if (nextMode === 'room' && roomReturn) {
      handleBackToRoom();
      return;
    }

    // Park the current mode's instance before switching (do not wipe storage).
    if (userId && focus) {
      writeViewFocus(window.localStorage, userId, 'rack-room', {
        ...focus,
        mode,
      });
    }

    setRoomReturn(null);
    setHighlightRackId(null);
    setMode(nextMode);

    const remembered = userId
      ? readViewFocusForMode(
        window.localStorage,
        userId,
        'rack-room',
        nextMode
      )
      : null;
    const allowed = eligibleModelIdsForView('rack-room', nextMode);
    if (remembered && allowed.includes(remembered.model_id)) {
      setFocus(enrichFocus({ ...remembered, mode: nextMode }));
      return;
    }
    // Empty for this mode — other mode's memory stays in focusByMode.
    setFocus(null);
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
        {viewType === 'rack-room' && roomReturn && mode === 'rack' && (
          <Button type="link" className="px-0" onClick={handleBackToRoom}>
            {t('ViewsHub.backToRoom')}
          </Button>
        )}
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
        {viewType === 'network' && focus && (
          <HopDepthControl value={networkHop} onChange={setNetworkHop} />
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
            <CompactEmptyState description={t('ViewsHub.emptyHint')} />
          </div>
        ) : (
          <ViewCanvasHost
            viewType={viewType}
            focus={focus}
            onFocusChange={handleFocusChange}
            onRoomRackDrill={
              viewType === 'rack-room' ? handleRoomRackDrill : undefined
            }
            highlightRackId={
              viewType === 'rack-room' ? highlightRackId : undefined
            }
            networkCenterHop={viewType === 'network' ? networkHop : undefined}
            onNetworkCenterHopChange={
              viewType === 'network' ? setNetworkHop : undefined
            }
          >
            {children}
          </ViewCanvasHost>
        )}
      </div>
    </div>
  );
};

export default ViewsWorkspaceShell;
