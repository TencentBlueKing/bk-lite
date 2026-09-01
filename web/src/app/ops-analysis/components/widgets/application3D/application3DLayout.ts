import {
  CARD_GAP,
  CARD_WORLD_HEIGHT,
  CARD_WORLD_WIDTH,
  resolveNeonLevel,
  type Application3DNeonLevel,
} from './application3DVisual';

export interface Application3DLayout {
  columns: number;
  rows: number;
  /** Cards per row; a short last row stays left-aligned to the wall. */
  rowCardCounts: number[];
  cardWidth: number;
  cardHeight: number;
  gapX: number;
  gapY: number;
  wallWidth: number;
  wallHeight: number;
}

export type Application3DCardTone = 'normal' | 'critical' | 'error' | 'warning' | 'info' | 'unknown';

/** Locale lookup used by Wall canvas chrome (outside React). */
export type Application3DTranslate = (id: string, defaultMessage?: string) => string;

export interface Application3DCardVisual {
  /** Wall card title; demo data may keep a 本地演示- prefix. */
  title: string;
  /** Human-readable status line; not color-only. */
  statusLabel: string;
  /** Legacy neon level for canvas fill / border / badge. */
  neonLevel: Application3DNeonLevel;
  /** Wall-card visual bucket. Mapping stays on resolveNeonLevel. */
  cardTone: Application3DCardTone;
  showBadge: boolean;
  badgeText: string;
}

/** Fallback translator keeps Chinese defaults when callers omit locale. */
export const defaultApplication3DTranslate: Application3DTranslate = (
  _id,
  defaultMessage = '',
) => defaultMessage;

/** Landscape walls prefer a square-to-slightly-wide card grid, not a 2×N tower. */
const TARGET_GRID_ASPECT_WIDE = 1.2;
const TARGET_GRID_ASPECT_TALL = 0.85;

const scoreColumnCandidate = (
  count: number,
  columns: number,
  viewportAspect: number,
): number => {
  const rows = Math.ceil(count / columns);
  const lastRowCount = count - (rows - 1) * columns;
  const incomplete = rows > 1 && lastRowCount !== columns;
  const shortfall = incomplete ? (columns - lastRowCount) / columns : 0;
  const orphan =
    incomplete && lastRowCount <= Math.max(1, Math.floor(columns / 3)) ? 0.45 : 0;
  const targetGridAspect =
    viewportAspect >= 1.05 ? TARGET_GRID_ASPECT_WIDE : TARGET_GRID_ASPECT_TALL;
  const gridAspect = columns / Math.max(rows, 1);
  const aspectCost = Math.abs(Math.log(gridAspect / targetGridAspect));
  const towerCost = rows > columns ? (rows / columns - 1) * 1.35 : 0;
  const incompleteCost = incomplete ? 0.28 + shortfall * 0.55 : 0;
  return aspectCost + incompleteCost + orphan + towerCost;
};

const collectColumnCandidates = (count: number, ideal: number): number[] => {
  const lo = Math.max(1, Math.floor(ideal) - 5);
  const hi = Math.min(count, Math.ceil(ideal) + 6);
  const candidates = new Set<number>();
  for (let columns = lo; columns <= hi; columns += 1) candidates.add(columns);
  for (let columns = 1; columns <= count; columns += 1) {
    if (count % columns === 0 && Math.abs(columns - ideal) <= 8) {
      candidates.add(columns);
    }
  }
  return [...candidates];
};

/** Prefer a square or slightly wide card grid; a short last row beats a 2-column tower. */
export const resolveApplication3DColumns = (
  count: number,
  viewportAspect: number,
): number => {
  const safeCount = Math.max(0, Math.floor(count));
  const safeAspect = Math.max(viewportAspect, 0.1);
  if (!safeCount) return 1;
  const targetGridAspect =
    safeAspect >= 1.05 ? TARGET_GRID_ASPECT_WIDE : TARGET_GRID_ASPECT_TALL;
  const ideal = Math.sqrt(safeCount * targetGridAspect);
  return collectColumnCandidates(safeCount, ideal)
    .reduce((best, candidate) => {
      const score = scoreColumnCandidate(safeCount, candidate, safeAspect);
      return !best || score < best.score ? { columns: candidate, score } : best;
    }, null as { columns: number; score: number } | null)?.columns || 1;
};

const resolveCardDensity = (count: number): number => {
  if (count <= 16) return 1;
  if (count <= 24) return 0.82;
  if (count <= 48) return 0.64;
  if (count <= 80) return 0.5;
  return 0.4;
};

export const buildApplication3DLayout = (
  count: number,
  viewportAspect: number,
): Application3DLayout => {
  const safeCount = Math.max(0, Math.floor(count));
  const columns = resolveApplication3DColumns(safeCount, viewportAspect);
  const rows = Math.max(1, Math.ceil(safeCount / columns) || 1);
  const finalRowCount = safeCount - (rows - 1) * columns;
  const rowCardCounts = Array.from(
    { length: rows },
    (_, row) => (row === rows - 1 ? Math.max(finalRowCount, 0) : columns),
  );
  const density = resolveCardDensity(safeCount);
  const cardWidth = CARD_WORLD_WIDTH * density;
  const cardHeight = CARD_WORLD_HEIGHT * density;
  const gapX = CARD_GAP * density;
  const gapY = CARD_GAP * density;
  return {
    columns,
    rows,
    rowCardCounts,
    cardWidth,
    cardHeight,
    gapX,
    gapY,
    wallWidth: columns * cardWidth + Math.max(0, columns - 1) * gapX,
    wallHeight: rows * cardHeight + Math.max(0, rows - 1) * gapY,
  };
};

/** Default wall occupies this fraction of the tighter viewport axis. */
export const WALL_VIEW_COVERAGE = 0.80;
export const APPLICATION3D_CAMERA_FOV = 34;
/** Pad only 1-card walls; 2×2 and larger frame the actual wall so cards stay readable. */
export const REFERENCE_WALL_WIDTH = 2 * CARD_WORLD_WIDTH + CARD_GAP;
export const REFERENCE_WALL_HEIGHT = 2 * CARD_WORLD_HEIGHT + CARD_GAP;
/** Keep a slight elevation so the floor stays visible without shrinking side cards. */
export const WALL_CAMERA_HEIGHT_FACTOR = 0.04;

export const fitApplication3DCameraDistance = (
  wallWidth: number,
  wallHeight: number,
  viewportAspect: number,
  fovDeg = APPLICATION3D_CAMERA_FOV,
  coverage = WALL_VIEW_COVERAGE,
): number => {
  const halfFov = ((fovDeg * Math.PI) / 180) / 2;
  const tan = Math.tan(halfFov);
  const framedWidth = Math.max(wallWidth, REFERENCE_WALL_WIDTH);
  const framedHeight = Math.max(wallHeight, REFERENCE_WALL_HEIGHT);
  const distanceForHeight = framedHeight / (2 * tan);
  const distanceForWidth =
    framedWidth / (2 * tan * Math.max(viewportAspect, 0.1));
  return Math.max(distanceForHeight, distanceForWidth) / Math.max(coverage, 0.2);
};

export const UNKNOWN_STATUS_BADGE = '--';

export const formatApplicationAlarmBadge = (count: number | null): string => {
  if (count === null) return '?';
  if (count >= 100) return '99+';
  return String(Math.max(0, Math.floor(count)));
};

export const formatApplication3DCardTitle = (name: string): string => name.trim();

export const neonLevelToCardTone = (level: Application3DNeonLevel): Application3DCardTone => {
  if (level === 'fatal') return 'critical';
  if (level === 'remain') return 'unknown';
  return level;
};

/** Corner count chips are unused; status lives in the tag. */
export const shouldShowApplication3DAlertBadge = (_health: {
  state: string;
  activeAlarmCount: number | null;
}): boolean => false;

export const resolveApplication3DBadge = (
  health: {
    state: string;
    activeAlarmCount: number | null;
  },
  tone: Application3DCardTone,
): { showBadge: boolean; badgeText: string } => {
  if (tone === 'unknown') {
    return { showBadge: false, badgeText: UNKNOWN_STATUS_BADGE };
  }
  return {
    showBadge: false,
    badgeText: formatApplicationAlarmBadge(health.activeAlarmCount ?? 0),
  };
};

const cardStatusLabel = (
  item: {
    health: {
      state: string;
      highestSeverity: { id: string } | null;
    };
  },
  tone: Application3DCardTone,
  t: Application3DTranslate,
): string => {
  if (item.health.state === 'normal') {
    return t('dashboard.application3DStatus_normal', '运行正常');
  }
  // Active alerts with empty/unmapped level: treat as warning (not critical/unknown).
  if (item.health.state === 'alarming' && !item.health.highestSeverity) {
    return t('dashboard.application3DStatus_warning', '警告');
  }
  if (tone === 'critical') return t('dashboard.application3DStatus_critical', '严重告警');
  if (tone === 'error') return t('dashboard.application3DStatus_error', '错误');
  if (tone === 'warning') return t('dashboard.application3DStatus_warning', '警告');
  if (tone === 'info') return t('dashboard.application3DStatus_info', '提示');
  return t('dashboard.application3DStatus_unknown', '状态未知');
};

/**
 * Resolve Wall card chrome from health DTO.
 * Unknown reasons (unavailable / no_application / no_host) share state=unknown.
 * Alarming cards use highestSeverity so they are not collapsed into one look.
 */
export const resolveApplication3DCardVisual = (
  item: {
    name: string;
    health: {
      state: string;
      reason: string;
      activeAlarmCount: number | null;
      highestSeverity: { id: string; label: string; color: string } | null;
    };
  },
  t: Application3DTranslate = defaultApplication3DTranslate,
): Application3DCardVisual => {
  const { health } = item;
  const neonLevel = resolveNeonLevel(item);
  const cardTone = neonLevelToCardTone(neonLevel);
  const { badgeText } = resolveApplication3DBadge(health, cardTone);
  const baseLabel = cardStatusLabel(item, cardTone, t);
  const counted =
    cardTone !== 'normal' &&
    cardTone !== 'unknown' &&
    /^\d+$/.test(badgeText) &&
    badgeText !== '0';

  return {
    title: formatApplication3DCardTitle(item.name),
    statusLabel: counted ? `${baseLabel} ${badgeText}` : baseLabel,
    neonLevel,
    cardTone,
    showBadge: false,
    badgeText,
  };
};
