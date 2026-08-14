import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  buildRoom3DInitialView,
  buildRoom3DSceneLayout,
  getRoom3DRackScenePosition,
  ROOM3D_ROW_GAP,
} from "../room3DScene";

const getProjectedRoomCenter = (
  layout: ReturnType<typeof buildRoom3DSceneLayout>,
  aspect: number,
) => {
  const { cameraPosition, target } = buildRoom3DInitialView(layout, aspect);
  const camera = new THREE.PerspectiveCamera(42, aspect, 0.1, 1000);
  camera.position.copy(cameraPosition);
  camera.lookAt(target);
  camera.updateMatrixWorld(true);

  const projectedBounds = [-1, 1].flatMap((xDirection) =>
    [0, 1.95].flatMap((height) =>
      [-1, 1].map((zDirection) =>
        new THREE.Vector3(
          (xDirection * layout.floorWidth) / 2,
          height,
          (zDirection * layout.floorDepth) / 2,
        ).project(camera),
      ),
    ),
  );
  const xCoordinates = projectedBounds.map((point) => point.x);
  const yCoordinates = projectedBounds.map((point) => point.y);

  return {
    x: (Math.min(...xCoordinates) + Math.max(...xCoordinates)) / 2,
    y: (Math.min(...yCoordinates) + Math.max(...yCoordinates)) / 2,
    minX: Math.min(...xCoordinates),
    maxX: Math.max(...xCoordinates),
    minY: Math.min(...yCoordinates),
    maxY: Math.max(...yCoordinates),
  };
};

describe("room3D scene layout", () => {
  it("keeps a long room readable without turning it into a narrow corridor", () => {
    const layout = buildRoom3DSceneLayout(
      Array.from({ length: 9 }, (_, index) => ({
        row: index + 1,
        col: 1,
      })),
    );

    expect(layout.floorDepth).toBeGreaterThan(layout.floorWidth);
    expect(layout.floorDepth / layout.floorWidth).toBeLessThanOrEqual(2.8);
    expect(
      Math.abs(layout.initialCameraPosition.z / layout.initialCameraPosition.x),
    ).toBeGreaterThan(0.85);
    expect(layout.initialCameraPosition.y).toBeLessThan(
      layout.initialCameraPosition.z,
    );
  });

  it("maps letter columns horizontally and numeric rows into scene depth", () => {
    const bounds = { maxRow: 9, maxCol: 2 };
    const firstRow = getRoom3DRackScenePosition(
      { row: 1, col: 1 },
      bounds,
    );
    const ninthRow = getRoom3DRackScenePosition(
      { row: 9, col: 1 },
      bounds,
    );
    const nextColumn = getRoom3DRackScenePosition(
      { row: 1, col: 2 },
      bounds,
    );

    expect(ninthRow.x).toBe(firstRow.x);
    expect(ninthRow.z).toBeLessThan(firstRow.z);
    expect(nextColumn.x).toBeGreaterThan(firstRow.x);
    expect(nextColumn.z).toBe(firstRow.z);
  });

  it("preserves service aisles and fits a row-dominant room from its long side", () => {
    const layout = buildRoom3DSceneLayout(
      Array.from({ length: 6 }, (_, rowIndex) =>
        Array.from({ length: 3 }, (_, colIndex) => ({
          row: rowIndex + 1,
          col: colIndex + 1,
        })),
      ).flat(),
    );

    expect(ROOM3D_ROW_GAP).toBe(5.4);
    expect(layout.floorDepth).toBeGreaterThan(layout.floorWidth);
    expect(layout.floorDepth / layout.floorWidth).toBeLessThanOrEqual(2.8);
    expect(Math.abs(layout.initialCameraPosition.x)).toBeGreaterThan(
      Math.abs(layout.initialCameraPosition.z),
    );
  });

  it("keeps the projected room near the center in the initial wide-screen view", () => {
    const layout = buildRoom3DSceneLayout(
      Array.from({ length: 6 }, (_, rowIndex) =>
        Array.from({ length: 3 }, (_, colIndex) => ({
          row: rowIndex + 1,
          col: colIndex + 1,
        })),
      ).flat(),
    );

    const projectedCenter = getProjectedRoomCenter(layout, 993 / 427);

    expect(Math.abs(projectedCenter.x)).toBeLessThan(0.12);
    expect(Math.abs(projectedCenter.y)).toBeLessThan(0.12);
    expect(projectedCenter.minX).toBeGreaterThanOrEqual(-1);
    expect(projectedCenter.maxX).toBeLessThanOrEqual(1);
    expect(projectedCenter.minY).toBeGreaterThanOrEqual(-1);
    expect(projectedCenter.maxY).toBeLessThanOrEqual(1);
  });
});
