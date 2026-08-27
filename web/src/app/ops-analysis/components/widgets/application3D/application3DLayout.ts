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
  /** Short wall title (common demo prefix stripped when present). */
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

const DEMO_NAME_PREFIX = '本地演示-';

/** Fallback translator keeps Chinese defaults when callers omit locale. */
export const defaultApplication3DTranslate: Application3DTranslate = (
  _id,
  defaultMessage = '',
) => defaultMessage;

export const buildApplication3DLayout = (
  count: number,
  viewportAspect: number,
): Application3DLayout => {
  const safeCount = Math.max(0, Math.floor(count));
  const safeAspect = Math.max(viewportAspect, 0.1);
  const idealColumns = Math.sqrt((safeCount * safeAspect) / CARD_ASPECT);
  const minColumns = Math.max(1, Math.floor(idealColumns) - 2);
  const maxColumns = Math.min(safeCount || 1, Math.ceil(idealColumns) + 2);
  const columns = safeCount
    ? Array.from({ length: maxColumns - minColumns + 1 }, (_, index) => minColumns + index)
      .reduce((best, candidate) => {
        const candidateRows = Math.ceil(safeCount / candidate);
        const lastRowCount = safeCount - (candidateRows - 1) * candidate;
        const candidateWidth = candidate * CARD_WORLD_WIDTH + (candidate - 1) * CARD_GAP;
        const candidateHeight =
          candidateRows * CARD_WORLD_HEIGHT + (candidateRows - 1) * CARD_GAP;
        const aspectCost = Math.abs(Math.log((candidateWidth / candidateHeight) / safeAspect));
        const raggednessCost = candidateRows > 1 ? (candidate - lastRowCount) / candidate : 0;
        const score = aspectCost * 1.2 + raggednessCost * 0.4;
        return !best || score < best.score ? { columns: candidate, score } : best;
      }, null as { columns: number; score: number } | null)?.columns || 1
    : 1;
  const rows = Math.max(1, Math.ceil(safeCount / columns));
  const finalRowCount = safeCount - (rows - 1) * columns;
  const rowCardCounts = Array.from(
    { length: rows },
    (_, row) => (row === rows - 1 ? Math.max(finalRowCount, 0) : columns),
  );
  // Few cards → larger; many cards → smaller. Overall slightly below legacy 3×4.
  const density =
    safeCount <= 6 ? 0.92 :
    safeCount <= 12 ? 0.78 :
    safeCount <= 24 ? 0.64 :
    safeCount <= 48 ? 0.52 :
    safeCount <= 80 ? 0.44 :
    0.38;
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
export const APPLICATION3D_CAMERA_FOV = 42;

export const fitApplication3DCameraDistance = (
  wallWidth: number,
  wallHeight: number,
  viewportAspect: number,
  fovDeg = APPLICATION3D_CAMERA_FOV,
  coverage = WALL_VIEW_COVERAGE,
): number => {
  const halfFov = ((fovDeg * Math.PI) / 180) / 2;
  const tan = Math.tan(halfFov);
  const distanceForHeight = wallHeight / (2 * tan);
  const distanceForWidth =
    wallWidth / (2 * tan * Math.max(viewportAspect, 0.1));
  return Math.max(distanceForHeight, distanceForWidth) / Math.max(coverage, 0.2);
};

export const UNKNOWN_STATUS_BADGE = '--';

export const formatApplicationAlarmBadge = (count: number | null): string => {
  if (count === null) return '?';
  if (count >= 100) return '99+';
  return String(Math.max(0, Math.floor(count)));
};

export const formatApplication3DCardTitle = (name: string): string => {
  const trimmed = name.trim();
  if (trimmed.startsWith(DEMO_NAME_PREFIX) && trimmed.length > DEMO_NAME_PREFIX.length) {
    return trimmed.slice(DEMO_NAME_PREFIX.length);
  }
  return trimmed;
};

export const neonLevelToCardTone = (level: Application3DNeonLevel): Application3DCardTone => {
  if (level === 'fatal') return 'critical';
  if (level === 'remain') return 'unknown';
  return level;
};

/** Alert count badge is only for a real positive alarming count, never 0 / ?. */
export const shouldShowApplication3DAlertBadge = (health: {
  state: string;
  activeAlarmCount: number | null;
}): boolean => {
  if (health.state === 'normal' || health.state === 'unknown') return false;
  return typeof health.activeAlarmCount === 'number' && health.activeAlarmCount > 0;
};

export const resolveApplication3DBadge = (
  health: {
    state: string;
    activeAlarmCount: number | null;
  },
  tone: Application3DCardTone,
): { showBadge: boolean; badgeText: string } => {
  if (tone === 'unknown') {
    return { showBadge: true, badgeText: UNKNOWN_STATUS_BADGE };
  }
  if (shouldShowApplication3DAlertBadge(health)) {
    return {
      showBadge: true,
      badgeText: formatApplicationAlarmBadge(health.activeAlarmCount),
    };
  }
  return { showBadge: false, badgeText: '' };
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
    return t('dashboard.application3DStatus_normal', '无活跃告警');
  }
  // Active alerts with empty/unmapped level: treat as warning (not critical/unknown).
  if (item.health.state === 'alarming' && !item.health.highestSeverity) {
    return t('dashboard.application3DStatus_warning', '警告');
  }
  if (tone === 'critical') return t('dashboard.application3DStatus_critical', '严重告警');
  if (tone === 'error') return t('dashboard.application3DStatus_error', '错误告警');
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
  const { showBadge, badgeText } = resolveApplication3DBadge(health, cardTone);

  return {
    title: formatApplication3DCardTitle(item.name),
    statusLabel: cardStatusLabel(item, cardTone, t),
    neonLevel,
    cardTone,
    showBadge,
    badgeText,
  };
};
