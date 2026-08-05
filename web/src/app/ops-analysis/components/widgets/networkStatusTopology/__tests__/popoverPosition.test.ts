import assert from 'node:assert/strict';
import test from 'node:test';
import {
  clampPopoverInContainer,
  placeBesideIcon,
  placeNearCursor,
  screenRectToLocalRect,
  toLocalPixels,
} from '../popoverPosition';

test('placeBesideIcon sticks to upper-right beside icon', () => {
  const point = placeBesideIcon(
    { x: 100, y: 100, width: 72, height: 72 },
    { width: 200, height: 90 },
    { width: 800, height: 600 },
    10,
  );
  assert.equal(point.x, 182); // 100 + 72 + 10
  assert.equal(point.y, 90); // 100 - 10，贴在 icon 旁而非正上方
});

test('placeBesideIcon flips left when right side overflows', () => {
  const point = placeBesideIcon(
    { x: 700, y: 200, width: 72, height: 72 },
    { width: 200, height: 90 },
    { width: 800, height: 600 },
    10,
  );
  assert.equal(point.x, 490); // 700 - 200 - 10
  assert.equal(point.y, 190); // 200 - 10
});

test('placeBesideIcon clamps when near top edge', () => {
  const point = placeBesideIcon(
    { x: 100, y: 12, width: 72, height: 72 },
    { width: 200, height: 90 },
    { width: 800, height: 600 },
    10,
  );
  assert.equal(point.x, 182);
  assert.equal(point.y, 8); // 12 - 10 = 2 → clamp 到 padding
});

test('clampPopoverInContainer keeps popover inside bounds', () => {
  const point = clampPopoverInContainer(
    { x: 900, y: 700 },
    { width: 200, height: 100 },
    { width: 800, height: 600 },
  );
  assert.equal(point.x, 592); // 800 - 200 - 8
  assert.equal(point.y, 492); // 600 - 100 - 8
});

test('placeNearCursor applies small offset then clamps', () => {
  const point = placeNearCursor(
    { x: 10, y: 10 },
    { width: 200, height: 100 },
    { width: 800, height: 600 },
    { x: 12, y: 12 },
  );
  assert.equal(point.x, 22);
  assert.equal(point.y, 22);
});

test('toLocalPixels undoes CSS viewport scale', () => {
  assert.equal(toLocalPixels(200, 0.5), 400);
  assert.equal(toLocalPixels(200, 1), 200);
  assert.equal(toLocalPixels(200, 0), 200); // invalid → treat as 1
});

test('screenRectToLocalRect restores local coords under scale', () => {
  const local = screenRectToLocalRect(
    { left: 150, top: 120, width: 36, height: 36 },
    { left: 100, top: 100 },
    0.5,
  );
  // screen delta (50, 20, 36, 36) / 0.5 → (100, 40, 72, 72)
  assert.equal(local.x, 100);
  assert.equal(local.y, 40);
  assert.equal(local.width, 72);
  assert.equal(local.height, 72);
});
