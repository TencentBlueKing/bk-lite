import {
  readBinding,
  type ArchitectureNodeStatusItem,
} from './model';

/** Matches ArchitectureNodeStatusService.MAX_INST_UUIDS. One request stays inside that cap. */
export const ARCHITECTURE_STATUS_BATCH_SIZE = 500;

export type OverlayLabel =
  | { type: 'text'; value: string }
  | { type: 'invalid' }
  | { type: 'forbidden' }
  | { type: 'unknown' }
  | { type: 'empty' }
  | { type: 'pending' };

/** Locale key of each resource status, shared by the binding and detail drawers. */
export const STATUS_LABEL_KEY: Record<ArchitectureNodeStatusItem['status'], string> = {
  normal: 'opsAnalysis.architecture.statusNormal',
  warning: 'opsAnalysis.architecture.statusWarning',
  critical: 'opsAnalysis.architecture.statusCritical',
  unmonitored: 'opsAnalysis.architecture.statusUnmonitored',
  unknown: 'opsAnalysis.architecture.statusUnknown',
  invalid: 'opsAnalysis.architecture.bindingInvalid',
  forbidden: 'opsAnalysis.architecture.bindingForbidden',
};

/**
 * Status dot colours, the same values as Isoflow's NODE_STATUS_COLOR (the
 * Isoflow bundle is loaded client-side only, so its values are not imported here).
 */
export const STATUS_DOT_COLOR: Record<ArchitectureNodeStatusItem['status'], string> = {
  normal: '#27C274',
  warning: '#FFAD42',
  critical: '#F43B2C',
  unmonitored: '#9ca3af',
  unknown: '#9ca3af',
  invalid: '#c2410c',
  forbidden: '#9ca3af',
};

/** A bound resource waits for its status until the status request settles. */
export function bindingStatusLoading(
  bound: boolean,
  status: ArchitectureNodeStatusItem | null | undefined,
  phase: 'idle' | 'ready' | 'failed',
): boolean {
  return bound && !status && phase !== 'failed';
}

export interface RectangleOverlay {
  label?: OverlayLabel;
  /** Unique bound resource uuids inside the area. */
  resourceCount?: number;
  /** Severe alerts inside the area, counted once per monitor instance. */
  criticalCount?: number;
  /** Warning alerts inside the area, including info, counted once per monitor instance. */
  warningCount?: number;
  /** Severe plus warning alerts inside the area, counted once per monitor instance. */
  alertTotal?: number;
}

export interface RegionAlertBadgePart {
  level: 'critical' | 'warning';
  text: string;
}

/** Severe first. A zero count is omitted. Labels are the localized level names. */
export function regionAlertBadgeParts(
  counts: { criticalCount?: number; warningCount?: number },
  labels: { critical: string; warning: string },
): RegionAlertBadgePart[] {
  const parts: RegionAlertBadgePart[] = [];
  const criticalCount = counts.criticalCount ?? 0;
  const warningCount = counts.warningCount ?? 0;
  if (criticalCount > 0) parts.push({ level: 'critical', text: `${labels.critical} ${criticalCount}` });
  if (warningCount > 0) parts.push({ level: 'warning', text: `${labels.warning} ${warningCount}` });
  return parts;
}

/**
 * Region corner badge: the number is the deduped total (severe + warning, the same total the
 * hover text reports); the colour is the highest active level. Null when the region has no alerts.
 */
export function regionAlertBadge(
  counts: { criticalCount?: number; warningCount?: number },
): { level: 'critical' | 'warning'; count: number } | null {
  const criticalCount = counts.criticalCount ?? 0;
  const warningCount = counts.warningCount ?? 0;
  const count = criticalCount + warningCount;
  if (count <= 0) return null;
  return { level: criticalCount > 0 ? 'critical' : 'warning', count };
}

export const RESOURCE_NAME_PLATE_LIMIT = 16;
export const DEFAULT_ICON_TITLE = 'Untitled';

export type IconPlateLine = 'forbidden' | 'invalid';

export interface IconPlate {
  /** Shown instead of the icon name. Set when the icon name is empty or Untitled. */
  title?: string;
  /** Second line, or a sentinel the host translates. */
  subtitle?: string;
  line?: IconPlateLine;
  hoverName: string;
  hoverModel: string;
  alertCount?: number;
  alertLevel?: string;
}

export interface IconOverlay {
  level: ArchitectureNodeStatusItem['status'];
  count?: number;
  hint?: 'unmonitored' | 'unknown' | 'forbidden' | 'invalid';
  badgeName?: string;
  badgeLevel?: string;
}

export interface IconBindingStats {
  bound: number;
  total: number;
  boundIds: string[];
  unboundIds: string[];
}

export interface RegionList {
  icons: ResourceLine[];
}

export interface ResourceLine {
  key: string;
  instUuid: string;
  modelId: string;
  highlightId?: string;
  clickable: boolean;
  title: OverlayLabel;
  level: ArchitectureNodeStatusItem['status'] | null;
  alertCount: number | null;
  iconName?: string;
}

export type DiagramClickAction =
  | { type: 'close' }
  | { type: 'toast'; reason: 'unbound' | 'invalid' | 'forbidden' }
  | { type: 'resource'; instUuid: string; modelId: string; highlightId?: string }
  | { type: 'region'; rectangleId: string }
  | { type: 'connector'; connectorId: string };

const STATUS_LEVELS = new Set<ArchitectureNodeStatusItem['status']>([
  'normal',
  'warning',
  'critical',
  'unmonitored',
  'unknown',
  'invalid',
  'forbidden',
]);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object';

const asViews = (views: unknown): Record<string, unknown>[] =>
  Array.isArray(views) ? views.filter(isRecord) : [];

const readCoord = (value: unknown): { x: number; y: number } | null => {
  if (!isRecord(value) || typeof value.x !== 'number' || typeof value.y !== 'number') {
    return null;
  }
  return { x: value.x, y: value.y };
};

export function architectureStatusRequestMode(input: {
  shareMode: boolean;
  editMode: boolean;
}): 'off' | 'once' | 'poll' {
  if (input.shareMode) return 'off';
  if (input.editMode) return 'once';
  return 'poll';
}

export function shouldPauseArchitectureStatusRefresh(hidden: boolean): boolean {
  return hidden;
}

export function unknownStatusItem(instUuid: string): ArchitectureNodeStatusItem {
  return {
    inst_uuid: instUuid,
    status: 'unknown',
    alert_count: 0,
    max_level: null,
    monitor_id: '',
    model_id: '',
    inst_name: '',
    level_counts: { critical: 0, error: 0, warning: 0 },
  };
}

export function unknownStatusMap(uuids: string[]): Record<string, ArchitectureNodeStatusItem> {
  return Object.fromEntries(uuids.map((uuid) => [uuid, unknownStatusItem(uuid)]));
}

const finiteCount = (value: unknown): number => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return 0;
  return Math.floor(value);
};

const coerceLevelCounts = (
  raw: unknown,
): ArchitectureNodeStatusItem['level_counts'] | undefined => {
  if (!isRecord(raw)) return undefined;
  return {
    critical: finiteCount(raw.critical),
    error: finiteCount(raw.error),
    warning: finiteCount(raw.warning),
  };
};

const coerceStatusItem = (raw: unknown): ArchitectureNodeStatusItem | null => {
  if (!isRecord(raw) || typeof raw.inst_uuid !== 'string' || !raw.inst_uuid.trim()) {
    return null;
  }
  const status = STATUS_LEVELS.has(raw.status as ArchitectureNodeStatusItem['status'])
    ? raw.status as ArchitectureNodeStatusItem['status']
    : 'unknown';
  const alertCount = typeof raw.alert_count === 'number' && Number.isFinite(raw.alert_count)
    ? raw.alert_count
    : 0;
  const item: ArchitectureNodeStatusItem = {
    inst_uuid: raw.inst_uuid.trim(),
    status,
    alert_count: alertCount,
    max_level: typeof raw.max_level === 'string' ? raw.max_level : null,
    monitor_id: typeof raw.monitor_id === 'string' ? raw.monitor_id : '',
    model_id: typeof raw.model_id === 'string' ? raw.model_id : '',
    inst_name: typeof raw.inst_name === 'string' ? raw.inst_name : '',
  };
  const levelCounts = coerceLevelCounts(raw.level_counts);
  if (levelCounts) item.level_counts = levelCounts;
  return item;
};

export function chunkBoundUuids(
  uuids: string[],
  size = ARCHITECTURE_STATUS_BATCH_SIZE,
): string[][] {
  if (!uuids.length) return [];
  const step = Number.isFinite(size) && size > 0 ? Math.floor(size) : uuids.length;
  const batches: string[][] = [];
  for (let index = 0; index < uuids.length; index += step) {
    batches.push(uuids.slice(index, index + step));
  }
  return batches;
}

export function combineStatusBatches(
  batches: Array<{ uuids: string[]; ok: boolean; items?: unknown }>,
  previous: Record<string, ArchitectureNodeStatusItem>,
): { byUuid: Record<string, ArchitectureNodeStatusItem>; failed: boolean } {
  const byUuid: Record<string, ArchitectureNodeStatusItem> = {};
  let failed = false;
  for (const batch of batches) {
    if (batch.ok) {
      Object.assign(byUuid, mergeStatusResponse(batch.uuids, batch.items));
      continue;
    }
    failed = true;
    const kept = keptStatusForRequest(previous, batch.uuids);
    Object.assign(byUuid, kept);
    for (const uuid of batch.uuids) {
      if (!byUuid[uuid]) byUuid[uuid] = unknownStatusItem(uuid);
    }
  }
  return { byUuid, failed };
}

export function mergeStatusResponse(
  uuids: string[],
  items: unknown,
): Record<string, ArchitectureNodeStatusItem> {
  const indexed: Record<string, ArchitectureNodeStatusItem> = {};
  const list = Array.isArray(items) ? items : [];
  for (const item of list) {
    const row = coerceStatusItem(item);
    if (row) indexed[row.inst_uuid] = row;
  }
  return Object.fromEntries(uuids.map((uuid) => [uuid, indexed[uuid] ?? unknownStatusItem(uuid)]));
}

export function collectBoundUuids(views: unknown): string[] {
  const found: string[] = [];
  for (const view of asViews(views)) {
    if (!Array.isArray(view.items)) continue;
    for (const entry of view.items) {
      const binding = isRecord(entry) ? readBinding(entry.bkBinding) : null;
      if (binding) found.push(binding.inst_uuid);
    }
  }
  return Array.from(new Set(found)).sort();
}

export function resourceTitle(
  status: ArchitectureNodeStatusItem | undefined,
  modelNames: Record<string, string>,
): OverlayLabel {
  if (!status) return { type: 'pending' };
  if (status.status === 'invalid') return { type: 'invalid' };
  if (status.status === 'forbidden') return { type: 'forbidden' };
  if (!status.inst_name) return { type: 'unknown' };
  const typeName = modelNames[status.model_id] || status.model_id;
  return {
    type: 'text',
    value: typeName ? `${status.inst_name} · ${typeName}` : status.inst_name,
  };
}

export function resourceClickable(status: ArchitectureNodeStatusItem | undefined): boolean {
  if (!status) return true;
  return status.status !== 'invalid' && status.status !== 'forbidden';
}

const tileInside = (
  tile: { x: number; y: number },
  from: { x: number; y: number },
  to: { x: number; y: number },
) => {
  const minX = Math.min(from.x, to.x);
  const maxX = Math.max(from.x, to.x);
  const minY = Math.min(from.y, to.y);
  const maxY = Math.max(from.y, to.y);
  return tile.x >= minX && tile.x <= maxX && tile.y >= minY && tile.y <= maxY;
};

interface PlacedIcon {
  id: string;
  tile: { x: number; y: number } | null;
  instUuid: string | null;
  modelId: string | null;
}

interface BoundIcon {
  id: string;
  tile: { x: number; y: number };
  instUuid: string;
  modelId: string;
}

const placedIcons = (view: Record<string, unknown>): PlacedIcon[] => {
  if (!Array.isArray(view.items)) return [];
  const icons: PlacedIcon[] = [];
  for (const entry of view.items) {
    if (!isRecord(entry) || typeof entry.id !== 'string') continue;
    const binding = readBinding(entry.bkBinding);
    icons.push({
      id: entry.id,
      tile: readCoord(entry.tile),
      instUuid: binding?.inst_uuid ?? null,
      modelId: binding?.model_id ?? null,
    });
  }
  return icons;
};

const boundIcons = (view: Record<string, unknown>): BoundIcon[] => {
  const icons: BoundIcon[] = [];
  for (const icon of placedIcons(view)) {
    if (!icon.tile || !icon.instUuid || !icon.modelId) continue;
    icons.push({
      id: icon.id,
      tile: icon.tile,
      instUuid: icon.instUuid,
      modelId: icon.modelId,
    });
  }
  return icons;
};

export function iconBindingStats(views: unknown): IconBindingStats {
  const boundIds: string[] = [];
  const unboundIds: string[] = [];
  for (const view of asViews(views)) {
    for (const icon of placedIcons(view)) {
      if (icon.instUuid && icon.modelId) boundIds.push(icon.id);
      else unboundIds.push(icon.id);
    }
  }
  return {
    bound: boundIds.length,
    total: boundIds.length + unboundIds.length,
    boundIds,
    unboundIds,
  };
}

export function rectangleIconCounts(
  views: unknown,
  rectangleId: string,
): { total: number; bound: number } {
  const found = findEntry(views, 'rectangles', rectangleId);
  if (!found) return { total: 0, bound: 0 };
  const from = readCoord(found.entry.from);
  const to = readCoord(found.entry.to);
  if (!from || !to) return { total: 0, bound: 0 };
  const inside = placedIcons(found.view).filter((icon) => icon.tile && tileInside(icon.tile, from, to));
  return {
    total: inside.length,
    bound: inside.filter((icon) => Boolean(icon.instUuid && icon.modelId)).length,
  };
}

export function keptStatusForRequest(
  cached: Record<string, ArchitectureNodeStatusItem>,
  requested: string[],
): Record<string, ArchitectureNodeStatusItem> {
  const next: Record<string, ArchitectureNodeStatusItem> = {};
  for (const uuid of requested) {
    const row = cached[uuid];
    if (row) next[uuid] = row;
  }
  return next;
}

export function truncateResourceName(name: string, limit = RESOURCE_NAME_PLATE_LIMIT): string {
  const chars = Array.from(name);
  if (chars.length <= limit) return name;
  return `${chars.slice(0, limit).join('')}…`;
}

const blankIconTitle = (name: string) => {
  const trimmed = name.trim();
  return !trimmed || trimmed === DEFAULT_ICON_TITLE;
};

export function buildIconPlates(
  views: unknown,
  statusByUuid: Record<string, ArchitectureNodeStatusItem>,
  modelNames: Record<string, string>,
  iconNames: Record<string, string>,
  options?: { nameAndType?: boolean },
): Record<string, IconPlate> {
  const plates: Record<string, IconPlate> = {};
  for (const view of asViews(views)) {
    for (const icon of boundIcons(view)) {
      const status = statusByUuid[icon.instUuid];
      if (!status) continue;
      const modelName = modelNames[status.model_id] || status.model_id || '';
      const alerting = status.status === 'warning' || status.status === 'critical';
      const plate: IconPlate = {
        hoverName: status.inst_name.trim(),
        hoverModel: modelName,
      };
      if (alerting && Number.isFinite(status.alert_count)) {
        plate.alertCount = status.alert_count;
        plate.alertLevel = status.max_level || status.status;
      }
      if (status.status === 'forbidden' || status.status === 'invalid') {
        plate.line = status.status;
        plates[icon.id] = plate;
        continue;
      }
      const resourceName = status.inst_name.trim();
      if (!resourceName) continue;
      const iconName = (iconNames[icon.id] ?? '').trim();
      if (options?.nameAndType) {
        delete plate.alertCount;
        delete plate.alertLevel;
        if (blankIconTitle(iconName)) {
          const shortName = truncateResourceName(resourceName, 12);
          plate.title = modelName ? `${shortName} · ${modelName}` : shortName;
        }
        plates[icon.id] = plate;
        continue;
      }
      if (blankIconTitle(iconName)) {
        plate.title = truncateResourceName(resourceName);
      }
      plates[icon.id] = plate;
    }
  }
  return plates;
}

export function buildNodeStatus(
  views: unknown,
  statusByUuid: Record<string, ArchitectureNodeStatusItem>,
): Record<string, IconOverlay> {
  const overlays: Record<string, IconOverlay> = {};
  for (const view of asViews(views)) {
    for (const icon of boundIcons(view)) {
      const status = statusByUuid[icon.instUuid];
      if (!status) continue;
      const overlay: IconOverlay = { level: status.status };
      if (status.status === 'warning' || status.status === 'critical') {
        if (Number.isFinite(status.alert_count)) overlay.count = status.alert_count;
        overlay.badgeName = status.inst_name || status.inst_uuid;
        overlay.badgeLevel = status.max_level || status.status;
      } else if (
        status.status === 'unmonitored'
        || status.status === 'unknown'
        || status.status === 'forbidden'
        || status.status === 'invalid'
      ) {
        overlay.hint = status.status;
      }
      overlays[icon.id] = overlay;
    }
  }
  return overlays;
}

export function buildRectangleOverlays(
  views: unknown,
  statusByUuid: Record<string, ArchitectureNodeStatusItem>,
  options: { followBorders: boolean },
): Record<string, RectangleOverlay> {
  const overlays: Record<string, RectangleOverlay> = {};
  for (const view of asViews(views)) {
    if (!Array.isArray(view.rectangles)) continue;
    const icons = boundIcons(view);
    for (const entry of view.rectangles) {
      if (!isRecord(entry) || typeof entry.id !== 'string') continue;
      const from = readCoord(entry.from);
      const to = readCoord(entry.to);
      const overlay: RectangleOverlay = {};
      if (options.followBorders && entry.bkFollowAlert === true && from && to) {
        const inside = icons.filter((icon) => tileInside(icon.tile, from, to));
        const resources = new Map<string, ArchitectureNodeStatusItem>();
        for (const icon of inside) {
          const status = statusByUuid[icon.instUuid];
          if (!status || resources.has(icon.instUuid)) continue;
          resources.set(icon.instUuid, status);
        }
        let alertTotal = 0;
        let criticalCount = 0;
        let warningCount = 0;
        const seenMonitors = new Set<string>();
        for (const status of resources.values()) {
          const counted = countResourceAlerts(status, seenMonitors);
          criticalCount += counted.critical;
          warningCount += counted.warning;
          alertTotal += counted.critical + counted.warning;
        }
        overlay.resourceCount = resources.size;
        overlay.criticalCount = criticalCount;
        overlay.warningCount = warningCount;
        overlay.alertTotal = alertTotal;
      }
      if (overlay.label || overlay.resourceCount !== undefined) {
        overlays[entry.id] = overlay;
      }
    }
  }
  return overlays;
}

const findEntry = (
  views: unknown,
  collection: 'items' | 'rectangles' | 'connectors',
  id: string,
): { view: Record<string, unknown>; entry: Record<string, unknown> } | null => {
  for (const view of asViews(views)) {
    if (!Array.isArray(view[collection])) continue;
    const entry = view[collection].find((item) => isRecord(item) && item.id === id);
    if (isRecord(entry)) return { view, entry };
  }
  return null;
};

const lineFromBinding = (
  key: string,
  binding: { inst_uuid: string; model_id: string },
  statusByUuid: Record<string, ArchitectureNodeStatusItem>,
  modelNames: Record<string, string>,
  highlightId?: string,
  iconName?: string,
): ResourceLine => {
  const status = statusByUuid[binding.inst_uuid];
  return {
    key,
    instUuid: binding.inst_uuid,
    modelId: binding.model_id || status?.model_id || '',
    highlightId,
    clickable: resourceClickable(status),
    title: resourceTitle(status, modelNames),
    level: status?.status ?? null,
    alertCount: status ? status.alert_count : null,
    iconName: iconName || undefined,
  };
};

/** Severe = critical + error. Warning = warning plus info and any other non-severe level. One monitor instance counts once. */
const countResourceAlerts = (
  status: ArchitectureNodeStatusItem,
  seenMonitors: Set<string>,
): { critical: number; warning: number } => {
  const monitorId = status.monitor_id.trim();
  if (monitorId) {
    if (seenMonitors.has(monitorId)) return { critical: 0, warning: 0 };
    seenMonitors.add(monitorId);
  }
  const levels = status.level_counts;
  if (levels) {
    return {
      critical: levels.critical + levels.error,
      warning: levels.warning,
    };
  }
  const amount = Number.isFinite(status.alert_count) ? status.alert_count : 0;
  if (status.status === 'critical' && amount > 0) return { critical: amount, warning: 0 };
  if (status.status === 'warning' && amount > 0) return { critical: 0, warning: amount };
  return { critical: 0, warning: 0 };
};

const emptyLine = (key: string): ResourceLine => ({
  key,
  instUuid: '',
  modelId: '',
  clickable: false,
  title: { type: 'empty' },
  level: null,
  alertCount: null,
});

const regionBucket = (
  level: ArchitectureNodeStatusItem['status'] | null,
): 'alert' | 'normal' | 'other' => {
  if (level === 'warning' || level === 'critical') return 'alert';
  if (level === 'normal') return 'normal';
  return 'other';
};

const ALERT_SEVERITY_RANK: Record<string, number> = {
  critical: 40,
  error: 30,
  warning: 20,
};

const alertSeverityRank = (
  level: ArchitectureNodeStatusItem['status'] | null,
  maxLevel: string | null,
): number => {
  if (level !== 'warning' && level !== 'critical') return 0;
  const named = maxLevel ? ALERT_SEVERITY_RANK[maxLevel.trim().toLowerCase()] : undefined;
  if (typeof named === 'number') return named;
  return level === 'critical' ? 40 : 20;
};

const BUCKET_RANK = { alert: 0, normal: 1, other: 2 };

export function regionCaption(views: unknown, rectangleId: string): string {
  const found = findEntry(views, 'rectangles', rectangleId);
  if (!found) return '';
  const from = readCoord(found.entry.from);
  const to = readCoord(found.entry.to);
  if (!from || !to || !Array.isArray(found.view.textBoxes)) return '';
  const front = { x: Math.min(from.x, to.x), y: Math.min(from.y, to.y) };
  let best: { content: string; distance: number } | null = null;
  for (const box of found.view.textBoxes) {
    if (!isRecord(box)) continue;
    const tile = readCoord(box.tile);
    const content = typeof box.content === 'string' ? box.content.trim() : '';
    if (!tile || !content) continue;
    const inside = tileInside(tile, from, to);
    const nearFront = Math.abs(tile.x - front.x) <= 1 && Math.abs(tile.y - front.y) <= 1;
    if (!inside && !nearFront) continue;
    const distance = Math.abs(tile.x - front.x) + Math.abs(tile.y - front.y);
    if (!best || distance < best.distance) best = { content, distance };
  }
  return best ? truncateResourceName(best.content) : '';
}

export function buildRegionList(
  views: unknown,
  rectangleId: string,
  statusByUuid: Record<string, ArchitectureNodeStatusItem>,
  modelNames: Record<string, string>,
  items?: unknown,
): RegionList {
  const found = findEntry(views, 'rectangles', rectangleId);
  if (!found) return { icons: [] };
  const from = readCoord(found.entry.from);
  const to = readCoord(found.entry.to);
  if (!from || !to) return { icons: [] };
  const icons = boundIcons(found.view)
    .filter((icon) => tileInside(icon.tile, from, to))
    .sort((left, right) => {
      const leftStatus = statusByUuid[left.instUuid];
      const rightStatus = statusByUuid[right.instUuid];
      const leftBucket = regionBucket(leftStatus?.status ?? null);
      const rightBucket = regionBucket(rightStatus?.status ?? null);
      const bucketDelta = BUCKET_RANK[leftBucket] - BUCKET_RANK[rightBucket];
      if (bucketDelta) return bucketDelta;
      const severityDelta = alertSeverityRank(rightStatus?.status ?? null, rightStatus?.max_level ?? null)
        - alertSeverityRank(leftStatus?.status ?? null, leftStatus?.max_level ?? null);
      if (severityDelta) return severityDelta;
      return left.tile.y - right.tile.y || left.tile.x - right.tile.x || left.id.localeCompare(right.id);
    });
  const lines = icons.map((icon) => lineFromBinding(icon.id, {
    inst_uuid: icon.instUuid,
    model_id: icon.modelId,
  }, statusByUuid, modelNames, icon.id, modelItemName(items, icon.id)));
  return { icons: lines };
}

interface ResolvedAnchor {
  binding: { inst_uuid: string; model_id: string } | null;
  itemId?: string;
}

const findAnchor = (view: Record<string, unknown>, anchorId: string): Record<string, unknown> | null => {
  if (!Array.isArray(view.connectors)) return null;
  for (const connector of view.connectors) {
    if (!isRecord(connector) || !Array.isArray(connector.anchors)) continue;
    const anchor = connector.anchors.find((item) => isRecord(item) && item.id === anchorId);
    if (isRecord(anchor)) return anchor;
  }
  return null;
};

const resolveAnchor = (
  anchor: Record<string, unknown> | null,
  view: Record<string, unknown>,
  visiting: Set<string>,
): ResolvedAnchor => {
  if (!anchor) return { binding: null };
  const anchorId = typeof anchor.id === 'string' ? anchor.id : '';
  if (anchorId && visiting.has(anchorId)) return { binding: null };
  const nextVisiting = new Set(visiting);
  if (anchorId) nextVisiting.add(anchorId);
  const ref = isRecord(anchor.ref) ? anchor.ref : {};
  if (typeof ref.item === 'string' && ref.item) {
    const item = Array.isArray(view.items)
      ? view.items.find((entry) => isRecord(entry) && entry.id === ref.item)
      : null;
    if (!isRecord(item) || typeof item.id !== 'string') return { binding: null };
    return { binding: readBinding(item.bkBinding), itemId: item.id };
  }
  if (typeof ref.anchor === 'string' && ref.anchor) {
    return resolveAnchor(findAnchor(view, ref.anchor), view, nextVisiting);
  }
  return { binding: null };
};

const modelItemName = (items: unknown, id: string | undefined): string => {
  if (!id || !Array.isArray(items)) return '';
  const match = items.find((entry) => isRecord(entry) && entry.id === id);
  if (!isRecord(match) || typeof match.name !== 'string') return '';
  return match.name.trim();
};

export function diagramItemName(items: unknown, id: string | undefined): string {
  return modelItemName(items, id);
}

export function connectorEndpointNames(
  views: unknown,
  items: unknown,
  connectorId: string,
): { start: string; end: string } {
  const found = findEntry(views, 'connectors', connectorId);
  const anchors = found && Array.isArray(found.entry.anchors)
    ? found.entry.anchors.filter(isRecord)
    : [];
  const ends = [anchors[0] ?? null, anchors.length ? anchors[anchors.length - 1] : null];
  const names = ends.map((anchor) => {
    if (!found || !anchor) return '';
    return modelItemName(items, resolveAnchor(anchor, found.view, new Set()).itemId);
  });
  return { start: names[0] ?? '', end: names[1] ?? '' };
}

export function connectorResourceLines(
  views: unknown,
  connectorId: string,
  statusByUuid: Record<string, ArchitectureNodeStatusItem>,
  modelNames: Record<string, string>,
  items?: unknown,
): ResourceLine[] {
  const found = findEntry(views, 'connectors', connectorId);
  const anchors = found && Array.isArray(found.entry.anchors)
    ? found.entry.anchors.filter(isRecord)
    : [];
  const ends = [anchors[0] ?? null, anchors.length ? anchors[anchors.length - 1] : null];
  return ends.map((anchor, index) => {
    const key = index === 0 ? 'start' : 'end';
    if (!found || !anchor) return emptyLine(key);
    const resolved = resolveAnchor(anchor, found.view, new Set());
    if (!resolved.binding) return emptyLine(key);
    return lineFromBinding(
      key,
      resolved.binding,
      statusByUuid,
      modelNames,
      resolved.itemId,
      modelItemName(items, resolved.itemId),
    );
  });
}

const openBoundResource = (
  binding: { inst_uuid: string; model_id: string },
  statusByUuid: Record<string, ArchitectureNodeStatusItem>,
  highlightId?: string,
): DiagramClickAction => {
  const blocked = blockResourceOpen(statusByUuid[binding.inst_uuid]);
  if (blocked) return { type: 'toast', reason: blocked };
  return {
    type: 'resource',
    instUuid: binding.inst_uuid,
    modelId: binding.model_id,
    highlightId,
  };
};

export function decideDiagramClick(input: {
  hit: { type: string; id: string } | null;
  views: unknown;
  statusByUuid: Record<string, ArchitectureNodeStatusItem>;
}): DiagramClickAction {
  const hit = input.hit;
  if (!hit) return { type: 'close' };
  if (hit.type === 'CONNECTOR') return { type: 'connector', connectorId: hit.id };
  if (hit.type === 'ITEM') {
    const found = findEntry(input.views, 'items', hit.id);
    const binding = found ? readBinding(found.entry.bkBinding) : null;
    if (!binding) return { type: 'toast', reason: 'unbound' };
    return openBoundResource(binding, input.statusByUuid, hit.id);
  }
  if (hit.type === 'RECTANGLE') {
    const found = findEntry(input.views, 'rectangles', hit.id);
    if (!found) return { type: 'close' };
    return { type: 'region', rectangleId: hit.id };
  }
  return { type: 'close' };
}

export function blockResourceOpen(
  status: ArchitectureNodeStatusItem | undefined,
): 'invalid' | 'forbidden' | null {
  if (!status) return null;
  if (status.status === 'invalid') return 'invalid';
  if (status.status === 'forbidden') return 'forbidden';
  return null;
}
