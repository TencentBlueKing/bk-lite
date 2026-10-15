import { describe, expect, it } from 'vitest';
import { createScreenTextItem } from '../screenItems';
import { moveScreenItemLayer, moveScreenItemToIndex } from '../screenLayer';

const stack = () => [
  createScreenTextItem([], { id: 'a', content: 'A', zIndex: 1 }),
  createScreenTextItem([], { id: 'b', content: 'B', zIndex: 2 }),
  createScreenTextItem([], { id: 'c', content: 'C', zIndex: 3 }),
];

const order = (items: ReturnType<typeof stack>) =>
  [...items]
    .sort((left, right) => right.zIndex - left.zIndex)
    .map((item) => item.id);

describe('screen layer order', () => {
  it('moves one step and to the ends without colliding on shared ranks', () => {
    expect(order(moveScreenItemLayer(stack(), 'a', 'bringForward'))).toEqual([
      'c',
      'a',
      'b',
    ]);
    expect(order(moveScreenItemLayer(stack(), 'c', 'sendBackward'))).toEqual([
      'b',
      'c',
      'a',
    ]);
    expect(order(moveScreenItemLayer(stack(), 'a', 'bringToFront'))).toEqual([
      'a',
      'c',
      'b',
    ]);
    expect(order(moveScreenItemLayer(stack(), 'c', 'bringToBack'))).toEqual([
      'b',
      'a',
      'c',
    ]);
    const original = stack();
    expect(moveScreenItemLayer(original, 'c', 'bringToFront')).toBe(original);
    expect(moveScreenItemLayer(original, 'a', 'bringToBack')).toBe(original);
  });

  it('drops a list row onto another row and rewrites zIndex from the top', () => {
    const next = moveScreenItemToIndex(stack(), 'c', 2);
    expect(order(next)).toEqual(['b', 'a', 'c']);
    expect(next.find((item) => item.id === 'b')?.zIndex).toBe(3);
    expect(next.find((item) => item.id === 'c')?.zIndex).toBe(1);
    const original = stack();
    expect(moveScreenItemToIndex(original, 'c', 0)).toBe(original);
  });
});
