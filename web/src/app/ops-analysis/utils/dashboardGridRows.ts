import type {
  DashboardLayoutItem,
  OtherConfig,
} from '@/app/ops-analysis/types/dashBoard';
import {
  migrateDashboardGridColumns,
  withCurrentDashboardGridCols,
  type MigratedDashboardGrid,
} from './dashboardGridColumns';

export const LEGACY_DASHBOARD_GRID_ROW_HEIGHT = 60;
export const DASHBOARD_GRID_ROW_HEIGHT = 30;
export const DASHBOARD_GRID_ROW_SCALE =
  LEGACY_DASHBOARD_GRID_ROW_HEIGHT / DASHBOARD_GRID_ROW_HEIGHT;

/** 组件选择器等既有默认尺寸仍以 60px 行为单位。 */
export const scaleDashboardGridHeight = (rows: number): number =>
  rows * DASHBOARD_GRID_ROW_SCALE;

export const withCurrentDashboardGrid = (other?: OtherConfig | null): OtherConfig => ({
  ...withCurrentDashboardGridCols(other),
  gridRowHeight: DASHBOARD_GRID_ROW_HEIGHT,
});

/**
 * 先反序列化成平铺布局再换算，分组标题和子组件的坐标使用同一单位。
 * 缺少行高标记的旧盘按 60px 解释；只在内存中升级，随正常保存写回标记。
 */
export const migrateDashboardGridLayout = (
  layout: DashboardLayoutItem[],
  other?: OtherConfig | null,
): MigratedDashboardGrid => {
  const columns = migrateDashboardGridColumns(layout, other);
  if (Number(other?.gridRowHeight) === DASHBOARD_GRID_ROW_HEIGHT) {
    return columns;
  }
  return {
    layout: columns.layout.map((item) => ({
      ...item,
      y: scaleDashboardGridHeight(item.y),
      h: scaleDashboardGridHeight(item.h),
    })),
    other: {
      ...columns.other,
      gridRowHeight: DASHBOARD_GRID_ROW_HEIGHT,
    },
    migrated: true,
  };
};
