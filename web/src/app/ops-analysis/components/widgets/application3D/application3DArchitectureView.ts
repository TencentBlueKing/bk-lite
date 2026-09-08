import * as THREE from 'three';
import type { Application3DTranslate } from './application3DLayout';
import { CARD_GLASS } from './application3DCardStyle';
import cabinetFrontAlbedo from './assets/cabinet-front-albedo-v2.png';
import cabinetSideAlbedo from './assets/cabinet-side-albedo.png';
import cabinetTopAlbedo from './assets/cabinet-top-albedo.png';
import {
  ARCH_FRUSTUM_HEIGHT,
  ARCH_FRUSTUM_TAPER,
  ARCH_LABEL_BILLBOARD,
  ARCH_LABEL_CANVAS_HEIGHT,
  ARCH_LABEL_CANVAS_WIDTH,
  ARCH_LABEL_FILL,
  ARCH_LABEL_HAS_BACKGROUND,
  ARCH_LABEL_WORLD_HEIGHT,
  ARCH_LABEL_WORLD_WIDTH,
  ARCH_PLANE_DEPTH_WRITE,
  ARCH_PLANE_EMISSIVE_INTENSITY,
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
  ARCH_PLANE_TITLE_SIDE,
  ARCH_PULSE_HALO_FALLOFF,
  ARCH_PULSE_HALO_INTENSITY,
  ARCH_PULSE_HALO_TRAIL_POWER,
  ARCH_PULSE_RADIAL_SEGMENTS,
  ARCH_PULSE_RGB_SCALE,
  ARCH_PULSE_SPEED,
  ARCH_PULSE_STYLE,
  ARCH_PULSE_TAIL_ALPHA,
  ARCH_PULSE_TUBULAR_SEGMENTS,
  ARCH_PULSE_WORLD_LENGTH,
  ARCH_PULSE_WRAP_OFFSET,
  ARCH_TITLE_FILL,
  ARCH_TITLE_SHADOW_BLUR,
  ARCH_TITLE_SHADOW_COLOR,
  ARCH_TUBE_EMISSIVE_INTENSITY,
  ARCH_TUBE_IN_GLOW_LAYER,
  ARCH_TUBE_OPACITY,
  ARCH_TUBE_RADIAL_SEGMENTS,
  ARCH_TUBE_TUBULAR_SEGMENTS,
  architecturePulseCompanionHead,
  architecturePulseHaloRadius,
  architecturePulseTrailForLength,
  architectureTitleLocalX,
  architectureTitleLocalZ,
  architectureTubeRadius,
  architectureTubeStyle,
  formatArchitecturePlaneTitle,
  layoutApplication3DArchitecture,
  type Application3DArchitectureLayout,
  type Application3DArchitecturePlane,
  type Application3DArchitecturePlacedEdge,
  type Application3DArchitecturePlacedNode,
} from './application3DArchitecture';
import type { Application3DArchitectureData } from '@/app/ops-analysis/types/sceneWidget';

export interface Application3DArchitecturePulse {
  mesh: THREE.Mesh;
  /** Pulse-local additive halo; omitted only in helper-unit stubs. */
  halo?: THREE.Mesh;
  curve: THREE.CatmullRomCurve3;
  phase: number;
  speed: number;
  trail: number;
}

export interface Application3DArchitectureView {
  group: THREE.Group;
  layout: Application3DArchitectureLayout;
  planeGroups: THREE.Group[];
  nodeGroups: Map<string, THREE.Group>;
  nodeLabels: Map<string, THREE.Mesh>;
  intraPlaneTubes: THREE.Object3D[];
  interPlaneTubes: THREE.Object3D[];
  pulses: Application3DArchitecturePulse[];
  billboardMeshes: THREE.Object3D[];
  rankedNodeIds: string[];
  setHoveredNode?: (nodeId: string | null) => void;
  tick: (dt: number, camera?: THREE.Camera) => void;
  dispose: () => void;
}

/**
 * Chassis identity (never alarm red / cyan). Hulls paint with ARCH_RACK_*
 * + albedo; this keeps rank-size tests off wall health tints.
 */
export const ARCH_CHASSIS_COLOR = 0x6e767e;
export const ARCH_NODE_FILL = ARCH_CHASSIS_COLOR;
export const ARCH_STROKE_EMISSIVE_INTENSITY = 0.72;
export const ARCH_RACK_LED_COUNT = 3;
/**
 * Front-albedo UV of the three painted header pits on
 * cabinet-front-albedo-v2.png (512×1024). u left→right; v from +Z bottom
 * (image y ≈ 39.9 → 0.9606). BoxGeometry +Z: u 0→1 is −X→+X, v 0→1 is −Y→+Y.
 * World: x = (u − 0.5) * width, y = (v − 0.5) * height.
 */
export const ARCH_RACK_LED_UV_U = [0.1122, 0.1708, 0.2294] as const;
export const ARCH_RACK_LED_UV_V = 0.9606;
/** Cylinder radius in UV of front albedo width. Header pits ~20px on 512-wide map (diameter 0.039). */
export const ARCH_RACK_LED_RADIUS_UV = 0.0195;
/** Sit a hair above the board so the hull is not a z-fight void. */
export const ARCH_RACK_LIFT = 0.02;
export const ARCH_RACK_STROKE_WIDTH = 0.006;
export const ARCH_RACK_SIDE_ROUGHNESS = 0.5;
export const ARCH_RACK_SIDE_METALNESS = 0.04;
export const ARCH_RACK_FRONT_ROUGHNESS = ARCH_RACK_SIDE_ROUGHNESS;
export const ARCH_RACK_FRONT_METALNESS = ARCH_RACK_SIDE_METALNESS;
export const ARCH_RACK_HULL_COLOR = 0xffffff;
/** Runtime albedo lift: out = offset + src * scale, clamp 255. Black → ~0x48. */
export const ARCH_RACK_ALBEDO_LIFT_OFFSET = 72;
export const ARCH_RACK_ALBEDO_LIFT_SCALE = 1.05;
/** Original card-veneer hue; higher opacity so the middle still reads. */
export const ARCH_PLANE = 0x163e5c;
export const ARCH_PLANE_EMISSIVE = 0x1a6e98;
export const ARCH_EDGE = 0x3ec8d0;
export const ARCH_EDGE_ALARM = 0xe05050;
export const ARCH_LED_COLOR = ARCH_EDGE;
export const ARCH_LED_ALARM_COLOR = ARCH_EDGE_ALARM;
/** Alarming hosts only. 素柜 never get a stroke, so there is no quiet-stroke color. */
export const ARCH_STROKE_ALARM_COLOR = ARCH_EDGE_ALARM;
export const ARCH_VENEER_LIFT = 0.002;
export const ARCH_RING_CYAN = 0x00d2ff;
export const ARCH_RING_ALARM = 0xff3b3b;

export const hostHasAlarm = (
  node: { kind: string; health?: { state: string } } | undefined,
) => node?.kind === 'host' && node.health?.state === 'alarming';

/**
 * Own-node alarm only. Applications never inherit host alarms.
 * Any `health.state === 'alarming'` (warning / error / critical alike)
 * paints the chip's outer stroke, inward inset, sheen, and wash red.
 */
export const applicationHasAlarm = (
  node: { kind: string; health?: { state: string } } | undefined,
) => node?.kind === 'application' && node.health?.state === 'alarming';

/** Floor ring follows that node's own face chrome. Hover only toggles visibility. */
export const architectureSelectionRingAlarming = (
  node: { kind: string; health?: { state: string } } | undefined,
) => hostHasAlarm(node) || applicationHasAlarm(node);

export const APP_CHIP_ICON_KINDS = [
  'layers',
  'hex-node',
  'code-brackets',
  'pulse-ring',
  'grid-tile',
] as const;

export type AppChipIconKind = (typeof APP_CHIP_ICON_KINDS)[number];

/**
 * Quiet thin slab for thickness only. Face canvas carries the wall-card
 * look. Never a picture-frame hole, never MeshPhysical transmission.
 */
export const ARCH_APP_CHIP_GLASS_COLOR = 0x16384c;
export const ARCH_APP_CHIP_OPACITY = 0.16;
export const ARCH_APP_CHIP_ROUGHNESS = 0.62;
export const ARCH_APP_CHIP_METALNESS = 0.02;
/** Locked off. Chips are a painted plate, not a transmission volume. */
export const ARCH_APP_CHIP_TRANSMISSION = 0;
/** Inset the slab so the baked face rim, not the bevel, is the border. */
export const ARCH_APP_CHIP_BODY_XY_SCALE = 0.96;
/** Lifted wall blues, lower alpha so the scene reads through. */
export const ARCH_APP_CHIP_PLATE_ALPHA = 0.48;
export const ARCH_APP_CHIP_TITLE_FILL = 'rgba(248, 252, 255, 0.96)';
export const ARCH_APP_CHIP_ICON_STROKE = 'rgba(210, 250, 255, 0.88)';
export const ARCH_APP_CHIP_ICON_FILL = 'rgba(120, 236, 244, 0.32)';
export const ARCH_APP_CHIP_ICON_FILL_STRONG = 'rgba(210, 250, 255, 0.42)';
export const ARCH_APP_CHIP_ICON_GLOW = 'rgba(94, 232, 240, 0.75)';
export const ARCH_APP_CHIP_SEPARATOR = 'rgba(186, 240, 246, 0.45)';
export const ARCH_APP_CHIP_SEPARATOR_SHADOW = 'rgba(160, 236, 244, 0.55)';
export const ARCH_APP_CHIP_TITLE_SHADOW = 'rgba(180, 240, 248, 0.55)';
export const ARCH_APP_CHIP_ICON_STROKE_ALARM = 'rgba(255, 208, 200, 0.9)';
export const ARCH_APP_CHIP_ICON_FILL_ALARM = 'rgba(255, 70, 58, 0.36)';
export const ARCH_APP_CHIP_ICON_FILL_STRONG_ALARM = 'rgba(255, 160, 150, 0.5)';
export const ARCH_APP_CHIP_ICON_GLOW_ALARM = 'rgba(255, 70, 58, 0.8)';
export const ARCH_APP_CHIP_SEPARATOR_ALARM = 'rgba(255, 170, 160, 0.72)';
export const ARCH_APP_CHIP_SEPARATOR_SHADOW_ALARM = 'rgba(255, 70, 58, 0.55)';
export const ARCH_APP_CHIP_TITLE_SHADOW_ALARM = 'rgba(255, 160, 150, 0.45)';
export const ARCH_APP_CHIP_NAME_MAX_CHARS = 9;
export const ARCH_APP_CHIP_TITLE_WEIGHT = 700;
export const ARCH_APP_CHIP_TITLE_SIZE = 46;
export const ARCH_APP_CHIP_CORNER = 0.12;
export const ARCH_APP_CHIP_BEVEL = 0.032;
/**
 * Extrude bevel adds `bevelThickness` on both lids. After `geometry.center()`
 * the unit body front is at `0.5 + bevel`, not `0.5`. Scale-z then stretches
 * that past `depth / 2`, so a face at `depth / 2 + ε` sits *behind* the lid.
 */
export const ARCH_APP_CHIP_FACE_LIFT = 0.002;

export const architectureAppChipBodyFrontZ = (depth: number) =>
  (0.5 + ARCH_APP_CHIP_BEVEL) * depth;

export const architectureAppChipFaceZ = (depth: number) =>
  architectureAppChipBodyFrontZ(depth) + ARCH_APP_CHIP_FACE_LIFT;
export const ARCH_APP_CHIP_FACE_CANVAS_WIDTH = 512;
export const ARCH_APP_CHIP_FACE_CANVAS_HEIGHT = 384;
export const ARCH_APP_CHIP_BODY_RENDER_ORDER = 0;
export const ARCH_APP_CHIP_FACE_RENDER_ORDER = 2;
/**
 * Chip rim is a canvas bake of `.app3d-wall-glass`, not board veneer.
 * Do not scale these from `ARCH_PLANE_RIM_*` world units.
 */
export const ARCH_APP_CHIP_WALL_BORDER = 'rgba(100, 162, 198, 0.74)';
/** `.app3d-wall-glass[data-tone='critical']` border — warning/critical share this. */
export const ARCH_APP_CHIP_WALL_BORDER_ALARM = 'rgba(255, 82, 72, 0.9)';
export const ARCH_APP_CHIP_WALL_INSET_LINE = 'rgba(140, 184, 214, 0.34)';
export const ARCH_APP_CHIP_WALL_INSET_GLOW = 'rgba(64, 128, 168, 0.4)';
export const ARCH_APP_CHIP_WALL_INSET_DEEP = 'rgba(36, 86, 124, 0.2)';
export const ARCH_APP_CHIP_WALL_INSET_TOP = 'rgba(72, 134, 172, 0.3)';
/** `.app3d-wall-glass[data-tone='critical']::before` inset tokens. */
export const ARCH_APP_CHIP_WALL_INSET_LINE_ALARM = 'rgba(255, 160, 150, 0.42)';
export const ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM = 'rgba(255, 70, 58, 0.5)';
export const ARCH_APP_CHIP_WALL_INSET_DEEP_ALARM = 'rgba(190, 28, 20, 0.2)';
export const ARCH_APP_CHIP_WALL_INSET_TOP_ALARM = 'rgba(255, 70, 58, 0.34)';
export const ARCH_APP_CHIP_WALL_SHEEN = 'rgba(186, 210, 230, 0.24)';
export const ARCH_APP_CHIP_WALL_DIAGONAL_WASH = 'rgba(206, 224, 240, 0.1)';
export const ARCH_APP_CHIP_WALL_TOP_VEIL = 'rgba(210, 226, 240, 0.08)';
/** `.app3d-wall-glass[data-tone='critical']::after` and ::before family. */
export const ARCH_APP_CHIP_WALL_SHEEN_ALARM = 'rgba(255, 208, 200, 0.24)';
export const ARCH_APP_CHIP_WALL_DIAGONAL_WASH_ALARM = 'rgba(255, 160, 150, 0.1)';
export const ARCH_APP_CHIP_WALL_TOP_VEIL_ALARM = 'rgba(255, 208, 200, 0.08)';
/** Lifted wall blues so the plate is micro-translucent, not near-black. */
export const ARCH_APP_CHIP_WALL_BODY_TOP = 'rgba(58, 108, 148, 0.48)';
export const ARCH_APP_CHIP_WALL_BODY_BOTTOM = 'rgba(32, 66, 96, 0.42)';
/** ~2.56px on a 512 face — CSS 1.5px hairline, ~0.5% of width. */
export const ARCH_APP_CHIP_WALL_STROKE_RATIO = 0.005;
export const ARCH_APP_CHIP_WALL_INSET_LINE_PX = 1;
export const ARCH_APP_CHIP_WALL_INSET_GLOW_PX = 10;
export const ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_PX = 18;
export const ARCH_APP_CHIP_WALL_INSET_GLOW_WIDTH = 2;
export const ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_WIDTH = 3;
/** Alarm-only: CSS inset spread/blur is stronger than a 2px canvas stroke. */
export const ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM_PX = 28;
export const ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_ALARM_PX = 44;
export const ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM_WIDTH = 10;
export const ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_ALARM_WIDTH = 16;
export const ARCH_APP_CHIP_WALL_INSET_TOP_BLUR_PX = 16;
export const ARCH_APP_CHIP_WALL_INSET_TOP_OFFSET_PX = 8;
export const ARCH_APP_CHIP_WALL_SHEEN_INSET_RATIO = 0.07;
export const ARCH_APP_CHIP_WALL_SHEEN_TOP_PX = 1;
export const ARCH_APP_CHIP_WALL_SHEEN_HEIGHT_PX = 2;
export const ARCH_APP_CHIP_RIM_HAS_EDGE_LINES = false;
export const ARCH_APP_CHIP_RIM_BAKED = true;
export const ARCH_APP_CHIP_RIM_STYLE = 'wall-css' as const;

const CHIP_YAW_WORLD = new THREE.Vector3();

/** FNV-1a — stable across frames; never random. */
export const hashAppChipIconIndex = (nodeId: string) => {
  let hash = 2166136261;
  for (let index = 0; index < nodeId.length; index += 1) {
    hash ^= nodeId.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) % APP_CHIP_ICON_KINDS.length;
};

export const appChipIconKind = (nodeId: string): AppChipIconKind =>
  APP_CHIP_ICON_KINDS[hashAppChipIconIndex(nodeId)];

export const truncateAppChipName = (
  name: string,
  maxChars = ARCH_APP_CHIP_NAME_MAX_CHARS,
) => {
  const trimmed = name.trim();
  if (trimmed.length <= maxChars) return trimmed;
  return `${trimmed.slice(0, maxChars)}...`;
};

/** Yaw-only cylindrical billboard. Never lookAt — that would pitch the card flat. */
export const yawObjectAroundYToCamera = (
  object: THREE.Object3D,
  camera: THREE.Camera,
) => {
  object.getWorldPosition(CHIP_YAW_WORLD);
  object.rotation.x = 0;
  object.rotation.z = 0;
  object.rotation.y = Math.atan2(
    camera.position.x - CHIP_YAW_WORLD.x,
    camera.position.z - CHIP_YAW_WORLD.z,
  );
};

export const findArchitectureRackRoot = (
  object: THREE.Object3D | null | undefined,
): THREE.Object3D | null => {
  let current: THREE.Object3D | null | undefined = object;
  while (current) {
    if (current.userData.archRole === 'rack-root') return current;
    current = current.parent;
  }
  return null;
};

export const architectureEdgeColor = (
  target: { kind: string; health?: { state: string } } | undefined,
) => (hostHasAlarm(target) ? ARCH_EDGE_ALARM : ARCH_EDGE);

const TUBE_SCROLL_SPEED = 0;
const PLANE_TITLE_WIDTH = 2.5;
const PLANE_TITLE_HEIGHT = 0.70;
const PULSE_POINT = new THREE.Vector3();

/**
 * Rectangular truncated pyramid. Top face is the platform racks sit on;
 * bottom face is smaller so sides taper inward going DOWN.
 */
export const createTrapezoidFrustumGeometry = (
  topWidth: number,
  topDepth: number,
  bottomWidth: number,
  bottomDepth: number,
  height: number,
  options?: { includeTop?: boolean; includeBottom?: boolean },
): THREE.BufferGeometry => {
  const yTop = height / 2;
  const yBot = -height / 2;
  const tx = topWidth / 2;
  const tz = topDepth / 2;
  const bx = bottomWidth / 2;
  const bz = bottomDepth / 2;
  const includeTop = options?.includeTop !== false;
  const includeBottom = options?.includeBottom !== false;
  const faces: number[][] = [];
  if (includeTop) {
    faces.push([-tx, yTop, -tz, tx, yTop, -tz, tx, yTop, tz, -tx, yTop, tz]);
  }
  if (includeBottom) {
    faces.push([-bx, yBot, bz, bx, yBot, bz, bx, yBot, -bz, -bx, yBot, -bz]);
  }
  faces.push(
    [-tx, yTop, tz, tx, yTop, tz, bx, yBot, bz, -bx, yBot, bz],
    [tx, yTop, -tz, -tx, yTop, -tz, -bx, yBot, -bz, bx, yBot, -bz],
    [tx, yTop, tz, tx, yTop, -tz, bx, yBot, -bz, bx, yBot, bz],
    [-tx, yTop, -tz, -tx, yTop, tz, -bx, yBot, bz, -bx, yBot, -bz],
  );
  const positions: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];
  faces.forEach((face, index) => {
    const base = index * 4;
    positions.push(...face);
    uvs.push(0, 1, 1, 1, 1, 0, 0, 0);
    indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
};

const createPlaneVeneerMaterial = () =>
  new THREE.MeshStandardMaterial({
    color: ARCH_PLANE,
    metalness: 0.04,
    roughness: 0.18,
    emissive: ARCH_PLANE_EMISSIVE,
    emissiveIntensity: ARCH_PLANE_EMISSIVE_INTENSITY,
    transparent: true,
    opacity: ARCH_PLANE_OPACITY,
    depthWrite: ARCH_PLANE_DEPTH_WRITE,
    side: THREE.DoubleSide,
  });

/** Frustum sides + bottom: top veneer hue, slightly more see-through, no stroke. */
const createPlaneSideMaterial = () =>
  new THREE.MeshStandardMaterial({
    color: ARCH_PLANE,
    metalness: 0.04,
    roughness: 0.18,
    emissive: ARCH_PLANE_EMISSIVE,
    emissiveIntensity: ARCH_PLANE_SIDE_EMISSIVE_INTENSITY,
    transparent: true,
    opacity: ARCH_PLANE_SIDE_OPACITY,
    depthWrite: ARCH_PLANE_DEPTH_WRITE,
    side: THREE.DoubleSide,
  });

export const architectureAppChipRimStrokePx = (
  canvasWidth = ARCH_APP_CHIP_FACE_CANVAS_WIDTH,
) => ARCH_APP_CHIP_WALL_STROKE_RATIO * canvasWidth;

export const architectureAppChipWallBorder = (alarming: boolean) =>
  alarming ? ARCH_APP_CHIP_WALL_BORDER_ALARM : ARCH_APP_CHIP_WALL_BORDER;

export const architectureAppChipWallInset = (alarming: boolean) =>
  alarming
    ? {
      line: ARCH_APP_CHIP_WALL_INSET_LINE_ALARM,
      glow: ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM,
      deep: ARCH_APP_CHIP_WALL_INSET_DEEP_ALARM,
      top: ARCH_APP_CHIP_WALL_INSET_TOP_ALARM,
    }
    : {
      line: ARCH_APP_CHIP_WALL_INSET_LINE,
      glow: ARCH_APP_CHIP_WALL_INSET_GLOW,
      deep: ARCH_APP_CHIP_WALL_INSET_DEEP,
      top: ARCH_APP_CHIP_WALL_INSET_TOP,
    };

export const architectureAppChipWallHighlight = (alarming: boolean) =>
  alarming
    ? {
      sheen: ARCH_APP_CHIP_WALL_SHEEN_ALARM,
      veil: ARCH_APP_CHIP_WALL_TOP_VEIL_ALARM,
      wash: ARCH_APP_CHIP_WALL_DIAGONAL_WASH_ALARM,
    }
    : {
      sheen: ARCH_APP_CHIP_WALL_SHEEN,
      veil: ARCH_APP_CHIP_WALL_TOP_VEIL,
      wash: ARCH_APP_CHIP_WALL_DIAGONAL_WASH,
    };

export const architectureAppChipWallInsetBloom = (alarming: boolean) =>
  alarming
    ? {
      glowPx: ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM_PX,
      deepPx: ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_ALARM_PX,
      glowWidth: ARCH_APP_CHIP_WALL_INSET_GLOW_ALARM_WIDTH,
      deepWidth: ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_ALARM_WIDTH,
    }
    : {
      glowPx: ARCH_APP_CHIP_WALL_INSET_GLOW_PX,
      deepPx: ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_PX,
      glowWidth: ARCH_APP_CHIP_WALL_INSET_GLOW_WIDTH,
      deepWidth: ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_WIDTH,
    };

export const architectureAppChipIconPaint = (alarming: boolean) =>
  alarming
    ? {
      stroke: ARCH_APP_CHIP_ICON_STROKE_ALARM,
      fill: ARCH_APP_CHIP_ICON_FILL_ALARM,
      fillStrong: ARCH_APP_CHIP_ICON_FILL_STRONG_ALARM,
      glow: ARCH_APP_CHIP_ICON_GLOW_ALARM,
      haze: 'rgba(255, 70, 58, 0.14)',
      hazeStroke: 'rgba(255, 160, 150, 0.28)',
    }
    : {
      stroke: ARCH_APP_CHIP_ICON_STROKE,
      fill: ARCH_APP_CHIP_ICON_FILL,
      fillStrong: ARCH_APP_CHIP_ICON_FILL_STRONG,
      glow: ARCH_APP_CHIP_ICON_GLOW,
      haze: 'rgba(94, 232, 240, 0.14)',
      hazeStroke: 'rgba(190, 250, 255, 0.28)',
    };

export const architectureAppChipSeparator = (alarming: boolean) =>
  alarming
    ? {
      stroke: ARCH_APP_CHIP_SEPARATOR_ALARM,
      shadow: ARCH_APP_CHIP_SEPARATOR_SHADOW_ALARM,
    }
    : {
      stroke: ARCH_APP_CHIP_SEPARATOR,
      shadow: ARCH_APP_CHIP_SEPARATOR_SHADOW,
    };

/**
 * Board veneer rim: hairline stroke + tight inset glow in WORLD units.
 * Normal blending — additive bloom is what made 2% UV look like fat neon.
 * App chips do not use this; they bake `.app3d-wall-glass` CSS onto the face.
 */
const createInwardRimMaterial = (
  worldWidth: number,
  worldHeight: number,
  options: {
    color: number;
    strokeWorld: number;
    haloWorld: number;
    cornerWorld?: number;
    opacity: number;
    strokeOpacity: number;
    falloff: number;
  },
) =>
  new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: true,
    side: THREE.DoubleSide,
    blending: THREE.NormalBlending,
    toneMapped: false,
    uniforms: {
      uColor: { value: new THREE.Color(options.color) },
      uStrokeWorld: { value: options.strokeWorld },
      uHaloWorld: { value: options.haloWorld },
      uWorldWidth: { value: worldWidth },
      uWorldDepth: { value: worldHeight },
      uCornerWorld: { value: options.cornerWorld ?? 0 },
      uFalloff: { value: options.falloff },
      uOpacity: { value: options.opacity },
      uStroke: { value: options.strokeOpacity },
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      uniform float uStrokeWorld;
      uniform float uHaloWorld;
      uniform float uWorldWidth;
      uniform float uWorldDepth;
      uniform float uCornerWorld;
      uniform float uFalloff;
      uniform float uOpacity;
      uniform float uStroke;
      varying vec2 vUv;

      float sdRoundedBox(vec2 p, vec2 b, float r) {
        vec2 q = abs(p) - b + r;
        return min(max(q.x, q.y), 0.0) + length(max(q, 0.0)) - r;
      }

      void main() {
        vec2 p = (vUv - 0.5) * vec2(uWorldWidth, uWorldDepth);
        vec2 b = vec2(uWorldWidth, uWorldDepth) * 0.5;
        float r = min(max(uCornerWorld, 0.0), min(b.x, b.y) - 1e-4);
        float sd = sdRoundedBox(p, b, r);
        if (sd > 0.0) discard;
        float edge = -sd;
        float stroke = 1.0 - smoothstep(0.0, uStrokeWorld, edge);
        float bloom = 1.0 - smoothstep(uStrokeWorld, uHaloWorld, edge);
        bloom = pow(max(bloom, 0.0), uFalloff);
        float alpha = max(stroke * uStroke, bloom * uOpacity);
        if (alpha < 0.008) discard;
        gl_FragColor = vec4(uColor, alpha);
      }
    `,
  });

const createPlaneRimMaterial = (worldWidth: number, worldDepth: number) =>
  createInwardRimMaterial(worldWidth, worldDepth, {
    color: ARCH_PLANE_RIM_COLOR,
    strokeWorld: ARCH_PLANE_RIM_STROKE_WORLD,
    haloWorld: ARCH_PLANE_RIM_HALO_WORLD,
    cornerWorld: 0,
    opacity: ARCH_PLANE_RIM_OPACITY,
    strokeOpacity: ARCH_PLANE_RIM_STROKE_OPACITY,
    falloff: ARCH_PLANE_RIM_FALLOFF,
  });

const stampRimUserData = (object: THREE.Object3D) => {
  object.userData.archRole = 'plane-rim';
  object.userData.planeSkin = 'veneer';
  object.userData.rimColor = ARCH_PLANE_RIM_COLOR;
  object.userData.rimOpacity = ARCH_PLANE_RIM_OPACITY;
  object.userData.rimStrokeOpacity = ARCH_PLANE_RIM_STROKE_OPACITY;
  object.userData.rimInner = ARCH_PLANE_RIM_INNER;
  object.userData.rimOuter = ARCH_PLANE_RIM_OUTER;
  object.userData.rimStrokeWorld = ARCH_PLANE_RIM_STROKE_WORLD;
  object.userData.rimHaloWorld = ARCH_PLANE_RIM_HALO_WORLD;
  object.userData.rimBlending = ARCH_PLANE_RIM_BLENDING;
  object.userData.rimFalloff = ARCH_PLANE_RIM_FALLOFF;
  object.userData.rimHasEdgeLines = ARCH_PLANE_RIM_HAS_EDGE_LINES;
  object.userData.rimStyle = 'inward-bloom';
};

const stampVeneerUserData = (
  mesh: THREE.Mesh,
  plane: Application3DArchitecturePlane,
  role: 'plane-mesh' | 'plane-veneer',
) => {
  mesh.userData.archRole = role;
  mesh.userData.planeSkin = 'veneer';
  mesh.userData.planeKind = plane.kind;
  mesh.userData.planeOrientation = ARCH_PLANE_ORIENTATION;
  mesh.userData.planeShape = plane.shape;
  mesh.userData.planeWidth = plane.width;
  mesh.userData.planeDepth = plane.depth;
  mesh.userData.planeHeight = plane.height;
  mesh.userData.planeThickness = plane.thickness;
  mesh.userData.hasRim = true;
  mesh.userData.restOpacity = ARCH_PLANE_OPACITY;
  mesh.userData.restEmissiveIntensity = ARCH_PLANE_EMISSIVE_INTENSITY;
};

const paintCanvasTexture = (
  width: number,
  height: number,
  paint: (ctx: CanvasRenderingContext2D, canvas: HTMLCanvasElement) => void,
) => {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D context unavailable');
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.shadowColor = 'transparent';
  context.shadowBlur = 0;
  paint(context, canvas);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
};

/** Host and application overhead plates share one world glyph size. */
export const architectureNodeLabelScale = () =>
  new THREE.Vector3(ARCH_LABEL_WORLD_WIDTH, ARCH_LABEL_WORLD_HEIGHT, 1);

const paintNodeLabel = (node: Application3DArchitecturePlacedNode) =>
  paintCanvasTexture(ARCH_LABEL_CANVAS_WIDTH, ARCH_LABEL_CANVAS_HEIGHT, (context, canvas) => {
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillStyle = ARCH_LABEL_FILL;
    context.font = `600 58px ${CARD_GLASS.fontFamily}`;
    context.fillText(node.name.slice(0, 18), canvas.width / 2, canvas.height / 2);
  });

const paintPlaneTitle = (plane: Application3DArchitecturePlane, translate: Application3DTranslate) => {
  const name = formatArchitecturePlaneTitle(translate(plane.titleKey, plane.titleFallback));
  return paintCanvasTexture(640, 160, (context, canvas) => {
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.shadowColor = ARCH_TITLE_SHADOW_COLOR;
    context.shadowBlur = ARCH_TITLE_SHADOW_BLUR;
    context.fillStyle = ARCH_TITLE_FILL;
    context.font = `600 68px ${CARD_GLASS.fontFamily}`;
    context.fillText(name, canvas.width / 2, canvas.height / 2);
  });
};

const paintTubeStripe = () => {
  const canvas = document.createElement('canvas');
  canvas.width = 64;
  canvas.height = 8;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D context unavailable');
  const gradient = context.createLinearGradient(0, 0, canvas.width, 0);
  gradient.addColorStop(0, 'rgba(12, 32, 52, 0.18)');
  gradient.addColorStop(0.5, 'rgba(46, 110, 138, 0.32)');
  gradient.addColorStop(1, 'rgba(10, 24, 40, 0.16)');
  context.fillStyle = gradient;
  context.fillRect(0, 0, canvas.width, canvas.height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(4, 1);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
};

export const createSelectionRingMaterial = (color: number) =>
  new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: true,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    toneMapped: false,
    uniforms: {
      uColor: { value: new THREE.Color(color) },
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      varying vec2 vUv;

      void main() {
        vec2 p = (vUv - 0.5) * 2.0;
        float d = length(p);
        if (d > 1.0) discard;

        // Sharp core ring around d = 0.78
        float mainRing = exp(-pow((d - 0.78) / 0.042, 2.0));
        // Subtle outer accent ring around d = 0.90
        float subRing = exp(-pow((d - 0.90) / 0.018, 2.0)) * 0.45;
        // Soft inner floor glow
        float innerFloor = smoothstep(0.78, 0.25, d) * 0.22;
        // Soft halo aura
        float aura = exp(-pow((d - 0.78) / 0.12, 2.0)) * 0.35;

        float alpha = mainRing * 0.85 + subRing + innerFloor + aura;
        if (alpha < 0.005) discard;

        vec3 color = uColor * (1.0 + mainRing * 0.4);
        gl_FragColor = vec4(color, alpha);
      }
    `,
  });

interface RackKitGeometries {
  box: THREE.BoxGeometry;
  led: THREE.CylinderGeometry;
  shadow: THREE.PlaneGeometry;
}

interface RackKitMaterials {
  /** BoxGeometry face order: +X, -X, +Y, -Y, +Z, -Z. */
  faces: THREE.MeshStandardMaterial[];
  textures: THREE.Texture[];
  led: THREE.MeshStandardMaterial;
  ledAlarm: THREE.MeshStandardMaterial;
  strokeAlarm: THREE.MeshStandardMaterial;
  shadow: THREE.MeshBasicMaterial;
  ringCyan: THREE.ShaderMaterial;
  ringAlarm: THREE.ShaderMaterial;
}

const textureSrc = (asset: string | { src: string }) =>
  typeof asset === 'string' ? asset : asset.src;

/** Lift near-black albedo pixels so a matte hull still reads without IBL. */
export const liftCabinetAlbedoPixels = (pixels: Uint8ClampedArray | Uint8Array) => {
  for (let i = 0; i < pixels.length; i += 4) {
    pixels[i] = Math.min(255, ARCH_RACK_ALBEDO_LIFT_OFFSET + pixels[i] * ARCH_RACK_ALBEDO_LIFT_SCALE);
    pixels[i + 1] = Math.min(255, ARCH_RACK_ALBEDO_LIFT_OFFSET + pixels[i + 1] * ARCH_RACK_ALBEDO_LIFT_SCALE);
    pixels[i + 2] = Math.min(255, ARCH_RACK_ALBEDO_LIFT_OFFSET + pixels[i + 2] * ARCH_RACK_ALBEDO_LIFT_SCALE);
  }
};

export const liftCabinetAlbedoTexture = (texture: THREE.Texture) => {
  if (texture.userData.albedoLifted) return;
  const image = texture.image as {
    width?: number;
    height?: number;
    data?: Uint8ClampedArray | Uint8Array;
  } | undefined;
  if (!image) return;

  if (image.data instanceof Uint8ClampedArray || image.data instanceof Uint8Array) {
    liftCabinetAlbedoPixels(image.data);
    texture.userData.albedoLifted = true;
    texture.needsUpdate = true;
    return;
  }

  const width = Number(image.width) || 0;
  const height = Number(image.height) || 0;
  if (width < 1 || height < 1) return;

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context) return;
  try {
    context.drawImage(image as CanvasImageSource, 0, 0);
    const imageData = context.getImageData(0, 0, width, height);
    liftCabinetAlbedoPixels(imageData.data);
    context.putImageData(imageData, 0, 0);
  } catch {
    return;
  }
  texture.image = canvas;
  texture.userData.albedoLifted = true;
  texture.needsUpdate = true;
};

const loadCabinetAlbedo = (loader: THREE.TextureLoader, url: string) => {
  const texture = loader.load(url, liftCabinetAlbedoTexture);
  texture.colorSpace = THREE.SRGBColorSpace;
  if (texture.image) liftCabinetAlbedoTexture(texture);
  return texture;
};

const createRackMaterials = (): RackKitMaterials => {
  const loader = new THREE.TextureLoader();
  const frontAlbedo = loadCabinetAlbedo(loader, textureSrc(cabinetFrontAlbedo));
  const sideAlbedo = loadCabinetAlbedo(loader, textureSrc(cabinetSideAlbedo));
  const topAlbedo = loadCabinetAlbedo(loader, textureSrc(cabinetTopAlbedo));
  const side = new THREE.MeshStandardMaterial({
    color: ARCH_RACK_HULL_COLOR,
    map: sideAlbedo,
    roughness: ARCH_RACK_SIDE_ROUGHNESS,
    metalness: ARCH_RACK_SIDE_METALNESS,
  });
  const top = new THREE.MeshStandardMaterial({
    color: ARCH_RACK_HULL_COLOR,
    map: topAlbedo,
    roughness: ARCH_RACK_SIDE_ROUGHNESS,
    metalness: ARCH_RACK_SIDE_METALNESS,
  });
  const front = new THREE.MeshStandardMaterial({
    color: ARCH_RACK_HULL_COLOR,
    map: frontAlbedo,
    roughness: ARCH_RACK_FRONT_ROUGHNESS,
    metalness: ARCH_RACK_FRONT_METALNESS,
    emissive: 0x000000,
    emissiveIntensity: 0,
  });
  const led = new THREE.MeshStandardMaterial({
    color: ARCH_LED_COLOR,
    metalness: 0.12,
    roughness: 0.28,
    emissive: ARCH_LED_COLOR,
    emissiveIntensity: 0.95,
    toneMapped: false,
  });
  const ledAlarm = new THREE.MeshStandardMaterial({
    color: ARCH_LED_ALARM_COLOR,
    metalness: 0.12,
    roughness: 0.28,
    emissive: ARCH_LED_ALARM_COLOR,
    emissiveIntensity: 0.95,
    toneMapped: false,
  });
  const strokeAlarm = new THREE.MeshStandardMaterial({
    color: ARCH_STROKE_ALARM_COLOR,
    metalness: 0.2,
    roughness: 0.35,
    emissive: ARCH_STROKE_ALARM_COLOR,
    emissiveIntensity: ARCH_STROKE_EMISSIVE_INTENSITY,
    toneMapped: false,
  });
  const shadow = new THREE.MeshBasicMaterial({
    color: 0x050608,
    transparent: true,
    opacity: 0.28,
    depthWrite: false,
  });
  const ringCyan = createSelectionRingMaterial(ARCH_RING_CYAN);
  const ringAlarm = createSelectionRingMaterial(ARCH_RING_ALARM);
  return {
    faces: [side, side, top, top, front, top],
    textures: [frontAlbedo, sideAlbedo, topAlbedo],
    led,
    ledAlarm,
    strokeAlarm,
    shadow,
    ringCyan,
    ringAlarm,
  };
};

const addBoxPart = (
  group: THREE.Group,
  geometry: THREE.BoxGeometry,
  material: THREE.Material | THREE.Material[],
  scale: [number, number, number],
  position: [number, number, number],
  role: string,
  extra?: Record<string, unknown>,
) => {
  const mesh = new THREE.Mesh(geometry, material);
  mesh.scale.set(scale[0], scale[1], scale[2]);
  mesh.position.set(position[0], position[1], position[2]);
  mesh.userData.archRole = role;
  if (extra) Object.assign(mesh.userData, extra);
  group.add(mesh);
  return mesh;
};

/**
 * Full AABB wire: 12 edges on the hull. Half-width inset so bars sit on
 * the faces instead of floating off the front. Quiet racks never call this.
 */
const addRackAlarmStrokes = (
  group: THREE.Group,
  size: { width: number; height: number; depth: number },
  geos: RackKitGeometries,
  material: THREE.Material,
) => {
  const { width, height, depth } = size;
  const strokeW = ARCH_RACK_STROKE_WIDTH;
  const hx = width / 2 - strokeW / 2;
  const hy = height / 2 - strokeW / 2;
  const hz = depth / 2 - strokeW / 2;
  const extra = {
    alarmTint: true,
    restEmissiveIntensity: ARCH_STROKE_EMISSIVE_INTENSITY,
    strokeColor: ARCH_STROKE_ALARM_COLOR,
  };
  const add = (
    scale: [number, number, number],
    position: [number, number, number],
  ) => addBoxPart(group, geos.box, material, scale, position, 'rack-stroke', extra);

  add([width, strokeW, strokeW], [0, hy, hz]);
  add([width, strokeW, strokeW], [0, -hy, hz]);
  add([strokeW, height, strokeW], [-hx, 0, hz]);
  add([strokeW, height, strokeW], [hx, 0, hz]);
  add([width, strokeW, strokeW], [0, hy, -hz]);
  add([width, strokeW, strokeW], [0, -hy, -hz]);
  add([strokeW, height, strokeW], [-hx, 0, -hz]);
  add([strokeW, height, strokeW], [hx, 0, -hz]);
  add([strokeW, strokeW, depth], [-hx, hy, 0]);
  add([strokeW, strokeW, depth], [hx, hy, 0]);
  add([strokeW, strokeW, depth], [-hx, -hy, 0]);
  add([strokeW, strokeW, depth], [hx, -hy, 0]);
};

/**
 * Shared mapped-rack kit. One BoxGeometry hull, per-face albedo.
 * Hosts only: quiet 素柜 keep 3 cyan/teal front LEDs, never a stroke.
 * Alarming hosts swap those LEDs to red and add a 12-edge AABB hairline.
 * Chassis maps never paint red/cyan; texture LED pits are not lights.
 */
const addRackMeshes = (
  group: THREE.Group,
  node: Application3DArchitecturePlacedNode,
  geos: RackKitGeometries,
  materials: RackKitMaterials,
  alarming: boolean,
) => {
  const width = node.width;
  const height = node.height;
  const depth = node.depth;
  const frontZ = depth / 2;

  const chassis = addBoxPart(
    group,
    geos.box,
    materials.faces,
    [width, height, depth],
    [0, 0, 0],
    'rack',
    {
      alarmPaintsBody: false,
      sharedMaterial: true,
      mappedHull: true,
      faceCount: 6,
      chassisColor: ARCH_RACK_HULL_COLOR,
    },
  );
  chassis.userData.nodeKind = node.kind;

  const ledRadius = width * ARCH_RACK_LED_RADIUS_UV;
  const ledDepth = ledRadius * 0.5;
  const ledY = (ARCH_RACK_LED_UV_V - 0.5) * height;
  const ledZ = frontZ + ledDepth * 0.35;
  const ledMaterial = alarming ? materials.ledAlarm : materials.led;
  const ledColor = alarming ? ARCH_LED_ALARM_COLOR : ARCH_LED_COLOR;
  for (let index = 0; index < ARCH_RACK_LED_COUNT; index += 1) {
    const led = new THREE.Mesh(geos.led, ledMaterial);
    led.scale.set(ledRadius, ledDepth, ledRadius);
    led.rotation.x = Math.PI / 2;
    led.position.set((ARCH_RACK_LED_UV_U[index] - 0.5) * width, ledY, ledZ);
    led.userData.archRole = 'rack-led';
    led.userData.alarmTint = alarming;
    led.userData.ledIndex = index;
    led.userData.ledColor = ledColor;
    group.add(led);
  }

  if (alarming) {
    addRackAlarmStrokes(group, { width, height, depth }, geos, materials.strokeAlarm);
  }

  const shadow = new THREE.Mesh(geos.shadow, materials.shadow);
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.set(0, -height / 2 + 0.001, 0);
  shadow.scale.set(width * 1.18, depth * 1.18, 1);
  shadow.userData.archRole = 'rack-contact-shadow';
  group.add(shadow);

  const ringSize = Math.max(width, depth) * 1.85;
  const ring = new THREE.Mesh(geos.shadow, materials.ringCyan);
  ring.rotation.x = -Math.PI / 2;
  ring.position.set(0, -height / 2 + 0.002, 0);
  ring.scale.set(ringSize, ringSize, 1);
  ring.visible = false;
  ring.userData.archRole = 'rack-selection-ring';
  group.add(ring);
  group.userData.selectionRing = ring;
};

const roundedRectPath = (
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
) => {
  const r = Math.min(radius, width / 2, height / 2);
  context.moveTo(x + r, y);
  context.lineTo(x + width - r, y);
  context.quadraticCurveTo(x + width, y, x + width, y + r);
  context.lineTo(x + width, y + height - r);
  context.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  context.lineTo(x + r, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - r);
  context.lineTo(x, y + r);
  context.quadraticCurveTo(x, y, x + r, y);
  context.closePath();
};

const paintFilledLayer = (
  context: CanvasRenderingContext2D,
  draw: () => void,
  options?: {
    fill?: string;
    stroke?: string;
    glow?: string;
    blur?: number;
    lineWidth?: number;
    alpha?: number;
  },
) => {
  context.save();
  context.globalAlpha = options?.alpha ?? 1;
  context.fillStyle = options?.fill ?? ARCH_APP_CHIP_ICON_FILL;
  context.strokeStyle = options?.stroke ?? ARCH_APP_CHIP_ICON_STROKE;
  context.lineWidth = options?.lineWidth ?? 3.5;
  context.lineJoin = 'round';
  context.lineCap = 'round';
  context.shadowColor = options?.glow ?? ARCH_APP_CHIP_ICON_GLOW;
  context.shadowBlur = options?.blur ?? 16;
  context.beginPath();
  draw();
  context.fill();
  context.stroke();
  context.restore();
};

const drawAppChipIcon = (
  context: CanvasRenderingContext2D,
  kind: AppChipIconKind,
  cx: number,
  cy: number,
  size: number,
  alarming = false,
) => {
  const paint = architectureAppChipIconPaint(alarming);
  if (kind === 'layers') {
    const plateW = size * 0.7;
    const plateH = size * 0.2;
    const gap = size * 0.15;
    const originY = cy + gap * 1.15;
    for (let index = 0; index < 4; index += 1) {
      const y = originY - index * gap;
      const w = plateW - index * size * 0.035;
      const ox = index * size * 0.018;
      paintFilledLayer(context, () => {
        context.moveTo(cx + ox, y - plateH / 2);
        context.lineTo(cx + ox + w / 2, y);
        context.lineTo(cx + ox, y + plateH / 2);
        context.lineTo(cx + ox - w / 2, y);
        context.closePath();
      }, {
        fill: index > 1 ? paint.fillStrong : paint.fill,
        glow: paint.glow,
        stroke: paint.stroke,
        alpha: 0.42 + index * 0.12,
        blur: 12 + index * 2,
      });
    }
    return;
  }
  if (kind === 'hex-node') {
    const outer = size * 0.36;
    const nodeR = size * 0.07;
    paintFilledLayer(context, () => {
      context.arc(cx, cy, size * 0.4, 0, Math.PI * 2);
    }, {
      fill: paint.haze,
      stroke: paint.hazeStroke,
      glow: paint.glow,
      blur: 22,
      lineWidth: 2,
    });
    for (let index = 0; index < 6; index += 1) {
      const angle = (Math.PI / 3) * index - Math.PI / 6;
      const x = cx + Math.cos(angle) * outer;
      const y = cy + Math.sin(angle) * outer;
      paintFilledLayer(context, () => {
        context.moveTo(cx, cy);
        context.lineTo(x, y);
        context.lineTo(x + Math.cos(angle + Math.PI / 2) * 4, y + Math.sin(angle + Math.PI / 2) * 4);
        context.closePath();
      }, {
        fill: paint.fill,
        stroke: paint.stroke,
        glow: paint.glow,
        blur: 10,
        lineWidth: 4,
      });
      paintFilledLayer(context, () => {
        context.arc(x, y, nodeR, 0, Math.PI * 2);
      }, { fill: paint.fillStrong, glow: paint.glow, stroke: paint.stroke, blur: 12 });
    }
    paintFilledLayer(context, () => {
      context.arc(cx, cy, nodeR * 1.45, 0, Math.PI * 2);
    }, { fill: paint.fillStrong, glow: paint.glow, stroke: paint.stroke, blur: 14 });
    return;
  }
  if (kind === 'code-brackets') {
    for (let index = 2; index >= 0; index -= 1) {
      const inset = size * (0.34 + index * 0.03);
      paintFilledLayer(context, () => {
        roundedRectPath(
          context,
          cx - inset + index * 7,
          cy - inset - index * 6,
          inset * 2,
          inset * 2,
          size * 0.12,
        );
      }, {
        fill: index === 0 ? paint.fillStrong : paint.fill,
        glow: paint.glow,
        stroke: paint.stroke,
        alpha: 0.38 + (2 - index) * 0.18,
        blur: 14,
      });
    }
    context.save();
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillStyle = ARCH_APP_CHIP_TITLE_FILL;
    context.shadowColor = paint.glow;
    context.shadowBlur = 16;
    context.font = `700 ${Math.round(size * 0.36)}px ${CARD_GLASS.fontFamily}`;
    context.fillText('</>', cx, cy);
    context.restore();
    return;
  }
  if (kind === 'pulse-ring') {
    [0.4, 0.28, 0.09].forEach((ratio, index) => {
      paintFilledLayer(context, () => {
        context.arc(cx, cy, size * ratio, 0, Math.PI * 2);
      }, {
        fill: index === 2 ? paint.fillStrong : paint.haze,
        glow: paint.glow,
        stroke: paint.stroke,
        alpha: 0.4 + index * 0.2,
        blur: 14,
        lineWidth: index === 2 ? 2 : 3.5,
      });
    });
    return;
  }
  const cell = size * 0.22;
  const gap = size * 0.08;
  const origin = -cell - gap / 2;
  paintFilledLayer(context, () => {
    roundedRectPath(context, cx - size * 0.36 + 8, cy - size * 0.4, size * 0.72, size * 0.72, size * 0.12);
  }, {
    fill: paint.haze,
    glow: paint.glow,
    stroke: paint.stroke,
    alpha: 0.45,
    blur: 18,
  });
  for (let row = 0; row < 2; row += 1) {
    for (let col = 0; col < 2; col += 1) {
      const x = cx + origin + col * (cell + gap);
      const y = cy + origin + row * (cell + gap);
      paintFilledLayer(context, () => {
        roundedRectPath(context, x, y, cell, cell, cell * 0.22);
      }, { fill: paint.fillStrong, glow: paint.glow, stroke: paint.stroke, blur: 12 });
    }
  }
};

/**
 * Wall-card plate: bake `.app3d-wall-glass` / `::before` / `::after`.
 * One thin CSS stroke + inward inset only. No plane-rim halo.
 */
export const paintAppChipGlassPlate = (
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  options?: { alarming?: boolean },
) => {
  const radius = ARCH_APP_CHIP_CORNER * Math.min(width, height);
  const strokePx = architectureAppChipRimStrokePx(width);
  const halfStroke = strokePx / 2;
  const outerBorder = architectureAppChipWallBorder(options?.alarming === true);
  const inset = architectureAppChipWallInset(options?.alarming === true);
  const highlight = architectureAppChipWallHighlight(options?.alarming === true);
  const bloom = architectureAppChipWallInsetBloom(options?.alarming === true);
  const alarming = options?.alarming === true;

  context.save();
  context.beginPath();
  roundedRectPath(context, 0, 0, width, height, radius);
  context.clip();

  const body = context.createLinearGradient(0, 0, 0, height);
  body.addColorStop(0, ARCH_APP_CHIP_WALL_BODY_TOP);
  body.addColorStop(1, ARCH_APP_CHIP_WALL_BODY_BOTTOM);
  context.fillStyle = body;
  context.fillRect(0, 0, width, height);

  const wash = context.createLinearGradient(0, 0, width, height * 0.48);
  wash.addColorStop(0, highlight.wash);
  wash.addColorStop(0.48, 'rgba(0, 0, 0, 0)');
  context.fillStyle = wash;
  context.fillRect(0, 0, width, height);

  const topVeil = context.createLinearGradient(0, 0, 0, height * 0.14);
  topVeil.addColorStop(0, highlight.veil);
  topVeil.addColorStop(1, 'rgba(0, 0, 0, 0)');
  context.fillStyle = topVeil;
  context.fillRect(0, 0, width, height * 0.14);

  context.shadowOffsetX = 0;
  context.shadowOffsetY = 0;
  context.shadowBlur = 0;
  context.shadowColor = 'rgba(0, 0, 0, 0)';
  context.strokeStyle = inset.line;
  context.lineWidth = ARCH_APP_CHIP_WALL_INSET_LINE_PX;
  context.beginPath();
  roundedRectPath(
    context,
    ARCH_APP_CHIP_WALL_INSET_LINE_PX / 2,
    ARCH_APP_CHIP_WALL_INSET_LINE_PX / 2,
    width - ARCH_APP_CHIP_WALL_INSET_LINE_PX,
    height - ARCH_APP_CHIP_WALL_INSET_LINE_PX,
    Math.max(radius - ARCH_APP_CHIP_WALL_INSET_LINE_PX / 2, 0),
  );
  context.stroke();

  context.strokeStyle = inset.glow;
  context.lineWidth = bloom.glowWidth;
  context.shadowColor = inset.glow;
  context.shadowBlur = bloom.glowPx;
  context.beginPath();
  // Quiet pad equals glow stroke width (2px); it is inset, not a second lineWidth.
  const glowPad = alarming ? halfStroke : ARCH_APP_CHIP_WALL_INSET_GLOW_WIDTH;
  roundedRectPath(
    context,
    glowPad,
    glowPad,
    width - glowPad * 2,
    height - glowPad * 2,
    Math.max(radius - glowPad, 0),
  );
  context.stroke();

  context.strokeStyle = inset.deep;
  context.lineWidth = bloom.deepWidth;
  context.shadowColor = inset.deep;
  context.shadowBlur = bloom.deepPx;
  context.beginPath();
  // Quiet pad equals deep stroke width (3px); alarm pad stays on the outer edge.
  const deepPad = alarming ? halfStroke + 1 : ARCH_APP_CHIP_WALL_INSET_GLOW_DEEP_WIDTH;
  roundedRectPath(
    context,
    deepPad,
    deepPad,
    width - deepPad * 2,
    height - deepPad * 2,
    Math.max(radius - deepPad, 0),
  );
  context.stroke();

  context.shadowColor = inset.top;
  context.shadowBlur = ARCH_APP_CHIP_WALL_INSET_TOP_BLUR_PX;
  context.shadowOffsetY = ARCH_APP_CHIP_WALL_INSET_TOP_OFFSET_PX;
  context.fillStyle = inset.top;
  context.fillRect(2, 0, width - 4, 2);

  context.shadowOffsetX = 0;
  context.shadowOffsetY = 0;
  context.shadowBlur = 0;
  context.shadowColor = 'rgba(0, 0, 0, 0)';
  context.strokeStyle = outerBorder;
  context.lineWidth = strokePx;
  context.beginPath();
  roundedRectPath(
    context,
    halfStroke,
    halfStroke,
    width - strokePx,
    height - strokePx,
    Math.max(radius - halfStroke, 0),
  );
  context.stroke();

  const sheenLeft = width * ARCH_APP_CHIP_WALL_SHEEN_INSET_RATIO;
  const sheenRight = width * (1 - ARCH_APP_CHIP_WALL_SHEEN_INSET_RATIO);
  const sheen = context.createLinearGradient(sheenLeft, 0, sheenRight, 0);
  sheen.addColorStop(0, 'rgba(0, 0, 0, 0)');
  sheen.addColorStop(0.5, highlight.sheen);
  sheen.addColorStop(1, 'rgba(0, 0, 0, 0)');
  context.fillStyle = sheen;
  context.fillRect(
    sheenLeft,
    ARCH_APP_CHIP_WALL_SHEEN_TOP_PX,
    sheenRight - sheenLeft,
    ARCH_APP_CHIP_WALL_SHEEN_HEIGHT_PX,
  );

  context.restore();
};

export const paintAppChipFace = (
  node: Application3DArchitecturePlacedNode,
  icon: AppChipIconKind,
) =>
  paintCanvasTexture(ARCH_APP_CHIP_FACE_CANVAS_WIDTH, ARCH_APP_CHIP_FACE_CANVAS_HEIGHT, (context, canvas) => {
    const width = canvas.width;
    const height = canvas.height;
    const radius = ARCH_APP_CHIP_CORNER * Math.min(width, height);
    const alarming = applicationHasAlarm(node);
    paintAppChipGlassPlate(context, width, height, { alarming });
    context.save();
    context.beginPath();
    roundedRectPath(context, 2, 2, width - 4, height - 4, Math.max(radius - 2, 0));
    context.clip();
    const iconCy = height * 0.36;
    const iconSize = Math.min(width, height) * 0.5;
    drawAppChipIcon(context, icon, width / 2, iconCy, iconSize, alarming);
    const separator = architectureAppChipSeparator(alarming);
    context.save();
    context.strokeStyle = separator.stroke;
    context.lineWidth = 2;
    context.shadowColor = separator.shadow;
    context.shadowBlur = 8;
    context.beginPath();
    context.moveTo(width * 0.18, height * 0.66);
    context.lineTo(width * 0.82, height * 0.66);
    context.stroke();
    context.restore();
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.shadowColor = alarming ? ARCH_APP_CHIP_TITLE_SHADOW_ALARM : ARCH_APP_CHIP_TITLE_SHADOW;
    context.shadowBlur = 10;
    context.fillStyle = ARCH_APP_CHIP_TITLE_FILL;
    context.font = `${ARCH_APP_CHIP_TITLE_WEIGHT} ${ARCH_APP_CHIP_TITLE_SIZE}px ${CARD_GLASS.fontFamily}`;
    context.fillText(truncateAppChipName(node.name), width / 2, height * 0.82);
    context.restore();
  });

const roundedRectShape = (hw: number, hh: number, radius: number) => {
  const r = Math.min(radius, hw - 1e-4, hh - 1e-4);
  const shape = new THREE.Shape();
  shape.moveTo(-hw + r, -hh);
  shape.lineTo(hw - r, -hh);
  shape.quadraticCurveTo(hw, -hh, hw, -hh + r);
  shape.lineTo(hw, hh - r);
  shape.quadraticCurveTo(hw, hh, hw - r, hh);
  shape.lineTo(-hw + r, hh);
  shape.quadraticCurveTo(-hw, hh, -hw, hh - r);
  shape.lineTo(-hw, -hh + r);
  shape.quadraticCurveTo(-hw, -hh, -hw + r, -hh);
  return shape;
};

/** Solid thin slab. Visible border is the face-canvas stroke, not this mesh. */
export const createRoundedChipGeometry = () => {
  const bevel = ARCH_APP_CHIP_BEVEL;
  const hw = 0.5 - bevel;
  const hh = 0.5 - bevel;
  const radius = Math.min(ARCH_APP_CHIP_CORNER, 0.22);
  const geometry = new THREE.ExtrudeGeometry(roundedRectShape(hw, hh, radius), {
    depth: 1,
    bevelEnabled: true,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelOffset: 0,
    bevelSegments: 2,
    curveSegments: 10,
  });
  geometry.center();
  geometry.computeVertexNormals();
  return geometry;
};

interface AppChipMaterials {
  body: THREE.MeshStandardMaterial;
}

const createAppChipMaterials = (): AppChipMaterials => ({
  body: new THREE.MeshStandardMaterial({
    color: ARCH_APP_CHIP_GLASS_COLOR,
    transparent: true,
    opacity: ARCH_APP_CHIP_OPACITY,
    roughness: ARCH_APP_CHIP_ROUGHNESS,
    metalness: ARCH_APP_CHIP_METALNESS,
    depthWrite: false,
    side: THREE.FrontSide,
  }),
});

const stampChipFaceRimUserData = (
  object: THREE.Object3D,
  alarming: boolean,
) => {
  const inset = architectureAppChipWallInset(alarming);
  const highlight = architectureAppChipWallHighlight(alarming);
  object.userData.rimBaked = ARCH_APP_CHIP_RIM_BAKED;
  object.userData.rimStyle = ARCH_APP_CHIP_RIM_STYLE;
  object.userData.rimColor = architectureAppChipWallBorder(alarming);
  object.userData.rimInsetLine = inset.line;
  object.userData.rimInsetGlow = inset.glow;
  object.userData.rimSheen = highlight.sheen;
  object.userData.rimStrokeRatio = ARCH_APP_CHIP_WALL_STROKE_RATIO;
  object.userData.rimStrokePx = architectureAppChipRimStrokePx();
  object.userData.rimInsetOnly = true;
  object.userData.rimHasOuterBloom = false;
  object.userData.rimHasEdgeLines = ARCH_APP_CHIP_RIM_HAS_EDGE_LINES;
  object.userData.alarmPaintsRim = alarming;
  object.userData.alarmPaintsInset = alarming;
  object.userData.alarmPaintsHighlight = alarming;
  object.userData.separatorColor = architectureAppChipSeparator(alarming).stroke;
  object.userData.iconStroke = architectureAppChipIconPaint(alarming).stroke;
  object.userData.insetGlowPx = architectureAppChipWallInsetBloom(alarming).glowPx;
};

/**
 * Wall-card chip (Option B): dark plate + baked rim + icon + truncated name.
 * Alarming apps turn the outer wall-CSS stroke, inward inset, sheen, and
 * wash red. No solid body fill, LED, or rack stroke. Overhead name billboard
 * is added with host labels in createArchitectureTreeGroup.
 */
const addAppChipMeshes = (
  group: THREE.Group,
  node: Application3DArchitecturePlacedNode,
  geos: RackKitGeometries,
  chipGeo: THREE.BufferGeometry,
  materials: AppChipMaterials,
  rackMaterials: RackKitMaterials,
  disposables: Array<{ dispose: () => void }>,
) => {
  const width = node.width;
  const height = node.height;
  const depth = node.depth;
  const icon = appChipIconKind(node.id);
  const alarming = applicationHasAlarm(node);

  const body = new THREE.Mesh(chipGeo, materials.body);
  body.scale.set(
    width * ARCH_APP_CHIP_BODY_XY_SCALE,
    height * ARCH_APP_CHIP_BODY_XY_SCALE,
    depth,
  );
  body.renderOrder = ARCH_APP_CHIP_BODY_RENDER_ORDER;
  body.userData.archRole = 'app-chip';
  body.userData.nodeKind = node.kind;
  body.userData.chipIcon = icon;
  body.userData.alarmPaintsBody = false;
  body.userData.chipAlarming = alarming;
  body.userData.sharedMaterial = true;
  body.userData.chipBodyRole = 'side-thickness';
  body.userData.chipBodyOpen = false;
  body.userData.chipBodyQuiet = true;
  body.userData.hasOpaqueLid = false;
  body.userData.chipTransmission = ARCH_APP_CHIP_TRANSMISSION;
  group.add(body);

  const faceTexture = paintAppChipFace(node, icon);
  const faceMaterial = new THREE.MeshBasicMaterial({
    map: faceTexture,
    transparent: true,
    depthWrite: false,
    depthTest: true,
    side: THREE.FrontSide,
    toneMapped: false,
  });
  const face = new THREE.Mesh(geos.shadow, faceMaterial);
  face.position.set(0, 0, architectureAppChipFaceZ(depth));
  face.scale.set(width, height, 1);
  face.renderOrder = ARCH_APP_CHIP_FACE_RENDER_ORDER;
  face.userData.archRole = 'app-chip-face';
  face.userData.chipIcon = icon;
  face.userData.hasAlarmDot = false;
  face.userData.chipAlarming = alarming;
  face.userData.iconFilled = true;
  face.userData.hasSeparator = true;
  face.userData.hasGlassBody = true;
  face.userData.hasSheen = true;
  face.userData.chipSeeThrough = true;
  face.userData.plateAlpha = ARCH_APP_CHIP_PLATE_ALPHA;
  face.userData.faceMaterialKind = 'basic';
  face.userData.chipTitle = truncateAppChipName(node.name);
  stampChipFaceRimUserData(face, alarming);
  group.add(face);
  disposables.push(faceTexture, faceMaterial);

  const shadow = new THREE.Mesh(geos.shadow, rackMaterials.shadow);
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.set(0, -height / 2 + 0.001, 0);
  shadow.scale.set(width * 1.18, depth * 1.18, 1);
  shadow.userData.archRole = 'rack-contact-shadow';
  group.add(shadow);

  const ringSize = Math.max(width, depth) * 1.85;
  const ring = new THREE.Mesh(geos.shadow, rackMaterials.ringCyan);
  ring.rotation.x = -Math.PI / 2;
  ring.position.set(0, -height / 2 + 0.002, 0);
  ring.scale.set(ringSize, ringSize, 1);
  ring.visible = false;
  ring.userData.archRole = 'rack-selection-ring';
  group.add(ring);
  group.userData.selectionRing = ring;
  group.userData.chipIcon = icon;
  group.userData.yawBillboard = true;
};

export const createArchitectureEdgeCurve = (
  start: { x: number; y: number; z: number },
  end: { x: number; y: number; z: number },
) => {
  const from = new THREE.Vector3(start.x, start.y, start.z);
  const to = new THREE.Vector3(end.x, end.y, end.z);
  const dy = to.y - from.y;
  if (Math.abs(dy) > 0.05) {
    const p1 = new THREE.Vector3(from.x, from.y + dy * 0.4, from.z);
    const p2 = new THREE.Vector3(to.x, to.y - dy * 0.4, to.z);
    return new THREE.CatmullRomCurve3([from, p1, p2, to], false, 'centripetal');
  }
  const mid = from.clone().lerp(to, 0.5);
  mid.y += 0.12;
  return new THREE.CatmullRomCurve3([from, mid, to]);
};

const createPulseTrailMaterial = (
  color: number,
  trail: number,
  options?: { gain?: number; haloFalloff?: number; haloTrailPower?: number },
) => {
  const gain = options?.gain ?? 1;
  const haloFalloff = options?.haloFalloff ?? 0;
  const haloTrailPower = options?.haloTrailPower ?? 1;
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: true,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    toneMapped: false,
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uHead: { value: 0 },
      uTrail: { value: trail },
      uTailAlpha: { value: ARCH_PULSE_TAIL_ALPHA },
      uWrapOffset: { value: ARCH_PULSE_WRAP_OFFSET },
      uGain: { value: gain },
      uHaloFalloff: { value: haloFalloff },
      uHaloTrailPower: { value: haloTrailPower },
    },
    vertexShader: `
      varying float vPath;
      varying float vNdotV;
      void main() {
        vPath = uv.x;
        vec3 n = normalize(normalMatrix * normal);
        vec3 viewPos = (modelViewMatrix * vec4(position, 1.0)).xyz;
        vec3 v = normalize(-viewPos);
        vNdotV = abs(dot(n, v));
        gl_Position = projectionMatrix * vec4(viewPos, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      uniform float uHead;
      uniform float uTrail;
      uniform float uTailAlpha;
      uniform float uWrapOffset;
      uniform float uGain;
      uniform float uHaloFalloff;
      uniform float uHaloTrailPower;
      varying float vPath;
      varying float vNdotV;

      float trailBand(float head, float path, float trail, float tailAlpha) {
        float behind = head - path;
        if (behind < 0.0 || behind > trail + 1e-6) return 0.0;
        float t = clamp(behind / trail, 0.0, 1.0);
        return mix(1.0, tailAlpha, t);
      }

      void main() {
        float band = max(
          trailBand(uHead, vPath, uTrail, uTailAlpha),
          trailBand(uHead + uWrapOffset, vPath, uTrail, uTailAlpha)
        );
        float along = uHaloTrailPower > 1.0
          ? pow(max(band, 0.0), uHaloTrailPower)
          : band;
        float radial = uHaloFalloff > 0.0
          ? pow(clamp(vNdotV, 0.0, 1.0), uHaloFalloff)
          : 1.0;
        float intensity = along * radial * uGain;
        if (intensity < 0.004) discard;
        vec3 color = uColor * band;
        gl_FragColor = vec4(color, intensity);
      }
    `,
  });
};

const stampPulseUniforms = (mesh: THREE.Mesh | undefined, u: number, trail: number) => {
  if (!mesh) return;
  const material = mesh.material as THREE.ShaderMaterial;
  if (material.uniforms?.uHead) material.uniforms.uHead.value = u;
  if (material.uniforms?.uTrail) material.uniforms.uTrail.value = trail;
};

export const architecturePulseProgress = (
  timeSec: number,
  phase = 0,
  speed = ARCH_PULSE_SPEED,
) => ((phase + timeSec * speed) % 1 + 1) % 1;

export const updateArchitecturePulse = (
  pulse: Application3DArchitecturePulse,
  timeSec: number,
) => {
  const u = architecturePulseProgress(timeSec, pulse.phase, pulse.speed);
  const headB = architecturePulseCompanionHead(u);
  stampPulseUniforms(pulse.mesh, u, pulse.trail);
  stampPulseUniforms(pulse.halo, u, pulse.trail);
  pulse.curve.getPointAt(u, PULSE_POINT);
  pulse.mesh.userData.pulseU = u;
  pulse.mesh.userData.pulseHeadB = headB;
  pulse.mesh.userData.pulseTrail = pulse.trail;
  pulse.mesh.userData.pulseStyle = ARCH_PULSE_STYLE;
  if (pulse.halo) {
    pulse.halo.userData.pulseU = u;
    pulse.halo.userData.pulseHeadB = headB;
    pulse.halo.userData.pulseTrail = pulse.trail;
    pulse.halo.userData.pulseStyle = ARCH_PULSE_STYLE;
  }
  return { u, headB, point: PULSE_POINT.clone() };
};

const createTubeGroup = (
  edge: Application3DArchitecturePlacedEdge,
  pulseColor: number,
  alarming: boolean,
  stripe: THREE.CanvasTexture,
) => {
  const curve = createArchitectureEdgeCurve(edge.start, edge.end);
  const radius = architectureTubeRadius(edge.intraPlane);
  const pathLength = curve.getLength();
  const trail = architecturePulseTrailForLength(pathLength);
  const tubeStyle = architectureTubeStyle(alarming);
  const geometry = new THREE.TubeGeometry(
    curve,
    ARCH_TUBE_TUBULAR_SEGMENTS,
    radius,
    ARCH_TUBE_RADIAL_SEGMENTS,
    false,
  );
  const map = stripe.clone();
  map.wrapS = THREE.RepeatWrapping;
  map.wrapT = THREE.RepeatWrapping;
  map.repeat.set(4, 1);
  map.needsUpdate = true;
  const material = new THREE.MeshStandardMaterial({
    color: tubeStyle.color,
    map,
    metalness: 0.08,
    roughness: 0.62,
    emissive: tubeStyle.color,
    emissiveIntensity: tubeStyle.emissiveIntensity,
    transparent: true,
    opacity: tubeStyle.opacity,
  });
  const mesh = new THREE.Mesh(geometry, material);
  const role = edge.intraPlane ? 'intra-plane-tube' : 'inter-plane-tube';
  mesh.userData.archRole = role;
  mesh.userData.scrollMap = map;
  mesh.userData.tubeRadius = radius;
  mesh.userData.tubeTubularSegments = ARCH_TUBE_TUBULAR_SEGMENTS;
  mesh.userData.tubeRadialSegments = ARCH_TUBE_RADIAL_SEGMENTS;
  mesh.userData.tubeOpacity = tubeStyle.opacity;
  mesh.userData.tubeEmissiveIntensity = tubeStyle.emissiveIntensity;
  mesh.userData.inGlowLayer = ARCH_TUBE_IN_GLOW_LAYER;
  const pulseGeometry = new THREE.TubeGeometry(
    curve,
    ARCH_PULSE_TUBULAR_SEGMENTS,
    radius,
    ARCH_PULSE_RADIAL_SEGMENTS,
    false,
  );
  const pulseMaterial = createPulseTrailMaterial(pulseColor, trail);
  const pulseMesh = new THREE.Mesh(pulseGeometry, pulseMaterial);
  pulseMesh.visible = false;
  const haloRadius = architecturePulseHaloRadius(radius);
  const haloGeometry = new THREE.TubeGeometry(
    curve,
    ARCH_PULSE_TUBULAR_SEGMENTS,
    haloRadius,
    ARCH_PULSE_RADIAL_SEGMENTS,
    false,
  );
  const haloMaterial = createPulseTrailMaterial(pulseColor, trail, {
    gain: ARCH_PULSE_HALO_INTENSITY,
    haloFalloff: ARCH_PULSE_HALO_FALLOFF,
    haloTrailPower: ARCH_PULSE_HALO_TRAIL_POWER,
  });
  const haloMesh = new THREE.Mesh(haloGeometry, haloMaterial);
  haloMesh.visible = false;
  const stampPulseMesh = (
    target: THREE.Mesh,
    archRole: 'edge-pulse' | 'edge-pulse-halo',
    layerRadius: number,
    renderOrder: number,
  ) => {
    target.renderOrder = renderOrder;
    target.userData.archRole = archRole;
    target.userData.pulseLayer = archRole === 'edge-pulse' ? 'core' : 'halo';
    target.userData.pulseStyle = ARCH_PULSE_STYLE;
    target.userData.pulseTrail = trail;
    target.userData.pulseWorldLength = ARCH_PULSE_WORLD_LENGTH;
    target.userData.pulsePathLength = pathLength;
    target.userData.pulseWrap = 'head-plus-one';
    target.userData.pulseWrapOffset = ARCH_PULSE_WRAP_OFFSET;
    target.userData.pulseTailAlpha = ARCH_PULSE_TAIL_ALPHA;
    target.userData.pulseRgbScale = ARCH_PULSE_RGB_SCALE;
    target.userData.pulseRadius = radius;
    target.userData.pulseTubularSegments = ARCH_PULSE_TUBULAR_SEGMENTS;
    target.userData.pulseRadialSegments = ARCH_PULSE_RADIAL_SEGMENTS;
    target.userData.pulseHaloRadius = haloRadius;
    target.userData.pulseHaloIntensity = ARCH_PULSE_HALO_INTENSITY;
    target.userData.pulseHaloFalloff = ARCH_PULSE_HALO_FALLOFF;
    target.userData.pulseHaloTrailPower = ARCH_PULSE_HALO_TRAIL_POWER;
    target.userData.pulseColor = pulseColor;
    target.userData.pulseBlending = 'additive';
    target.userData.hasGradientTrail = true;
    target.userData.hasPulseHalo = true;
    if (archRole === 'edge-pulse-halo') {
      target.userData.pulseHalo = true;
      target.userData.layerRadius = layerRadius;
    }
  };
  stampPulseMesh(pulseMesh, 'edge-pulse', radius, 2);
  stampPulseMesh(haloMesh, 'edge-pulse-halo', haloRadius, 1);
  const pulse: Application3DArchitecturePulse = {
    mesh: pulseMesh,
    halo: haloMesh,
    curve,
    phase: 0,
    speed: ARCH_PULSE_SPEED,
    trail,
  };
  updateArchitecturePulse(pulse, 0);
  const group = new THREE.Group();
  group.userData.archRole = role;
  group.userData.edgeId = edge.id;
  group.userData.sourceId = edge.sourceId;
  group.userData.targetId = edge.targetId;
  group.userData.alarming = alarming;
  group.userData.defaultOpacity = tubeStyle.opacity;
  group.userData.defaultEmissiveIntensity = tubeStyle.emissiveIntensity;
  group.userData.baseMesh = mesh;
  group.userData.pulseMesh = pulseMesh;
  group.userData.haloMesh = haloMesh;
  group.add(mesh, haloMesh, pulseMesh);
  return { group, mesh, pulse, scrollMap: map };
};

export const createArchitectureTreeGroup = (
  data: Application3DArchitectureData,
  translate: Application3DTranslate,
): Application3DArchitectureView => {
  const layout = layoutApplication3DArchitecture(data);
  const group = new THREE.Group();
  group.name = 'application3d-architecture';
  const planeGroups: THREE.Group[] = [];
  const nodeGroups = new Map<string, THREE.Group>();
  const nodeLabels = new Map<string, THREE.Mesh>();
  const intraPlaneTubes: THREE.Object3D[] = [];
  const interPlaneTubes: THREE.Object3D[] = [];
  const pulses: Application3DArchitecturePulse[] = [];
  const nodesById = new Map(layout.nodes.map((node) => [node.id, node]));
  const disposables: Array<{ dispose: () => void }> = [];
  const scrollMaps: THREE.CanvasTexture[] = [];

  const keyLight = new THREE.DirectionalLight(0xc8dcec, 0.95);
  keyLight.position.set(14, 32, 20);
  const fillLight = new THREE.AmbientLight(0x6a90a8, 0.62);
  group.add(keyLight, fillLight);

  const chassisGeo = new THREE.BoxGeometry(1, 1, 1);
  const ledGeo = new THREE.CylinderGeometry(1, 1, 1, 12);
  const planeGeo = new THREE.PlaneGeometry(1, 1);
  const rackGeos: RackKitGeometries = { box: chassisGeo, led: ledGeo, shadow: planeGeo };
  const rackMats = createRackMaterials();
  const chipGeo = createRoundedChipGeometry();
  const chipMats = createAppChipMaterials();
  disposables.push(
    chassisGeo,
    ledGeo,
    planeGeo,
    chipGeo,
    chipMats.body,
    ...new Set(rackMats.faces),
    ...rackMats.textures,
    rackMats.led,
    rackMats.ledAlarm,
    rackMats.strokeAlarm,
    rackMats.shadow,
    rackMats.ringCyan,
    rackMats.ringAlarm,
  );

  const stripe = paintTubeStripe();
  disposables.push(stripe);

  const billboardMeshes: THREE.Object3D[] = [];
  let pulseElapsed = 0;

  layout.planes.forEach((plane) => {
    const planeGroup = new THREE.Group();
    planeGroup.name = `architecture-plane-${plane.kind}`;
    planeGroup.userData.archRole = 'plane';
    planeGroup.userData.planeKind = plane.kind;
    planeGroup.userData.planeOrientation = ARCH_PLANE_ORIENTATION;
    planeGroup.userData.planeShape = plane.shape;
    planeGroup.userData.restPosition = new THREE.Vector3(plane.x, plane.y, plane.z);
    const isFrustum = plane.shape === 'frustum';
    const veneerMaterial = createPlaneVeneerMaterial();
    const veneer = new THREE.Mesh(planeGeo, veneerMaterial);
    veneer.rotation.x = ARCH_PLANE_ROTATION_X;
    veneer.scale.set(plane.width, plane.depth, 1);
    if (isFrustum) veneer.position.y = ARCH_VENEER_LIFT;
    stampVeneerUserData(veneer, plane, isFrustum ? 'plane-veneer' : 'plane-mesh');
    veneer.userData.frustumHeight = isFrustum ? ARCH_FRUSTUM_HEIGHT : 0;
    veneer.userData.frustumTaper = isFrustum ? ARCH_FRUSTUM_TAPER : 1;
    if (isFrustum) {
      const sideMaterial = createPlaneSideMaterial();
      const sides = new THREE.Mesh(
        createTrapezoidFrustumGeometry(
          plane.width,
          plane.depth,
          plane.width * plane.taper,
          plane.depth * plane.taper,
          plane.thickness,
          { includeTop: false },
        ),
        sideMaterial,
      );
      // Geometry is Y-up; shift so the TOP lip is the platform at group y=0.
      sides.position.y = -plane.thickness / 2;
      sides.rotation.x = 0;
      sides.userData.archRole = 'plane-mesh';
      sides.userData.planeSkin = 'veneer-side';
      sides.userData.planeKind = plane.kind;
      sides.userData.planeOrientation = ARCH_PLANE_ORIENTATION;
      sides.userData.planeShape = plane.shape;
      sides.userData.planeWidth = plane.width;
      sides.userData.planeDepth = plane.depth;
      sides.userData.planeHeight = plane.height;
      sides.userData.planeThickness = plane.thickness;
      sides.userData.frustumHeight = ARCH_FRUSTUM_HEIGHT;
      sides.userData.frustumTaper = ARCH_FRUSTUM_TAPER;
      sides.userData.hasRim = false;
      sides.userData.hasStroke = ARCH_PLANE_SIDE_HAS_STROKE;
      sides.userData.matchesTopHue = ARCH_PLANE_SIDE_MATCHES_TOP_HUE;
      sides.userData.restOpacity = ARCH_PLANE_SIDE_OPACITY;
      sides.userData.restEmissiveIntensity = ARCH_PLANE_SIDE_EMISSIVE_INTENSITY;
      planeGroup.add(sides);
      disposables.push(sides.geometry, sideMaterial);
    }
    planeGroup.add(veneer);
    const rimMaterial = createPlaneRimMaterial(plane.width, plane.depth);
    const rimMesh = new THREE.Mesh(planeGeo, rimMaterial);
    rimMesh.position.copy(veneer.position);
    rimMesh.rotation.copy(veneer.rotation);
    rimMesh.scale.copy(veneer.scale);
    stampRimUserData(rimMesh);
    rimMesh.userData.planeKind = plane.kind;
    rimMesh.userData.planeShape = plane.shape;
    planeGroup.add(rimMesh);
    const titleTexture = paintPlaneTitle(plane, translate);
    const titleMaterial = new THREE.MeshBasicMaterial({
      map: titleTexture,
      transparent: true,
      depthWrite: false,
      toneMapped: false,
    });
    const title = new THREE.Mesh(
      new THREE.PlaneGeometry(PLANE_TITLE_WIDTH, PLANE_TITLE_HEIGHT),
      titleMaterial,
    );
    title.position.set(
      architectureTitleLocalX(plane.width),
      0.38,
      architectureTitleLocalZ(plane.depth),
    );
    title.userData.archRole = 'plane-title';
    title.userData.billboard = ARCH_LABEL_BILLBOARD;
    title.userData.planeTitleSide = ARCH_PLANE_TITLE_SIDE;
    title.userData.titleHasBackground = false;
    title.userData.titleHasArrow = false;
    title.userData.titleFill = ARCH_TITLE_FILL;
    title.userData.titleGlow = ARCH_TITLE_SHADOW_COLOR;
    title.userData.titleGlowBlur = ARCH_TITLE_SHADOW_BLUR;
    title.userData.planeTitle = formatArchitecturePlaneTitle(
      translate(plane.titleKey, plane.titleFallback),
    );
    planeGroup.add(title);
    billboardMeshes.push(title);
    planeGroup.position.copy(planeGroup.userData.restPosition as THREE.Vector3);
    group.add(planeGroup);
    planeGroups.push(planeGroup);
    disposables.push(
      veneerMaterial,
      rimMaterial,
      titleTexture,
      title.geometry,
      titleMaterial,
    );
  });

  layout.nodes.forEach((node) => {
    const nodeGroup = new THREE.Group();
    nodeGroup.userData.archRole = 'rack-root';
    nodeGroup.userData.nodeId = node.id;
    nodeGroup.userData.nodeKind = node.kind;
    const alarming = hostHasAlarm(node);
    nodeGroup.userData.alarming = alarming;
    nodeGroup.userData.plainMetal = !alarming;
    if (node.kind === 'application') {
      addAppChipMeshes(nodeGroup, node, rackGeos, chipGeo, chipMats, rackMats, disposables);
    } else {
      addRackMeshes(nodeGroup, node, rackGeos, rackMats, alarming);
    }
    // Y-up node sitting ON the horizontal XZ platform — do not pitch the body.
    nodeGroup.rotation.x = 0;
    if (node.kind === 'host' || node.kind === 'application') {
      const texture = paintNodeLabel(node);
      const labelMaterial = new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        depthWrite: false,
        toneMapped: false,
      });
      const label = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), labelMaterial);
      const labelScale = architectureNodeLabelScale();
      label.userData.labelScale = labelScale;
      label.userData.archRole = 'node-label';
      label.userData.billboard = ARCH_LABEL_BILLBOARD;
      label.userData.labelHasBackground = ARCH_LABEL_HAS_BACKGROUND;
      label.userData.labelFill = ARCH_LABEL_FILL;
      label.scale.set(0, 0, 1);
      label.position.set(0, node.height / 2 + 0.28, 0);
      nodeGroup.add(label);
      billboardMeshes.push(label);
      nodeLabels.set(node.id, label);
      disposables.push(texture, label.geometry, labelMaterial);
    }
    nodeGroup.position.set(node.x, node.y + ARCH_RACK_LIFT, node.z);
    group.add(nodeGroup);
    nodeGroups.set(node.id, nodeGroup);
  });

  layout.edges.forEach((edge) => {
    const target = nodesById.get(edge.targetId);
    const built = createTubeGroup(
      edge,
      architectureEdgeColor(target),
      hostHasAlarm(target),
      stripe,
    );
    group.add(built.group);
    (edge.intraPlane ? intraPlaneTubes : interPlaneTubes).push(built.group);
    pulses.push(built.pulse);
    scrollMaps.push(built.scrollMap);
    disposables.push(
      built.mesh.geometry,
      built.mesh.material as THREE.Material,
      built.pulse.mesh.geometry,
      built.pulse.mesh.material as THREE.Material,
      built.scrollMap,
    );
    if (built.pulse.halo) {
      disposables.push(
        built.pulse.halo.geometry,
        built.pulse.halo.material as THREE.Material,
      );
    }
  });

  const rankedNodeIds = layout.nodes.map((node) => node.id);

  const setHoveredNode = (hoveredId: string | null) => {
    if (!hoveredId) {
      interPlaneTubes.forEach((tubeGroup) => {
        tubeGroup.visible = true;
        const mesh = (tubeGroup.userData.baseMesh ?? tubeGroup.children[0]) as THREE.Mesh | undefined;
        if (mesh && 'material' in mesh) {
          const mat = mesh.material as THREE.MeshStandardMaterial;
          mat.opacity = Number(tubeGroup.userData.defaultOpacity ?? ARCH_TUBE_OPACITY);
          mat.emissiveIntensity = Number(
            tubeGroup.userData.defaultEmissiveIntensity ?? ARCH_TUBE_EMISSIVE_INTENSITY,
          );
        }
        const pulse = tubeGroup.userData.pulseMesh as THREE.Mesh | undefined;
        if (pulse) pulse.visible = false;
        const halo = tubeGroup.userData.haloMesh as THREE.Mesh | undefined;
        if (halo) halo.visible = false;
      });

      nodeGroups.forEach((nodeGroup) => {
        const ring = nodeGroup.userData.selectionRing as THREE.Mesh | undefined;
        if (ring) ring.visible = false;
        nodeGroup.scale.set(1, 1, 1);
      });

      nodeLabels.forEach((label) => {
        const mat = label.material as THREE.MeshBasicMaterial;
        mat.opacity = 1.0;
        const targetScale = label.userData.labelScale as THREE.Vector3 | undefined;
        if (targetScale) {
          label.scale.set(targetScale.x, targetScale.y, 1);
        }
      });
      return;
    }

    const hoveredNode = nodesById.get(hoveredId);
    if (!hoveredNode) return;

    const matchingEdgeIds = new Set<string>();
    const connectedNodeIds = new Set<string>([hoveredId]);

    layout.edges.forEach((edge) => {
      if (hoveredNode.kind === 'application' && edge.sourceId === hoveredId) {
        matchingEdgeIds.add(edge.id);
        connectedNodeIds.add(edge.targetId);
      } else if (hoveredNode.kind === 'host' && edge.targetId === hoveredId) {
        matchingEdgeIds.add(edge.id);
        connectedNodeIds.add(edge.sourceId);
      }
    });

    interPlaneTubes.forEach((tubeGroup) => {
      const mesh = (tubeGroup.userData.baseMesh ?? tubeGroup.children[0]) as THREE.Mesh | undefined;
      const pulse = tubeGroup.userData.pulseMesh as THREE.Mesh | undefined;
      const halo = tubeGroup.userData.haloMesh as THREE.Mesh | undefined;
      const isMatch = matchingEdgeIds.has(tubeGroup.userData.edgeId as string);

      tubeGroup.visible = isMatch;
      if (isMatch) {
        if (mesh && 'material' in mesh) {
          const mat = mesh.material as THREE.MeshStandardMaterial;
          mat.opacity = 0.95;
          mat.emissiveIntensity = 0.85;
        }
        if (pulse) pulse.visible = true;
        if (halo) halo.visible = true;
      } else {
        if (pulse) pulse.visible = false;
        if (halo) halo.visible = false;
      }
    });

    nodeGroups.forEach((nodeGroup, nodeId) => {
      const isConnected = connectedNodeIds.has(nodeId);
      const ring = nodeGroup.userData.selectionRing as THREE.Mesh | undefined;
      const node = nodesById.get(nodeId);
      const isAlarm = architectureSelectionRingAlarming(node);

      if (ring) {
        if (isConnected) {
          ring.visible = true;
          ring.material = isAlarm ? rackMats.ringAlarm : rackMats.ringCyan;
        } else {
          ring.visible = false;
        }
      }

      nodeGroup.scale.set(1, 1, 1);
    });

    nodeLabels.forEach((label, nodeId) => {
      const mat = label.material as THREE.MeshBasicMaterial;
      const targetScale = label.userData.labelScale as THREE.Vector3 | undefined;
      const isConnected = connectedNodeIds.has(nodeId);
      mat.opacity = isConnected ? 1.0 : 0.2;
      if (targetScale) {
        label.scale.set(targetScale.x, targetScale.y, 1);
      }
    });
  };

  return {
    group,
    layout,
    planeGroups,
    nodeGroups,
    nodeLabels,
    intraPlaneTubes,
    interPlaneTubes,
    pulses,
    billboardMeshes,
    rankedNodeIds,
    setHoveredNode,
    tick: (dt: number, camera?: THREE.Camera) => {
      scrollMaps.forEach((map) => {
        map.offset.x = (map.offset.x + dt * TUBE_SCROLL_SPEED) % 1;
      });
      pulseElapsed += dt;
      pulses.forEach((pulse) => {
        updateArchitecturePulse(pulse, pulseElapsed);
      });
      if (!camera) return;
      nodeGroups.forEach((nodeGroup) => {
        if (nodeGroup.userData.nodeKind !== 'application') return;
        yawObjectAroundYToCamera(nodeGroup, camera);
      });
      billboardMeshes.forEach((mesh) => {
        mesh.lookAt(camera.position);
      });
    },
    dispose: () => {
      group.removeFromParent();
      disposables.forEach((item) => item.dispose());
      nodeGroups.clear();
      nodeLabels.clear();
      planeGroups.length = 0;
      intraPlaneTubes.length = 0;
      interPlaneTubes.length = 0;
      pulses.length = 0;
      billboardMeshes.length = 0;
    },
  };
};
