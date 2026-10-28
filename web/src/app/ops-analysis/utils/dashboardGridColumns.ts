import type {
  DashboardLayoutItem,
  OtherConfig,
} from '@/app/ops-analysis/types/dashBoard';

/** 旧仪表盘横向格数。缺省或显式写成这个值时，打开后按当前格数换算。 */
export const LEGACY_DASHBOARD_GRID_COLS = 12;

/** 当前仪表盘横向格数。一步约为原来的一半，行高不变。 */
export const DASHBOARD_GRID_COLUMN_SCALE = 2;

export const DASHBOARD_GRID_COLS = LEGACY_DASHBOARD_GRID_COLS * DASHBOARD_GRID_COLUMN_SCALE;

/** 无坐标的提案仍按一行三个组件铺满当前栅格。 */
export const DASHBOARD_PROPOSAL_WIDGETS_PER_ROW = 3;

export const DASHBOARD_PROPOSAL_CELL_WIDTH =
  DASHBOARD_GRID_COLS / DASHBOARD_PROPOSAL_WIDGETS_PER_ROW;

/**
 * 把 12 列时期的横向格数精确乘到当前栅格。
 * 只用整数倍，不做四舍五入。
 */
export const scaleDashboardGridSpan = (span: number): number =>
  span * DASHBOARD_GRID_COLUMN_SCALE;

const readGridCols = (other: OtherConfig | null | undefined): number | undefined => {
  if (!other || typeof other !== 'object') {
    return undefined;
  }
  // 历史 JSON 可能把列数写成字符串；显式字段类型仍是 number。
  const value: unknown = (other as { gridCols?: unknown }).gridCols;
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

/** 未记录列数，或仍标记为 12 列，都按旧盘处理。 */
export const isLegacyDashboardGrid = (other: OtherConfig | null | undefined): boolean => {
  const cols = readGridCols(other);
  return cols == null || cols === LEGACY_DASHBOARD_GRID_COLS;
};

export const withCurrentDashboardGridCols = (other?: OtherConfig | null): OtherConfig => ({
  ...(other && typeof other === 'object' ? other : {}),
  gridCols: DASHBOARD_GRID_COLS,
});

export const scaleDashboardLayoutColumns = (
  layout: DashboardLayoutItem[],
): DashboardLayoutItem[] =>
  layout.map((item) => ({
    ...item,
    x: scaleDashboardGridSpan(item.x),
    w: scaleDashboardGridSpan(item.w),
  }));

export interface MigratedDashboardGrid {
  layout: DashboardLayoutItem[];
  other: OtherConfig;
  migrated: boolean;
}

/**
 * 旧盘把每个组件和分组（含子项）的 x、w 精确 ×2，y、h 不动，并写入 gridCols=24。
 * 已经是 24 列的盘不改布局数字。
 */
export const migrateDashboardGridColumns = (
  layout: DashboardLayoutItem[],
  other?: OtherConfig | null,
): MigratedDashboardGrid => {
  const source: OtherConfig = other && typeof other === 'object' ? { ...other } : {};
  if (!isLegacyDashboardGrid(source)) {
    return {
      layout,
      other: source,
      migrated: false,
    };
  }
  return {
    layout: scaleDashboardLayoutColumns(layout),
    other: withCurrentDashboardGridCols(source),
    migrated: true,
  };
};
