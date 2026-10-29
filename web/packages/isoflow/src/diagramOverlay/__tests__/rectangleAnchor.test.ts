import assert from 'node:assert/strict';
import { getTilePosition } from 'src/utils/renderer';
import { RECTANGLE_STATUS_STROKE_HOVER_WIDTH } from 'src/diagramOverlay/colors';
import {
  getRectangleFrontTile,
  getRectangleFrontVertex,
  RECTANGLE_CORNER_RADIUS,
  RECTANGLE_EDGE_LABEL_OFFSET,
  getEdgeLabelScale,
  getRectangleRightTile,
  getRectangleRightVertex,
  getRectangleTopTile,
  getRectangleTopVertex
} from '../rectangleAnchor';

const forward = { from: { x: 0, y: 1 }, to: { x: 2, y: 4 } };
const reversed = { from: { x: 2, y: 4 }, to: { x: 0, y: 1 } };

assert.deepEqual(getRectangleTopTile(forward.from, forward.to), { x: 2, y: 4 });
assert.deepEqual(
  getRectangleTopTile(reversed.from, reversed.to),
  getRectangleTopTile(forward.from, forward.to)
);
assert.deepEqual(
  getRectangleTopVertex(reversed.from, reversed.to),
  getRectangleTopVertex(forward.from, forward.to)
);

const peak = getRectangleTopVertex(forward.from, forward.to);
const corners = [
  { x: 0, y: 1 },
  { x: 2, y: 1 },
  { x: 0, y: 4 },
  { x: 2, y: 4 }
];

corners.forEach((tile) => {
  const top = getTilePosition({ tile, origin: 'TOP' });
  assert.ok(peak.y <= top.y);
});

assert.deepEqual(getRectangleFrontTile(forward.from, forward.to), { x: 0, y: 1 });
assert.deepEqual(
  getRectangleFrontTile(reversed.from, reversed.to),
  getRectangleFrontTile(forward.from, forward.to)
);
assert.deepEqual(
  getRectangleFrontVertex(reversed.from, reversed.to),
  getRectangleFrontVertex(forward.from, forward.to)
);

const front = getRectangleFrontVertex(forward.from, forward.to);
corners.forEach((tile) => {
  const bottom = getTilePosition({ tile, origin: 'BOTTOM' });
  assert.ok(front.y >= bottom.y);
});

assert.deepEqual(getRectangleRightTile(forward.from, forward.to), { x: 2, y: 1 });
assert.deepEqual(
  getRectangleRightTile(reversed.from, reversed.to),
  getRectangleRightTile(forward.from, forward.to)
);
assert.deepEqual(
  getRectangleRightVertex(reversed.from, reversed.to),
  getRectangleRightVertex(forward.from, forward.to)
);

const right = getRectangleRightVertex(forward.from, forward.to);
corners.forEach((tile) => {
  const side = getTilePosition({ tile, origin: 'RIGHT' });
  assert.ok(right.x >= side.x);
});
// RIGHT origin only shifts x, so the vertex keeps the corner tile's height.
assert.equal(right.y, getTilePosition({ tile: { x: 2, y: 1 }, origin: 'CENTER' }).y);

// The edge label hugs the lower-right corner, inside the rounded corner, and
// still clears the border (the hover stroke is centred on the outline).
assert.ok(RECTANGLE_EDGE_LABEL_OFFSET.along > 0);
assert.ok(RECTANGLE_EDGE_LABEL_OFFSET.along < RECTANGLE_CORNER_RADIUS);
assert.ok(RECTANGLE_EDGE_LABEL_OFFSET.inset > RECTANGLE_STATUS_STROKE_HOVER_WIDTH / 2);

// Long lower-right edges keep the full label; a one-tile edge shrinks it to fit
// between the rounded corners, and the scale never collapses.
assert.equal(getEdgeLabelScale({ x: 0, y: 0 }, { x: 2, y: 2 }, 11), 1);
const short = getEdgeLabelScale({ x: 0, y: 0 }, { x: 0, y: 1 }, 4);
assert.ok(short < 1 && short >= 0.6);
assert.equal(
  getEdgeLabelScale({ x: 0, y: 1 }, { x: 0, y: 0 }, 4),
  short
);
assert.equal(getEdgeLabelScale({ x: 0, y: 0 }, { x: 0, y: 0 }, 1234), 0.6);

console.log('rectangleAnchor ok');
