import type { ScreenItem } from '@/app/ops-analysis/types/screen';

export type ScreenLayerAction =
  | 'bringToFront'
  | 'bringToBack'
  | 'bringForward'
  | 'sendBackward';

export const SCREEN_LAYER_DRAG_MIME = 'application/x-bk-screen-layer';

export const orderScreenItemsByLayer = (items: ScreenItem[]) =>
  [...items].sort((left, right) => {
    const zDiff = (right.zIndex || 0) - (left.zIndex || 0);
    if (zDiff !== 0) return zDiff;
    return left.id.localeCompare(right.id);
  });

const assignLayerOrder = (ordered: ScreenItem[]) =>
  ordered.map((item, index) => {
    const zIndex = ordered.length - index;
    return item.zIndex === zIndex ? item : { ...item, zIndex };
  });

export const moveScreenItemToIndex = (
  items: ScreenItem[],
  itemId: string,
  toIndex: number,
): ScreenItem[] => {
  const ordered = orderScreenItemsByLayer(items);
  const from = ordered.findIndex((item) => item.id === itemId);
  if (from < 0) return items;

  const moving = ordered[from];
  const rest = ordered.filter((item) => item.id !== itemId);
  const insertAt = Math.max(0, Math.min(toIndex, rest.length));
  const next = [
    ...rest.slice(0, insertAt),
    moving,
    ...rest.slice(insertAt),
  ];
  if (next.every((item, index) => item.id === ordered[index]?.id)) {
    return items;
  }
  return assignLayerOrder(next);
};

export const moveScreenItemLayer = (
  items: ScreenItem[],
  itemId: string,
  action: ScreenLayerAction,
): ScreenItem[] => {
  const ordered = orderScreenItemsByLayer(items);
  const index = ordered.findIndex((item) => item.id === itemId);
  if (index < 0) return items;

  let toIndex = index;
  if (action === 'bringToFront') toIndex = 0;
  else if (action === 'bringToBack') toIndex = ordered.length - 1;
  else if (action === 'bringForward') toIndex = Math.max(0, index - 1);
  else toIndex = Math.min(ordered.length - 1, index + 1);

  if (toIndex === index) return items;
  return moveScreenItemToIndex(items, itemId, toIndex);
};
