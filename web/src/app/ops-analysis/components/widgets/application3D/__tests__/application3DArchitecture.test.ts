import * as THREE from 'three';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { Application3DArchitectureData } from '@/app/ops-analysis/types/sceneWidget';
import { CARD_GLASS, CARD_TONE } from '../application3DCardStyle';
import { APPLICATION3D_CAMERA_FOV } from '../application3DLayout';
import {
  ARCH_CAMERA_FRAME_FILL,
  ARCH_CAMERA_PHI,
  ARCH_CAMERA_RADIUS,
  ARCH_FRUSTUM_HEIGHT,
  ARCH_FRUSTUM_TAPER,
  ARCH_FRONT_INSET,
  ARCH_GRID_PITCH,
  ARCH_WRAP_COLS,
  ARCH_LABEL_BILLBOARD,
  ARCH_LABEL_CANVAS_HEIGHT,
  ARCH_LABEL_CANVAS_WIDTH,
  ARCH_LABEL_FILL,
  ARCH_LABEL_HAS_BACKGROUND,
  ARCH_LABEL_WORLD_HEIGHT,
  ARCH_LABEL_WORLD_WIDTH,
  ARCH_NODE_SIZE,
  ARCH_PLANE_COUNT,
  ARCH_PLANE_DEPTH_WRITE,
  ARCH_PLANE_EMISSIVE_INTENSITY,
  ARCH_PLANE_GAP,
  ARCH_PLANE_MIN_DEPTH,
  ARCH_PLANE_MIN_WIDTH,
  ARCH_PLANE_OPACITY,
  ARCH_PLANE_ORIENTATION,
  ARCH_PLANE_RIM_BLENDING,
  ARCH_PLANE_RIM_COLOR,
  ARCH_PLANE_RIM_FALLOFF,
  ARCH_PLANE_RIM_HALO_WORLD,
  ARCH_PLANE_RIM_HAS_EDGE_LINES,
  ARCH_PLANE_RIM_INNER,
  ARCH_PLANE_RIM_OPACITY,
  ARCH_PLANE_RIM_OUTER,
  ARCH_PLANE_RIM_STROKE_OPACITY,
  ARCH_PLANE_RIM_STROKE_WORLD,
  ARCH_PLANE_ROTATION_X,
  ARCH_PLANE_SIDE_EMISSIVE_INTENSITY,
  ARCH_PLANE_SIDE_HAS_STROKE,
  ARCH_PLANE_SIDE_MATCHES_TOP_HUE,
  ARCH_PLANE_SIDE_OPACITY,
  ARCH_PLANE_PAD,
  ARCH_PLANE_THICKNESS,
  ARCH_PLANE_TITLE,
  ARCH_PLANE_TITLE_SIDE,
  ARCH_PLANE_WORLD_DEPTH,
  ARCH_PLANE_WORLD_HEIGHT,
  ARCH_PLANE_FRONT_Z,
  ARCH_PLANE_WORLD_WIDTH,
  ARCH_PLANE_Y,
  ARCH_PULSE_HALO_BLENDING,
  ARCH_PULSE_HALO_FALLOFF,
  ARCH_PULSE_HALO_INTENSITY,
  ARCH_PULSE_HALO_RADIUS,
  ARCH_PULSE_HALO_TRAIL_POWER,
  ARCH_PULSE_RADIAL_SEGMENTS,
  ARCH_PULSE_RADIUS,
  ARCH_PULSE_RGB_SCALE,
  ARCH_PULSE_SPEED,
  ARCH_PULSE_STYLE,
  ARCH_PULSE_TAIL_ALPHA,
  ARCH_PULSE_TRAIL,
  ARCH_PULSE_TRAIL_MAX,
  ARCH_PULSE_TUBULAR_SEGMENTS,
  ARCH_PULSE_WORLD_LENGTH,
  ARCH_PULSE_WRAP_OFFSET,
  ARCH_STACK_ORIGIN,
  ARCH_TITLE_FILL,
  ARCH_TITLE_FRONT_INSET,
  ARCH_TITLE_RIGHT_OUTSET,
  ARCH_TITLE_SHADOW_BLUR,
  ARCH_TITLE_SHADOW_COLOR,
  ARCH_TUBE_ALARM_COLOR,
  ARCH_TUBE_ALARM_EMISSIVE_INTENSITY,
  ARCH_TUBE_ALARM_OPACITY,
  ARCH_TUBE_COLOR,
  ARCH_TUBE_EMISSIVE_INTENSITY,
  ARCH_TUBE_IN_GLOW_LAYER,
  ARCH_TUBE_OPACITY,
  ARCH_TUBE_RADIAL_SEGMENTS,
  ARCH_TUBE_RADIUS_INTER,
  ARCH_TUBE_RADIUS_INTRA,
  ARCH_TUBE_TUBULAR_SEGMENTS,
  architectureBoardFromContentMinZ,
  architectureCameraFitWidth,
  architectureFrontZ,
  architecturePulseBandIntensity,
  architecturePulseCompanionHead,
  architecturePulseCoreBlend,
  architecturePulseHaloAlong,
  architecturePulseHaloBlend,
  architecturePulseHaloRadius,
  architecturePulseIntensity,
  architecturePulsePathLit,
  architecturePulseRgbScale,
  architecturePulseTrailForLength,
  architectureRimBloomWeight,
  architectureRimUvWidth,
  architectureTitleLocalX,
  architectureTitleLocalZ,
  architectureTubeRadius,
  architectureWideBoardFloor,
  architectureWrapBoardWidth,
  architectureTubeStyle,
  describeArchitectureLandedFrame,
  fitArchitectureCameraDistance,
  describeWallCameraSpherical,
  formatArchitecturePlaneTitle,
  layoutApplication3DArchitecture,
  resolveArchitectureCameraPose,
  sphericalToOffset,
} from '../application3DArchitecture';
import {
  ARCH_CHASSIS_COLOR,
  ARCH_EDGE,
  ARCH_EDGE_ALARM,
  ARCH_LED_ALARM_COLOR,
  ARCH_LED_COLOR,
  ARCH_NODE_FILL,
  ARCH_PLANE,
  ARCH_PLANE_EMISSIVE,
  ARCH_RACK_FRONT_METALNESS,
  ARCH_RACK_FRONT_ROUGHNESS,
  ARCH_RACK_HULL_COLOR,
  ARCH_RACK_ALBEDO_LIFT_OFFSET,
  ARCH_RACK_ALBEDO_LIFT_SCALE,
  ARCH_RACK_LED_COUNT,
  ARCH_RACK_LED_RADIUS_UV,
  ARCH_RACK_LED_UV_U,
  ARCH_RACK_LED_UV_V,
  ARCH_RACK_LIFT,
  ARCH_RACK_SIDE_METALNESS,
  ARCH_RACK_SIDE_ROUGHNESS,
  ARCH_RACK_STROKE_WIDTH,
  ARCH_STROKE_ALARM_COLOR,
  ARCH_STROKE_EMISSIVE_INTENSITY,
  ARCH_RING_CYAN,
  ARCH_RING_ALARM,
  APP_CHIP_ICON_KINDS,
  ARCH_APP_CHIP_BEVEL,
  ARCH_APP_CHIP_FACE_LIFT,
  ARCH_APP_CHIP_BODY_RENDER_ORDER,
  ARCH_APP_CHIP_FACE_RENDER_ORDER,
  ARCH_APP_CHIP_GLASS_COLOR,
  ARCH_APP_CHIP_METALNESS,
  ARCH_APP_CHIP_NAME_MAX_CHARS,
  ARCH_APP_CHIP_OPACITY,
  ARCH_APP_CHIP_BODY_XY_SCALE,
  ARCH_APP_CHIP_PLATE_ALPHA,
  ARCH_APP_CHIP_RIM_BAKED,
  ARCH_APP_CHIP_RIM_HAS_EDGE_LINES,
  ARCH_APP_CHIP_RIM_STYLE,
  ARCH_APP_CHIP_ROUGHNESS,
  ARCH_APP_CHIP_ICON_FILL,
  ARCH_APP_CHIP_ICON_FILL_ALARM,
  ARCH_APP_CHIP_ICON_FILL_STRONG,
  ARCH_APP_CHIP_ICON_FILL_STRONG_ALARM,
  ARCH_APP_CHIP_ICON_GLOW,
  ARCH_APP_CHIP_ICON_GLOW_ALARM,
  ARCH_APP_CHIP_ICON_STROKE,
  ARCH_APP_CHIP_ICON_STROKE_ALARM,
  ARCH_APP_CHIP_SEPARATOR,
  ARCH_APP_CHIP_SEPARATOR_ALARM,
  ARCH_APP_CHIP_TITLE_FILL,
  ARCH_APP_CHIP_TITLE_SIZE,
  ARCH_APP_CHIP_TITLE_WEIGHT,
  ARCH_APP_CHIP_TRANSMISSION,
  ARCH_APP_CHIP_WALL_BORDER,
  ARCH_APP_CHIP_WALL_BORDER_ALARM,
  ARCH_APP_CHIP_WALL_BODY_BOTTOM,
  ARCH_APP_CHIP_WALL_BODY_TOP,
  ARCH_APP_CHIP_WALL_DIAGONAL_WASH,
  ARCH_APP_CHIP_WALL_DIAGONAL_WASH_ALARM,
  ARCH_APP_CHIP_WALL_INSET_DEEP,
  ARCH_APP_CHIP_WALL_INSET_DEEP_ALARM,
  ARCH_APP_CHIP_WALL_INSET_GLOW,
  ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM,
  ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM_PX,
  ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM_WIDTH,
  ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_ALARM_PX,
  ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_PX,
  ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_WIDTH,
  ARCH_APP_CHIP_WALL_INSET_GLOW_WIDTH,
  ARCH_APP_CHIP_WALL_INSET_GLOW_PX,
  ARCH_APP_CHIP_WALL_INSET_LINE,
  ARCH_APP_CHIP_WALL_INSET_LINE_ALARM,
  ARCH_APP_CHIP_WALL_INSET_LINE_PX,
  ARCH_APP_CHIP_WALL_INSET_TOP,
  ARCH_APP_CHIP_WALL_INSET_TOP_ALARM,
  ARCH_APP_CHIP_WALL_SHEEN,
  ARCH_APP_CHIP_WALL_SHEEN_ALARM,
  ARCH_APP_CHIP_WALL_SHEEN_HEIGHT_PX,
  ARCH_APP_CHIP_WALL_STROKE_RATIO,
  ARCH_APP_CHIP_WALL_TOP_VEIL,
  ARCH_APP_CHIP_WALL_TOP_VEIL_ALARM,
  architectureAppChipBodyFrontZ,
  architectureAppChipFaceZ,
  architectureAppChipRimStrokePx,
  architectureAppChipWallBorder,
  architectureAppChipWallHighlight,
  architectureAppChipWallInset,
  architectureAppChipWallInsetBloom,
  architectureAppChipIconPaint,
  architectureAppChipSeparator,
  paintAppChipGlassPlate,
  appChipIconKind,
  applicationHasAlarm,
  architectureEdgeColor,
  architectureSelectionRingAlarming,
  architectureNodeLabelScale,
  architecturePulseProgress,
  createArchitectureEdgeCurve,
  createArchitectureTreeGroup,
  createRoundedChipGeometry,
  createTrapezoidFrustumGeometry,
  hashAppChipIconIndex,
  hostHasAlarm,
  findArchitectureRackRoot,
  liftCabinetAlbedoPixels,
  liftCabinetAlbedoTexture,
  truncateAppChipName,
  updateArchitecturePulse,
  yawObjectAroundYToCamera,
} from '../application3DArchitectureView';
import { ARCHITECTURE_MOTION } from '../application3DMotion';

const health = {
  state: 'normal' as const,
  reason: 'no_active_alarm' as const,
  activeAlarmCount: 0,
  severityCounts: { critical: 0, error: 0, warning: 0, info: 0 },
  noDataAlarmCount: 0,
  highestSeverity: { id: 'normal' as const, label: '正常', rank: 0 as const, color: 'success' as const },
  stale: false,
};

const tree = (overrides?: Partial<Application3DArchitectureData>): Application3DArchitectureData => ({
  systemId: 'sys-1',
  refreshedAt: '2026-09-01T00:00:00Z',
  nodes: [
    { id: 'sys-1', kind: 'system', name: '门户系统', health },
    { id: 'app-1', kind: 'application', name: '门户', health },
    { id: 'app-2', kind: 'application', name: '订单', health },
    { id: 'host-1', kind: 'host', name: 'web-1', health },
    { id: 'host-shared', kind: 'host', name: 'shared', health },
  ],
  edges: [
    { id: 'e1', sourceId: 'sys-1', targetId: 'app-1', relation: 'system_contains_application' },
    { id: 'e2', sourceId: 'sys-1', targetId: 'app-2', relation: 'system_contains_application' },
    { id: 'e3', sourceId: 'app-1', targetId: 'host-1', relation: 'application_run_host' },
    { id: 'e4', sourceId: 'app-1', targetId: 'host-shared', relation: 'application_run_host' },
    { id: 'e5', sourceId: 'app-2', targetId: 'host-shared', relation: 'application_run_host' },
  ],
  ...overrides,
});

const wallPose = {
  position: { x: 0, y: 0.48, z: 20 },
  target: { x: 0, y: 0, z: 0 },
};

/** Historical fences — production no longer exports these rejected sizes/poses. */
const ARCH_PREVIOUS_NODE_SIZE = {
  application: { width: 0.32, height: 0.52, depth: 0.26 },
  host: { width: 0.26, height: 0.42, depth: 0.22 },
} as const;
const ARCH_INVERTED_NODE_SIZE = {
  application: { width: 0.42, height: 0.68, depth: 0.34 },
  host: { width: 0.34, height: 0.55, depth: 0.28 },
} as const;
const ARCH_PREVIOUS_FILL_PLANE_WIDTH = 27.6;
const ARCH_PREVIOUS_FILL_PLANE_DEPTH = 19.2;
const ARCH_PREVIOUS_CAMERA_PHI = Math.PI / 2 - Math.PI / 8;
const ARCH_PREVIOUS_CHASSIS_COLOR = 0x3a3e44;

describe('application3D architecture layout', () => {
  it('places exactly two horizontal XZ ranks: 主机 lower, 应用 higher on +Y', () => {
    const layout = layoutApplication3DArchitecture(tree());
    const byId = Object.fromEntries(layout.nodes.map((node) => [node.id, node]));
    expect(layout.nodes.find((node) => node.kind === 'system')).toBeUndefined();
    expect(byId['sys-1']).toBeUndefined();
    expect(byId['app-1'].y).toBeGreaterThan(ARCH_PLANE_Y.application);
    expect(byId['host-1'].y).toBeGreaterThan(ARCH_PLANE_Y.host);
    expect(ARCH_PLANE_Y.application - ARCH_PLANE_Y.host).toBe(ARCH_PLANE_GAP);
    expect(ARCH_PLANE_Y.host).toBeLessThan(ARCH_PLANE_Y.application);
    expect(ARCH_STACK_ORIGIN).toBe(ARCH_PLANE_Y.host);
    expect(ARCH_PLANE_Y.host).toBeGreaterThan(0);
    expect(ARCH_PLANE_Y.application).toBeGreaterThan(ARCH_PLANE_Y.host);
    expect(byId['host-1'].y).toBeLessThan(byId['app-1'].y);
    expect(layout.nodes.filter((node) => node.id === 'host-shared')).toHaveLength(1);
    expect(layout.edges.filter((edge) => edge.targetId === 'host-shared')).toHaveLength(2);
    expect(byId['app-1'].x).not.toBe(byId['app-2'].x);
    expect(byId['app-1'].z).toBeCloseTo(architectureFrontZ(0));
    expect(byId['app-2'].z).toBeCloseTo(architectureFrontZ(0));
    expect(byId['app-1'].z).toBeGreaterThan(0);
    expect(byId['host-1'].z).toBeCloseTo(architectureFrontZ(0));
    expect(architectureFrontZ(0)).toBeGreaterThan(ARCH_PLANE_WORLD_DEPTH / 4);
    expect(ARCH_FRONT_INSET).toBeGreaterThan(0.5);
    expect(layout.planes).toHaveLength(2);
    expect(ARCH_PLANE_COUNT).toBe(2);
    expect(layout.planes.map((plane) => plane.kind)).toEqual(['host', 'application']);
    expect(layout.planes.map((plane) => plane.titleFallback)).toEqual(['主机', '应用']);
    expect(layout.planes.map((plane) => plane.titleText)).toEqual(['主机', '应用']);
    expect(layout.planes.map((plane) => plane.y)).toEqual([
      ARCH_PLANE_Y.host,
      ARCH_PLANE_Y.application,
    ]);
    expect(layout.planes[0].y).toBeLessThan(layout.planes[1].y);
    expect(layout.planes.every((plane) => plane.orientation === 'xz')).toBe(true);
    expect(layout.planes.every((plane) => Math.abs(plane.rotationX - (-Math.PI / 2)) < 1e-6)).toBe(true);
    expect(layout.planes.every((plane) => plane.z === 0 && plane.x === 0)).toBe(true);
    expect(layout.planes[0].shape).toBe('frustum');
    expect(layout.planes[1].shape).toBe('plane');
    expect(layout.stackBottomY).toBeLessThan(layout.planes[0].y);
    expect(layout.stackTopY).toBeGreaterThan(layout.planes[1].y);
    expect(ARCH_PLANE).toBe(0x163e5c);
    expect(ARCH_PLANE_EMISSIVE).toBe(0x1a6e98);
    expect(ARCH_PLANE_OPACITY).toBe(0.46);
    expect(ARCH_PLANE_OPACITY).toBeGreaterThan(0.1);
    expect(ARCH_PLANE_OPACITY).toBeLessThan(0.55);
    expect(ARCH_PLANE_EMISSIVE_INTENSITY).toBe(0.38);
    expect(ARCH_PLANE_EMISSIVE_INTENSITY).toBeGreaterThan(0.14);
    expect(ARCH_PLANE_EMISSIVE_INTENSITY).toBeLessThan(0.7);
    expect(ARCH_PLANE_DEPTH_WRITE).toBe(false);
    expect(ARCH_PLANE_TITLE_SIDE).toBe('right');
    expect(ARCH_PLANE_RIM_STROKE_OPACITY).toBeGreaterThan(0.5);
    expect(ARCH_PLANE_RIM_OPACITY).toBeGreaterThan(0.2);
    expect(ARCH_PLANE_RIM_OPACITY).toBeLessThan(0.5);
    expect(ARCH_PLANE_RIM_STROKE_WORLD).toBeGreaterThan(0.006);
    expect(ARCH_PLANE_RIM_STROKE_WORLD).toBeLessThan(0.02);
    expect(ARCH_PLANE_RIM_HALO_WORLD).toBeGreaterThan(ARCH_PLANE_RIM_STROKE_WORLD);
    expect(ARCH_PLANE_RIM_HALO_WORLD).toBeLessThan(0.2);
    expect(ARCH_PLANE_RIM_HALO_WORLD).toBeCloseTo(0.12);
    expect(ARCH_PLANE_RIM_BLENDING).toBe('normal');
    expect(ARCH_PLANE_RIM_INNER).toBe(architectureRimUvWidth(ARCH_PLANE_RIM_STROKE_WORLD));
    expect(ARCH_PLANE_RIM_OUTER).toBe(architectureRimUvWidth(ARCH_PLANE_RIM_HALO_WORLD));
    expect(ARCH_PLANE_RIM_INNER).toBeLessThan(0.008);
    expect(ARCH_PLANE_RIM_OUTER).toBeLessThan(0.016);
    expect(ARCH_PLANE_RIM_OUTER).toBeLessThan(0.022);
    expect(ARCH_PLANE_RIM_OUTER).toBeGreaterThan(ARCH_PLANE_RIM_INNER);
    expect(ARCH_PLANE_RIM_FALLOFF).toBeGreaterThanOrEqual(1);
    expect(architectureRimBloomWeight(ARCH_PLANE_RIM_STROKE_WORLD)).toBe(1);
    expect(architectureRimBloomWeight(0.05)).toBeGreaterThan(0);
    expect(architectureRimBloomWeight(0.05)).toBeLessThan(1);
    expect(architectureRimBloomWeight(ARCH_PLANE_RIM_HALO_WORLD)).toBe(0);
    expect(architectureRimBloomWeight(0.2)).toBe(0);
    expect(architectureRimBloomWeight(0.5)).toBe(0);
    expect(architectureRimUvWidth(ARCH_PLANE_RIM_HALO_WORLD, 12)).toBeLessThan(0.022);
    expect(ARCH_PLANE_RIM_HAS_EDGE_LINES).toBe(false);
    expect(ARCH_PLANE_RIM_COLOR).toBeGreaterThan(0);
    expect(ARCH_PLANE_SIDE_OPACITY).toBe(0.32);
    expect(ARCH_PLANE_SIDE_EMISSIVE_INTENSITY).toBe(0.30);
    expect(ARCH_PLANE_SIDE_OPACITY).not.toBe(ARCH_PLANE_OPACITY);
    expect(ARCH_PLANE_SIDE_OPACITY).toBeLessThan(ARCH_PLANE_OPACITY);
    expect(ARCH_PLANE_SIDE_OPACITY).toBeGreaterThan(0.16);
    expect(ARCH_PLANE_SIDE_HAS_STROKE).toBe(false);
    expect(ARCH_PLANE_SIDE_MATCHES_TOP_HUE).toBe(true);
    expect(layout.edges.every((edge) => !edge.intraPlane)).toBe(true);
    expect(layout.edges.some((edge) => edge.start.y !== edge.end.y)).toBe(true);
  });

  it('uses a lampshade frustum, see-through glass, and small grid-spaced racks', () => {
    const layout = layoutApplication3DArchitecture(tree());
    const rack = layout.nodes.find((node) => node.kind === 'application');
    const byId = Object.fromEntries(layout.nodes.map((node) => [node.id, node]));
    expect(ARCH_PLANE_WORLD_WIDTH).toBeLessThan(ARCH_PREVIOUS_FILL_PLANE_WIDTH);
    expect(ARCH_PLANE_WORLD_DEPTH).toBeLessThan(ARCH_PREVIOUS_FILL_PLANE_DEPTH);
    expect(ARCH_PLANE_WORLD_WIDTH).toBeLessThan(23);
    expect(ARCH_PLANE_WORLD_DEPTH).toBeLessThan(15);
    expect(ARCH_PLANE_WORLD_HEIGHT).toBeCloseTo(ARCH_PLANE_WORLD_DEPTH);
    expect(ARCH_PLANE_GAP).toBe(3.2);
    expect(ARCH_PLANE_GAP).toBeLessThan(4.2);
    expect(ARCH_PLANE_GAP).toBeGreaterThan(2.6);
    expect(ARCH_PLANE_THICKNESS).toBeLessThan(0.02);
    expect(ARCH_FRUSTUM_HEIGHT).toBeGreaterThan(3);
    expect(ARCH_FRUSTUM_TAPER).toBeGreaterThanOrEqual(0.1);
    expect(ARCH_FRUSTUM_TAPER).toBeLessThanOrEqual(0.15);
    expect(ARCH_FRUSTUM_TAPER).toBeLessThan(0.4);
    expect(layout.planes).toHaveLength(2);
    expect(layout.planes[0].shape).toBe('frustum');
    expect(layout.planes[0].thickness).toBe(ARCH_FRUSTUM_HEIGHT);
    expect(layout.planes[0].taper).toBe(ARCH_FRUSTUM_TAPER);
    expect(layout.planes[1].shape).toBe('plane');
    expect(layout.planes[1].thickness).toBe(ARCH_PLANE_THICKNESS);
    expect(layout.planes.every((plane) => (
      plane.width >= ARCH_PLANE_WORLD_WIDTH
      && plane.depth >= ARCH_PLANE_WORLD_DEPTH
      && plane.width < ARCH_PREVIOUS_FILL_PLANE_WIDTH
      && plane.depth < ARCH_PREVIOUS_FILL_PLANE_DEPTH
    ))).toBe(true);
    const bottomWidth = layout.planes[0].width * ARCH_FRUSTUM_TAPER;
    expect(bottomWidth / layout.planes[0].width).toBeGreaterThanOrEqual(0.1);
    expect(bottomWidth / layout.planes[0].width).toBeLessThanOrEqual(0.15);
    expect((rack?.width ?? 0) / layout.planes[0].width).toBeLessThan(0.05);
    expect(layout.planes[0].width / (rack?.width ?? 1)).toBeGreaterThan(20);
    expect(ARCH_NODE_SIZE.application).toEqual({ width: 0.48, height: 0.36, depth: 0.12 });
    expect(ARCH_NODE_SIZE.application.width).toBeGreaterThan(ARCH_PREVIOUS_NODE_SIZE.application.width);
    expect(ARCH_NODE_SIZE.application.height).toBeLessThan(ARCH_PREVIOUS_NODE_SIZE.application.height);
    expect(ARCH_NODE_SIZE.application.depth).toBeLessThan(ARCH_PREVIOUS_NODE_SIZE.application.depth);
    expect(ARCH_NODE_SIZE.host.width).toBeGreaterThan(ARCH_PREVIOUS_NODE_SIZE.host.width);
    expect(ARCH_NODE_SIZE.host.height).toBeGreaterThan(ARCH_PREVIOUS_NODE_SIZE.host.height);
    expect(ARCH_NODE_SIZE.application.width).toBeLessThan(0.55);
    expect(ARCH_NODE_SIZE.host.width).toBeLessThan(ARCH_NODE_SIZE.application.width);
    expect(ARCH_NODE_SIZE.host.height).toBeGreaterThan(ARCH_NODE_SIZE.application.height);
    expect(ARCH_NODE_SIZE.host.depth).toBeGreaterThan(ARCH_NODE_SIZE.application.depth);
    expect(ARCH_NODE_SIZE.host.height).toBeGreaterThan(ARCH_INVERTED_NODE_SIZE.host.height);
    expect(ARCH_NODE_SIZE.application.height).toBeLessThan(ARCH_INVERTED_NODE_SIZE.application.height);
    expect(ARCH_INVERTED_NODE_SIZE.application.height).toBeGreaterThan(ARCH_INVERTED_NODE_SIZE.host.height);
    expect(ARCH_GRID_PITCH).toBeGreaterThan(ARCH_NODE_SIZE.application.width * 3);
    expect(ARCH_GRID_PITCH - ARCH_NODE_SIZE.application.width).toBeGreaterThan(1);
    expect(Math.abs(byId['app-1'].x - byId['app-2'].x)).toBeCloseTo(ARCH_GRID_PITCH);
    expect(layout.width).toBeGreaterThanOrEqual(ARCH_PLANE_WORLD_WIDTH);
    expect(layout.depth).toBeGreaterThanOrEqual(ARCH_PLANE_WORLD_DEPTH);
    expect(ARCH_CAMERA_RADIUS).toBeGreaterThanOrEqual(8);
    expect(ARCH_CAMERA_RADIUS).toBeLessThan(18);
    expect(ARCH_CAMERA_FRAME_FILL).toBeGreaterThan(0.52);
    expect(ARCH_CAMERA_FRAME_FILL).toBeLessThan(0.88);
    expect(ARCH_CAMERA_FRAME_FILL).not.toBeCloseTo(0.92);
  });

  it('still places isolated applications with no host edges and omits the system node', () => {
    const layout = layoutApplication3DArchitecture(tree({
      nodes: [
        { id: 'sys-1', kind: 'system', name: '无主机', health },
        { id: 'app-1', kind: 'application', name: '孤立', health },
      ],
      edges: [
        { id: 'e1', sourceId: 'sys-1', targetId: 'app-1', relation: 'system_contains_application' },
      ],
    }));
    expect(layout.nodes.map((node) => node.id)).toEqual(['app-1']);
    expect(layout.nodes[0].z).toBeCloseTo(architectureFrontZ(0));
    expect(layout.nodes[0].z).toBeGreaterThan(0);
    expect(layout.nodes.find((node) => node.kind === 'host')).toBeUndefined();
    expect(layout.edges).toHaveLength(0);
    expect(layout.planes).toHaveLength(2);
    expect(layout.planes.map((plane) => plane.kind)).toEqual(['host', 'application']);
  });

  it('places isolated hosts in a row grid on the host plane', () => {
    const layout = layoutApplication3DArchitecture(tree({
      nodes: [
        { id: 'sys-1', kind: 'system', name: '空边', health },
        { id: 'app-orphan', kind: 'application', name: '孤立应用', health },
        { id: 'host-a', kind: 'host', name: 'h-a', health },
        { id: 'host-b', kind: 'host', name: 'h-b', health },
      ],
      edges: [],
    }));
    const byId = Object.fromEntries(layout.nodes.map((node) => [node.id, node]));
    expect(layout.nodes).toHaveLength(3);
    expect(byId['app-orphan'].y).toBeCloseTo(
      ARCH_PLANE_Y.application + ARCH_PLANE_THICKNESS / 2 + ARCH_NODE_SIZE.application.height / 2,
    );
    expect(byId['host-a'].y).toBeCloseTo(byId['host-b'].y);
    expect(byId['host-a'].y).toBeCloseTo(
      ARCH_PLANE_Y.host + ARCH_NODE_SIZE.host.height / 2,
    );
    expect(byId['host-a'].x).not.toBe(byId['host-b'].x);
    expect(Math.abs(byId['host-a'].x - byId['host-b'].x)).toBeCloseTo(ARCH_GRID_PITCH);
    expect(byId['host-a'].z).toBeCloseTo(architectureFrontZ(0));
    expect(byId['host-b'].z).toBeCloseTo(architectureFrontZ(0));
    expect(byId['host-a'].z).toBeGreaterThan(0);
    expect(layout.edges).toHaveLength(0);
  });

  it('keeps eight-or-fewer isolated hosts on the front host row', () => {
    const hosts = Array.from({ length: 5 }, (_, index) => ({
      id: `host-${index}`,
      kind: 'host' as const,
      name: `h-${index}`,
      health,
    }));
    const layout = layoutApplication3DArchitecture(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '多孤立', health }, ...hosts],
      edges: [],
    }));
    const placed = layout.nodes.filter((node) => node.kind === 'host');
    expect(placed).toHaveLength(5);
    const hostY = ARCH_PLANE_Y.host + ARCH_NODE_SIZE.host.height / 2;
    expect(placed.every((node) => Math.abs(node.y - hostY) < 1e-6)).toBe(true);
    expect(new Set(placed.map((node) => `${node.x.toFixed(2)},${node.z.toFixed(2)}`)).size).toBe(5);
    const zs = [...new Set(placed.map((node) => node.z))].sort((left, right) => left - right);
    expect(zs).toHaveLength(1);
    expect(zs[0]).toBeCloseTo(architectureFrontZ(0));
    expect(ARCH_WRAP_COLS).toBe(8);
  });

  const layerNodes = (
    kind: 'application' | 'host',
    count: number,
  ) => Array.from({ length: count }, (_, index) => ({
    id: `${kind}-${index}`,
    kind,
    name: `${kind}-${index}`,
    health,
  }));

  it('wraps applications at 8 per row and sends the 9th backward on −Z', () => {
    const apps = layerNodes('application', 9);
    const layout = layoutApplication3DArchitecture(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '九应用', health }, ...apps],
      edges: [],
    }));
    const placed = layout.nodes.filter((node) => node.kind === 'application');
    expect(placed).toHaveLength(9);
    const front = placed.filter((node) => Math.abs(node.z - architectureFrontZ(0)) < 1e-6);
    const next = placed.filter((node) => Math.abs(node.z - architectureFrontZ(1)) < 1e-6);
    expect(front).toHaveLength(ARCH_WRAP_COLS);
    expect(next).toHaveLength(1);
    expect(next[0].z).toBeLessThan(front[0].z);
    expect(next[0].z).toBeCloseTo(architectureFrontZ(0) - ARCH_GRID_PITCH);
    const xs = [...new Set(front.map((node) => node.x))].sort((left, right) => left - right);
    expect(xs).toHaveLength(ARCH_WRAP_COLS);
    expect(xs[1] - xs[0]).toBeCloseTo(ARCH_GRID_PITCH);
  });

  it('keeps eight or fewer cabinets on a single front-packed row', () => {
    const apps = layerNodes('application', 8);
    const hosts = layerNodes('host', 3);
    const layout = layoutApplication3DArchitecture(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '满一行', health }, ...apps, ...hosts],
      edges: [],
    }));
    const placedApps = layout.nodes.filter((node) => node.kind === 'application');
    const placedHosts = layout.nodes.filter((node) => node.kind === 'host');
    expect(placedApps.every((node) => Math.abs(node.z - architectureFrontZ(0)) < 1e-6)).toBe(true);
    expect(placedHosts.every((node) => Math.abs(node.z - architectureFrontZ(0)) < 1e-6)).toBe(true);
    expect(new Set(placedApps.map((node) => node.x)).size).toBe(8);
    expect(new Set(placedHosts.map((node) => node.x)).size).toBe(3);
    expect(layout.width).toBeGreaterThan(ARCH_PLANE_MIN_WIDTH);
    expect(layout.depth).toBe(ARCH_PLANE_MIN_DEPTH);
  });

  it('does not grow width linearly with 20 hosts — wrap caps the X span at 8 columns', () => {
    const hosts20 = layerNodes('host', 20);
    const hosts8 = layerNodes('host', 8);
    const layout20 = layoutApplication3DArchitecture(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '二十主机', health }, ...hosts20],
      edges: [],
    }));
    const layout8 = layoutApplication3DArchitecture(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '八主机', health }, ...hosts8],
      edges: [],
    }));
    const placed20 = layout20.nodes.filter((node) => node.kind === 'host');
    const zs = [...new Set(placed20.map((node) => node.z))].sort((left, right) => left - right);
    expect(zs).toHaveLength(3);
    expect(zs[0]).toBeCloseTo(architectureFrontZ(2));
    expect(zs[zs.length - 1]).toBeCloseTo(architectureFrontZ(0));
    expect(zs[1] - zs[0]).toBeCloseTo(ARCH_GRID_PITCH);
    expect(layout20.width).toBeCloseTo(layout8.width);
    expect(layout20.width).toBeLessThan(20 * ARCH_GRID_PITCH);
    const eightSpan = (ARCH_WRAP_COLS - 1) * ARCH_GRID_PITCH
      + ARCH_NODE_SIZE.host.width
      + ARCH_PLANE_PAD * 2;
    expect(layout20.width).toBeCloseTo(Math.max(eightSpan, ARCH_PLANE_MIN_WIDTH));
    expect(layout20.width).toBeLessThan(eightSpan + ARCH_GRID_PITCH);
  });

  it('wraps isolated and connected hosts on the same 8-column grid', () => {
    const connected = layerNodes('host', 5).map((node, index) => ({
      ...node,
      id: `host-c-${index}`,
    }));
    const isolated = layerNodes('host', 5).map((node, index) => ({
      ...node,
      id: `host-i-${index}`,
    }));
    const layout = layoutApplication3DArchitecture(tree({
      nodes: [
        { id: 'sys-1', kind: 'system', name: '混合主机', health },
        { id: 'app-1', kind: 'application', name: '门户', health },
        ...connected,
        ...isolated,
      ],
      edges: connected.map((node, index) => ({
        id: `ec-${index}`,
        sourceId: 'app-1',
        targetId: node.id,
        relation: 'application_run_host' as const,
      })),
    }));
    const placed = layout.nodes.filter((node) => node.kind === 'host');
    expect(placed).toHaveLength(10);
    expect(layout.nodes.filter((node) => node.id === 'host-c-0')).toHaveLength(1);
    const front = placed.filter((node) => Math.abs(node.z - architectureFrontZ(0)) < 1e-6);
    const next = placed.filter((node) => Math.abs(node.z - architectureFrontZ(1)) < 1e-6);
    expect(front).toHaveLength(ARCH_WRAP_COLS);
    expect(next).toHaveLength(2);
    expect(next[0].z).toBeLessThan(front[0].z);
    const xs = placed.map((node) => node.x);
    expect(Math.max(...xs) - Math.min(...xs)).toBeCloseTo((ARCH_WRAP_COLS - 1) * ARCH_GRID_PITCH);
    expect(layout.width).toBeLessThan(10 * ARCH_GRID_PITCH);
  });

  it('grows the board only toward −Z so the front lip stays with row 0', () => {
    const few = layoutApplication3DArchitecture(tree());
    const manyHosts = layerNodes('host', 40);
    const many = layoutApplication3DArchitecture(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '四十主机', health }, ...manyHosts],
      edges: [],
    }));
    const fewFront = few.nodes.filter((node) => node.kind === 'host');
    const manyPlaced = many.nodes.filter((node) => node.kind === 'host');
    const manyFirst = manyPlaced.reduce((best, node) => (node.z > best.z ? node : best));
    const manyLast = manyPlaced.reduce((best, node) => (node.z < best.z ? node : best));
    expect(fewFront[0].z).toBeCloseTo(architectureFrontZ(0));
    expect(manyFirst.z).toBeCloseTo(fewFront[0].z);
    expect(manyFirst.z).toBeCloseTo(architectureFrontZ(0));
    const fewPlane = few.planes[0];
    const manyPlane = many.planes[0];
    const fewFrontEdge = fewPlane.z + fewPlane.depth / 2;
    const manyFrontEdge = manyPlane.z + manyPlane.depth / 2;
    const manyBackEdge = manyPlane.z - manyPlane.depth / 2;
    expect(fewFrontEdge).toBeCloseTo(ARCH_PLANE_FRONT_Z);
    expect(manyFrontEdge).toBeCloseTo(fewFrontEdge);
    expect(manyFrontEdge).toBeCloseTo(ARCH_PLANE_WORLD_DEPTH / 2);
    expect(fewPlane.z).toBeCloseTo(0);
    expect(manyPlane.z).toBeLessThan(0);
    expect(many.depth).toBeGreaterThan(ARCH_PLANE_MIN_DEPTH);
    expect(many.depth).toBeCloseTo(architectureBoardFromContentMinZ(
      manyLast.z - manyLast.depth / 2,
    ).depth);
    expect(manyLast.z).toBeGreaterThanOrEqual(manyBackEdge);
    expect(manyLast.z - manyLast.depth / 2).toBeGreaterThanOrEqual(manyBackEdge);
    expect(manyLast.z - manyLast.depth / 2).toBeCloseTo(manyBackEdge + ARCH_PLANE_PAD);
    expect(many.centerZ).toBe(0);
    expect(many.centerZ).toBe(few.centerZ);
    expect(architectureTitleLocalZ(fewPlane.depth)).toBeCloseTo(
      fewPlane.depth / 2 - ARCH_TITLE_FRONT_INSET,
    );
    expect(architectureTitleLocalZ(manyPlane.depth)).toBeCloseTo(
      manyPlane.depth / 2 - ARCH_TITLE_FRONT_INSET,
    );
    expect(architectureTitleLocalZ(manyPlane.depth)).toBeGreaterThan(
      architectureTitleLocalZ(fewPlane.depth),
    );
    expect(architectureTitleLocalZ(manyPlane.depth)).not.toBeCloseTo(0, 1);
    expect(ARCH_TITLE_FRONT_INSET).toBeGreaterThan(0);
    expect(ARCH_TITLE_FRONT_INSET).toBeLessThan(0.2);
  });

  it('uses two landed-camera width tiers: min board vs 8-col cap, not wrap depth', () => {
    const threeApps = layerNodes('application', 3);
    const sixHosts = layerNodes('host', 6);
    const sevenHosts = layerNodes('host', 7);
    const eightHosts = layerNodes('host', 8);
    const deepHosts = layerNodes('host', 40);
    const threeApp = layoutApplication3DArchitecture(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '三应用', health }, ...threeApps],
      edges: [],
    }));
    const sixHost = layoutApplication3DArchitecture(tree({
      nodes: [
        { id: 'sys-1', kind: 'system', name: '六主机', health },
        ...threeApps,
        ...sixHosts,
      ],
      edges: [],
    }));
    const sevenHost = layoutApplication3DArchitecture(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '七主机', health }, ...sevenHosts],
      edges: [],
    }));
    const eightHost = layoutApplication3DArchitecture(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '八主机', health }, ...eightHosts],
      edges: [],
    }));
    const deep = layoutApplication3DArchitecture(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '深板', health }, ...deepHosts],
      edges: [],
    }));
    expect(threeApp.width).toBe(ARCH_PLANE_MIN_WIDTH);
    expect(sixHost.width).toBeLessThan(architectureWideBoardFloor());
    expect(architectureCameraFitWidth(threeApp.width)).toBe(ARCH_PLANE_MIN_WIDTH);
    expect(architectureCameraFitWidth(sixHost.width)).toBe(ARCH_PLANE_MIN_WIDTH);
    expect(architectureCameraFitWidth(eightHost.width)).toBeCloseTo(
      architectureWrapBoardWidth(),
    );
    expect(architectureCameraFitWidth(deep.width)).toBeCloseTo(
      architectureWrapBoardWidth(),
    );
    expect(eightHost.width).toBeCloseTo(deep.width);
    expect(eightHost.width).toBeCloseTo(architectureWrapBoardWidth());
    expect(deep.depth).toBeGreaterThan(ARCH_PLANE_MIN_DEPTH);
    expect(eightHost.depth).toBe(ARCH_PLANE_MIN_DEPTH);
    const smallFit = fitArchitectureCameraDistance(threeApp, 16 / 9);
    const sixFit = fitArchitectureCameraDistance(sixHost, 16 / 9);
    const sevenFit = fitArchitectureCameraDistance(sevenHost, 16 / 9);
    const eightFit = fitArchitectureCameraDistance(eightHost, 16 / 9);
    const deepFit = fitArchitectureCameraDistance(deep, 16 / 9);
    expect(sixFit).toBeCloseTo(smallFit);
    expect(smallFit).toBeCloseTo(
      fitArchitectureCameraDistance(layoutApplication3DArchitecture(tree()), 16 / 9),
    );
    expect(eightFit).toBeCloseTo(deepFit);
    expect(sevenFit).toBeCloseTo(eightFit);
    expect(eightFit).toBeGreaterThan(smallFit);
    const smallPose = resolveArchitectureCameraPose(threeApp, 16 / 9);
    const sixPose = resolveArchitectureCameraPose(sixHost, 16 / 9);
    const eightPose = resolveArchitectureCameraPose(eightHost, 16 / 9);
    const deepPose = resolveArchitectureCameraPose(deep, 16 / 9);
    expect(smallPose.phi).toBeCloseTo(ARCH_CAMERA_PHI);
    expect(sixPose.phi).toBeCloseTo(ARCH_CAMERA_PHI);
    expect(eightPose.phi).toBeCloseTo(ARCH_CAMERA_PHI);
    expect(deepPose.phi).toBeCloseTo(ARCH_CAMERA_PHI);
    expect(deepPose.phi).toBeCloseTo(eightPose.phi);
    expect(sixPose.radius).toBeCloseTo(smallPose.radius);
    expect(deepPose.radius).toBeCloseTo(eightPose.radius);
    expect(eightPose.radius).toBeGreaterThan(smallPose.radius);
    expect(deepPose.target.z).toBeCloseTo(eightPose.target.z);
    expect(deep.centerZ).toBe(0);
    expect(smallPose.target.z).toBeCloseTo(eightPose.target.z);
  });

  it('keeps an empty system as two empty planes with no visual system node', () => {
    const layout = layoutApplication3DArchitecture(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '空系统', health }],
      edges: [],
    }));
    expect(layout.nodes).toHaveLength(0);
    expect(layout.edges).toHaveLength(0);
    expect(layout.planes.map((plane) => plane.titleFallback)).toEqual(
      Object.values(ARCH_PLANE_TITLE).map((item) => item.titleFallback),
    );
    expect(layout.planes).toHaveLength(2);
  });

  it('distinguishes ranks by size rather than wall health tints', () => {
    expect(ARCH_NODE_SIZE.system.width).toBeGreaterThanOrEqual(ARCH_NODE_SIZE.application.width);
    expect(ARCH_NODE_SIZE.application.width).toBeGreaterThan(ARCH_NODE_SIZE.host.width);
    expect(ARCH_NODE_SIZE.host.height).toBeGreaterThan(ARCH_NODE_SIZE.application.height);
    expect(ARCH_NODE_SIZE.host.depth).toBeGreaterThan(ARCH_NODE_SIZE.application.depth);
    expect(ARCH_NODE_FILL).toBe(ARCH_CHASSIS_COLOR);
    expect(ARCH_NODE_FILL).not.toBe(CARD_TONE.critical.tint);
    expect(ARCH_NODE_FILL).not.toBe(CARD_TONE.warning.tint);
    expect(ARCH_NODE_FILL).not.toBe(CARD_TONE.error.tint);
    expect(architectureEdgeColor({ kind: 'host', health: { state: 'normal' } })).toBe(ARCH_EDGE);
    expect(architectureEdgeColor({ kind: 'host', health: { state: 'alarming' } })).toBe(ARCH_EDGE_ALARM);
    expect(architectureEdgeColor({ kind: 'application', health: { state: 'alarming' } })).toBe(ARCH_EDGE);
    expect(hostHasAlarm({ kind: 'host', health: { state: 'alarming' } })).toBe(true);
    expect(hostHasAlarm({ kind: 'application', health: { state: 'alarming' } })).toBe(false);
    expect(applicationHasAlarm({ kind: 'application', health: { state: 'alarming' } })).toBe(true);
    expect(applicationHasAlarm({ kind: 'application', health: { state: 'normal' } })).toBe(false);
    expect(applicationHasAlarm({ kind: 'host', health: { state: 'alarming' } })).toBe(false);
    expect(architectureSelectionRingAlarming({ kind: 'host', health: { state: 'alarming' } })).toBe(true);
    expect(architectureSelectionRingAlarming({ kind: 'host', health: { state: 'normal' } })).toBe(false);
    expect(architectureSelectionRingAlarming({ kind: 'application', health: { state: 'alarming' } })).toBe(true);
    expect(architectureSelectionRingAlarming({ kind: 'application', health: { state: 'normal' } })).toBe(false);
    expect(architectureAppChipWallBorder(false)).toBe(ARCH_APP_CHIP_WALL_BORDER);
    expect(architectureAppChipWallBorder(true)).toBe(ARCH_APP_CHIP_WALL_BORDER_ALARM);
    expect(ARCH_APP_CHIP_WALL_BORDER_ALARM).toBe('rgba(255, 82, 72, 0.9)');
    expect(architectureAppChipWallInset(false)).toEqual({
      line: ARCH_APP_CHIP_WALL_INSET_LINE,
      glow: ARCH_APP_CHIP_WALL_INSET_GLOW,
      deep: ARCH_APP_CHIP_WALL_INSET_DEEP,
      top: ARCH_APP_CHIP_WALL_INSET_TOP,
    });
    expect(architectureAppChipWallInset(true)).toEqual({
      line: ARCH_APP_CHIP_WALL_INSET_LINE_ALARM,
      glow: ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM,
      deep: ARCH_APP_CHIP_WALL_INSET_DEEP_ALARM,
      top: ARCH_APP_CHIP_WALL_INSET_TOP_ALARM,
    });
    expect(ARCH_APP_CHIP_WALL_INSET_LINE_ALARM).toBe('rgba(255, 160, 150, 0.42)');
    expect(ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM).toBe('rgba(255, 70, 58, 0.5)');
    expect(architectureAppChipWallHighlight(false)).toEqual({
      sheen: ARCH_APP_CHIP_WALL_SHEEN,
      veil: ARCH_APP_CHIP_WALL_TOP_VEIL,
      wash: ARCH_APP_CHIP_WALL_DIAGONAL_WASH,
    });
    expect(architectureAppChipWallHighlight(true)).toEqual({
      sheen: ARCH_APP_CHIP_WALL_SHEEN_ALARM,
      veil: ARCH_APP_CHIP_WALL_TOP_VEIL_ALARM,
      wash: ARCH_APP_CHIP_WALL_DIAGONAL_WASH_ALARM,
    });
    expect(ARCH_APP_CHIP_WALL_SHEEN_ALARM).toBe('rgba(255, 208, 200, 0.24)');
    expect(ARCH_APP_CHIP_WALL_TOP_VEIL_ALARM).toBe('rgba(255, 208, 200, 0.08)');
    expect(ARCH_APP_CHIP_WALL_DIAGONAL_WASH_ALARM).toBe('rgba(255, 160, 150, 0.1)');
    expect(architectureAppChipWallInsetBloom(false)).toEqual({
      glowPx: ARCH_APP_CHIP_WALL_INSET_GLOW_PX,
      deepPx: ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_PX,
      glowWidth: ARCH_APP_CHIP_WALL_INSET_GLOW_WIDTH,
      deepWidth: ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_WIDTH,
    });
    expect(ARCH_APP_CHIP_WALL_INSET_GLOW_WIDTH).toBe(2);
    expect(ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_WIDTH).toBe(3);
    expect(architectureAppChipWallInsetBloom(true).glowPx).toBe(ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM_PX);
    expect(architectureAppChipWallInsetBloom(true).glowPx)
      .toBeGreaterThan(architectureAppChipWallInsetBloom(false).glowPx);
    expect(architectureAppChipWallInsetBloom(true).glowWidth)
      .toBe(ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM_WIDTH);
    expect(architectureAppChipIconPaint(false).stroke).toBe(ARCH_APP_CHIP_ICON_STROKE);
    expect(architectureAppChipIconPaint(false).fill).toBe(ARCH_APP_CHIP_ICON_FILL);
    expect(architectureAppChipIconPaint(false).fillStrong).toBe(ARCH_APP_CHIP_ICON_FILL_STRONG);
    expect(architectureAppChipIconPaint(false).glow).toBe(ARCH_APP_CHIP_ICON_GLOW);
    expect(architectureAppChipIconPaint(true).stroke).toBe(ARCH_APP_CHIP_ICON_STROKE_ALARM);
    expect(architectureAppChipIconPaint(true).fill).toBe(ARCH_APP_CHIP_ICON_FILL_ALARM);
    expect(architectureAppChipIconPaint(true).fillStrong).toBe(ARCH_APP_CHIP_ICON_FILL_STRONG_ALARM);
    expect(architectureAppChipIconPaint(true).glow).toBe(ARCH_APP_CHIP_ICON_GLOW_ALARM);
    expect(architectureAppChipIconPaint(false).haze).toBe('rgba(94, 232, 240, 0.14)');
    expect(architectureAppChipIconPaint(true).haze).toBe('rgba(255, 70, 58, 0.14)');
    expect(architectureAppChipSeparator(false).stroke).toBe(ARCH_APP_CHIP_SEPARATOR);
    expect(architectureAppChipSeparator(true).stroke).toBe(ARCH_APP_CHIP_SEPARATOR_ALARM);
    expect(ARCH_APP_CHIP_ICON_STROKE).toBe('rgba(210, 250, 255, 0.88)');
    expect(ARCH_APP_CHIP_SEPARATOR).toBe('rgba(186, 240, 246, 0.45)');
    expect(formatArchitecturePlaneTitle('应用')).toBe('应用');
    expect(formatArchitecturePlaneTitle('应用')).not.toMatch(/➤|▶|>/);
  });

  it('lands the camera low looking into the stack, not wallPhi − π/2.5 overhead', () => {
    const layout = layoutApplication3DArchitecture(tree());
    const wall = describeWallCameraSpherical(wallPose);
    const pose = resolveArchitectureCameraPose(layout, 16 / 9);
    const rejectedOverheadPhi = wall.phi - Math.PI / 2.5;
    expect(wall.phi).toBeGreaterThan(Math.PI / 2 - 0.1);
    expect('cameraBetaDelta' in ARCHITECTURE_MOTION).toBe(false);
    expect(pose.phi).toBeCloseTo(ARCH_CAMERA_PHI);
    expect(pose.beta).toBe(pose.phi);
    expect(ARCH_CAMERA_PHI).toBeGreaterThan(ARCH_PREVIOUS_CAMERA_PHI);
    expect(Math.abs(Math.PI / 2 - pose.phi)).toBeLessThan(
      Math.abs(Math.PI / 2 - ARCH_PREVIOUS_CAMERA_PHI),
    );
    expect(pose.phi).toBeGreaterThan(ARCH_PREVIOUS_CAMERA_PHI);
    expect(pose.phi).toBeGreaterThan(1.3);
    expect(pose.phi).toBeLessThan(Math.PI / 2);
    expect(pose.phi).not.toBeCloseTo(rejectedOverheadPhi, 1);
    expect(Math.abs(pose.phi - rejectedOverheadPhi)).toBeGreaterThan(0.6);
    expect(pose.radius).toBeGreaterThanOrEqual(ARCH_CAMERA_RADIUS);
    const previousOffset = sphericalToOffset(pose.radius, ARCH_PREVIOUS_CAMERA_PHI, pose.theta);
    expect(pose.position.y).toBeLessThan(pose.target.y + previousOffset.y - 1);
    const halfFov = ((APPLICATION3D_CAMERA_FOV * Math.PI) / 180) / 2;
    const tan = Math.tan(halfFov);
    const visibleWidth = 2 * pose.radius * tan * (16 / 9);
    const visibleHeight = 2 * pose.radius * tan;
    expect(layout.width / visibleWidth).toBeLessThan(0.88);
    expect(layout.stackHeight / visibleHeight).toBeLessThan(0.88);
    expect(layout.stackHeight / visibleHeight).toBeGreaterThan(0.6);
    expect(layout.width / visibleWidth).toBeGreaterThan(0.45);
    expect(pose.position.y).toBeGreaterThan(pose.target.y);
    expect(pose.position.z).toBeGreaterThan(pose.target.z);
    const landedCam = new THREE.PerspectiveCamera(APPLICATION3D_CAMERA_FOV, 16 / 9, 0.1, 200);
    landedCam.position.set(pose.position.x, pose.position.y, pose.position.z);
    landedCam.lookAt(pose.target.x, pose.target.y, pose.target.z);
    landedCam.updateProjectionMatrix();
    landedCam.updateMatrixWorld();
    const toNdc = (x: number, y: number, z: number) =>
      new THREE.Vector3(x, y, z).project(landedCam);
    const footNdc = toNdc(0, layout.stackBottomY, 0);
    const topNdc = toNdc(0, layout.stackTopY, 0);
    const appNdc = toNdc(0, ARCH_PLANE_Y.application, architectureFrontZ(0));
    const hostNdc = toNdc(0, ARCH_PLANE_Y.host, architectureFrontZ(0));
    expect(footNdc.y).toBeGreaterThan(-1);
    expect(topNdc.y).toBeLessThan(1);
    expect(topNdc.y - footNdc.y).toBeGreaterThan(0.55);
    expect(appNdc.y).toBeGreaterThan(hostNdc.y);
    expect(pose.target.y).toBeCloseTo(layout.centerY + ARCHITECTURE_MOTION.cameraTargetLift);
    expect(pose.target.y).toBeGreaterThan(layout.stackBottomY);
    expect(pose.target.y).toBeLessThan(layout.stackTopY);
    expect(layout.centerY).toBeGreaterThan(ARCH_PLANE_Y.host);
    expect(layout.centerY).toBeLessThan(ARCH_PLANE_Y.application);
    expect(layout.planes[0].y).toBeLessThan(layout.planes[1].y);
    const frame = describeArchitectureLandedFrame(layout, pose);
    expect(frame.planes[0].shape).toBe('frustum');
    expect(frame.planes[1].shape).toBe('plane');
    expect(frame.frustum.taper).toBeLessThan(0.2);
    expect(frame.frustum.bottomWidth / frame.frustum.topWidth).toBeCloseTo(ARCH_FRUSTUM_TAPER);
    expect(frame.glass.opacity).toBeGreaterThan(0.1);
    expect(frame.glass.emissiveIntensity).toBeGreaterThan(0.14);
    expect(frame.glass.rimOpacity).toBeGreaterThan(0.2);
    expect(frame.glass.rimOpacity).toBeLessThan(0.5);
    expect(frame.glass.rimInner).toBeLessThan(0.008);
    expect(frame.glass.rimOuter).toBeLessThan(0.016);
    expect(frame.glass.rimOuter).toBe(ARCH_PLANE_RIM_OUTER);
    expect(frame.glass.rimStrokeWorld).toBe(ARCH_PLANE_RIM_STROKE_WORLD);
    expect(frame.glass.rimHaloWorld).toBe(ARCH_PLANE_RIM_HALO_WORLD);
    expect(frame.glass.rimBlending).toBe('normal');
    expect(frame.glass.rimFalloff).toBe(ARCH_PLANE_RIM_FALLOFF);
    expect(frame.glass.rimHasEdgeLines).toBe(false);
    expect(frame.glassSides.opacity).toBe(ARCH_PLANE_SIDE_OPACITY);
    expect(frame.glassSides.emissiveIntensity).toBe(ARCH_PLANE_SIDE_EMISSIVE_INTENSITY);
    expect(frame.glassSides.hasStroke).toBe(false);
    expect(frame.glassSides.matchesTopHue).toBe(true);
    expect(frame.pulse.style).toBe(ARCH_PULSE_STYLE);
    expect(frame.pulse.trail).toBe(ARCH_PULSE_TRAIL);
    expect(frame.pulse.trail).toBeGreaterThan(0.25);
    expect(frame.pulse.trail).toBe(ARCH_PULSE_TRAIL_MAX);
    expect(frame.pulse.worldLength).toBe(ARCH_PULSE_WORLD_LENGTH);
    expect(frame.pulse.length).toBe(ARCH_PULSE_WORLD_LENGTH);
    expect(frame.pulse.tailAlpha).toBe(ARCH_PULSE_TAIL_ALPHA);
    expect(frame.pulse.tailAlpha).toBeLessThan(0.12);
    expect(frame.pulse.wrapOffset).toBe(ARCH_PULSE_WRAP_OFFSET);
    expect(frame.pulse.radius).toBe(ARCH_TUBE_RADIUS_INTER);
    expect(frame.pulse.radius).toBe(ARCH_PULSE_RADIUS);
    expect(frame.pulse.haloRadius).toBe(ARCH_PULSE_HALO_RADIUS);
    expect(frame.pulse.haloRadius).toBeGreaterThan(frame.pulse.radius);
    expect(frame.pulse.haloIntensity).toBe(ARCH_PULSE_HALO_INTENSITY);
    expect(frame.pulse.haloIntensity).toBeGreaterThan(0);
    expect(frame.pulse.haloIntensity).toBeLessThan(0.25);
    expect(frame.pulse.haloFalloff).toBe(ARCH_PULSE_HALO_FALLOFF);
    expect(frame.pulse.haloTrailPower).toBe(ARCH_PULSE_HALO_TRAIL_POWER);
    expect(frame.pulse.haloTrailPower).toBeGreaterThan(1);
    expect(frame.pulse.rgbScale).toBe('band');
    expect(frame.pulse.haloBlending).toBe('additive');
    expect(frame.pulse.blending).toBe('additive');
    expect(frame.pulse.tubularSegments).toBe(ARCH_PULSE_TUBULAR_SEGMENTS);
    expect(frame.pulse.radialSegments).toBe(ARCH_PULSE_RADIAL_SEGMENTS);
    expect(frame.pulse.tubularSegments).toBeGreaterThan(28);
    expect(frame.pulse.radialSegments).toBeGreaterThanOrEqual(24);
    expect(frame.tubes.tubularSegments).toBe(ARCH_TUBE_TUBULAR_SEGMENTS);
    expect(frame.tubes.radialSegments).toBe(ARCH_TUBE_RADIAL_SEGMENTS);
    expect(frame.titles.side).toBe('right');
    expect(frame.titles.arrow).toBe('');
    expect(frame.glass.depthWrite).toBe(false);
    expect(frame.tubes.interRadius).toBe(0.01);
    expect(frame.tubes.intraRadius).toBe(0.015);
    expect(frame.tubes.opacity).toBe(ARCH_TUBE_OPACITY);
    expect(frame.tubes.emissiveIntensity).toBe(ARCH_TUBE_EMISSIVE_INTENSITY);
    expect(frame.tubes.inGlowLayer).toBe(false);
    expect(frame.pulse.speed).toBe(ARCH_PULSE_SPEED);
    expect(frame.gridPitch).toBe(ARCH_GRID_PITCH);
    expect(frame.frameFill).not.toBeCloseTo(0.92);
  });

  it('keeps wall-card face CSS as the halo language source, unchanged', () => {
    const wallCss = readFileSync(
      resolve(process.cwd(), 'src/app/ops-analysis/components/widgets/application3D/application3DChrome.css'),
      'utf8',
    );
    expect(wallCss).toContain('border: 1.5px solid rgba(100, 162, 198, 0.74);');
    expect(wallCss).toContain('inset 0 0 0 1px rgba(140, 184, 214, 0.34)');
    expect(wallCss).toContain('inset 0 0 10px 2px rgba(64, 128, 168, 0.4)');
    expect(wallCss).toContain('inset 0 0 18px 3px rgba(36, 86, 124, 0.2)');
  });
});

describe('application3D architecture view', () => {
  const paintCalls: Array<{
    text: string;
    fillStyle: string;
    shadowColor: string;
    shadowBlur: number;
    font: string;
  }> = [];
  const fillRectCalls: Array<{ fillStyle: string }> = [];

  beforeAll(() => {
    const mockContext: Record<string, unknown> = {
      fillStyle: '',
      strokeStyle: '',
      shadowColor: '',
      shadowBlur: 0,
      font: '',
      lineWidth: 1,
      lineJoin: 'round',
      lineCap: 'round',
      textAlign: 'center',
      textBaseline: 'middle',
      globalAlpha: 1,
      clearRect: () => undefined,
      beginPath: () => undefined,
      closePath: () => undefined,
      moveTo: () => undefined,
      lineTo: () => undefined,
      quadraticCurveTo: () => undefined,
      bezierCurveTo: () => undefined,
      arc: () => undefined,
      stroke: () => undefined,
      fill: () => undefined,
      clip: () => undefined,
      save: () => undefined,
      restore: () => undefined,
      translate: () => undefined,
      rotate: () => undefined,
      scale: () => undefined,
      setLineDash: () => undefined,
      measureText: (text: string) => ({ width: String(text).length * 28 }),
      createRadialGradient: () => ({ addColorStop: () => undefined }),
      fillRect() {
        fillRectCalls.push({ fillStyle: String(mockContext.fillStyle) });
      },
      fillText(text: string) {
        paintCalls.push({
          text,
          fillStyle: String(mockContext.fillStyle),
          shadowColor: String(mockContext.shadowColor),
          shadowBlur: Number(mockContext.shadowBlur),
          font: String(mockContext.font),
        });
      },
      createLinearGradient: () => ({ addColorStop: () => undefined }),
    };
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      mockContext as unknown as CanvasRenderingContext2D,
    );
  });

  it('builds two XZ horizontal platforms, upright racks and tube edges', () => {
    const view = createArchitectureTreeGroup(tree(), (_id, fallback = '') => fallback);
    const lines: THREE.Line[] = [];
    const tubes: THREE.Mesh[] = [];
    const planeMeshes: THREE.Mesh[] = [];
    const veneerMeshes: THREE.Mesh[] = [];
    const racks: THREE.Object3D[] = [];
    const titles: THREE.Mesh[] = [];
    const labels: THREE.Mesh[] = [];
    const rims: THREE.Object3D[] = [];
    view.group.traverse((child) => {
      if (child instanceof THREE.Line) lines.push(child);
      if (child.userData.archRole === 'plane-rim') rims.push(child);
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh;
        if (mesh.geometry.type === 'TubeGeometry') tubes.push(mesh);
        if (mesh.userData.archRole === 'plane-mesh') planeMeshes.push(mesh);
        if (mesh.userData.planeSkin === 'veneer' && mesh.userData.archRole !== 'plane-rim') {
          veneerMeshes.push(mesh);
        }
        if (mesh.userData.archRole === 'plane-title') titles.push(mesh);
        if (mesh.userData.archRole === 'node-label') labels.push(mesh);
      }
      if (child.userData.archRole === 'rack-root') racks.push(child);
    });
    expect(view.planeGroups).toHaveLength(2);
    expect(planeMeshes).toHaveLength(2);
    expect(planeMeshes.every((mesh) => {
      const material = mesh.material as THREE.MeshStandardMaterial;
      return (
        material.transparent
        && material.side === THREE.DoubleSide
        && material.depthWrite === false
      );
    })).toBe(true);
    const appMesh = planeMeshes.find((mesh) => mesh.userData.planeKind === 'application');
    const hostMesh = planeMeshes.find((mesh) => mesh.userData.planeKind === 'host');
    const hostSides = hostMesh?.material as THREE.MeshStandardMaterial;
    const appVeneerMesh = appMesh?.material as THREE.MeshStandardMaterial;
    expect(hostMesh?.userData.planeSkin).toBe('veneer-side');
    expect(hostMesh?.userData.hasRim).toBe(false);
    expect(hostMesh?.userData.hasStroke).toBe(false);
    expect(hostMesh?.userData.matchesTopHue).toBe(true);
    expect(hostSides.opacity).toBe(ARCH_PLANE_SIDE_OPACITY);
    expect(hostSides.emissiveIntensity).toBe(ARCH_PLANE_SIDE_EMISSIVE_INTENSITY);
    expect(hostSides.color.getHex()).toBe(ARCH_PLANE);
    expect(appMesh?.userData.planeSkin).toBe('veneer');
    expect(appMesh?.userData.hasRim).toBe(true);
    expect(appVeneerMesh.opacity).toBe(ARCH_PLANE_OPACITY);
    expect(appVeneerMesh.emissiveIntensity).toBe(ARCH_PLANE_EMISSIVE_INTENSITY);
    expect(appVeneerMesh.color.getHex()).toBe(ARCH_PLANE);
    expect(appVeneerMesh.color.getHex()).toBe(hostSides.color.getHex());
    expect(hostSides.opacity).toBeLessThan(appVeneerMesh.opacity);
    expect(veneerMeshes).toHaveLength(2);
    expect(veneerMeshes.every((mesh) => {
      const material = mesh.material as THREE.MeshStandardMaterial;
      return (
        mesh.userData.hasRim === true
        && material.opacity === ARCH_PLANE_OPACITY
        && material.color.getHex() === ARCH_PLANE
        && mesh.geometry.type === 'PlaneGeometry'
      );
    })).toBe(true);
    const hostVeneer = veneerMeshes.find((mesh) => mesh.userData.planeKind === 'host');
    expect(hostVeneer?.userData.archRole).toBe('plane-veneer');
    expect(hostVeneer?.rotation.x).toBeCloseTo(ARCH_PLANE_ROTATION_X);
    expect(hostMesh?.userData.planeShape).toBe('frustum');
    expect(hostMesh?.geometry.type).not.toBe('PlaneGeometry');
    expect(hostMesh?.userData.planeThickness).toBeCloseTo(ARCH_FRUSTUM_HEIGHT);
    expect(hostMesh?.userData.frustumHeight).toBeCloseTo(ARCH_FRUSTUM_HEIGHT);
    expect(hostMesh?.userData.frustumTaper).toBeCloseTo(ARCH_FRUSTUM_TAPER);
    expect(hostMesh?.rotation.x ?? 1).toBeCloseTo(0);
    hostMesh?.geometry.computeBoundingBox();
    const frustumBox = hostMesh?.geometry.boundingBox;
    expect(frustumBox).toBeTruthy();
    expect((frustumBox?.max.y ?? 0) - (frustumBox?.min.y ?? 0)).toBeCloseTo(ARCH_FRUSTUM_HEIGHT);
    expect((frustumBox?.max.x ?? 0) - (frustumBox?.min.x ?? 0)).toBeCloseTo(ARCH_PLANE_WORLD_WIDTH);
    const positions = hostMesh?.geometry.getAttribute('position');
    let bottomMinX = Infinity;
    let bottomMaxX = -Infinity;
    if (positions) {
      for (let index = 0; index < positions.count; index += 1) {
        if (positions.getY(index) > -1e-6) continue;
        bottomMinX = Math.min(bottomMinX, positions.getX(index));
        bottomMaxX = Math.max(bottomMaxX, positions.getX(index));
      }
    }
    expect(bottomMaxX - bottomMinX).toBeCloseTo(ARCH_PLANE_WORLD_WIDTH * ARCH_FRUSTUM_TAPER);
    expect((bottomMaxX - bottomMinX) / ARCH_PLANE_WORLD_WIDTH).toBeLessThan(0.2);
    const sample = createTrapezoidFrustumGeometry(2, 2, 0.24, 0.24, 1);
    sample.computeBoundingBox();
    expect((sample.boundingBox?.max.x ?? 0) - (sample.boundingBox?.min.x ?? 0)).toBeCloseTo(2);
    sample.dispose();
    expect(appMesh?.userData.planeShape).toBe('plane');
    expect(appMesh?.geometry.type).toBe('PlaneGeometry');
    expect(appMesh?.rotation.x).toBeCloseTo(ARCH_PLANE_ROTATION_X);
    expect(appMesh?.userData.planeOrientation).toBe(ARCH_PLANE_ORIENTATION);
    expect(appMesh?.scale.x).toBeGreaterThanOrEqual(ARCH_PLANE_WORLD_WIDTH);
    expect(appMesh?.scale.y).toBeGreaterThanOrEqual(ARCH_PLANE_WORLD_DEPTH);
    expect(appMesh?.userData.planeThickness).toBeCloseTo(ARCH_PLANE_THICKNESS);
    expect(view.planeGroups[0].userData.planeKind).toBe('host');
    expect(view.planeGroups[1].userData.planeKind).toBe('application');
    expect(view.planeGroups[0].userData.planeShape).toBe('frustum');
    expect(view.planeGroups[1].userData.planeShape).toBe('plane');
    expect(view.planeGroups[0].position.y).toBeCloseTo(ARCH_PLANE_Y.host);
    expect(view.planeGroups[1].position.y).toBeCloseTo(ARCH_PLANE_Y.application);
    expect(view.planeGroups[0].position.y).toBeLessThan(view.planeGroups[1].position.y);
    expect(titles.map((title) => title.userData.planeTitle)).toEqual(['主机', '应用']);
    expect(titles.every((title) => title.userData.planeTitleSide === 'right')).toBe(true);
    expect(titles.every((title) => title.userData.titleHasBackground === false)).toBe(true);
    expect(titles.every((title) => title.userData.titleHasArrow === false)).toBe(true);
    expect(titles.every((title) => title.userData.titleFill === ARCH_TITLE_FILL)).toBe(true);
    expect(titles.every((title) => title.userData.titleGlow === ARCH_TITLE_SHADOW_COLOR)).toBe(true);
    expect(titles.every((title) => title.userData.titleGlowBlur === ARCH_TITLE_SHADOW_BLUR)).toBe(true);
    expect(titles.every((title) => title.userData.billboard === true)).toBe(true);
    expect(labels.every((label) => label.userData.billboard === true)).toBe(true);
    expect(labels.every((label) => label.userData.labelHasBackground === ARCH_LABEL_HAS_BACKGROUND)).toBe(true);
    expect(labels.every((label) => label.userData.labelFill === ARCH_LABEL_FILL)).toBe(true);
    expect(labels.every((label) => {
      const scale = label.userData.labelScale as THREE.Vector3;
      return (
        scale.x === ARCH_LABEL_WORLD_WIDTH
        && scale.y === ARCH_LABEL_WORLD_HEIGHT
        && Math.abs(scale.x / scale.y - ARCH_LABEL_CANVAS_WIDTH / ARCH_LABEL_CANVAS_HEIGHT) < 1e-6
      );
    })).toBe(true);
    expect(ARCH_LABEL_HAS_BACKGROUND).toBe(false);
    expect(ARCH_LABEL_BILLBOARD).toBe(true);
    expect(ARCH_LABEL_WORLD_HEIGHT).toBe(0.36);
    expect(ARCH_LABEL_WORLD_WIDTH).toBeCloseTo(
      ARCH_LABEL_WORLD_HEIGHT * (ARCH_LABEL_CANVAS_WIDTH / ARCH_LABEL_CANVAS_HEIGHT),
    );
    expect(labels).toHaveLength(
      view.layout.nodes.filter((node) => node.kind === 'host' || node.kind === 'application').length,
    );
    expect(view.nodeLabels.size).toBe(labels.length);
    expect(view.billboardMeshes.length).toBe(titles.length + labels.length);
    expect(titles.every((title) => {
      const plane = view.layout.planes.find((item) => item.kind === title.parent?.userData.planeKind);
      return plane != null
        && Math.abs(title.position.z - architectureTitleLocalZ(plane.depth)) < 1e-6
        && Math.abs(title.position.z - (plane.depth / 2 - ARCH_TITLE_FRONT_INSET)) < 1e-6
        && title.position.z > plane.depth / 2 - 0.2
        && Math.abs(title.position.x - architectureTitleLocalX(plane.width)) < 1e-6
        && title.position.x > plane.width / 2;
    })).toBe(true);
    expect(titles.every((title) => title.position.x > 0)).toBe(true);
    expect(titles.every((title) => {
      const geo = title.geometry as THREE.PlaneGeometry;
      return geo.parameters.width === 2.5 && geo.parameters.height === 0.70;
    })).toBe(true);
    expect(ARCH_TITLE_RIGHT_OUTSET).toBeGreaterThan(0);
    expect(rims).toHaveLength(2);
    expect(rims.every((rim) => rim instanceof THREE.Mesh)).toBe(true);
    expect(rims.some((rim) => rim instanceof THREE.LineSegments)).toBe(false);
    expect(rims.every((rim) => !(rim instanceof THREE.Line))).toBe(true);
    expect(rims.every((rim) => rim.userData.rimColor === ARCH_PLANE_RIM_COLOR)).toBe(true);
    expect(rims.every((rim) => rim.userData.rimStyle === 'inward-bloom')).toBe(true);
    expect(rims.every((rim) => rim.userData.rimHasEdgeLines === false)).toBe(true);
    expect(rims.every((rim) => rim.userData.rimInner === ARCH_PLANE_RIM_INNER)).toBe(true);
    expect(rims.every((rim) => rim.userData.rimOuter === ARCH_PLANE_RIM_OUTER)).toBe(true);
    expect(rims.every((rim) => rim.userData.rimStrokeWorld === ARCH_PLANE_RIM_STROKE_WORLD)).toBe(true);
    expect(rims.every((rim) => rim.userData.rimHaloWorld === ARCH_PLANE_RIM_HALO_WORLD)).toBe(true);
    expect(rims.every((rim) => rim.userData.rimBlending === 'normal')).toBe(true);
    expect(rims.every((rim) => rim.userData.rimFalloff === ARCH_PLANE_RIM_FALLOFF)).toBe(true);
    expect(rims.every((rim) => {
      const material = (rim as THREE.Mesh).material as THREE.ShaderMaterial;
      const haloWorld = Number(material.uniforms.uHaloWorld.value);
      const worldWidth = Number(material.uniforms.uWorldWidth.value);
      return (
        material.blending === THREE.NormalBlending
        && material.blending !== THREE.AdditiveBlending
        && haloWorld === ARCH_PLANE_RIM_HALO_WORLD
        && Number(material.uniforms.uStrokeWorld.value) === ARCH_PLANE_RIM_STROKE_WORLD
        && haloWorld / worldWidth < 0.022
        && Number(material.uniforms.uFalloff.value) >= 1
      );
    })).toBe(true);
    expect(rims.every((rim) => (rim as THREE.Mesh).geometry.type === 'PlaneGeometry')).toBe(true);
    expect(veneerMeshes.every((mesh) => (
      rims.some((rim) => (
        rim.parent === mesh.parent && rim.userData.planeKind === mesh.userData.planeKind
      ))
    ))).toBe(true);
    expect(lines).toHaveLength(0);
    const edgeTubes = tubes.filter((mesh) => (
      mesh.userData.archRole !== 'edge-pulse'
      && mesh.userData.archRole !== 'edge-pulse-halo'
      && mesh.userData.archRole !== 'app-chip-rim'
      && mesh.userData.archRole !== 'app-chip-rim-halo'
    ));
    expect(edgeTubes.length).toBe(view.layout.edges.length);
    expect(view.interPlaneTubes.length).toBe(view.layout.edges.length);
    expect(view.intraPlaneTubes).toHaveLength(0);
    expect(view.pulses).toHaveLength(view.layout.edges.length);
    expect(view.pulses.every((pulse) => {
      const halo = pulse.halo;
      if (!halo) return false;
      const coreGeom = pulse.mesh.geometry as THREE.TubeGeometry;
      const haloGeom = halo.geometry as THREE.TubeGeometry;
      const haloMaterial = halo.material as THREE.ShaderMaterial;
      return (
        pulse.mesh.userData.pulseLayer === 'core'
        && halo.userData.archRole === 'edge-pulse-halo'
        && haloGeom.parameters.radius > coreGeom.parameters.radius
        && coreGeom.parameters.tubularSegments === ARCH_PULSE_TUBULAR_SEGMENTS
        && coreGeom.parameters.radialSegments === ARCH_PULSE_RADIAL_SEGMENTS
        && haloGeom.parameters.tubularSegments === coreGeom.parameters.tubularSegments
        && haloGeom.parameters.radialSegments === coreGeom.parameters.radialSegments
        && coreGeom.parameters.radialSegments >= 24
        && coreGeom.parameters.tubularSegments > 28
        && haloMaterial.blending === THREE.AdditiveBlending
        && haloMaterial.uniforms.uGain.value === ARCH_PULSE_HALO_INTENSITY
        && haloMaterial.uniforms.uHaloFalloff.value === ARCH_PULSE_HALO_FALLOFF
        && haloMaterial.uniforms.uHaloTrailPower.value === ARCH_PULSE_HALO_TRAIL_POWER
        && (pulse.mesh.material as THREE.ShaderMaterial).uniforms.uHaloTrailPower.value === 1
      );
    })).toBe(true);
    expect(edgeTubes.every((mesh) => (
      mesh.userData.tubeRadius === ARCH_TUBE_RADIUS_INTER
      && (mesh.geometry as THREE.TubeGeometry).parameters.radius === ARCH_TUBE_RADIUS_INTER
      && (mesh.geometry as THREE.TubeGeometry).parameters.tubularSegments === ARCH_TUBE_TUBULAR_SEGMENTS
      && (mesh.geometry as THREE.TubeGeometry).parameters.radialSegments === ARCH_TUBE_RADIAL_SEGMENTS
    ))).toBe(true);
    expect(edgeTubes.every((mesh) => {
      const material = mesh.material as THREE.MeshStandardMaterial;
      return (
        material.opacity === ARCH_TUBE_OPACITY
        && material.emissiveIntensity === ARCH_TUBE_EMISSIVE_INTENSITY
        && material.color.getHex() === ARCH_TUBE_COLOR
        && material.blending !== THREE.AdditiveBlending
        && mesh.userData.inGlowLayer === false
      );
    })).toBe(true);
    expect(ARCH_TUBE_OPACITY).toBeLessThan(0.4);
    expect(ARCH_TUBE_EMISSIVE_INTENSITY).toBeLessThan(0.25);
    expect(ARCH_TUBE_OPACITY).toBeLessThan(0.92);
    expect(ARCH_TUBE_EMISSIVE_INTENSITY).toBeLessThan(0.85);
    expect(racks).toHaveLength(view.layout.nodes.length);
    expect(racks.every((rack) => Math.abs(rack.rotation.x) < 1e-6)).toBe(true);
    const sampleRack = view.layout.nodes[0];
    expect(appMesh?.userData.planeWidth / (sampleRack?.width ?? 1)).toBeGreaterThan(20);
    expect(view.nodeGroups.has('sys-1')).toBe(false);
    expect(view.nodeGroups.size).toBe(view.layout.nodes.length);
    view.dispose();
  });

  it('paints veneer rims, right-side glowing titles, and plaque-free node names', () => {
    paintCalls.length = 0;
    fillRectCalls.length = 0;
    const view = createArchitectureTreeGroup(tree(), (_id, fallback = '') => fallback);
    const titleTexts = paintCalls.filter((call) => call.text === '应用' || call.text === '主机');
    expect(titleTexts).toHaveLength(2);
    expect(titleTexts.every((call) => (
      call.fillStyle === ARCH_TITLE_FILL
      && call.shadowColor === ARCH_TITLE_SHADOW_COLOR
      && call.shadowBlur === ARCH_TITLE_SHADOW_BLUR
      && call.font.startsWith('600 68px ')
      && !call.text.includes('➤')
    ))).toBe(true);
    const hostTexts = paintCalls.filter((call) => ['web-1', 'shared'].includes(call.text));
    const appTexts = paintCalls.filter((call) => ['门户', '订单'].includes(call.text));
    const appFaceTexts = appTexts.filter((call) => (
      call.font.startsWith(`${ARCH_APP_CHIP_TITLE_WEIGHT} ${ARCH_APP_CHIP_TITLE_SIZE}px `)
    ));
    const appLabelTexts = appTexts.filter((call) => call.font.startsWith('600 58px '));
    expect(hostTexts.length).toBeGreaterThanOrEqual(2);
    expect(appFaceTexts.length).toBeGreaterThanOrEqual(2);
    expect(appLabelTexts.length).toBeGreaterThanOrEqual(2);
    expect(hostTexts.every((call) => (
      call.fillStyle === ARCH_LABEL_FILL
      && call.shadowBlur === 0
      && call.font.startsWith('600 58px ')
    ))).toBe(true);
    expect(appFaceTexts.every((call) => (
      call.fillStyle === ARCH_APP_CHIP_TITLE_FILL
      && call.font.startsWith(`${ARCH_APP_CHIP_TITLE_WEIGHT} ${ARCH_APP_CHIP_TITLE_SIZE}px `)
    ))).toBe(true);
    expect(appLabelTexts.every((call) => (
      call.fillStyle === ARCH_LABEL_FILL
      && call.shadowBlur === 0
      && call.font.startsWith('600 58px ')
    ))).toBe(true);
    expect(paintCalls.some((call) => call.text.includes('➤'))).toBe(false);
    expect(fillRectCalls.some((call) => call.fillStyle.includes('12, 32, 52'))).toBe(false);
    expect(view.layout.nodes.every((node) => node.z > 0)).toBe(true);
    view.dispose();
  });

  it('pins layer titles to the grown board front lip, not the mesh center', () => {
    const hosts = Array.from({ length: 40 }, (_, index) => ({
      id: `host-${index}`,
      kind: 'host' as const,
      name: `host-${index}`,
      health,
    }));
    const view = createArchitectureTreeGroup(tree({
      nodes: [{ id: 'sys-1', kind: 'system', name: '四十主机', health }, ...hosts],
      edges: [],
    }), (_id, fallback = '') => fallback);
    expect(view.layout.planes[0].depth).toBeGreaterThan(ARCH_PLANE_MIN_DEPTH);
    const titles: THREE.Mesh[] = [];
    view.group.traverse((child) => {
      if (child.userData.archRole === 'plane-title') titles.push(child as THREE.Mesh);
    });
    expect(titles).toHaveLength(2);
    titles.forEach((title) => {
      const plane = view.layout.planes.find((item) => item.kind === title.parent?.userData.planeKind);
      expect(plane).toBeTruthy();
      expect(title.position.z).toBeCloseTo(architectureTitleLocalZ(plane!.depth));
      expect(title.position.z).toBeCloseTo(plane!.depth / 2 - ARCH_TITLE_FRONT_INSET);
      expect(title.position.z).toBeGreaterThan(4);
      expect(Math.abs(title.position.z)).toBeGreaterThan(0.2);
      expect(title.position.x).toBeGreaterThan(plane!.width / 2);
    });
    view.dispose();
  });

  it('billboards titles and labels to face the camera each tick', () => {
    const view = createArchitectureTreeGroup(tree(), (_id, fallback = '') => fallback);
    view.nodeLabels.forEach((label) => {
      const scale = label.userData.labelScale as THREE.Vector3;
      label.scale.copy(scale);
    });
    const camera = new THREE.PerspectiveCamera(50, 16 / 9, 0.1, 200);
    camera.position.set(6, 4, 12);
    view.tick(0.016, camera);
    const cameraWorld = camera.position.clone();
    view.billboardMeshes.forEach((mesh) => {
      expect(mesh.userData.billboard).toBe(true);
      const world = new THREE.Vector3();
      mesh.getWorldPosition(world);
      const toCamera = cameraWorld.clone().sub(world).normalize();
      const normal = new THREE.Vector3(0, 0, 1).transformDirection(mesh.matrixWorld);
      expect(normal.dot(toCamera)).toBeGreaterThan(0.92);
    });
    view.dispose();
  });

  it('still builds isolated host racks on the host plane when the tree has no edges', () => {
    const view = createArchitectureTreeGroup(tree({
      nodes: [
        { id: 'sys-1', kind: 'system', name: '空边', health },
        { id: 'host-a', kind: 'host', name: 'h-a', health },
        { id: 'host-b', kind: 'host', name: 'h-b', health },
      ],
      edges: [],
    }), (_id, fallback = '') => fallback);
    expect(view.nodeGroups.has('host-a')).toBe(true);
    expect(view.nodeGroups.has('host-b')).toBe(true);
    expect(view.nodeGroups.get('host-a')?.position.y).toBeCloseTo(
      view.nodeGroups.get('host-b')?.position.y ?? 0,
    );
    expect(view.nodeGroups.get('host-a')?.position.y).toBeCloseTo(
      ARCH_PLANE_Y.host + ARCH_PLANE_THICKNESS / 2 + ARCH_NODE_SIZE.host.height / 2 + ARCH_RACK_LIFT,
    );
    expect(view.interPlaneTubes).toHaveLength(0);
    expect(view.planeGroups).toHaveLength(2);
    view.dispose();
  });

  it('tints the tube and pulse to an alarming host red', () => {
    const view = createArchitectureTreeGroup(tree({
      nodes: [
        { id: 'sys-1', kind: 'system', name: '门户系统', health },
        { id: 'app-1', kind: 'application', name: '门户', health },
        {
          id: 'host-1',
          kind: 'host',
          name: 'web-1',
          health: { ...health, state: 'alarming' },
        },
      ],
      edges: [
        { id: 'e1', sourceId: 'sys-1', targetId: 'app-1', relation: 'system_contains_application' },
        { id: 'e2', sourceId: 'app-1', targetId: 'host-1', relation: 'application_run_host' },
      ],
    }), (_id, fallback = '') => fallback);
    const alarmTube = view.interPlaneTubes.find((tube) => {
      let found = false;
      tube.traverse((child) => {
        const mesh = child as THREE.Mesh;
        if (!mesh.isMesh) return;
        const standard = mesh.material as THREE.MeshStandardMaterial;
        const shader = mesh.material as THREE.ShaderMaterial;
        if (standard.color?.getHex() === ARCH_EDGE_ALARM) found = true;
        if (shader.uniforms?.uColor?.value?.getHex() === ARCH_EDGE_ALARM) found = true;
      });
      return found;
    });
    expect(alarmTube).toBeTruthy();
    const idleAlarm = view.interPlaneTubes[0];
    idleAlarm?.traverse((child) => {
      const mesh = child as THREE.Mesh;
      if (!mesh.isMesh || String(mesh.userData.archRole).startsWith('edge-pulse')) return;
      const standard = mesh.material as THREE.MeshStandardMaterial;
      expect(standard.color.getHex()).toBe(ARCH_TUBE_ALARM_COLOR);
      expect(standard.opacity).toBe(ARCH_TUBE_ALARM_OPACITY);
      expect(standard.emissiveIntensity).toBe(ARCH_TUBE_ALARM_EMISSIVE_INTENSITY);
      expect(standard.emissiveIntensity).toBeLessThan(0.3);
      expect(standard.opacity).toBeLessThan(0.45);
    });
    expect(view.pulses[0]?.mesh.userData.archRole).toBe('edge-pulse');
    expect(view.pulses[0]?.mesh.userData.pulseStyle).toBe(ARCH_PULSE_STYLE);
    const pulseMaterial = view.pulses[0]?.mesh.material as THREE.ShaderMaterial;
    expect(pulseMaterial.uniforms.uColor.value.getHex()).toBe(ARCH_EDGE_ALARM);
    expect(pulseMaterial.blending).toBe(THREE.AdditiveBlending);
    expect(pulseMaterial.uniforms.uTrail.value).toBe(view.pulses[0]?.trail);
    expect(pulseMaterial.uniforms.uTailAlpha.value).toBe(ARCH_PULSE_TAIL_ALPHA);
    expect(pulseMaterial.uniforms.uWrapOffset.value).toBe(ARCH_PULSE_WRAP_OFFSET);
    const alarmHalo = view.pulses[0]?.halo;
    expect(alarmHalo?.userData.archRole).toBe('edge-pulse-halo');
    const haloMaterial = alarmHalo?.material as THREE.ShaderMaterial;
    expect(haloMaterial.uniforms.uColor.value.getHex()).toBe(ARCH_EDGE_ALARM);
    expect(haloMaterial.blending).toBe(THREE.AdditiveBlending);
    expect(haloMaterial.uniforms.uGain.value).toBe(ARCH_PULSE_HALO_INTENSITY);
    expect(haloMaterial.uniforms.uHaloFalloff.value).toBe(ARCH_PULSE_HALO_FALLOFF);
    expect(haloMaterial.uniforms.uHaloTrailPower.value).toBe(ARCH_PULSE_HALO_TRAIL_POWER);
    expect(pulseMaterial.uniforms.uHaloTrailPower.value).toBe(1);
    view.dispose();
  });

  const collectRackParts = (root: THREE.Object3D) => {
    const chassis: THREE.Mesh[] = [];
    const doors: THREE.Mesh[] = [];
    const bays: THREE.Mesh[] = [];
    const lips: THREE.Mesh[] = [];
    const leds: THREE.Mesh[] = [];
    const strokes: THREE.Mesh[] = [];
    const bezels: THREE.Mesh[] = [];
    const hints: THREE.Mesh[] = [];
    const vents: THREE.Mesh[] = [];
    const frontStripes: THREE.Mesh[] = [];
    const shadows: THREE.Mesh[] = [];
    root.traverse((child) => {
      if (!(child as THREE.Mesh).isMesh) return;
      const mesh = child as THREE.Mesh;
      if (mesh.userData.archRole === 'rack') chassis.push(mesh);
      if (mesh.userData.archRole === 'rack-door') doors.push(mesh);
      if (mesh.userData.archRole === 'rack-bay') bays.push(mesh);
      if (mesh.userData.archRole === 'rack-bay-lip') lips.push(mesh);
      if (mesh.userData.archRole === 'rack-led') leds.push(mesh);
      if (mesh.userData.archRole === 'rack-stroke') strokes.push(mesh);
      if (mesh.userData.archRole === 'rack-bezel') bezels.push(mesh);
      if (mesh.userData.archRole === 'rack-contact-hint') hints.push(mesh);
      if (mesh.userData.archRole === 'rack-contact-shadow') shadows.push(mesh);
      if (mesh.userData.archRole === 'rack-vent') vents.push(mesh);
      if (
        mesh.userData.archRole === 'rack-hdd-stripe'
        || mesh.userData.archRole === 'rack-front-stripe'
        || mesh.userData.archRole === 'rack-door-stripe'
      ) {
        frontStripes.push(mesh);
      }
    });
    return { chassis, doors, bays, lips, leds, strokes, bezels, hints, vents, frontStripes, shadows };
  };

  const hullFaces = (mesh: THREE.Mesh) => {
    const materials = mesh.material;
    expect(Array.isArray(materials)).toBe(true);
    return materials as THREE.MeshStandardMaterial[];
  };

  const hexChannelSum = (hex: number) =>
    ((hex >> 16) & 255) + ((hex >> 8) & 255) + (hex & 255);

  it('uses one mapped hull: per-face albedo, cyan LEDs on 素柜, red LEDs+stroke on alarming hosts', () => {
    expect(ARCH_NODE_SIZE.host.height).toBeGreaterThan(ARCH_NODE_SIZE.application.height);
    expect(ARCH_NODE_SIZE.host.width).toBeLessThan(ARCH_NODE_SIZE.application.width);
    expect(ARCH_RACK_LED_COUNT).toBe(3);
    expect(ARCH_RACK_STROKE_WIDTH).toBeLessThan(0.012);
    expect(ARCH_RACK_LIFT).toBeGreaterThan(0);
    expect(ARCH_CHASSIS_COLOR).not.toBe(ARCH_LED_ALARM_COLOR);
    expect(ARCH_CHASSIS_COLOR).not.toBe(ARCH_LED_COLOR);
    expect(hexChannelSum(ARCH_CHASSIS_COLOR)).toBeGreaterThan(hexChannelSum(ARCH_PREVIOUS_CHASSIS_COLOR));
    expect(ARCH_RACK_HULL_COLOR).toBe(0xffffff);
    expect(ARCH_RACK_SIDE_ROUGHNESS).toBeCloseTo(0.5);
    expect(ARCH_RACK_SIDE_METALNESS).toBe(0.04);
    expect(ARCH_RACK_FRONT_ROUGHNESS).toBeCloseTo(ARCH_RACK_SIDE_ROUGHNESS);
    expect(ARCH_RACK_FRONT_METALNESS).toBeCloseTo(ARCH_RACK_SIDE_METALNESS);
    expect(ARCH_RACK_ALBEDO_LIFT_OFFSET).toBe(72);
    expect(ARCH_RACK_ALBEDO_LIFT_SCALE).toBeCloseTo(1.05);
    expect(ARCH_RACK_LED_RADIUS_UV).toBeCloseTo(0.0195);
    expect(ARCH_RACK_LED_UV_U).toEqual([0.1122, 0.1708, 0.2294]);
    expect(ARCH_RACK_LED_UV_U).toHaveLength(ARCH_RACK_LED_COUNT);
    expect(ARCH_RACK_LED_UV_V).toBeCloseTo(0.9606, 4);

    const view = createArchitectureTreeGroup(tree({
      nodes: [
        { id: 'sys-1', kind: 'system', name: '门户系统', health },
        {
          id: 'app-1',
          kind: 'application',
          name: '门户',
          health: { ...health, state: 'alarming' },
        },
        {
          id: 'host-1',
          kind: 'host',
          name: 'web-1',
          health: { ...health, state: 'alarming' },
        },
        { id: 'host-quiet', kind: 'host', name: 'web-ok', health },
      ],
      edges: [
        { id: 'e1', sourceId: 'sys-1', targetId: 'app-1', relation: 'system_contains_application' },
        { id: 'e2', sourceId: 'app-1', targetId: 'host-1', relation: 'application_run_host' },
        { id: 'e3', sourceId: 'app-1', targetId: 'host-quiet', relation: 'application_run_host' },
      ],
    }), (_id, fallback = '') => fallback);

    const hostGroup = view.nodeGroups.get('host-1');
    const quietGroup = view.nodeGroups.get('host-quiet');
    const appGroup = view.nodeGroups.get('app-1');
    expect(hostGroup).toBeTruthy();
    expect(quietGroup).toBeTruthy();
    expect(appGroup).toBeTruthy();
    expect(hostGroup?.userData.alarming).toBe(true);
    expect(quietGroup?.userData.alarming).toBe(false);
    expect(appGroup?.userData.alarming).toBe(false);
    expect(hostGroup?.userData.nodeId).toBe('host-1');
    expect(quietGroup?.userData.nodeId).toBe('host-quiet');
    expect(appGroup?.userData.nodeId).toBe('app-1');
    expect(hostGroup?.userData.plainMetal).toBe(false);
    expect(quietGroup?.userData.plainMetal).toBe(true);
    expect(appGroup?.userData.plainMetal).toBe(true);
    expect(hostHasAlarm(view.layout.nodes.find((node) => node.id === 'host-1'))).toBe(true);
    expect(hostHasAlarm(view.layout.nodes.find((node) => node.id === 'host-quiet'))).toBe(false);
    expect(hostHasAlarm(view.layout.nodes.find((node) => node.id === 'app-1'))).toBe(false);

    const host = collectRackParts(hostGroup as THREE.Object3D);
    const quiet = collectRackParts(quietGroup as THREE.Object3D);
    const app = collectRackParts(appGroup as THREE.Object3D);
    expect(host.chassis).toHaveLength(1);
    expect(app.chassis).toHaveLength(0);
    expect(quiet.chassis).toHaveLength(1);
    expect(quiet.chassis[0].material).toBe(host.chassis[0].material);
    expect(host.doors).toHaveLength(0);
    expect(app.doors).toHaveLength(0);
    expect(quiet.doors).toHaveLength(0);
    expect(host.bays).toHaveLength(0);
    expect(app.bays).toHaveLength(0);
    expect(quiet.bays).toHaveLength(0);
    expect(host.lips).toHaveLength(0);
    expect(app.lips).toHaveLength(0);
    expect(host.bezels).toHaveLength(0);
    expect(app.bezels).toHaveLength(0);
    expect(quiet.bezels).toHaveLength(0);

    expect(app.leds).toHaveLength(0);
    expect(app.strokes).toHaveLength(0);
    expect(quiet.leds).toHaveLength(ARCH_RACK_LED_COUNT);
    expect(quiet.strokes).toHaveLength(0);
    expect(host.leds).toHaveLength(ARCH_RACK_LED_COUNT);
    expect(host.strokes).toHaveLength(12);
    expect(findArchitectureRackRoot(host.leds[0])).toBe(hostGroup);
    expect(findArchitectureRackRoot(host.chassis[0])).toBe(hostGroup);
    expect(findArchitectureRackRoot(quiet.leds[0])).toBe(quietGroup);
    expect(app.hints).toHaveLength(0);
    expect(quiet.hints).toHaveLength(0);
    expect(host.hints).toHaveLength(0);
    expect(app.vents).toHaveLength(0);
    expect(quiet.vents).toHaveLength(0);
    expect(host.vents).toHaveLength(0);
    expect(app.frontStripes).toHaveLength(0);
    expect(quiet.frontStripes).toHaveLength(0);
    expect(host.frontStripes).toHaveLength(0);
    expect(app.shadows).toHaveLength(1);
    expect(quiet.shadows).toHaveLength(1);
    expect(host.shadows).toHaveLength(1);

    const hostFaces = hullFaces(host.chassis[0]);
    expect(hostFaces).toHaveLength(6);
    expect(host.chassis[0].userData.faceCount).toBe(6);
    expect(host.chassis[0].userData.mappedHull).toBe(true);
    const [posX, negX, posY, negY, posZ, negZ] = hostFaces;
    expect(posX).toBeInstanceOf(THREE.MeshStandardMaterial);
    expect(negX).toBeInstanceOf(THREE.MeshStandardMaterial);
    expect(posY).toBeInstanceOf(THREE.MeshStandardMaterial);
    expect(negY).toBeInstanceOf(THREE.MeshStandardMaterial);
    expect(posZ).toBeInstanceOf(THREE.MeshStandardMaterial);
    expect(negZ).toBeInstanceOf(THREE.MeshStandardMaterial);
    expect(posX).toBe(negX);
    expect(posY).toBe(negY);
    expect(negZ).toBe(posY);
    expect(posZ).not.toBe(negZ);
    expect(posX).not.toBe(posY);
    expect(posX).not.toBe(posZ);
    expect(posY).not.toBe(posZ);
    expect(posX.map).toBeTruthy();
    expect(posY.map).toBeTruthy();
    expect(posZ.map).toBeTruthy();
    expect(negZ.map).toBe(posY.map);
    expect(posZ.map).not.toBe(negZ.map);
    expect(posX.map).not.toBe(posY.map);
    expect(posX.map).not.toBe(posZ.map);
    expect(posY.map).not.toBe(posZ.map);
    expect(posX.map?.colorSpace).toBe(THREE.SRGBColorSpace);
    expect(posY.map?.colorSpace).toBe(THREE.SRGBColorSpace);
    expect(posZ.map?.colorSpace).toBe(THREE.SRGBColorSpace);
    expect(posX.color.getHex()).toBe(ARCH_RACK_HULL_COLOR);
    expect(posY.color.getHex()).toBe(ARCH_RACK_HULL_COLOR);
    expect(posZ.color.getHex()).toBe(ARCH_RACK_HULL_COLOR);
    expect(posX.roughness).toBeCloseTo(ARCH_RACK_SIDE_ROUGHNESS);
    expect(posX.metalness).toBeCloseTo(ARCH_RACK_SIDE_METALNESS);
    expect(posY.roughness).toBeCloseTo(ARCH_RACK_SIDE_ROUGHNESS);
    expect(posY.metalness).toBeCloseTo(ARCH_RACK_SIDE_METALNESS);
    expect(('clearcoat' in posX) ? (posX as THREE.MeshPhysicalMaterial).clearcoat : 0).toBe(0);
    const front = posZ;
    expect(front).toBeInstanceOf(THREE.MeshStandardMaterial);
    expect(front).not.toBeInstanceOf(THREE.MeshPhysicalMaterial);
    expect(front.roughness).toBeCloseTo(ARCH_RACK_FRONT_ROUGHNESS);
    expect(front.metalness).toBeCloseTo(ARCH_RACK_FRONT_METALNESS);
    expect(('clearcoat' in front) ? (front as THREE.MeshPhysicalMaterial).clearcoat : 0).toBe(0);
    hostFaces.forEach((face) => {
      expect(face).toBeInstanceOf(THREE.MeshStandardMaterial);
      expect(face).not.toBeInstanceOf(THREE.MeshPhysicalMaterial);
      expect(face.envMap).toBeFalsy();
      expect(('clearcoat' in face) ? (face as THREE.MeshPhysicalMaterial).clearcoat : 0).toBe(0);
    });
    expect(front.envMap).toBeFalsy();
    expect(front.roughnessMap).toBeFalsy();
    expect(front.emissive.getHex()).toBe(0);
    expect(front.emissiveIntensity).toBe(0);
    expect(front.color.getHex()).not.toBe(ARCH_LED_ALARM_COLOR);
    expect(front.color.getHex()).not.toBe(ARCH_LED_COLOR);
    expect(front.emissive.getHex()).not.toBe(ARCH_LED_ALARM_COLOR);
    expect(front.emissive.getHex()).not.toBe(ARCH_LED_COLOR);
    expect(host.chassis[0].userData.alarmPaintsBody).toBe(false);

    const hostNode = view.layout.nodes.find((node) => node.id === 'host-1');
    const appNode = view.layout.nodes.find((node) => node.id === 'app-1');
    expect(hostNode).toBeTruthy();
    expect(appNode).toBeTruthy();
    expect((hostNode?.height ?? 0)).toBeGreaterThan(appNode?.height ?? 0);
    expect(host.chassis[0].scale.x).toBeCloseTo(hostNode?.width ?? 0);
    expect(host.chassis[0].scale.y).toBeCloseTo(hostNode?.height ?? 0);
    expect(host.chassis[0].scale.z).toBeCloseTo(hostNode?.depth ?? 0);
    expect(host.chassis[0].position.x).toBeCloseTo(0);
    expect(host.chassis[0].position.y).toBeCloseTo(0);
    expect(host.chassis[0].position.z).toBeCloseTo(0);

    const assertCyanLeds = (leds: THREE.Mesh[]) => {
      leds.forEach((led) => {
        const material = led.material as THREE.MeshStandardMaterial;
        expect(led.geometry.type).toBe('CylinderGeometry');
        expect(material.emissive.getHex()).toBe(ARCH_LED_COLOR);
        expect(material.color.getHex()).toBe(ARCH_LED_COLOR);
        expect(material.emissive.getHex()).not.toBe(ARCH_LED_ALARM_COLOR);
        expect(led.userData.alarmTint).toBe(false);
        expect(led.userData.ledColor).toBe(ARCH_LED_COLOR);
      });
      expect(leds[1].position.x).toBeGreaterThan(leds[0].position.x);
      expect(leds[2].position.x).toBeGreaterThan(leds[1].position.x);
      expect(Math.abs(leds[0].position.y - leds[1].position.y)).toBeLessThan(1e-6);
    };
    assertCyanLeds(quiet.leds);
    expect(host.leds[0].material).not.toBe(quiet.leds[0].material);
    const assertLedUv = (leds: THREE.Mesh[], node: { width: number; height: number }) => {
      const ledRadius = node.width * ARCH_RACK_LED_RADIUS_UV;
      leds.forEach((led, index) => {
        expect(led.position.x).toBeCloseTo((ARCH_RACK_LED_UV_U[index] - 0.5) * node.width, 5);
        expect(led.position.y).toBeCloseTo((ARCH_RACK_LED_UV_V - 0.5) * node.height, 5);
        expect(led.scale.x).toBeCloseTo(ledRadius, 5);
        expect(led.scale.z).toBeCloseTo(ledRadius, 5);
        expect(led.scale.y).toBeCloseTo(ledRadius * 0.5, 5);
      });
    };
    assertLedUv(quiet.leds, view.layout.nodes.find((node) => node.id === 'host-quiet') as { width: number; height: number });
    assertLedUv(host.leds, hostNode as { width: number; height: number });

    host.leds.forEach((led) => {
      const material = led.material as THREE.MeshStandardMaterial;
      expect(led.geometry.type).toBe('CylinderGeometry');
      expect(material.emissive.getHex()).toBe(ARCH_LED_ALARM_COLOR);
      expect(material.color.getHex()).toBe(ARCH_LED_ALARM_COLOR);
      expect(led.userData.alarmTint).toBe(true);
      expect(led.userData.ledColor).toBe(ARCH_LED_ALARM_COLOR);
    });
    expect(host.leds[1].position.x).toBeGreaterThan(host.leds[0].position.x);
    expect(host.leds[2].position.x).toBeGreaterThan(host.leds[1].position.x);
    expect(Math.abs(host.leds[0].position.y - host.leds[1].position.y)).toBeLessThan(1e-6);

    const strokeW = ARCH_RACK_STROKE_WIDTH;
    const hx = (hostNode?.width ?? 0) / 2 - strokeW / 2;
    const hy = (hostNode?.height ?? 0) / 2 - strokeW / 2;
    const hz = (hostNode?.depth ?? 0) / 2 - strokeW / 2;
    const frontStrokes = host.strokes.filter((stroke) => Math.abs(stroke.position.z - hz) < 1e-6);
    const backStrokes = host.strokes.filter((stroke) => Math.abs(stroke.position.z + hz) < 1e-6);
    const depthStrokes = host.strokes.filter((stroke) => Math.abs(stroke.position.z) < 1e-6);
    expect(frontStrokes).toHaveLength(4);
    expect(backStrokes).toHaveLength(4);
    expect(depthStrokes).toHaveLength(4);
    host.strokes.forEach((stroke) => {
      const material = stroke.material as THREE.MeshStandardMaterial;
      const thinAxes = [stroke.scale.x, stroke.scale.y, stroke.scale.z].filter(
        (axis) => Math.abs(axis - ARCH_RACK_STROKE_WIDTH) < 1e-6,
      );
      expect(thinAxes.length).toBeGreaterThanOrEqual(2);
      expect(Math.abs(stroke.position.x)).toBeLessThanOrEqual(hx + 1e-6);
      expect(Math.abs(stroke.position.y)).toBeLessThanOrEqual(hy + 1e-6);
      expect(Math.abs(stroke.position.z)).toBeLessThanOrEqual(hz + 1e-6);
      expect(material.emissive.getHex()).toBe(ARCH_STROKE_ALARM_COLOR);
      expect(material.color.getHex()).toBe(ARCH_STROKE_ALARM_COLOR);
      expect(material.emissiveIntensity).toBe(ARCH_STROKE_EMISSIVE_INTENSITY);
      expect(stroke.userData.alarmTint).toBe(true);
      expect(stroke.userData.restEmissiveIntensity).toBe(ARCH_STROKE_EMISSIVE_INTENSITY);
    });

    const viewSrc = readFileSync(
      resolve(process.cwd(), 'src/app/ops-analysis/components/widgets/application3D/application3DArchitectureView.ts'),
      'utf8',
    );
    expect(viewSrc).not.toContain('0x6a3038');
    expect(viewSrc).not.toContain('0x5a1820');
    expect(viewSrc).not.toContain('createRackMaterials(true)');
    expect(viewSrc).not.toContain('metalness: 0.64');
    expect(viewSrc).not.toContain('makeLed(ARCH_LED_COLOR)');
    expect(viewSrc).not.toMatch(/\bARCH_STROKE_COLOR\b/);
    expect(viewSrc).not.toContain('makeStroke(');
    expect(viewSrc).not.toContain('ARCH_RACK_VENT_COUNT');
    expect(viewSrc).not.toContain("'rack-vent'");
    expect(viewSrc).not.toContain("'rack-hdd-stripe'");
    expect(viewSrc).not.toContain("'rack-front-stripe'");
    expect(viewSrc).not.toContain("'rack-door-stripe'");
    expect(viewSrc).not.toContain("'rack-door'");
    expect(viewSrc).not.toContain("'rack-bezel'");
    expect(viewSrc).not.toContain("'rack-bay'");
    expect(viewSrc).toContain('cabinet-front-albedo-v2.png');
    expect(viewSrc).not.toContain('cabinet-front-roughness.png');
    expect(viewSrc).toContain('cabinet-side-albedo.png');
    expect(viewSrc).toContain('cabinet-top-albedo.png');
    expect(viewSrc).not.toContain('ARCH_RACK_LED_HEADER_RATIO');
    expect(viewSrc).not.toContain('ARCH_RACK_LED_SIDE_INSET_RATIO');
    expect(viewSrc).toContain('ARCH_RACK_LED_RADIUS_UV');
    expect(viewSrc).not.toContain('* 0.032');
    expect(viewSrc).toContain('width * ARCH_RACK_LED_RADIUS_UV');
    expect(viewSrc).toContain('faces: [side, side, top, top, front, top]');
    expect(viewSrc).toContain('liftCabinetAlbedoTexture');
    expect(viewSrc).toContain('addAppChipMeshes');
    expect(viewSrc).toContain('addRackMeshes');
    expect(viewSrc).not.toContain('MeshPhysicalMaterial');
    expect(viewSrc).not.toContain('clearcoat');
    expect(viewSrc).not.toContain('envMap');
    expect(viewSrc).not.toContain('RoomEnvironment');
    expect(viewSrc).not.toContain('createScopedArchitectureEnvironment');
    expect(viewSrc).not.toContain('ARCH_RACK_FRONT_CLEARCOAT');
    expect(viewSrc).toContain('MeshStandardMaterial');
    expect(viewSrc).toContain('rack-led');
    expect(viewSrc).toContain('rack-stroke');
    expect(viewSrc).toContain('addRackAlarmStrokes');
    expect(viewSrc).not.toContain('strokeZ = frontZ + strokeW * 0.45');
    expect(viewSrc).toContain('if (alarming)');
    expect(viewSrc).toContain('materials.led');
    expect(viewSrc).toContain('ARCH_LED_COLOR');
    view.dispose();
  });

  it('lifts near-black albedo pixels to readable slate at runtime', () => {
    const pixels = new Uint8ClampedArray([0, 0, 0, 255, 1, 2, 3, 255, 255, 200, 0, 128]);
    liftCabinetAlbedoPixels(pixels);
    expect(Array.from(pixels)).toEqual([
      72, 72, 72, 255,
      73, 74, 75, 255,
      255, 255, 72, 128,
    ]);

    const data = new Uint8ClampedArray([0, 0, 0, 255]);
    const texture = new THREE.DataTexture(data, 1, 1);
    liftCabinetAlbedoTexture(texture);
    expect(texture.userData.albedoLifted).toBe(true);
    expect(data[0]).toBe(72);
    liftCabinetAlbedoTexture(texture);
    expect(data[0]).toBe(72);
  });

  it('advances a long soft gradient band that wraps the seam without a dead gap', () => {
    expect(architectureTubeRadius(false)).toBe(ARCH_TUBE_RADIUS_INTER);
    expect(architectureTubeRadius(true)).toBe(ARCH_TUBE_RADIUS_INTRA);
    expect(ARCH_TUBE_RADIUS_INTER).toBeLessThan(0.015);
    expect(ARCH_TUBE_RADIUS_INTRA).toBeLessThan(0.018);
    expect(architectureTubeStyle(false)).toEqual({
      color: ARCH_TUBE_COLOR,
      opacity: ARCH_TUBE_OPACITY,
      emissiveIntensity: ARCH_TUBE_EMISSIVE_INTENSITY,
    });
    expect(architectureTubeStyle(true).color).toBe(ARCH_TUBE_ALARM_COLOR);
    expect(ARCH_TUBE_IN_GLOW_LAYER).toBe(false);
    expect(ARCH_PULSE_RADIUS).toBe(ARCH_TUBE_RADIUS_INTER);
    expect(ARCH_PULSE_HALO_RADIUS).toBeGreaterThan(ARCH_PULSE_RADIUS);
    expect(ARCH_PULSE_HALO_RADIUS).toBeLessThan(0.05);
    expect(architecturePulseHaloRadius(ARCH_PULSE_RADIUS)).toBe(ARCH_PULSE_HALO_RADIUS);
    expect(architecturePulseHaloRadius(ARCH_TUBE_RADIUS_INTRA)).toBeGreaterThan(ARCH_TUBE_RADIUS_INTRA);
    expect(ARCH_PULSE_HALO_INTENSITY).toBeGreaterThan(0.04);
    expect(ARCH_PULSE_HALO_INTENSITY).toBeLessThan(0.25);
    expect(ARCH_PULSE_HALO_FALLOFF).toBeGreaterThan(1);
    expect(ARCH_PULSE_HALO_BLENDING).toBe('additive');
    expect(ARCH_PULSE_WORLD_LENGTH).toBe(4);
    expect(ARCH_PULSE_TRAIL).toBe(ARCH_PULSE_TRAIL_MAX);
    expect(ARCH_PULSE_TRAIL).toBeGreaterThan(0.25);
    expect(ARCH_PULSE_TRAIL).toBeGreaterThan(0.07);
    expect(ARCH_PULSE_TRAIL).toBeLessThan(0.85);
    expect(ARCH_PULSE_TRAIL).not.toBe(0.07);
    expect(architecturePulseTrailForLength(10)).toBeCloseTo(0.4);
    expect(architecturePulseTrailForLength(4)).toBe(ARCH_PULSE_TRAIL_MAX);
    expect(architecturePulseTrailForLength(3)).toBe(ARCH_PULSE_TRAIL_MAX);
    expect(architecturePulseTrailForLength(20)).toBeCloseTo(0.2);
    expect(architecturePulseTrailForLength(20)).toBeGreaterThan(0.07);
    expect(ARCH_PULSE_TAIL_ALPHA).toBeLessThan(0.12);
    expect(ARCH_PULSE_TAIL_ALPHA).toBeGreaterThanOrEqual(0);
    expect(ARCH_PULSE_TAIL_ALPHA).not.toBeCloseTo(0.5);
    expect(ARCH_PULSE_RGB_SCALE).toBe('band');
    expect(ARCH_PULSE_HALO_TRAIL_POWER).toBeGreaterThan(1);
    expect(ARCH_PULSE_WRAP_OFFSET).toBe(1);
    expect(ARCH_PULSE_STYLE).toBe('gradient-trail');
    const headBand = architecturePulseBandIntensity(0.8, 0.8);
    const tailBand = architecturePulseBandIntensity(0.8 - ARCH_PULSE_TRAIL, 0.8);
    const midBand = architecturePulseBandIntensity(0.8 - ARCH_PULSE_TRAIL / 2, 0.8);
    expect(headBand).toBeCloseTo(1);
    expect(tailBand).toBeCloseTo(ARCH_PULSE_TAIL_ALPHA);
    expect(architecturePulseBandIntensity(0.8 - ARCH_PULSE_TRAIL - 0.001, 0.8)).toBe(0);
    expect(midBand).toBeCloseTo((1 + ARCH_PULSE_TAIL_ALPHA) / 2);
    expect(headBand).toBeGreaterThan(tailBand * 8);
    expect(architecturePulseRgbScale(headBand)).toBeCloseTo(1);
    expect(architecturePulseRgbScale(tailBand)).toBeCloseTo(tailBand);
    expect(architecturePulseRgbScale(midBand)).toBeCloseTo(midBand);
    expect(architecturePulseRgbScale(tailBand)).toBeLessThan(0.45 + 0.55 * tailBand);
    expect(architecturePulseCoreBlend(headBand)).toBeCloseTo(1);
    expect(architecturePulseCoreBlend(tailBand)).toBeLessThan(0.02);
    expect(architecturePulseHaloAlong(tailBand)).toBeLessThan(architecturePulseHaloAlong(headBand));
    expect(architecturePulseHaloAlong(midBand)).toBeLessThan(midBand);
    expect(architecturePulseHaloBlend(tailBand)).toBeLessThan(architecturePulseCoreBlend(tailBand));
    expect(architecturePulseHaloBlend(tailBand)).toBeLessThan(architecturePulseHaloBlend(headBand) * 0.05);
    const headLit = architecturePulseCoreBlend(headBand) + architecturePulseHaloBlend(headBand);
    const tailLit = architecturePulseCoreBlend(tailBand) + architecturePulseHaloBlend(tailBand);
    expect(headLit).toBeGreaterThan(tailLit * 20);
    const wrapHead = 0.02;
    const companion = architecturePulseCompanionHead(wrapHead);
    expect(companion).toBeCloseTo(wrapHead + 1);
    expect(architecturePulseIntensity(wrapHead, wrapHead)).toBeCloseTo(1);
    expect(architecturePulseIntensity(0.99, wrapHead)).toBeGreaterThan(0);
    expect(architecturePulseIntensity(0.99, 0)).toBeGreaterThan(0.45);
    expect(architecturePulseIntensity(0, 0)).toBeCloseTo(1);
    expect(architecturePulseIntensity(0.5, 0.5)).toBeCloseTo(1);
    expect(architecturePulseIntensity(0.01, 0.99)).toBe(0);
    const tailOfWrap = 1 - (ARCH_PULSE_TRAIL - wrapHead);
    expect(architecturePulseIntensity(tailOfWrap, wrapHead)).toBeCloseTo(ARCH_PULSE_TAIL_ALPHA, 1);
    [0, 0.02, 0.5, 0.98, 0.999].forEach((head) => {
      expect(architecturePulsePathLit(head)).toBeGreaterThan(0.9);
    });
    const curve = createArchitectureEdgeCurve({ x: 0, y: 0, z: 0 }, { x: 0, y: 4, z: 0 });
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.2, 0.04), new THREE.ShaderMaterial({
      uniforms: { uHead: { value: 0 }, uTrail: { value: 0 } },
    }));
    const pulse = {
      mesh,
      curve,
      phase: 0,
      speed: ARCH_PULSE_SPEED,
      trail: ARCH_PULSE_TRAIL,
    };
    const start = updateArchitecturePulse(pulse, 0);
    const mid = updateArchitecturePulse(pulse, 0.5 / ARCH_PULSE_SPEED);
    const looped = updateArchitecturePulse(pulse, 1 / ARCH_PULSE_SPEED);
    expect(start.u).toBeCloseTo(0);
    expect(mid.u).toBeCloseTo(0.5);
    expect(looped.u).toBeCloseTo(0);
    expect(start.headB).toBeCloseTo(1);
    expect(looped.headB).toBeCloseTo(1);
    expect(mid.point.y).toBeGreaterThan(start.point.y);
    expect((mesh.material as THREE.ShaderMaterial).uniforms.uHead.value).toBeCloseTo(0);
    expect((mesh.material as THREE.ShaderMaterial).uniforms.uTrail.value).toBe(ARCH_PULSE_TRAIL);
    expect(architecturePulseProgress(1 / ARCH_PULSE_SPEED)).toBeCloseTo(0);
    const view = createArchitectureTreeGroup(tree(), (_id, fallback = '') => fallback);
    expect(view.pulses.length).toBeGreaterThan(0);
    const pulseMesh = view.pulses[0].mesh;
    const pathLength = view.pulses[0].curve.getLength();
    const expectedTrail = architecturePulseTrailForLength(pathLength);
    expect(view.pulses[0].trail).toBe(expectedTrail);
    expect(expectedTrail).toBeGreaterThan(0.2);
    expect(expectedTrail * pathLength).toBeGreaterThan(1.5);
    expect(expectedTrail * pathLength).toBeLessThanOrEqual(pathLength * ARCH_PULSE_TRAIL_MAX + 1e-6);
    expect((pulseMesh.geometry as THREE.TubeGeometry).parameters.radius).toBe(ARCH_TUBE_RADIUS_INTER);
    expect((pulseMesh.geometry as THREE.TubeGeometry).parameters.tubularSegments).toBe(ARCH_PULSE_TUBULAR_SEGMENTS);
    expect((pulseMesh.geometry as THREE.TubeGeometry).parameters.radialSegments).toBe(ARCH_PULSE_RADIAL_SEGMENTS);
    expect((pulseMesh.geometry as THREE.TubeGeometry).parameters.tubularSegments).toBeGreaterThan(28);
    expect((pulseMesh.geometry as THREE.TubeGeometry).parameters.radialSegments).toBeGreaterThanOrEqual(24);
    expect(pulseMesh.userData.pulseRadius).toBe(ARCH_TUBE_RADIUS_INTER);
    expect(pulseMesh.userData.pulseTubularSegments).toBe(ARCH_PULSE_TUBULAR_SEGMENTS);
    expect(pulseMesh.userData.pulseRadialSegments).toBe(ARCH_PULSE_RADIAL_SEGMENTS);
    expect(pulseMesh.userData.pulseHaloRadius).toBe(ARCH_PULSE_HALO_RADIUS);
    expect(pulseMesh.userData.hasPulseHalo).toBe(true);
    expect(pulseMesh.userData.pulseWorldLength).toBe(ARCH_PULSE_WORLD_LENGTH);
    expect(pulseMesh.userData.pulseWrap).toBe('head-plus-one');
    expect(pulseMesh.userData.pulseWrapOffset).toBe(1);
    expect(pulseMesh.userData.pulseTailAlpha).toBe(ARCH_PULSE_TAIL_ALPHA);
    expect(pulseMesh.userData.pulseRgbScale).toBe('band');
    expect(pulseMesh.userData.pulseHaloTrailPower).toBe(ARCH_PULSE_HALO_TRAIL_POWER);
    expect((pulseMesh.material as THREE.ShaderMaterial).blending).toBe(THREE.AdditiveBlending);
    expect((pulseMesh.material as THREE.ShaderMaterial).uniforms.uTrail.value).toBe(expectedTrail);
    expect((pulseMesh.material as THREE.ShaderMaterial).uniforms.uTailAlpha.value).toBe(ARCH_PULSE_TAIL_ALPHA);
    expect((pulseMesh.material as THREE.ShaderMaterial).uniforms.uGain.value).toBe(1);
    expect((pulseMesh.material as THREE.ShaderMaterial).uniforms.uHaloFalloff.value).toBe(0);
    expect((pulseMesh.material as THREE.ShaderMaterial).uniforms.uHaloTrailPower.value).toBe(1);
    expect((pulseMesh.material as THREE.ShaderMaterial).fragmentShader).toContain('uColor * band');
    expect((pulseMesh.material as THREE.ShaderMaterial).fragmentShader).not.toContain('0.45 + 0.55');
    const haloMesh = view.pulses[0].halo;
    expect(haloMesh).toBeDefined();
    expect(haloMesh?.userData.archRole).toBe('edge-pulse-halo');
    expect(haloMesh?.userData.pulseLayer).toBe('halo');
    expect((haloMesh?.geometry as THREE.TubeGeometry).parameters.radius).toBe(ARCH_PULSE_HALO_RADIUS);
    expect((haloMesh?.geometry as THREE.TubeGeometry).parameters.tubularSegments).toBe(
      (pulseMesh.geometry as THREE.TubeGeometry).parameters.tubularSegments,
    );
    expect((haloMesh?.geometry as THREE.TubeGeometry).parameters.radialSegments).toBe(
      (pulseMesh.geometry as THREE.TubeGeometry).parameters.radialSegments,
    );
    expect((haloMesh?.geometry as THREE.TubeGeometry).parameters.radialSegments).toBeGreaterThanOrEqual(24);
    expect((haloMesh?.geometry as THREE.TubeGeometry).parameters.radius).toBeGreaterThan(
      (pulseMesh.geometry as THREE.TubeGeometry).parameters.radius,
    );
    expect((haloMesh?.material as THREE.ShaderMaterial).blending).toBe(THREE.AdditiveBlending);
    expect((haloMesh?.material as THREE.ShaderMaterial).uniforms.uGain.value).toBe(ARCH_PULSE_HALO_INTENSITY);
    expect((haloMesh?.material as THREE.ShaderMaterial).uniforms.uHaloFalloff.value).toBe(ARCH_PULSE_HALO_FALLOFF);
    expect((haloMesh?.material as THREE.ShaderMaterial).uniforms.uHaloTrailPower.value).toBe(
      ARCH_PULSE_HALO_TRAIL_POWER,
    );
    expect((haloMesh?.material as THREE.ShaderMaterial).uniforms.uTrail.value).toBe(expectedTrail);
    expect((haloMesh?.material as THREE.ShaderMaterial).uniforms.uTailAlpha.value).toBe(ARCH_PULSE_TAIL_ALPHA);
    expect((haloMesh?.material as THREE.ShaderMaterial).uniforms.uWrapOffset.value).toBe(ARCH_PULSE_WRAP_OFFSET);
    expect((haloMesh?.material as THREE.ShaderMaterial).fragmentShader).toContain('uHaloTrailPower');
    expect((haloMesh?.material as THREE.ShaderMaterial).fragmentShader).toContain('uColor * band');
    expect(haloMesh?.userData.pulseHaloIntensity).toBeLessThan(0.25);
    expect(haloMesh?.userData.pulseHaloTrailPower).toBe(ARCH_PULSE_HALO_TRAIL_POWER);
    expect(haloMesh?.userData.pulseRgbScale).toBe('band');
    const firstU = pulseMesh.userData.pulseU as number;
    const firstHead = (pulseMesh.material as THREE.ShaderMaterial).uniforms.uHead.value;
    const firstHaloHead = (haloMesh?.material as THREE.ShaderMaterial).uniforms.uHead.value;
    expect(firstHaloHead).toBeCloseTo(firstHead);
    view.tick(0.4);
    const nextU = pulseMesh.userData.pulseU as number;
    const nextHead = (pulseMesh.material as THREE.ShaderMaterial).uniforms.uHead.value;
    const nextHaloHead = (haloMesh?.material as THREE.ShaderMaterial).uniforms.uHead.value;
    expect(nextU).not.toBeCloseTo(firstU);
    expect(nextHead).not.toBeCloseTo(firstHead);
    expect(nextHaloHead).toBeCloseTo(nextHead);
    expect(haloMesh?.userData.pulseU).toBe(nextU);
    expect(pulseMesh.userData.pulseStyle).toBe('gradient-trail');
    expect(pulseMesh.userData.hasGradientTrail).toBe(true);
    expect(haloMesh?.userData.hasGradientTrail).toBe(true);
    expect(pulseMesh.material).toBeInstanceOf(THREE.ShaderMaterial);
    expect(typeof pulseMesh.userData.pulseU).toBe('number');
    expect(typeof pulseMesh.userData.pulseHeadB).toBe('number');
    mesh.geometry.dispose();
    (mesh.material as THREE.Material).dispose();
    view.dispose();
  });

  it('keeps pulse glow local — no full-scene bloom, idle filament stays thin and dim', () => {
    const viewSrc = readFileSync(
      resolve(process.cwd(), 'src/app/ops-analysis/components/widgets/application3D/application3DArchitectureView.ts'),
      'utf8',
    );
    const sceneSrc = readFileSync(
      resolve(process.cwd(), 'src/app/ops-analysis/components/widgets/application3D/application3DScene.ts'),
      'utf8',
    );
    expect(viewSrc).not.toContain('UnrealBloomPass');
    expect(viewSrc).not.toContain('EffectComposer');
    expect(viewSrc).toContain('edge-pulse-halo');
    expect(sceneSrc).toContain('bloomPass.enabled = false');
    expect(sceneSrc).not.toContain('RoomEnvironment');
    expect(sceneSrc).not.toContain('PMREMGenerator');
    expect(sceneSrc).not.toContain('scene.environment');
    expect(sceneSrc).not.toContain('pmrem.fromScene');
    expect(sceneSrc).not.toContain('scene.background =');
    expect(ARCH_TUBE_IN_GLOW_LAYER).toBe(false);
    expect(ARCH_TUBE_RADIUS_INTER).toBe(0.01);
    expect(ARCH_TUBE_OPACITY).toBeLessThan(0.4);
    expect(ARCH_PULSE_RADIUS).toBe(ARCH_TUBE_RADIUS_INTER);
    expect(ARCH_PULSE_HALO_RADIUS).toBeGreaterThan(ARCH_PULSE_RADIUS);
    expect(ARCH_PULSE_TUBULAR_SEGMENTS).toBeGreaterThan(28);
    expect(ARCH_PULSE_RADIAL_SEGMENTS).toBeGreaterThanOrEqual(24);
    expect(ARCH_TUBE_TUBULAR_SEGMENTS).toBe(28);
    expect(ARCH_TUBE_RADIAL_SEGMENTS).toBe(8);
    expect(ARCH_PULSE_TUBULAR_SEGMENTS).toBeGreaterThan(ARCH_TUBE_TUBULAR_SEGMENTS);
    expect(ARCH_PULSE_RADIAL_SEGMENTS).toBeGreaterThan(ARCH_TUBE_RADIAL_SEGMENTS);
    expect(viewSrc).not.toContain('new THREE.TubeGeometry(curve, 28, radius, 8');
    expect(viewSrc).not.toContain('new THREE.TubeGeometry(curve, 28, haloRadius, 16');
    expect(viewSrc).not.toContain('ARCH_PULSE_OVERLAP');
    expect(viewSrc).not.toContain('ARCH_PLANE_GLASS');
    expect(viewSrc).toContain('uColor * band');
    expect(viewSrc).not.toContain('0.45 + 0.55 * band');
    expect(viewSrc).toContain('uHaloTrailPower');
  });

  it('creates orthogonal conduit curves with vertical exit and entry for deployment links', () => {
    const from = { x: 0, y: 5, z: 0 };
    const to = { x: 3, y: 1.8, z: 2 };
    const curve = createArchitectureEdgeCurve(from, to);
    expect(curve).toBeInstanceOf(THREE.CatmullRomCurve3);
    const startPoint = curve.getPointAt(0);
    const endPoint = curve.getPointAt(1);
    expect(startPoint.x).toBeCloseTo(from.x);
    expect(startPoint.y).toBeCloseTo(from.y);
    expect(startPoint.z).toBeCloseTo(from.z);
    expect(endPoint.x).toBeCloseTo(to.x);
    expect(endPoint.y).toBeCloseTo(to.y);
    expect(endPoint.z).toBeCloseTo(to.z);

    // Tangents at start and end drop vertically along Y
    const startTangent = curve.getTangentAt(0.01);
    const endTangent = curve.getTangentAt(0.99);
    expect(startTangent.y).toBeLessThan(-0.5);
    expect(endTangent.y).toBeLessThan(-0.5);
  });

  it('maintains clean unified rack models without crown and controls pulse/opacity on hover', () => {
    const view = createArchitectureTreeGroup(tree(), (_id, fallback = '') => fallback);
    const appGroup = view.nodeGroups.get('app-1');
    const hostGroup = view.nodeGroups.get('host-1');
    expect(appGroup).toBeTruthy();
    expect(hostGroup).toBeTruthy();

    let crownFound = false;
    view.group.traverse((child) => {
      if (child.userData.archRole === 'app-crown') crownFound = true;
    });
    expect(crownFound).toBe(false);

    // Initial / quiet state: pulses are hidden so no flowing comets
    expect(view.pulses.every((p) => p.mesh.visible === false && p.halo?.visible === false)).toBe(true);

    expect(typeof view.setHoveredNode).toBe('function');
    const appTubes = view.interPlaneTubes.filter(
      (tube) => tube.userData.sourceId === 'app-1',
    );
    const nonAppTubes = view.interPlaneTubes.filter(
      (tube) => tube.userData.sourceId !== 'app-1',
    );
    expect(appTubes.length).toBeGreaterThan(0);
    expect(nonAppTubes.length).toBeGreaterThan(0);

    // Hover app-1: matching tubes highlight with visible pulses, non-matching tubes hide, model scale stays constant
    view.setHoveredNode?.('app-1');
    expect(appGroup?.scale.x).toBeCloseTo(1);
    appTubes.forEach((tubeGroup) => {
      expect(tubeGroup.visible).toBe(true);
      const mesh = tubeGroup.children[0] as THREE.Mesh;
      const mat = mesh.material as THREE.MeshStandardMaterial;
      const pulse = tubeGroup.userData.pulseMesh as THREE.Mesh;
      const halo = tubeGroup.userData.haloMesh as THREE.Mesh;
      expect(mat.opacity).toBeGreaterThan(0.5);
      expect(mat.emissiveIntensity).toBeGreaterThan(0.3);
      expect(pulse.visible).toBe(true);
      expect(halo.visible).toBe(true);
    });
    nonAppTubes.forEach((tubeGroup) => {
      expect(tubeGroup.visible).toBe(false);
      const pulse = tubeGroup.userData.pulseMesh as THREE.Mesh;
      const halo = tubeGroup.userData.haloMesh as THREE.Mesh;
      expect(pulse.visible).toBe(false);
      expect(halo.visible).toBe(false);
    });

    // Unhover: restore visibility and default opacity, hide pulses
    view.setHoveredNode?.(null);
    expect(appGroup?.scale.x).toBeCloseTo(1);
    expect(view.pulses.every((p) => p.mesh.visible === false && p.halo?.visible === false)).toBe(true);
    view.interPlaneTubes.forEach((tubeGroup) => {
      expect(tubeGroup.visible).toBe(true);
      const mesh = tubeGroup.children[0] as THREE.Mesh;
      const mat = mesh.material as THREE.MeshStandardMaterial;
      expect(mat.opacity).toBe(ARCH_TUBE_OPACITY);
      expect(mat.emissiveIntensity).toBe(ARCH_TUBE_EMISSIVE_INTENSITY);
    });

    // Hover multi-deployment shared host: both parent app tubes highlight
    view.setHoveredNode?.('host-shared');
    const sharedTubes = view.interPlaneTubes.filter(
      (tube) => tube.userData.targetId === 'host-shared',
    );
    expect(sharedTubes).toHaveLength(2);
    sharedTubes.forEach((tubeGroup) => {
      const mesh = tubeGroup.children[0] as THREE.Mesh;
      const mat = mesh.material as THREE.MeshStandardMaterial;
      const pulse = tubeGroup.userData.pulseMesh as THREE.Mesh;
      expect(mat.opacity).toBeGreaterThan(0.5);
      expect(pulse.visible).toBe(true);
    });

    view.dispose();
  });

  it('renders luminous base selection rings across the deployment chain, cyan for normal and red for alarming', () => {
    const alarmingHealth = {
      ...health,
      state: 'alarming' as const,
      reason: 'active_alarm' as const,
      activeAlarmCount: 2,
    };
    const archWithAlarm = tree({
      nodes: [
        { id: 'sys-1', kind: 'system', name: '门户系统', health },
        { id: 'app-1', kind: 'application', name: '门户', health },
        { id: 'app-2', kind: 'application', name: '订单', health },
        { id: 'host-1', kind: 'host', name: 'web-1', health: alarmingHealth },
        { id: 'host-shared', kind: 'host', name: 'shared', health },
      ],
    });
    const view = createArchitectureTreeGroup(archWithAlarm, (_id, fallback = '') => fallback);

    // Initial state: every node has a selection ring mesh, all hidden by default
    view.nodeGroups.forEach((group) => {
      const ring = group.userData.selectionRing as THREE.Mesh | undefined;
      expect(ring).toBeTruthy();
      expect(ring?.userData.archRole).toBe('rack-selection-ring');
      expect(ring?.visible).toBe(false);
      expect(ring?.geometry).toBeInstanceOf(THREE.PlaneGeometry);
      expect(ring?.scale.x).toBeGreaterThan(0.4);
      expect(ring?.scale.x).toBeLessThan(1.0);
    });

    // Hover app-1: app-1, host-1, host-shared rings turn visible
    view.setHoveredNode?.('app-1');
    const app1Ring = view.nodeGroups.get('app-1')?.userData.selectionRing as THREE.Mesh;
    const app2Ring = view.nodeGroups.get('app-2')?.userData.selectionRing as THREE.Mesh;
    const host1Ring = view.nodeGroups.get('host-1')?.userData.selectionRing as THREE.Mesh;
    const hostSharedRing = view.nodeGroups.get('host-shared')?.userData.selectionRing as THREE.Mesh;

    expect(app1Ring.visible).toBe(true);
    expect(host1Ring.visible).toBe(true);
    expect(hostSharedRing.visible).toBe(true);
    expect(app2Ring.visible).toBe(false);

    // Normal app & normal host get cyan ring
    const app1Mat = app1Ring.material as THREE.ShaderMaterial;
    expect(app1Mat.uniforms.uColor.value.getHex()).toBe(ARCH_RING_CYAN);
    const hostSharedMat = hostSharedRing.material as THREE.ShaderMaterial;
    expect(hostSharedMat.uniforms.uColor.value.getHex()).toBe(ARCH_RING_CYAN);

    // Alarming host gets red ring
    const host1Mat = host1Ring.material as THREE.ShaderMaterial;
    expect(host1Mat.uniforms.uColor.value.getHex()).toBe(ARCH_RING_ALARM);

    // Unhover clears all rings
    view.setHoveredNode?.(null);
    expect(app1Ring.visible).toBe(false);
    expect(host1Ring.visible).toBe(false);
    expect(hostSharedRing.visible).toBe(false);

    view.dispose();
  });

  it('colors hover floor rings by each node own health, not the hovered node', () => {
    const alarmingHealth = {
      ...health,
      state: 'alarming' as const,
      reason: 'active_alarm' as const,
      activeAlarmCount: 2,
    };
    const view = createArchitectureTreeGroup(tree({
      nodes: [
        { id: 'sys-1', kind: 'system', name: '门户系统', health },
        { id: 'app-quiet', kind: 'application', name: '安静应用', health },
        { id: 'app-alarm', kind: 'application', name: '告警应用', health: alarmingHealth },
        { id: 'host-quiet', kind: 'host', name: 'web-quiet', health },
        { id: 'host-alarm', kind: 'host', name: 'web-alarm', health: alarmingHealth },
        { id: 'host-ok', kind: 'host', name: 'web-ok', health },
        { id: 'host-bad', kind: 'host', name: 'web-bad', health: alarmingHealth },
      ],
      edges: [
        { id: 'e1', sourceId: 'sys-1', targetId: 'app-quiet', relation: 'system_contains_application' },
        { id: 'e2', sourceId: 'sys-1', targetId: 'app-alarm', relation: 'system_contains_application' },
        { id: 'e3', sourceId: 'app-quiet', targetId: 'host-quiet', relation: 'application_run_host' },
        { id: 'e4', sourceId: 'app-quiet', targetId: 'host-alarm', relation: 'application_run_host' },
        { id: 'e5', sourceId: 'app-alarm', targetId: 'host-ok', relation: 'application_run_host' },
        { id: 'e6', sourceId: 'app-alarm', targetId: 'host-bad', relation: 'application_run_host' },
      ],
    }), (_id, fallback = '') => fallback);

    const ringOf = (id: string) => view.nodeGroups.get(id)?.userData.selectionRing as THREE.Mesh;
    const ringHex = (id: string) =>
      (ringOf(id).material as THREE.ShaderMaterial).uniforms.uColor.value.getHex();

    view.setHoveredNode?.('host-alarm');
    expect(ringOf('host-alarm').visible).toBe(true);
    expect(ringHex('host-alarm')).toBe(ARCH_RING_ALARM);
    expect(ringOf('app-quiet').visible).toBe(true);
    expect(ringHex('app-quiet')).toBe(ARCH_RING_CYAN);
    expect(ringOf('host-quiet').visible).toBe(false);
    expect(ringOf('app-alarm').visible).toBe(false);

    view.setHoveredNode?.('host-bad');
    expect(ringOf('host-bad').visible).toBe(true);
    expect(ringHex('host-bad')).toBe(ARCH_RING_ALARM);
    expect(ringOf('app-alarm').visible).toBe(true);
    expect(ringHex('app-alarm')).toBe(ARCH_RING_ALARM);
    expect(ringOf('host-ok').visible).toBe(false);

    view.setHoveredNode?.('host-quiet');
    expect(ringOf('host-quiet').visible).toBe(true);
    expect(ringHex('host-quiet')).toBe(ARCH_RING_CYAN);
    expect(ringOf('app-quiet').visible).toBe(true);
    expect(ringHex('app-quiet')).toBe(ARCH_RING_CYAN);
    expect(ringOf('host-alarm').visible).toBe(false);

    view.setHoveredNode?.('host-ok');
    expect(ringOf('host-ok').visible).toBe(true);
    expect(ringHex('host-ok')).toBe(ARCH_RING_CYAN);
    expect(ringOf('app-alarm').visible).toBe(true);
    expect(ringHex('app-alarm')).toBe(ARCH_RING_ALARM);

    view.setHoveredNode?.('app-quiet');
    expect(ringOf('app-quiet').visible).toBe(true);
    expect(ringHex('app-quiet')).toBe(ARCH_RING_CYAN);
    expect(ringOf('host-quiet').visible).toBe(true);
    expect(ringHex('host-quiet')).toBe(ARCH_RING_CYAN);
    expect(ringOf('host-alarm').visible).toBe(true);
    expect(ringHex('host-alarm')).toBe(ARCH_RING_ALARM);
    expect(ringOf('app-alarm').visible).toBe(false);
    expect(ringOf('host-ok').visible).toBe(false);

    view.setHoveredNode?.('app-alarm');
    expect(ringOf('app-alarm').visible).toBe(true);
    expect(ringHex('app-alarm')).toBe(ARCH_RING_ALARM);
    expect(ringOf('host-ok').visible).toBe(true);
    expect(ringHex('host-ok')).toBe(ARCH_RING_CYAN);
    expect(ringOf('host-bad').visible).toBe(true);
    expect(ringHex('host-bad')).toBe(ARCH_RING_ALARM);
    expect(ringOf('app-quiet').visible).toBe(false);

    view.setHoveredNode?.(null);
    expect(ringOf('app-alarm').visible).toBe(false);
    expect(ringOf('host-bad').visible).toBe(false);

    const viewSrc = readFileSync(
      resolve(process.cwd(), 'src/app/ops-analysis/components/widgets/application3D/application3DArchitectureView.ts'),
      'utf8',
    );
    expect(viewSrc).toContain('architectureSelectionRingAlarming(node)');
    expect(viewSrc).not.toMatch(/const isAlarm = hostHasAlarm\(node\)/);

    view.dispose();
  });

  it('assigns chip icons from a stable node.id hash and truncates face names', () => {
    expect(APP_CHIP_ICON_KINDS).toEqual([
      'layers',
      'hex-node',
      'code-brackets',
      'pulse-ring',
      'grid-tile',
    ]);
    expect(hashAppChipIconIndex('app-1')).toBe(hashAppChipIconIndex('app-1'));
    expect(appChipIconKind('app-1')).toBe(APP_CHIP_ICON_KINDS[hashAppChipIconIndex('app-1')]);
    expect(hashAppChipIconIndex('app-1')).toBeGreaterThanOrEqual(0);
    expect(hashAppChipIconIndex('app-1')).toBeLessThan(APP_CHIP_ICON_KINDS.length);
    const seen = new Set(
      ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'app-1', 'app-2', '订单服务'].map(hashAppChipIconIndex),
    );
    expect(seen.size).toBeGreaterThan(1);
    expect(truncateAppChipName('门户')).toBe('门户');
    expect(truncateAppChipName('订单服务平台监控')).toBe('订单服务平台监控');
    expect(truncateAppChipName('订单服务平台监控中心')).toBe('订单服务平台监控中...');
    expect(ARCH_APP_CHIP_NAME_MAX_CHARS).toBe(9);
  });

  it('paints the chip plate with wall-card glass body, border, and inset glow', () => {
    const fills: string[] = [];
    const strokes: string[] = [];
    const shadows: string[] = [];
    const stops: string[] = [];
    const lineWidths: number[] = [];
    const shadowBlurs: number[] = [];
    const ctx = {
      canvas: { width: 512, height: 384 },
      save: () => undefined,
      restore: () => undefined,
      beginPath: () => undefined,
      closePath: () => undefined,
      moveTo: () => undefined,
      lineTo: () => undefined,
      quadraticCurveTo: () => undefined,
      clip: () => undefined,
      fillRect: () => undefined,
      fill: () => undefined,
      stroke: () => undefined,
      set fillStyle(value: string | CanvasGradient) {
        fills.push(String(value));
      },
      get fillStyle() {
        return '';
      },
      set strokeStyle(value: string) {
        strokes.push(String(value));
      },
      get strokeStyle() {
        return '';
      },
      set shadowColor(value: string) {
        shadows.push(String(value));
      },
      get shadowColor() {
        return '';
      },
      set shadowBlur(value: number) {
        shadowBlurs.push(value);
      },
      get shadowBlur() {
        return 0;
      },
      set lineWidth(value: number) {
        lineWidths.push(value);
      },
      get lineWidth() {
        return 1;
      },
      shadowOffsetX: 0,
      shadowOffsetY: 0,
      createLinearGradient: () => ({
        addColorStop: (_offset: number, color: string) => {
          stops.push(color);
        },
      }),
    } as unknown as CanvasRenderingContext2D;

    paintAppChipGlassPlate(ctx, 512, 384);
    const strokePx = architectureAppChipRimStrokePx(512);
    const planeRimPx = (ARCH_PLANE_RIM_STROKE_WORLD / ARCH_NODE_SIZE.application.width) * 512;
    expect(stops).toContain(ARCH_APP_CHIP_WALL_BODY_TOP);
    expect(stops).not.toContain(CARD_GLASS.bodyCenter);
    expect(stops).not.toContain(CARD_GLASS.body);
    expect(stops).toContain(ARCH_APP_CHIP_WALL_BODY_BOTTOM);
    expect(stops).toContain(ARCH_APP_CHIP_WALL_DIAGONAL_WASH);
    expect(stops).toContain(ARCH_APP_CHIP_WALL_TOP_VEIL);
    expect(stops).not.toContain('rgba(30, 62, 94, 0.7)');
    expect(stops).not.toContain('rgba(30, 62, 94, 0.92)');
    expect(stops).not.toContain(CARD_GLASS.sheen);
    expect(stops).not.toContain(CARD_GLASS.sheenFade);
    expect(stops).toContain(ARCH_APP_CHIP_WALL_SHEEN);
    expect(stops).not.toContain('#8fe4ea');
    expect(strokes).toContain(ARCH_APP_CHIP_WALL_BORDER);
    expect(strokes).toContain(ARCH_APP_CHIP_WALL_INSET_LINE);
    expect(strokes).toContain(ARCH_APP_CHIP_WALL_INSET_GLOW);
    expect(strokes).toContain(ARCH_APP_CHIP_WALL_INSET_DEEP);
    expect(strokes).not.toContain(CARD_GLASS.bodyRim);
    expect(strokes).not.toContain(CARD_TONE.normal.innerGlow);
    expect(strokes).not.toContain(CARD_TONE.normal.edge);
    expect(shadows).toContain(ARCH_APP_CHIP_WALL_INSET_GLOW);
    expect(shadows).toContain(ARCH_APP_CHIP_WALL_INSET_DEEP);
    expect(shadows).toContain(ARCH_APP_CHIP_WALL_INSET_TOP);
    expect(shadows).not.toContain(CARD_TONE.normal.glow.color);
    expect(strokePx).toBeCloseTo(512 * ARCH_APP_CHIP_WALL_STROKE_RATIO);
    expect(strokePx).toBeGreaterThanOrEqual(2);
    expect(strokePx).toBeLessThanOrEqual(3);
    expect(strokePx).toBeLessThan(planeRimPx / 2);
    expect(ARCH_APP_CHIP_WALL_STROKE_RATIO).toBeGreaterThanOrEqual(0.004);
    expect(ARCH_APP_CHIP_WALL_STROKE_RATIO).toBeLessThanOrEqual(0.006);
    expect(lineWidths).toContain(strokePx);
    expect(lineWidths).toContain(ARCH_APP_CHIP_WALL_INSET_LINE_PX);
    expect(Math.max(...lineWidths)).toBeLessThan(8);
    expect(lineWidths).not.toContain(planeRimPx);
    expect(shadowBlurs).toContain(ARCH_APP_CHIP_WALL_INSET_GLOW_PX);
    expect(shadowBlurs).toContain(ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_PX);
    expect(Math.max(...shadowBlurs)).toBeLessThan(24);
    expect(ARCH_APP_CHIP_WALL_SHEEN_HEIGHT_PX).toBe(2);
    expect(ARCH_APP_CHIP_WALL_BODY_TOP).toBe('rgba(58, 108, 148, 0.48)');
    expect(ARCH_APP_CHIP_WALL_BODY_BOTTOM).toBe('rgba(32, 66, 96, 0.42)');
    expect(ARCH_APP_CHIP_PLATE_ALPHA).toBe(0.48);
    expect(ARCH_APP_CHIP_PLATE_ALPHA).toBeLessThan(0.68);

    strokes.length = 0;
    shadows.length = 0;
    stops.length = 0;
    lineWidths.length = 0;
    shadowBlurs.length = 0;
    paintAppChipGlassPlate(ctx, 512, 384, { alarming: true });
    expect(strokes).toContain(ARCH_APP_CHIP_WALL_BORDER_ALARM);
    expect(strokes).toContain(ARCH_APP_CHIP_WALL_INSET_LINE_ALARM);
    expect(strokes).toContain(ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM);
    expect(strokes).toContain(ARCH_APP_CHIP_WALL_INSET_DEEP_ALARM);
    expect(strokes).not.toContain(ARCH_APP_CHIP_WALL_BORDER);
    expect(strokes).not.toContain(ARCH_APP_CHIP_WALL_INSET_LINE);
    expect(strokes).not.toContain(ARCH_APP_CHIP_WALL_INSET_GLOW);
    expect(shadows).toContain(ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM);
    expect(shadows).toContain(ARCH_APP_CHIP_WALL_INSET_DEEP_ALARM);
    expect(shadows).toContain(ARCH_APP_CHIP_WALL_INSET_TOP_ALARM);
    expect(shadows).not.toContain(ARCH_APP_CHIP_WALL_INSET_GLOW);
    expect(stops).toContain(ARCH_APP_CHIP_WALL_SHEEN_ALARM);
    expect(stops).toContain(ARCH_APP_CHIP_WALL_TOP_VEIL_ALARM);
    expect(stops).toContain(ARCH_APP_CHIP_WALL_DIAGONAL_WASH_ALARM);
    expect(stops).not.toContain(ARCH_APP_CHIP_WALL_SHEEN);
    expect(stops).not.toContain(ARCH_APP_CHIP_WALL_TOP_VEIL);
    expect(stops).not.toContain(ARCH_APP_CHIP_WALL_DIAGONAL_WASH);
    expect(stops).not.toContain(ARCH_APP_CHIP_WALL_BORDER_ALARM);
    expect(stops).toContain(ARCH_APP_CHIP_WALL_BODY_TOP);
    expect(lineWidths).toContain(strokePx);
    expect(lineWidths).toContain(ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM_WIDTH);
    expect(shadowBlurs).toContain(ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM_PX);
    expect(shadowBlurs).toContain(ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_ALARM_PX);
    expect(Math.max(...shadowBlurs)).toBeGreaterThan(ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_PX);
  });

  it('builds wall-card application chips instead of racks, with Y-only camera yaw', () => {
    expect(ARCH_APP_CHIP_OPACITY).toBeGreaterThan(0);
    expect(ARCH_APP_CHIP_OPACITY).toBeLessThan(0.28);
    expect(ARCH_APP_CHIP_ROUGHNESS).toBeCloseTo(0.62);
    expect(ARCH_APP_CHIP_METALNESS).toBeGreaterThanOrEqual(0);
    expect(ARCH_APP_CHIP_METALNESS).toBeLessThanOrEqual(0.05);
    expect(ARCH_APP_CHIP_TRANSMISSION).toBe(0);
    expect(ARCH_APP_CHIP_GLASS_COLOR).toBe(0x16384c);
    expect(ARCH_APP_CHIP_GLASS_COLOR).not.toBe(0x0a1624);
    expect(ARCH_APP_CHIP_GLASS_COLOR).not.toBe(0x1e3e5e);
    expect(ARCH_APP_CHIP_BODY_XY_SCALE).toBeGreaterThanOrEqual(0.92);
    expect(ARCH_APP_CHIP_BODY_XY_SCALE).toBeLessThan(1);
    expect(ARCH_APP_CHIP_BEVEL).toBeGreaterThan(0);
    expect(architectureAppChipBodyFrontZ(ARCH_NODE_SIZE.application.depth))
      .toBeGreaterThan(ARCH_NODE_SIZE.application.depth / 2 + 0.001);
    expect(architectureAppChipFaceZ(ARCH_NODE_SIZE.application.depth))
      .toBeGreaterThan(architectureAppChipBodyFrontZ(ARCH_NODE_SIZE.application.depth));
    expect(ARCH_APP_CHIP_FACE_LIFT).toBeGreaterThan(0);
    expect(ARCH_APP_CHIP_WALL_BORDER).not.toBe(ARCH_PLANE_RIM_COLOR);
    expect(ARCH_APP_CHIP_WALL_BORDER).not.toBe(ARCH_EDGE);
    expect(ARCH_APP_CHIP_WALL_STROKE_RATIO).not.toBe(
      ARCH_PLANE_RIM_STROKE_WORLD / ARCH_NODE_SIZE.application.width,
    );
    expect(architectureAppChipRimStrokePx(512)).toBeCloseTo(512 * ARCH_APP_CHIP_WALL_STROKE_RATIO);
    expect(architectureAppChipRimStrokePx(512)).toBeLessThan(
      (ARCH_PLANE_RIM_STROKE_WORLD / ARCH_NODE_SIZE.application.width) * 512,
    );
    expect(ARCH_APP_CHIP_RIM_HAS_EDGE_LINES).toBe(false);
    expect(ARCH_APP_CHIP_RIM_BAKED).toBe(true);
    expect(ARCH_APP_CHIP_RIM_STYLE).toBe('wall-css');
    expect(ARCH_APP_CHIP_FACE_RENDER_ORDER).toBeGreaterThan(ARCH_APP_CHIP_BODY_RENDER_ORDER);
    expect(ARCH_APP_CHIP_WALL_BORDER).toBe('rgba(100, 162, 198, 0.74)');

    const view = createArchitectureTreeGroup(tree({
      nodes: [
        { id: 'sys-1', kind: 'system', name: '门户系统', health },
        { id: 'app-1', kind: 'application', name: '订单服务平台监控', health },
        {
          id: 'app-alarm',
          kind: 'application',
          name: '告警应用',
          health: { ...health, state: 'alarming' },
        },
        { id: 'host-1', kind: 'host', name: 'web-1', health },
        {
          id: 'host-alarm',
          kind: 'host',
          name: 'web-alarm',
          health: { ...health, state: 'alarming' },
        },
      ],
      edges: [
        { id: 'e1', sourceId: 'sys-1', targetId: 'app-1', relation: 'system_contains_application' },
        { id: 'e2', sourceId: 'app-1', targetId: 'host-1', relation: 'application_run_host' },
        { id: 'e3', sourceId: 'app-alarm', targetId: 'host-alarm', relation: 'application_run_host' },
      ],
    }), (_id, fallback = '') => fallback);

    const appGroup = view.nodeGroups.get('app-1');
    const alarmApp = view.nodeGroups.get('app-alarm');
    const hostGroup = view.nodeGroups.get('host-1');
    expect(appGroup?.userData.archRole).toBe('rack-root');
    expect(appGroup?.userData.nodeId).toBe('app-1');
    expect(appGroup?.userData.yawBillboard).toBe(true);
    expect(hostGroup?.userData.yawBillboard).toBeUndefined();
    expect(view.nodeLabels.has('app-1')).toBe(true);
    expect(view.nodeLabels.has('app-alarm')).toBe(true);
    expect(view.nodeLabels.has('host-1')).toBe(true);

    const collect = (root: THREE.Object3D) => {
      const chips: THREE.Mesh[] = [];
      const faces: THREE.Mesh[] = [];
      const rims: THREE.Mesh[] = [];
      const halos: THREE.Mesh[] = [];
      const dots: THREE.Mesh[] = [];
      const racks: THREE.Mesh[] = [];
      const leds: THREE.Mesh[] = [];
      const labels: THREE.Mesh[] = [];
      root.traverse((child) => {
        if (!(child as THREE.Mesh).isMesh) return;
        const mesh = child as THREE.Mesh;
        if (mesh.userData.archRole === 'app-chip') chips.push(mesh);
        if (mesh.userData.archRole === 'app-chip-face') faces.push(mesh);
        if (mesh.userData.archRole === 'app-chip-rim') rims.push(mesh);
        if (mesh.userData.archRole === 'app-chip-rim-halo') halos.push(mesh);
        if (mesh.userData.archRole === 'app-chip-alarm-dot') dots.push(mesh);
        if (mesh.userData.archRole === 'rack') racks.push(mesh);
        if (mesh.userData.archRole === 'rack-led') leds.push(mesh);
        if (mesh.userData.archRole === 'node-label') labels.push(mesh);
      });
      return { chips, faces, rims, halos, dots, racks, leds, labels };
    };

    const quiet = collect(appGroup as THREE.Object3D);
    const alarmed = collect(alarmApp as THREE.Object3D);
    const host = collect(hostGroup as THREE.Object3D);
    expect(quiet.chips).toHaveLength(1);
    expect(quiet.faces).toHaveLength(1);
    expect(quiet.rims).toHaveLength(0);
    expect(quiet.halos).toHaveLength(0);
    expect(quiet.dots).toHaveLength(0);
    expect(quiet.racks).toHaveLength(0);
    expect(quiet.leds).toHaveLength(0);
    expect(quiet.labels).toHaveLength(1);
    expect(host.chips).toHaveLength(0);
    expect(host.racks).toHaveLength(1);
    expect(host.leds).toHaveLength(ARCH_RACK_LED_COUNT);
    expect(host.labels).toHaveLength(1);

    const bodyMat = quiet.chips[0].material as THREE.MeshStandardMaterial;
    expect(bodyMat).toBeInstanceOf(THREE.MeshStandardMaterial);
    expect(bodyMat).not.toBeInstanceOf(THREE.MeshPhysicalMaterial);
    expect(bodyMat.transparent).toBe(true);
    expect(bodyMat.opacity).toBeCloseTo(ARCH_APP_CHIP_OPACITY);
    expect(bodyMat.roughness).toBeCloseTo(ARCH_APP_CHIP_ROUGHNESS);
    expect(bodyMat.metalness).toBeCloseTo(ARCH_APP_CHIP_METALNESS);
    expect(('transmission' in bodyMat) ? Number((bodyMat as THREE.MeshPhysicalMaterial).transmission) : 0)
      .toBe(0);
    expect(bodyMat.side).toBe(THREE.FrontSide);
    expect(bodyMat.depthWrite).toBe(false);
    expect(bodyMat.envMap).toBeFalsy();
    expect(bodyMat.color.getHex()).toBe(ARCH_APP_CHIP_GLASS_COLOR);
    expect(bodyMat.color.getHex()).not.toBe(0x8fe4ea);
    expect(bodyMat.color.getHex()).not.toBe(0x0a1624);
    expect(quiet.chips[0].renderOrder).toBe(ARCH_APP_CHIP_BODY_RENDER_ORDER);
    expect(quiet.chips[0].userData.chipBodyRole).toBe('side-thickness');
    expect(quiet.chips[0].userData.chipBodyOpen).toBe(false);
    expect(quiet.chips[0].userData.chipBodyQuiet).toBe(true);
    expect(quiet.chips[0].userData.hasOpaqueLid).toBe(false);
    expect(quiet.chips[0].userData.chipTransmission).toBe(0);
    const chipGeo = quiet.chips[0].geometry as THREE.ExtrudeGeometry;
    expect(chipGeo.parameters.options.bevelEnabled).toBe(true);
    expect(chipGeo.parameters.options.bevelSize).toBe(ARCH_APP_CHIP_BEVEL);
    const extruded = chipGeo.parameters.shapes;
    const holeShapes = Array.isArray(extruded) ? extruded[0]?.holes : extruded?.holes;
    expect(holeShapes ?? []).toHaveLength(0);
    const unitChip = createRoundedChipGeometry();
    expect(unitChip.parameters.options.bevelEnabled).toBe(true);
    unitChip.computeBoundingBox();
    const unitFront = unitChip.boundingBox?.max.z ?? 0;
    expect(unitFront).toBeCloseTo(0.5 + ARCH_APP_CHIP_BEVEL);
    expect(unitFront * ARCH_NODE_SIZE.application.depth).toBeCloseTo(
      architectureAppChipBodyFrontZ(ARCH_NODE_SIZE.application.depth),
    );
    unitChip.dispose();
    expect(quiet.chips[0].scale.x).toBeCloseTo(
      ARCH_NODE_SIZE.application.width * ARCH_APP_CHIP_BODY_XY_SCALE,
    );
    expect(quiet.chips[0].scale.y).toBeCloseTo(
      ARCH_NODE_SIZE.application.height * ARCH_APP_CHIP_BODY_XY_SCALE,
    );
    expect(quiet.chips[0].scale.z).toBeCloseTo(ARCH_NODE_SIZE.application.depth);
    expect(quiet.chips[0].scale.x).toBeLessThan(quiet.faces[0].scale.x);
    expect(quiet.chips[0].userData.chipIcon).toBe(appChipIconKind('app-1'));
    const faceMat = quiet.faces[0].material as THREE.MeshBasicMaterial;
    expect(faceMat).toBeInstanceOf(THREE.MeshBasicMaterial);
    expect(faceMat).not.toBeInstanceOf(THREE.MeshPhysicalMaterial);
    expect(faceMat.transparent).toBe(true);
    expect(faceMat.depthWrite).toBe(false);
    expect(faceMat.side).toBe(THREE.FrontSide);
    expect(quiet.faces[0].renderOrder).toBe(ARCH_APP_CHIP_FACE_RENDER_ORDER);
    expect(quiet.faces[0].renderOrder).toBeGreaterThan(quiet.chips[0].renderOrder);
    expect(quiet.faces[0].scale.x).toBeCloseTo(ARCH_NODE_SIZE.application.width);
    expect(quiet.faces[0].scale.y).toBeCloseTo(ARCH_NODE_SIZE.application.height);
    expect(quiet.faces[0].position.z).toBeCloseTo(
      architectureAppChipFaceZ(ARCH_NODE_SIZE.application.depth),
    );
    expect(quiet.faces[0].position.z).toBeGreaterThan(
      architectureAppChipBodyFrontZ(ARCH_NODE_SIZE.application.depth),
    );
    expect(quiet.faces[0].position.z).toBeGreaterThan(
      ARCH_NODE_SIZE.application.depth / 2 + 0.001,
    );
    expect(quiet.faces[0].userData.chipIcon).toBe(appChipIconKind('app-1'));
    expect(quiet.faces[0].userData.chipTitle).toBe('订单服务平台监控');
    expect(quiet.faces[0].userData.hasAlarmDot).toBe(false);
    expect(quiet.faces[0].userData.chipAlarming).toBe(false);
    expect(quiet.faces[0].userData.alarmPaintsRim).toBe(false);
    expect(quiet.faces[0].userData.alarmPaintsInset).toBe(false);
    expect(quiet.faces[0].userData.alarmPaintsHighlight).toBe(false);
    expect(quiet.faces[0].userData.rimInsetLine).toBe(ARCH_APP_CHIP_WALL_INSET_LINE);
    expect(quiet.faces[0].userData.separatorColor).toBe(ARCH_APP_CHIP_SEPARATOR);
    expect(quiet.faces[0].userData.iconStroke).toBe(ARCH_APP_CHIP_ICON_STROKE);
    expect(quiet.faces[0].userData.insetGlowPx).toBe(ARCH_APP_CHIP_WALL_INSET_GLOW_PX);
    expect(quiet.chips[0].userData.chipAlarming).toBe(false);
    expect(quiet.chips[0].userData.alarmPaintsBody).toBe(false);
    expect(quiet.faces[0].userData.iconFilled).toBe(true);
    expect(quiet.faces[0].userData.hasSeparator).toBe(true);
    expect(quiet.faces[0].userData.hasGlassBody).toBe(true);
    expect(quiet.faces[0].userData.hasSheen).toBe(true);
    expect(quiet.faces[0].userData.chipSeeThrough).toBe(true);
    expect(quiet.faces[0].userData.plateAlpha).toBe(ARCH_APP_CHIP_PLATE_ALPHA);
    expect(quiet.faces[0].userData.faceMaterialKind).toBe('basic');
    expect(quiet.faces[0].userData.rimBaked).toBe(true);
    expect(quiet.faces[0].userData.rimStyle).toBe('wall-css');
    expect(quiet.faces[0].userData.rimColor).toBe(ARCH_APP_CHIP_WALL_BORDER);
    expect(quiet.faces[0].userData.rimStrokeRatio).toBe(ARCH_APP_CHIP_WALL_STROKE_RATIO);
    expect(quiet.faces[0].userData.rimStrokePx).toBeCloseTo(architectureAppChipRimStrokePx());
    expect(quiet.faces[0].userData.rimInsetOnly).toBe(true);
    expect(quiet.faces[0].userData.rimHasOuterBloom).toBe(false);
    expect(quiet.faces[0].userData.rimStrokeWorld).toBeUndefined();
    expect(quiet.faces[0].userData.rimHaloWorld).toBeUndefined();
    expect(quiet.faces[0].userData.rimHasEdgeLines).toBe(false);
    expect(quiet.faces[0].userData.rimCornerWorld).toBeUndefined();

    expect(alarmed.dots).toHaveLength(0);
    expect(alarmed.faces[0].userData.hasAlarmDot).toBe(false);
    expect(alarmed.faces[0].userData.chipAlarming).toBe(true);
    expect(alarmed.faces[0].userData.alarmPaintsRim).toBe(true);
    expect(alarmed.faces[0].userData.alarmPaintsInset).toBe(true);
    expect(alarmed.faces[0].userData.alarmPaintsHighlight).toBe(true);
    expect(alarmed.faces[0].userData.rimInsetLine).toBe(ARCH_APP_CHIP_WALL_INSET_LINE_ALARM);
    expect(alarmed.faces[0].userData.rimInsetGlow).toBe(ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM);
    expect(alarmed.faces[0].userData.rimSheen).toBe(ARCH_APP_CHIP_WALL_SHEEN_ALARM);
    expect(alarmed.faces[0].userData.separatorColor).toBe(ARCH_APP_CHIP_SEPARATOR_ALARM);
    expect(alarmed.faces[0].userData.iconStroke).toBe(ARCH_APP_CHIP_ICON_STROKE_ALARM);
    expect(alarmed.faces[0].userData.insetGlowPx).toBe(ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM_PX);
    expect(alarmed.rims).toHaveLength(0);
    expect(alarmed.halos).toHaveLength(0);
    expect(alarmed.faces[0].userData.rimBaked).toBe(true);
    expect(alarmed.faces[0].userData.rimColor).toBe(ARCH_APP_CHIP_WALL_BORDER_ALARM);
    expect(alarmed.faces[0].userData.rimColor).not.toBe(ARCH_APP_CHIP_WALL_BORDER);
    expect(alarmed.faces[0].userData.rimStrokeRatio).toBe(ARCH_APP_CHIP_WALL_STROKE_RATIO);
    expect(alarmed.chips[0].userData.chipAlarming).toBe(true);
    expect(alarmed.chips[0].userData.alarmPaintsBody).toBe(false);
    expect((alarmed.chips[0].material as THREE.MeshStandardMaterial).color.getHex()).toBe(
      ARCH_APP_CHIP_GLASS_COLOR,
    );
    expect(alarmed.labels).toHaveLength(1);
    const appLabel = view.nodeLabels.get('app-1');
    const hostLabel = view.nodeLabels.get('host-1');
    const appNode = view.layout.nodes.find((node) => node.id === 'app-1');
    const hostNode = view.layout.nodes.find((node) => node.id === 'host-1');
    const sharedLabelScale = architectureNodeLabelScale();
    expect(sharedLabelScale.x).toBe(ARCH_LABEL_WORLD_WIDTH);
    expect(sharedLabelScale.y).toBe(ARCH_LABEL_WORLD_HEIGHT);
    expect(appLabel?.userData.archRole).toBe('node-label');
    expect(appLabel?.userData.billboard).toBe(ARCH_LABEL_BILLBOARD);
    expect(appLabel?.userData.labelHasBackground).toBe(ARCH_LABEL_HAS_BACKGROUND);
    expect(appLabel?.userData.labelFill).toBe(ARCH_LABEL_FILL);
    expect(appLabel?.userData.labelScale).toEqual(sharedLabelScale);
    expect(hostLabel?.userData.labelScale).toEqual(sharedLabelScale);
    expect(appLabel?.userData.labelScale).toEqual(hostLabel?.userData.labelScale);
    expect(appNode?.width).not.toBe(hostNode?.width);
    expect(appLabel?.position.y).toBeCloseTo((appNode?.height ?? 0) / 2 + 0.28);
    expect(hostLabel?.userData.archRole).toBe('node-label');
    expect(hostLabel?.position.y).toBeCloseTo((hostNode?.height ?? 0) / 2 + 0.28);
    expect(hostHasAlarm(view.layout.nodes.find((node) => node.id === 'app-alarm'))).toBe(false);
    expect(applicationHasAlarm(view.layout.nodes.find((node) => node.id === 'app-alarm'))).toBe(true);
    expect(architectureEdgeColor(view.layout.nodes.find((node) => node.id === 'app-alarm'))).toBe(ARCH_EDGE);
    expect(architectureEdgeColor(view.layout.nodes.find((node) => node.id === 'host-alarm'))).toBe(ARCH_EDGE_ALARM);

    view.setHoveredNode?.('app-alarm');
    const alarmAppRing = alarmApp?.userData.selectionRing as THREE.Mesh;
    expect(alarmAppRing.visible).toBe(true);
    expect((alarmAppRing.material as THREE.ShaderMaterial).uniforms.uColor.value.getHex()).toBe(
      ARCH_RING_ALARM,
    );
    view.setHoveredNode?.(null);

    const viewSrc = readFileSync(
      resolve(process.cwd(), 'src/app/ops-analysis/components/widgets/application3D/application3DArchitectureView.ts'),
      'utf8',
    );
    expect(viewSrc).toContain('addAppChipMeshes');
    expect(viewSrc).toMatch(/if \(node\.kind === 'application'\) \{\s*addAppChipMeshes/);
    expect(viewSrc).toContain("node.kind === 'host' || node.kind === 'application'");
    expect(viewSrc).toContain('paintNodeLabel');
    expect(viewSrc).not.toContain('app-chip-alarm-dot');
    expect(viewSrc).not.toContain('rimAlarm');
    expect(viewSrc).not.toContain('createAppChipRimGeometries');
    expect(viewSrc).not.toContain('app-chip-rim-halo');
    expect(viewSrc).not.toContain('createChipRimMaterial');
    expect(viewSrc).not.toContain('MeshPhysicalMaterial');
    expect(viewSrc).not.toContain('addChipRim');
    expect(viewSrc).not.toContain('ARCH_APP_CHIP_SIDE_WALL');
    expect(viewSrc).not.toContain('.holes.push');
    expect(viewSrc).toContain('paintAppChipGlassPlate');
    expect(viewSrc).toContain('ARCH_APP_CHIP_WALL_BORDER');
    expect(viewSrc).toContain('ARCH_APP_CHIP_WALL_BORDER_ALARM');
    expect(viewSrc).toContain('ARCH_APP_CHIP_WALL_INSET_LINE_ALARM');
    expect(viewSrc).toContain('architectureAppChipWallInset');
    expect(viewSrc).toContain('architectureAppChipWallHighlight');
    expect(viewSrc).toContain('architectureAppChipWallInsetBloom');
    expect(viewSrc).toContain('drawAppChipIcon(context, icon, width / 2, iconCy, iconSize, alarming)');
    expect(viewSrc).toContain('ARCH_APP_CHIP_WALL_SHEEN_ALARM');
    expect(viewSrc).toContain('applicationHasAlarm(node)');
    expect(viewSrc).toContain('ARCH_APP_CHIP_WALL_STROKE_RATIO');
    expect(viewSrc).not.toContain('CARD_TONE.normal');
    expect(viewSrc).not.toContain('architectureAppChipRimHaloPx');
    expect(viewSrc).not.toContain('ARCH_APP_CHIP_RIM_STROKE_WORLD');
    expect(viewSrc).not.toContain('ARCH_APP_CHIP_RIM_HALO_WORLD');
    expect(viewSrc).not.toContain('ARCH_APP_CHIP_RIM_COLOR');
    expect(viewSrc).not.toContain('architectureAppChipRimCornerWorld');
    expect(viewSrc).not.toContain('createRoundedRectCurve');
    expect(viewSrc).not.toContain('chipSide');
    expect(viewSrc).toContain('fill: paint.haze');
    expect(viewSrc).toContain('ARCH_APP_CHIP_WALL_INSET_GLOW_WIDTH');
    expect(viewSrc).toContain('sdRoundedBox');
    expect(viewSrc).toContain('yawObjectAroundYToCamera');
    expect(viewSrc).toContain('addRackMeshes(nodeGroup, node, rackGeos, rackMats, alarming)');

    const camera = new THREE.PerspectiveCamera(50, 16 / 9, 0.1, 200);
    camera.position.set(6, 4, 12);
    const hostYawBefore = hostGroup?.rotation.y ?? 0;
    view.tick(0.016, camera);
    const appWorld = new THREE.Vector3();
    appGroup?.getWorldPosition(appWorld);
    const expectedYaw = Math.atan2(camera.position.x - appWorld.x, camera.position.z - appWorld.z);
    expect(appGroup?.rotation.x).toBeCloseTo(0);
    expect(appGroup?.rotation.z).toBeCloseTo(0);
    expect(appGroup?.rotation.y).toBeCloseTo(expectedYaw);
    expect(hostGroup?.rotation.x).toBeCloseTo(0);
    expect(hostGroup?.rotation.y).toBeCloseTo(hostYawBefore);
    expect(hostGroup?.rotation.y).toBeCloseTo(0);

    const dummy = new THREE.Group();
    dummy.position.set(1, 2, 3);
    dummy.rotation.set(0.4, 0.1, 0.3);
    yawObjectAroundYToCamera(dummy, camera);
    expect(dummy.rotation.x).toBe(0);
    expect(dummy.rotation.z).toBe(0);
    expect(dummy.rotation.y).toBeCloseTo(Math.atan2(5, 9));

    view.dispose();
  });
});
