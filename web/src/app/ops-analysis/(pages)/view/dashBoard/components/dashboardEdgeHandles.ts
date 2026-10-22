/**
 * 与大屏同一屏幕像素阈值。仪表盘角点是 14px，48px 时边中点与角点仍留约 10px，
 * 再小就挤在一起。宽度不足隐藏上下边中点，高度不足隐藏左右边中点。
 */
export const DASHBOARD_EDGE_HANDLE_MIN_SCREEN_PX = 48;
export const DASHBOARD_HIDE_NS_EDGE_CLASS = 'dashboard-edge-handle-hide-ns';
export const DASHBOARD_HIDE_EW_EDGE_CLASS = 'dashboard-edge-handle-hide-ew';

export const syncDashboardEdgeHandleVisibility = (
  root: ParentNode,
  minScreenPx = DASHBOARD_EDGE_HANDLE_MIN_SCREEN_PX,
) => {
  root.querySelectorAll<HTMLElement>('.grid-stack-item').forEach((item) => {
    const content = item.querySelector<HTMLElement>(
      ':scope > .grid-stack-item-content',
    );
    const box = content ?? item;
    item.classList.toggle(
      DASHBOARD_HIDE_NS_EDGE_CLASS,
      box.clientWidth < minScreenPx,
    );
    item.classList.toggle(
      DASHBOARD_HIDE_EW_EDGE_CLASS,
      box.clientHeight < minScreenPx,
    );
  });
};
