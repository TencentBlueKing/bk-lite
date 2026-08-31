import {
  CARD_ASPECT,
  CARD_GAP,
  CARD_WORLD_HEIGHT,
  CARD_WORLD_WIDTH,
  resolveNeonLevel,
  type Application3DNeonLevel,
} from './application3DVisual';

export interface Application3DLayout {
  columns: number;
  rows: number;
  /** Number of cards in each row; the final row is centered independently. */
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

const scoreColumnCandidate = (
  count: number,
  columns: number,
  viewportAspect: number,
): number => {
  const rows = Math.ceil(count / columns);
  const lastRowCount = count - (rows - 1) * columns;
  const width = columns * CARD_WORLD_WIDTH + (columns - 1) * CARD_GAP;
  const height = rows * CARD_WORLD_HEIGHT + (rows - 1) * CARD_GAP;
  const aspectCost = Math.abs(Math.log((width / Math.max(height, 0.01)) / viewportAspect));
  const raggednessCost = rows > 1 ? (columns - lastRowCount) / columns : 0;
  return aspectCost * 1.2 + raggednessCost * 0.4;
};

/** Design mock is a 4×4 landscape HUD wall. Few cards stay short and wide. */
export const resolveApplication3DColumns = (
  count: number,
  viewportAspect: number,
): number => {
  const safeCount = Math.max(0, Math.floor(count));
  const safeAspect = Math.max(viewportAspect, 0.1);
  if (safeCount <= 1) return 1;
  if (safeCount <= 3) return safeCount;
  if (safeCount === 4) return 2;
  if (safeCount <= 6) return 3;
  if (safeCount <= 16) return 4;
  const ideal = Math.sqrt((safeCount * safeAspect) / CARD_ASPECT);
  const minColumns = Math.max(4, Math.floor(ideal) - 1);
  const maxColumns = Math.min(safeCount, Math.max(minColumns, Math.ceil(ideal) + 1));
  return Array.from({ length: maxColumns - minColumns + 1 }, (_, index) => minColumns + index)
    .reduce((best, candidate) => {
      const score = scoreColumnCandidate(safeCount, candidate, safeAspect);
      return !best || score < best.score ? { columns: candidate, score } : best;
    }, null as { columns: number; score: number } | null)?.columns || 4;
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
export const WALL_VIEW_COVERAGE = 0.68;
export const APPLICATION3D_CAMERA_FOV = 34;
/** 4×4 mock wall; fewer cards keep this framing so they do not become billboards. */
export const REFERENCE_WALL_WIDTH = 4 * CARD_WORLD_WIDTH + 3 * CARD_GAP;
export const REFERENCE_WALL_HEIGHT = 4 * CARD_WORLD_HEIGHT + 3 * CARD_GAP;
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
 * Uses highestSeverity / reason so alarming cards are not collapsed into one look.
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
