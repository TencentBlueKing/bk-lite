import { describe, expect, it } from 'vitest';
import {
  DASHBOARD_EDGE_HANDLE_MIN_SCREEN_PX,
  DASHBOARD_HIDE_EW_EDGE_CLASS,
  DASHBOARD_HIDE_NS_EDGE_CLASS,
  syncDashboardEdgeHandleVisibility,
} from '../dashboardEdgeHandles';

const box = (width: number, height: number) => {
  const item = document.createElement('div');
  item.className = 'grid-stack-item';
  const content = document.createElement('div');
  content.className = 'grid-stack-item-content';
  Object.defineProperty(content, 'clientWidth', { value: width });
  Object.defineProperty(content, 'clientHeight', { value: height });
  item.appendChild(content);
  const root = document.createElement('div');
  root.appendChild(item);
  return { root, item };
};

describe('dashboard edge handle visibility', () => {
  it('hides the midpoint on a side shorter than 48 screen pixels', () => {
    expect(DASHBOARD_EDGE_HANDLE_MIN_SCREEN_PX).toBe(48);

    const wide = box(160, 47);
    syncDashboardEdgeHandleVisibility(wide.root);
    expect(wide.item.classList.contains(DASHBOARD_HIDE_NS_EDGE_CLASS)).toBe(false);
    expect(wide.item.classList.contains(DASHBOARD_HIDE_EW_EDGE_CLASS)).toBe(true);

    const narrow = box(47, 160);
    syncDashboardEdgeHandleVisibility(narrow.root);
    expect(narrow.item.classList.contains(DASHBOARD_HIDE_NS_EDGE_CLASS)).toBe(true);
    expect(narrow.item.classList.contains(DASHBOARD_HIDE_EW_EDGE_CLASS)).toBe(false);

    const tiny = box(20, 20);
    syncDashboardEdgeHandleVisibility(tiny.root);
    expect(tiny.item.classList.contains(DASHBOARD_HIDE_NS_EDGE_CLASS)).toBe(true);
    expect(tiny.item.classList.contains(DASHBOARD_HIDE_EW_EDGE_CLASS)).toBe(true);

    const grown = box(80, 80);
    grown.item.classList.add(DASHBOARD_HIDE_NS_EDGE_CLASS, DASHBOARD_HIDE_EW_EDGE_CLASS);
    syncDashboardEdgeHandleVisibility(grown.root);
    expect(grown.item.classList.contains(DASHBOARD_HIDE_NS_EDGE_CLASS)).toBe(false);
    expect(grown.item.classList.contains(DASHBOARD_HIDE_EW_EDGE_CLASS)).toBe(false);
  });
});
