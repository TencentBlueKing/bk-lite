import type { Coords } from 'src/types';
import { getTilePosition, sortByPosition } from 'src/utils/renderer';
import { UNPROJECTED_TILE_SIZE } from 'src/config';

/** Unprojected corner radius of an area's rounded rectangle. */
export const RECTANGLE_CORNER_RADIUS = 22;

/**
 * Placement of the area alert label in the area's own ground plane (unprojected
 * px, before the iso matrix). `along` is how far the label ends before the
 * sharp right corner; it sits inside the rounded corner so the badge hugs the
 * lower-right of the area. `inset` keeps it just clear of the border stroke.
 */
export const RECTANGLE_EDGE_LABEL_OFFSET = {
  along: 8,
  inset: 6
} as const;

/** Label box in the area plane: height, side padding, icon, icon-to-number gap, font. */
export const RECTANGLE_EDGE_LABEL_SIZE = {
  height: 42,
  padX: 17,
  icon: 20,
  gap: 10,
  fontSize: 22,
  radius: 7
} as const;

/**
 * Scale for the edge label so it fits the straight part of a short lower-right
 * edge (between the two rounded corners). 1 when it fits; never below 0.6.
 */
export const getEdgeLabelScale = (from: Coords, to: Coords, count: number): number => {
  const { lowX, highX } = sortByPosition([from, to]);
  const edge = (highX - lowX + 1) * UNPROJECTED_TILE_SIZE;
  const room = edge - RECTANGLE_EDGE_LABEL_OFFSET.along - RECTANGLE_CORNER_RADIUS;
  const { padX, icon, gap, fontSize } = RECTANGLE_EDGE_LABEL_SIZE;
  // Bold tabular digits are about 0.62 em wide.
  const width = 2 * padX + icon + gap + String(count).length * fontSize * 0.62;

  return Math.min(1, Math.max(0.6, room / width));
};

// Screen-top vertex of a rectangle. Tile y grows toward the top of the
// isometric view, so the corner with the greatest x + y is the peak.
// low/high normalisation makes from/to order irrelevant.
export const getRectangleTopTile = (from: Coords, to: Coords): Coords => {
  const { highX, highY } = sortByPosition([from, to]);

  return { x: highX, y: highY };
};

export const getRectangleTopVertex = (from: Coords, to: Coords): Coords => {
  return getTilePosition({
    tile: getRectangleTopTile(from, to),
    origin: 'TOP'
  });
};

// Screen-front vertex. The corner with the smallest x + y is nearest the
// viewer, and BOTTOM origin sits on the outside of that corner.
export const getRectangleFrontTile = (from: Coords, to: Coords): Coords => {
  const { lowX, lowY } = sortByPosition([from, to]);

  return { x: lowX, y: lowY };
};

export const getRectangleFrontVertex = (from: Coords, to: Coords): Coords => {
  return getTilePosition({
    tile: getRectangleFrontTile(from, to),
    origin: 'BOTTOM'
  });
};

// Screen-right vertex. Screen x is tile.x - tile.y, so the corner with the
// greatest x and the smallest y is the rightmost. RIGHT origin sits outside it.
export const getRectangleRightTile = (from: Coords, to: Coords): Coords => {
  const { highX, lowY } = sortByPosition([from, to]);

  return { x: highX, y: lowY };
};

export const getRectangleRightVertex = (from: Coords, to: Coords): Coords => {
  return getTilePosition({
    tile: getRectangleRightTile(from, to),
    origin: 'RIGHT'
  });
};
