export const ICON_HIT_SELECTOR = '[data-icon-hit]';
export const RECTANGLE_BADGE_HIT_SELECTOR = '[data-rectangle-badge-hit]';

export interface IconHitRect {
  id: string;
  order: number;
  index: number;
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface IconHitElement {
  getAttribute(name: string): string | null;
  getBoundingClientRect(): {
    left: number;
    top: number;
    right: number;
    bottom: number;
  };
}

export interface IconHitRoot {
  querySelectorAll(selector: string): ArrayLike<IconHitElement>;
}

const finiteOr = (value: number, fallback: number) => {
  return Number.isFinite(value) ? value : fallback;
};

export const readIconHitRects = (root: IconHitRoot): IconHitRect[] => {
  const nodes = Array.from(root.querySelectorAll(ICON_HIT_SELECTOR));
  const rects: IconHitRect[] = [];

  nodes.forEach((node, index) => {
    const id = node.getAttribute('data-icon-hit')?.trim() ?? '';

    if (!id) return;

    const box = node.getBoundingClientRect();
    const width = box.right - box.left;
    const height = box.bottom - box.top;

    if (width <= 0 || height <= 0) return;

    const pad = Math.max(0, finiteOr(Number(node.getAttribute('data-icon-pad')), 0));

    rects.push({
      id,
      order: finiteOr(Number(node.getAttribute('data-icon-order')), 0),
      index,
      left: box.left - pad,
      top: box.top - pad,
      right: box.right + pad,
      bottom: box.bottom + pad
    });
  });

  return rects;
};

const containsPoint = (rect: IconHitRect, point: { x: number; y: number }) => {
  return (
    point.x >= rect.left &&
    point.x <= rect.right &&
    point.y >= rect.top &&
    point.y <= rect.bottom
  );
};

const isAbove = (candidate: IconHitRect, current: IconHitRect) => {
  return (
    candidate.order > current.order ||
    (candidate.order === current.order && candidate.index > current.index)
  );
};

export const findIconHit = (
  point: { x: number; y: number },
  rects: IconHitRect[]
): string | null => {
  let best: IconHitRect | null = null;

  for (const rect of rects) {
    if (!containsPoint(rect, point)) continue;

    if (!best || isAbove(rect, best)) best = rect;
  }

  return best ? best.id : null;
};

export const findDrawnIconId = (
  root: IconHitRoot | null | undefined,
  point: { x: number; y: number }
): string | null => {
  if (!root) return null;

  return findIconHit(point, readIconHitRects(root));
};

export const findRectangleBadgeId = (
  root: IconHitRoot | null | undefined,
  point: { x: number; y: number }
): string | null => {
  if (!root) return null;

  const nodes = Array.from(root.querySelectorAll(RECTANGLE_BADGE_HIT_SELECTOR));
  let best: { id: string; index: number } | null = null;

  for (let index = 0; index < nodes.length; index += 1) {
    const node = nodes[index];
    const id = node.getAttribute('data-rectangle-badge-hit')?.trim() ?? '';

    if (!id) continue;

    const box = node.getBoundingClientRect();

    if (
      point.x < box.left ||
      point.x > box.right ||
      point.y < box.top ||
      point.y > box.bottom
    ) {
      continue;
    }

    if (!best || index >= best.index) best = { id, index };
  }

  return best ? best.id : null;
};

export type ViewClickItem = {
  type: 'ITEM' | 'RECTANGLE' | 'CONNECTOR';
  id: string;
};

export type ViewClickDecision =
  | { kind: 'ignore' }
  | { kind: 'click'; item: ViewClickItem | null };

interface TilePoint {
  x: number;
  y: number;
}

export interface TextClickRegion {
  id: string;
  from: TilePoint;
  to: TilePoint;
}

export interface TextClickBox {
  id: string;
  tile: TilePoint;
  content?: string;
}

const tileInside = (tile: TilePoint, from: TilePoint, to: TilePoint) => {
  const minX = Math.min(from.x, to.x);
  const maxX = Math.max(from.x, to.x);
  const minY = Math.min(from.y, to.y);
  const maxY = Math.max(from.y, to.y);

  return tile.x >= minX && tile.x <= maxX && tile.y >= minY && tile.y <= maxY;
};

const firstRegionAt = (tile: TilePoint, regions: TextClickRegion[]) => {
  return regions.find((region) => tileInside(tile, region.from, region.to))?.id ?? null;
};

const frontCorner = (region: TextClickRegion): TilePoint => {
  return {
    x: Math.min(region.from.x, region.to.x),
    y: Math.min(region.from.y, region.to.y)
  };
};

const regionCaptionId = (region: TextClickRegion, boxes: TextClickBox[]) => {
  const front = frontCorner(region);
  let best: { id: string; distance: number } | null = null;

  for (const box of boxes) {
    const content = box.content?.trim() ?? '';

    if (!content) continue;

    const inside = tileInside(box.tile, region.from, region.to);
    const nearFront =
      Math.abs(box.tile.x - front.x) <= 1 && Math.abs(box.tile.y - front.y) <= 1;

    if (!inside && !nearFront) continue;

    const distance = Math.abs(box.tile.x - front.x) + Math.abs(box.tile.y - front.y);

    if (!best || distance < best.distance) best = { id: box.id, distance };
  }

  return best?.id ?? null;
};

/** Region opened by a view-mode click on a text box. Rectangles stay in diagram order. */
export const regionIdForTextClick = (input: {
  tile: TilePoint;
  textBoxId: string;
  rectangles: TextClickRegion[];
  textBoxes: TextClickBox[];
}): string | null => {
  const covered = firstRegionAt(input.tile, input.rectangles);

  if (covered) return covered;

  const box = input.textBoxes.find((entry) => entry.id === input.textBoxId);

  if (!box) return null;

  const anchored = firstRegionAt(box.tile, input.rectangles);

  if (anchored) return anchored;

  for (const region of input.rectangles) {
    if (regionCaptionId(region, input.textBoxes) === box.id) return region.id;
  }

  return null;
};

export const resolveViewClick = (input: {
  /** Area alert label under the pointer. An icon drawn over it wins. */
  badgeId?: string | null;
  iconId: string | null;
  tileHit: { type: string; id: string } | null;
  textRegionId?: string | null;
}): ViewClickDecision => {
  if (input.iconId) {
    return { kind: 'click', item: { type: 'ITEM', id: input.iconId } };
  }

  if (input.badgeId) {
    return { kind: 'click', item: { type: 'RECTANGLE', id: input.badgeId } };
  }

  const hit = input.tileHit;

  if (!hit) return { kind: 'click', item: null };

  if (hit.type === 'TEXTBOX') {
    if (input.textRegionId) {
      return { kind: 'click', item: { type: 'RECTANGLE', id: input.textRegionId } };
    }

    return { kind: 'ignore' };
  }

  if (
    hit.type === 'ITEM' ||
    hit.type === 'RECTANGLE' ||
    hit.type === 'CONNECTOR'
  ) {
    return { kind: 'click', item: { type: hit.type, id: hit.id } };
  }

  return { kind: 'ignore' };
};

/**
 * Only the primary button may start a click/select/drag; other buttons stay
 * inert. Synthetic touch events carry no button and count as primary.
 */
export const isPrimaryPointerEvent = (event: { button?: number }) => {
  return (event.button ?? 0) === 0;
};

export const viewHoverCursor = (input: {
  badgeId?: string | null;
  iconId: string | null;
  tileHit: { type: string; id: string } | null;
  textRegionId?: string | null;
}): 'pointer' | 'grab' => {
  if (input.iconId) return 'pointer';
  if (input.badgeId) return 'pointer';

  const hit = input.tileHit;

  if (hit?.type === 'RECTANGLE') return 'pointer';

  if (hit?.type === 'TEXTBOX') return input.textRegionId ? 'pointer' : 'grab';

  if (hit && (hit.type === 'ITEM' || hit.type === 'CONNECTOR')) {
    return 'pointer';
  }

  return 'grab';
};
