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
import { eligibleModelIdsForView, resolveRackRoomMode, viewAllowsMultiSelect } from '../viewEligibility';
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
  readViewFocuses,
  readViewFocusesForMode,
  writeViewFocus,
  writeViewFocuses,
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

const focusesKey = (focuses: ViewFocus[]): string =>
  focuses.map((item) => focusKey(item)).join('|');

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

  const [focuses, setFocuses] = useState<ViewFocus[]>([]);
  const focus = focuses[0] ?? null;
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

  const focusesFromParsed = useCallback(
    (parsed: ReturnType<typeof parseViewsSearch>): ViewFocus[] => {
      if (!parsed.model_id || !parsed.inst_uuids.length) return [];
      const parsedMode =
        viewType === 'rack-room'
          ? resolveRackRoomMode(parsed.model_id, parsed.mode) ?? parsed.mode ?? 'room'
          : parsed.mode;
      const uuids = viewAllowsMultiSelect(viewType, parsedMode)
        ? parsed.inst_uuids
        : parsed.inst_uuids.slice(0, 1);
      return uuids.map((uuid, index) => {
        const next = enrichFocus({
          model_id: parsed.model_id!,
          inst_uuid: uuid,
          inst_name: index === 0 ? parsed.inst_name : undefined,
          model_name: parsed.model_name,
          icn: parsed.icn,
          mode: parsedMode,
        });
        return viewType === 'rack-room' && parsedMode
          ? { ...next, mode: parsedMode }
          : next;
      });
    },
    [enrichFocus, viewType]
  );

  // Hydrate focus from URL, then localStorage memory. Never auto-pick first instance.
  // Parent remounts this shell with key={viewType} so view switches start clean.
  useEffect(() => {
    if (hydratedRef.current) return;
    if (!userId) return;

    const parsed = parseViewsSearch(searchParams);
    let next: ViewFocus[] = [];

    if (parsed.model_id && parsed.inst_uuids.length) {
      next = focusesFromParsed(parsed);
    } else {
      const remembered = readViewFocuses(window.localStorage, userId, viewType);
      next = remembered.map((item) => {
        const enriched = enrichFocus(item);
        if (viewType !== 'rack-room') return enriched;
        const nextMode = resolveRackRoomMode(enriched.model_id, enriched.mode) ?? 'room';
        return { ...enriched, mode: nextMode };
      });
    }

    const nextMode = next[0]?.mode;
    if (viewType === 'rack-room' && nextMode) {
      setMode(nextMode);
    } else if (viewType === 'rack-room' && parsed.mode) {
      setMode(parsed.mode);
    }

    setFocuses(next);
    hydratedRef.current = true;
    setReady(true);
  }, [userId, viewType, searchParams, enrichFocus, focusesFromParsed]);

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
    if (!ready || !modelsReady || !focuses.length) return;
    if (focuses.some((item) => !eligibleModelIds.includes(item.model_id))) {
      setRoomReturn(null);
      setHighlightRackId(null);
      setFocuses([]);
    }
  }, [ready, modelsReady, eligibleModelIds, focuses]);

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
    const urlFocuses = focusesFromParsed(parsed);
    const urlFocus = urlFocuses[0] ?? null;

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

    setFocuses((prev) => {
      if (viewType === 'network' && prev[0]?.inst_uuid !== urlFocus?.inst_uuid) {
        setNetworkHop(NETWORK_TOPO_DEFAULT_CENTER_HOP);
      }
      return focusesKey(prev) === focusesKey(urlFocuses) ? prev : urlFocuses;
    });
  }, [ready, searchParams, focusesFromParsed, viewType]);

  const persistAndSync = useCallback(
    (next: ViewFocus[]) => {
      if (!userId) return;
      const currentParams = searchParamsRef.current;
      const key = focusesKey(next);
      if (next.length) {
        writeViewFocuses(window.localStorage, userId, viewType, next);
        if (key !== lastSyncedKeyRef.current) {
          next.forEach((item) => {
            pushViewRecent(window.localStorage, userId, viewType, item);
          });
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
    persistAndSync(focuses);
  }, [focuses, ready, persistAndSync]);

  const applyFocuses = useCallback((next: ViewFocus[]) => {
    const enriched = next.map((item) => enrichFocus(item));
    if (!enriched.length) {
      setRoomReturn(null);
      setHighlightRackId(null);
      setFocuses([]);
      setNetworkHop(NETWORK_TOPO_DEFAULT_CENTER_HOP);
      return;
    }
    const primary = enriched[0];
    if (
      roomReturn
      && !(
        primary.mode === 'rack'
        && primary.model_id === 'rack'
      )
      && focusKey(primary) !== focusKey(roomReturn.focus)
    ) {
      setRoomReturn(null);
    }
    if (viewType === 'rack-room' && primary.mode) {
      setMode(primary.mode);
    }
    setFocuses((prev) => {
      if (viewType === 'network' && prev[0]?.inst_uuid !== primary.inst_uuid) {
        setNetworkHop(NETWORK_TOPO_DEFAULT_CENTER_HOP);
      }
      if (focusesKey(prev) === focusesKey(enriched)) {
        const merged = enriched.map((item, index) => ({
          ...item,
          inst_name: item.inst_name || prev[index]?.inst_name,
          model_name: item.model_name || prev[index]?.model_name,
          icn: item.icn || prev[index]?.icn,
        }));
        const unchanged = merged.every((item, index) => (
          prev[index]
          && prev[index].inst_name === item.inst_name
          && prev[index].model_name === item.model_name
          && prev[index].icn === item.icn
        ));
        return unchanged ? prev : merged;
      }
      return enriched;
    });
  }, [enrichFocus, viewType, roomReturn]);

  const handleFocusChange = useCallback((next: ViewFocus | null) => {
    applyFocuses(next ? [next] : []);
  }, [applyFocuses]);

  const handleFocusesChange = useCallback((next: ViewFocus[]) => {
    applyFocuses(next);
  }, [applyFocuses]);

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
    setFocuses([target]);
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
    if (userId && focuses.length) {
      writeViewFocuses(
        window.localStorage,
        userId,
        'rack-room',
        focuses.map((item) => ({ ...item, mode }))
      );
    }

    setRoomReturn(null);
    setHighlightRackId(null);
    setMode(nextMode);

    const remembered = userId
      ? readViewFocusesForMode(
        window.localStorage,
        userId,
        'rack-room',
        nextMode
      )
      : [];
    const allowed = eligibleModelIdsForView('rack-room', nextMode);
    const restored = remembered
      .filter((item) => allowed.includes(item.model_id))
      .map((item) => enrichFocus({ ...item, mode: nextMode }));
    setFocuses(restored);
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
          focuses={focuses}
          onFocusChange={handleFocusChange}
          onFocusesChange={handleFocusesChange}
        />
        {networkDiscovering && viewType === 'network' && (
          <Spin size="small" />
        )}
        {viewType === 'network' && focus && (
          <HopDepthControl value={networkHop} onChange={setNetworkHop} />
        )}
        <div className="ml-auto shrink-0">
          {focus && focuses.length === 1 && (
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
            focuses={focuses}
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
