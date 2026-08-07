import type { NetworkTopologyLayoutMode } from '@/app/cmdb/components/networkTopology';
import { applyNodePositionOverrides } from '@/app/cmdb/components/networkTopology/graphModel';
import type { NetworkTopologyLayoutResult } from '@/app/cmdb/components/networkTopology/types';
import type {
  NetworkStatusTopologyConfig,
  NetworkStatusTopologyLayoutMode,
  NetworkStatusTopologyModeLayout,
} from '@/app/ops-analysis/types/sceneWidget';

export {
  MANUAL_EDGE_VERTEX_COLLINEAR_TOLERANCE,
  MANUAL_EDGE_VERTEX_MIN_SEGMENT,
  normalizeManualEdgeVertices,
} from '@/app/cmdb/components/networkTopology/edgeGeometry';
export type { EdgeGeometryPoint } from '@/app/cmdb/components/networkTopology/edgeGeometry';

export const DEFAULT_NETWORK_STATUS_TOPOLOGY_LAYOUT_MODE: NetworkTopologyLayoutMode =
  'hierarchical';

export interface TopologyPoint { x: number; y: number }

export type TopologyNodePositions = Record<string, TopologyPoint>;
export type TopologyLinkVertices = Record<string, TopologyPoint[]>;

export type ResolvedLinkEdgeGeometry =
  | {
      kind: 'manual';
      vertices: TopologyPoint[];
      parallelOffset: 0;
    }
  | {
      kind: 'parallel';
      vertices: [];
      parallelOffset: number;
    };

export const normalizeNetworkStatusTopologyLayoutMode = (
  value?: string | null,
): NetworkTopologyLayoutMode => {
  if (value === 'force' || value === 'circular' || value === 'hierarchical') {
    return value;
  }
  return DEFAULT_NETWORK_STATUS_TOPOLOGY_LAYOUT_MODE;
};

/** 画布编辑态且非分享、且有写回回调时才允许持久化布局 */
export const canPersistNetworkStatusTopologyLayout = ({
  layoutEditable = false,
  shareMode = false,
  hasWriteback = false,
}: {
  layoutEditable?: boolean;
  shareMode?: boolean;
  hasWriteback?: boolean;
}): boolean => Boolean(layoutEditable && !shareMode && hasWriteback);

export const applyNodePositionsToLayout = (
  layout: NetworkTopologyLayoutResult,
  nodePositions?: TopologyNodePositions | null,
): NetworkTopologyLayoutResult => {
  if (!nodePositions || Object.keys(nodePositions).length === 0) {
    return layout;
  }
  const overrides = new Map<string, TopologyPoint>();
  Object.entries(nodePositions).forEach(([id, point]) => {
    if (
      !point ||
      !Number.isFinite(point.x) ||
      !Number.isFinite(point.y)
    ) {
      return;
    }
    overrides.set(String(id), { x: point.x, y: point.y });
  });
  if (overrides.size === 0) {
    return layout;
  }
  return applyNodePositionOverrides(layout, overrides);
};

/**
 * 网络状态拓扑节点在 X6 中的 cell 原点相对布局坐标的偏移。
 * 与 statusTopologyGraph 中 NODE_WIDTH / ICON_CENTER_Y 保持一致。
 */
export const STATUS_TOPOLOGY_CELL_OFFSET = {
  width: 160,
  iconCenterY: 40,
} as const;

/** 布局算法坐标 → X6 cell 左上角 */
export const layoutPointToCellPosition = (point: TopologyPoint): TopologyPoint => ({
  x: point.x - STATUS_TOPOLOGY_CELL_OFFSET.width / 2,
  y: point.y - STATUS_TOPOLOGY_CELL_OFFSET.iconCenterY,
});

/** X6 cell 左上角 → 布局算法坐标 */
export const cellPositionToLayoutPoint = (point: TopologyPoint): TopologyPoint => ({
  x: point.x + STATUS_TOPOLOGY_CELL_OFFSET.width / 2,
  y: point.y + STATUS_TOPOLOGY_CELL_OFFSET.iconCenterY,
});

const normalizeVertices = (
  vertices?: TopologyPoint[] | null,
): TopologyPoint[] =>
  (vertices || [])
    .filter(
      (point) =>
        point && Number.isFinite(point.x) && Number.isFinite(point.y),
    )
    .map((point) => ({ x: point.x, y: point.y }));

export const resolveLinkEdgeGeometry = ({
  parallelOffset = 0,
  manualVertices,
}: {
  parallelOffset?: number;
  manualVertices?: TopologyPoint[] | null;
}): ResolvedLinkEdgeGeometry => {
  const vertices = normalizeVertices(manualVertices);
  if (vertices.length > 0) {
    return {
      kind: 'manual',
      vertices,
      parallelOffset: 0,
    };
  }
  return {
    kind: 'parallel',
    vertices: [],
    parallelOffset: Number(parallelOffset) || 0,
  };
};

const hasOwnEntries = (value?: Record<string, unknown> | null) =>
  !!value && Object.keys(value).length > 0;

const cloneModeLayout = (
  layout?: NetworkStatusTopologyModeLayout | null,
): NetworkStatusTopologyModeLayout | undefined => {
  if (!layout) return undefined;
  const next: NetworkStatusTopologyModeLayout = {};
  if (hasOwnEntries(layout.nodePositions as Record<string, unknown> | undefined)) {
    next.nodePositions = { ...layout.nodePositions };
  }
  if (hasOwnEntries(layout.linkVertices as Record<string, unknown> | undefined)) {
    next.linkVertices = { ...layout.linkVertices };
  }
  return hasOwnEntries(next as Record<string, unknown>) ? next : undefined;
};

const pruneModeLayout = (
  layout: NetworkStatusTopologyModeLayout | undefined,
  nodeIdSet: Set<string>,
  linkIdSet: Set<string>,
): NetworkStatusTopologyModeLayout | undefined => {
  if (!layout) return undefined;
  const nodePositions = Object.fromEntries(
    Object.entries(layout.nodePositions || {}).filter(([id]) =>
      nodeIdSet.has(String(id)),
    ),
  );
  const linkVertices = Object.fromEntries(
    Object.entries(layout.linkVertices || {}).filter(([id]) =>
      linkIdSet.has(String(id)),
    ),
  );
  return cloneModeLayout({
    ...(Object.keys(nodePositions).length > 0 ? { nodePositions } : {}),
    ...(Object.keys(linkVertices).length > 0 ? { linkVertices } : {}),
  });
};

/**
 * 解析指定 layoutMode 下应应用的手工几何。
 * 优先 layoutByMode[mode]；若无桶且存在旧扁平字段，仅当 mode 等于配置中的 layoutMode
 * （缺省 hierarchical）时回退到扁平字段。
 */
export const resolveLayoutGeometry = (
  config: Pick<
    NetworkStatusTopologyConfig,
    'layoutMode' | 'layoutByMode' | 'nodePositions' | 'linkVertices'
  > | null | undefined,
  mode: NetworkStatusTopologyLayoutMode,
): NetworkStatusTopologyModeLayout => {
  const bucket = cloneModeLayout(config?.layoutByMode?.[mode]);
  if (bucket) {
    return bucket;
  }

  const legacyMode = normalizeNetworkStatusTopologyLayoutMode(config?.layoutMode);
  if (mode !== legacyMode) {
    return {};
  }

  return (
    cloneModeLayout({
      nodePositions: config?.nodePositions,
      linkVertices: config?.linkVertices,
    }) || {}
  );
};

const persistLayoutByMode = (
  layoutByMode?: NetworkStatusTopologyConfig['layoutByMode'],
): NetworkStatusTopologyConfig['layoutByMode'] | undefined => {
  if (!layoutByMode) return undefined;
  const next: NonNullable<NetworkStatusTopologyConfig['layoutByMode']> = {};
  (['hierarchical', 'force', 'circular'] as NetworkStatusTopologyLayoutMode[]).forEach(
    (mode) => {
      const bucket = cloneModeLayout(layoutByMode[mode]);
      if (bucket) {
        next[mode] = bucket;
      }
    },
  );
  return Object.keys(next).length > 0 ? next : undefined;
};

export const buildPersistedNetworkStatusTopologyConfig = (
  config: NetworkStatusTopologyConfig,
): NetworkStatusTopologyConfig => {
  const layoutMode = config.layoutMode
    ? normalizeNetworkStatusTopologyLayoutMode(config.layoutMode)
    : undefined;

  // 若只有旧扁平字段、尚无分桶，写入时迁入当时 layoutMode 桶
  let layoutByMode = persistLayoutByMode(config.layoutByMode);
  if (
    !layoutByMode &&
    (hasOwnEntries(config.nodePositions as Record<string, unknown> | undefined) ||
      hasOwnEntries(config.linkVertices as Record<string, unknown> | undefined))
  ) {
    const legacyMode = layoutMode || DEFAULT_NETWORK_STATUS_TOPOLOGY_LAYOUT_MODE;
    const legacyBucket = cloneModeLayout({
      nodePositions: config.nodePositions,
      linkVertices: config.linkVertices,
    });
    if (legacyBucket) {
      layoutByMode = { [legacyMode]: legacyBucket };
    }
  }

  const next: NetworkStatusTopologyConfig = {
    modelId: config.modelId || '',
    instId: config.instId || '',
    depth: config.depth || 2,
  };

  if (layoutMode) {
    next.layoutMode = layoutMode;
  }
  if (layoutByMode) {
    next.layoutByMode = layoutByMode;
  }
  return next;
};

export const pruneNetworkStatusTopologyLayout = (
  layout: Pick<
    NetworkStatusTopologyConfig,
    'layoutMode' | 'layoutByMode' | 'nodePositions' | 'linkVertices'
  >,
  nodeIds: Iterable<string>,
  linkIds: Iterable<string>,
): Pick<
  NetworkStatusTopologyConfig,
  'layoutMode' | 'layoutByMode'
> => {
  const nodeIdSet = new Set(Array.from(nodeIds, String));
  const linkIdSet = new Set(Array.from(linkIds, String));

  // 先归一成 layoutByMode（含旧扁平迁入），再修剪各桶
  const normalized = buildPersistedNetworkStatusTopologyConfig({
    modelId: '',
    instId: '',
    depth: 2,
    layoutMode: layout.layoutMode,
    layoutByMode: layout.layoutByMode,
    nodePositions: layout.nodePositions,
    linkVertices: layout.linkVertices,
  });

  const prunedByMode: NonNullable<NetworkStatusTopologyConfig['layoutByMode']> = {};
  (['hierarchical', 'force', 'circular'] as NetworkStatusTopologyLayoutMode[]).forEach(
    (mode) => {
      const pruned = pruneModeLayout(
        normalized.layoutByMode?.[mode],
        nodeIdSet,
        linkIdSet,
      );
      if (pruned) {
        prunedByMode[mode] = pruned;
      }
    },
  );

  return {
    ...(normalized.layoutMode ? { layoutMode: normalized.layoutMode } : {}),
    ...(Object.keys(prunedByMode).length > 0 ? { layoutByMode: prunedByMode } : {}),
  };
};

/** 只清空指定 mode 的手工几何，保留其它桶与当前 layoutMode */
export const resetNetworkStatusTopologyLayout = (
  config: NetworkStatusTopologyConfig,
  mode?: NetworkStatusTopologyLayoutMode | null,
): NetworkStatusTopologyConfig => {
  const layoutMode = normalizeNetworkStatusTopologyLayoutMode(
    mode ?? config.layoutMode,
  );
  const normalized = buildPersistedNetworkStatusTopologyConfig(config);
  const layoutByMode = { ...(normalized.layoutByMode || {}) };
  delete layoutByMode[layoutMode];

  const next: NetworkStatusTopologyConfig = {
    modelId: config.modelId || '',
    instId: config.instId || '',
    depth: config.depth || 2,
    layoutMode: normalizeNetworkStatusTopologyLayoutMode(
      config.layoutMode ?? layoutMode,
    ),
  };
  if (Object.keys(layoutByMode).length > 0) {
    next.layoutByMode = layoutByMode;
  }
  return next;
};

/** 将几何补丁写入指定 mode 桶，其它桶保持不变 */
export const patchLayoutByMode = (
  config: NetworkStatusTopologyConfig,
  mode: NetworkStatusTopologyLayoutMode,
  patch: NetworkStatusTopologyModeLayout,
): NetworkStatusTopologyConfig['layoutByMode'] => {
  const normalized = buildPersistedNetworkStatusTopologyConfig(config);
  const layoutByMode = { ...(normalized.layoutByMode || {}) };
  const current = cloneModeLayout(layoutByMode[mode]) || {};
  const nextBucket = cloneModeLayout({
    nodePositions:
      patch.nodePositions !== undefined
        ? patch.nodePositions
        : current.nodePositions,
    linkVertices:
      patch.linkVertices !== undefined
        ? patch.linkVertices
        : current.linkVertices,
  });
  if (nextBucket) {
    layoutByMode[mode] = nextBucket;
  } else {
    delete layoutByMode[mode];
  }
  return Object.keys(layoutByMode).length > 0 ? layoutByMode : undefined;
};
