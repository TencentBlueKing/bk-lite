import assert from 'node:assert/strict';
import { PROJECTED_TILE_SIZE } from 'src/config';
import { getTilePosition, screenToIso } from 'src/utils/renderer';
import { CoordsUtils } from 'src/utils/CoordsUtils';
import {
  findDrawnIconId,
  findIconHit,
  findRectangleBadgeId,
  readIconHitRects,
  isPrimaryPointerEvent,
  regionIdForTextClick,
  resolveViewClick,
  viewHoverCursor,
  type IconHitRect,
  type IconHitRoot
} from '../viewPointer';

const rendererSize = { width: 800, height: 600 };
const center = { x: rendererSize.width / 2, y: rendererSize.height / 2 };
const scroll = { position: CoordsUtils.zero(), offset: CoordsUtils.zero() };

const anchorScreen = getTilePosition({ tile: { x: 0, y: 0 }, origin: 'BOTTOM' });
const anchor = {
  x: center.x + anchorScreen.x,
  y: center.y + anchorScreen.y
};

const tileAt = (point: { x: number; y: number }) => {
  return screenToIso({
    mouse: point,
    zoom: 1,
    scroll,
    rendererSize
  });
};

const imageWidth = PROJECTED_TILE_SIZE.width * 0.8;
const imageHeight = PROJECTED_TILE_SIZE.width;
const imageRect: IconHitRect = {
  id: 'node-a',
  order: 0,
  index: 0,
  left: anchor.x - imageWidth / 2,
  top: anchor.y - imageHeight,
  right: anchor.x + imageWidth / 2,
  bottom: anchor.y
};

const upperPoint = { x: anchor.x, y: imageRect.top + 4 };

const badgeWidth = 16;
const badgeLeft = anchor.x + PROJECTED_TILE_SIZE.width / 2 - 2;
const badgeTop = anchor.y - PROJECTED_TILE_SIZE.height / 2 - badgeWidth / 2;
const badgeRect: IconHitRect = {
  id: 'node-a',
  order: 0,
  index: 1,
  left: badgeLeft,
  top: badgeTop,
  right: badgeLeft + badgeWidth,
  bottom: badgeTop + badgeWidth
};
const badgeEdge = { x: badgeRect.right - 1, y: anchor.y - PROJECTED_TILE_SIZE.height / 2 };

const upperTile = tileAt(upperPoint);

assert.notDeepEqual(upperTile, { x: 0, y: 0 });
assert.equal(findIconHit(upperPoint, [imageRect, badgeRect]), 'node-a');
assert.deepEqual(
  resolveViewClick({
    iconId: findIconHit(upperPoint, [imageRect]),
    tileHit: { type: 'RECTANGLE', id: 'zone-above' }
  }),
  { kind: 'click', item: { type: 'ITEM', id: 'node-a' } }
);
assert.deepEqual(
  resolveViewClick({
    iconId: findIconHit(upperPoint, [imageRect]),
    tileHit: { type: 'CONNECTOR', id: 'line-above' }
  }),
  { kind: 'click', item: { type: 'ITEM', id: 'node-a' } }
);

assert.equal(findIconHit(badgeEdge, [imageRect, badgeRect]), 'node-a');
assert.deepEqual(
  resolveViewClick({
    iconId: 'node-a',
    tileHit: { type: 'CONNECTOR', id: 'line-beside' }
  }),
  { kind: 'click', item: { type: 'ITEM', id: 'node-a' } }
);

const missed = { x: imageRect.left - 30, y: imageRect.bottom + 30 };

assert.equal(findIconHit(missed, [imageRect, badgeRect]), null);
assert.deepEqual(
  resolveViewClick({ iconId: null, tileHit: { type: 'RECTANGLE', id: 'zone' } }),
  { kind: 'click', item: { type: 'RECTANGLE', id: 'zone' } }
);
// The area alert label lies under icons: an icon on the corner tile wins,
// otherwise the label opens its area, even over another tile hit.
assert.deepEqual(
  resolveViewClick({
    badgeId: 'zone',
    iconId: 'node-a',
    tileHit: { type: 'RECTANGLE', id: 'zone' }
  }),
  { kind: 'click', item: { type: 'ITEM', id: 'node-a' } }
);
assert.deepEqual(
  resolveViewClick({
    badgeId: 'zone',
    iconId: null,
    tileHit: { type: 'CONNECTOR', id: 'line' }
  }),
  { kind: 'click', item: { type: 'RECTANGLE', id: 'zone' } }
);
assert.deepEqual(
  resolveViewClick({ iconId: null, tileHit: { type: 'CONNECTOR', id: 'line' } }),
  { kind: 'click', item: { type: 'CONNECTOR', id: 'line' } }
);
assert.deepEqual(resolveViewClick({ iconId: null, tileHit: null }), {
  kind: 'click',
  item: null
});
assert.deepEqual(
  resolveViewClick({ iconId: null, tileHit: { type: 'TEXTBOX', id: 'caption' } }),
  { kind: 'ignore' }
);
assert.deepEqual(
  resolveViewClick({
    iconId: null,
    tileHit: { type: 'TEXTBOX', id: 'caption' },
    textRegionId: 'zone'
  }),
  { kind: 'click', item: { type: 'RECTANGLE', id: 'zone' } }
);
assert.deepEqual(
  resolveViewClick({ iconId: null, tileHit: { type: 'ITEM', id: 'node-a' } }),
  { kind: 'click', item: { type: 'ITEM', id: 'node-a' } }
);

const back: IconHitRect = {
  id: 'back',
  order: -2,
  index: 5,
  left: 0,
  top: 0,
  right: 40,
  bottom: 40
};
const front: IconHitRect = {
  id: 'front',
  order: 1,
  index: 0,
  left: 10,
  top: 10,
  right: 30,
  bottom: 30
};

assert.equal(findIconHit({ x: 20, y: 20 }, [back, front]), 'front');

const element = (
  id: string,
  order: string | null,
  pad: string | null,
  box: { left: number; top: number; right: number; bottom: number }
) => {
  return {
    getAttribute: (name: string) => {
      if (name === 'data-icon-hit') return id;
      if (name === 'data-icon-order') return order;
      if (name === 'data-icon-pad') return pad;
      return null;
    },
    getBoundingClientRect: () => box
  };
};

const root: IconHitRoot = {
  querySelectorAll: () => [
    element('node-a', '0', '3', { left: 10, top: 20, right: 30, bottom: 40 }),
    element('', '0', null, { left: 0, top: 0, right: 8, bottom: 8 }),
    element('flat', '1', null, { left: 0, top: 0, right: 0, bottom: 4 }),
    element('badge', '-1', null, { left: 100, top: 100, right: 116, bottom: 116 })
  ]
};
const read = readIconHitRects(root);

assert.deepEqual(
  read.map((rect) => rect.id),
  ['node-a', 'badge']
);
assert.equal(findIconHit({ x: 8, y: 18 }, read), 'node-a');
assert.equal(findIconHit({ x: 6, y: 18 }, read), null);
assert.equal(findDrawnIconId(root, { x: 115, y: 108 }), 'badge');
assert.equal(findDrawnIconId(null, { x: 0, y: 0 }), null);

assert.equal(viewHoverCursor({ iconId: 'node-a', tileHit: { type: 'RECTANGLE', id: 'zone' } }), 'pointer');
assert.equal(viewHoverCursor({ iconId: null, tileHit: { type: 'ITEM', id: 'node-a' } }), 'pointer');
assert.equal(viewHoverCursor({ iconId: null, tileHit: { type: 'RECTANGLE', id: 'zone' } }), 'pointer');
assert.equal(viewHoverCursor({ iconId: null, tileHit: { type: 'CONNECTOR', id: 'line' } }), 'pointer');
assert.equal(viewHoverCursor({ iconId: null, tileHit: { type: 'TEXTBOX', id: 'caption' } }), 'grab');
assert.equal(
  viewHoverCursor({
    iconId: null,
    tileHit: { type: 'TEXTBOX', id: 'caption' },
    textRegionId: 'zone'
  }),
  'pointer'
);
assert.equal(viewHoverCursor({ iconId: null, tileHit: null }), 'grab');
assert.equal(
  viewHoverCursor({ badgeId: 'zone', iconId: null, tileHit: null }),
  'pointer'
);

const plateRect: IconHitRect = {
  id: 'node-a',
  order: 1_000_000,
  index: 2,
  left: anchor.x - 40,
  top: imageRect.top - 36,
  right: anchor.x + 40,
  bottom: imageRect.top - 4
};
const platePoint = { x: anchor.x, y: plateRect.top + 6 };

assert.equal(findIconHit(platePoint, [imageRect]), null);
assert.equal(findIconHit(platePoint, [imageRect, plateRect]), 'node-a');
assert.deepEqual(
  resolveViewClick({
    iconId: findIconHit(platePoint, [imageRect, plateRect]),
    tileHit: { type: 'RECTANGLE', id: 'zone-under-plate' }
  }),
  { kind: 'click', item: { type: 'ITEM', id: 'node-a' } }
);

const badgeRoot: IconHitRoot = {
  querySelectorAll(selector: string) {
    if (selector !== '[data-rectangle-badge-hit]') return [];

    return [
      {
        getAttribute: () => 'zone',
        getBoundingClientRect: () => ({ left: 10, top: 10, right: 80, bottom: 32 })
      }
    ];
  }
};

assert.equal(findRectangleBadgeId(badgeRoot, { x: 20, y: 20 }), 'zone');
assert.equal(findRectangleBadgeId(badgeRoot, { x: 1, y: 1 }), null);

const zone = { id: 'zone', from: { x: 0, y: 0 }, to: { x: 3, y: 3 } };
const overlap = { id: 'overlap', from: { x: 2, y: 2 }, to: { x: 5, y: 5 } };
const title = { id: 'title', tile: { x: 1, y: 1 }, content: '这是一个区域' };
const caption = { id: 'caption', tile: { x: -1, y: 0 }, content: '画出的标题' };
const farther = { id: 'farther', tile: { x: -1, y: -1 }, content: '更远的字' };
const stray = { id: 'stray', tile: { x: 8, y: 8 }, content: '外面' };
const blank = { id: 'blank', tile: { x: -1, y: -1 }, content: '   ' };

assert.equal(
  regionIdForTextClick({
    tile: { x: 1, y: 1 },
    textBoxId: 'title',
    rectangles: [zone, overlap],
    textBoxes: [title]
  }),
  'zone'
);
assert.equal(
  regionIdForTextClick({
    tile: { x: 2, y: 2 },
    textBoxId: 'title',
    rectangles: [zone, overlap],
    textBoxes: [title]
  }),
  'zone'
);
assert.equal(
  regionIdForTextClick({
    tile: { x: 4, y: 4 },
    textBoxId: 'title',
    rectangles: [zone, overlap],
    textBoxes: [title]
  }),
  'overlap'
);
assert.equal(
  regionIdForTextClick({
    tile: { x: 6, y: 0 },
    textBoxId: 'title',
    rectangles: [zone],
    textBoxes: [title]
  }),
  'zone'
);
assert.equal(
  regionIdForTextClick({
    tile: { x: -1, y: 0 },
    textBoxId: 'caption',
    rectangles: [zone],
    textBoxes: [caption, farther]
  }),
  'zone'
);
assert.equal(
  regionIdForTextClick({
    tile: { x: -1, y: -1 },
    textBoxId: 'farther',
    rectangles: [zone],
    textBoxes: [caption, farther]
  }),
  null
);
assert.equal(
  regionIdForTextClick({
    tile: { x: 8, y: 8 },
    textBoxId: 'stray',
    rectangles: [zone],
    textBoxes: [stray, blank]
  }),
  null
);
assert.equal(
  regionIdForTextClick({
    tile: { x: -1, y: -1 },
    textBoxId: 'blank',
    rectangles: [zone],
    textBoxes: [blank]
  }),
  null
);

// Primary-button gate: right button never starts click/select/drag.
assert.equal(isPrimaryPointerEvent({ button: 0 }), true);
assert.equal(isPrimaryPointerEvent({ button: 2 }), false);
assert.equal(isPrimaryPointerEvent({ button: 1 }), false);
assert.equal(isPrimaryPointerEvent({}), true);

console.log('viewPointer ok');
