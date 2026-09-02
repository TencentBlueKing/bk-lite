import type {
  Application3DArchitectureData,
  Application3DArchitectureEdge,
  Application3DArchitectureKind,
  Application3DArchitectureNode,
  Application3DHealth,
} from '@/app/ops-analysis/types/sceneWidget';
import { APPLICATION3D_CAMERA_FOV } from './application3DLayout';
import { ARCHITECTURE_MOTION, ARCHITECTURE_PLANE_COUNT } from './application3DMotion';

/**
 * Architecture-only rack sizes. One cabinet family, two scales, sitting ON
 * the horizontal platforms — they do not define the plane AABB.
 * Host is the taller/slimmer 3U-like member; application is shorter and
 * sturdier. Both stay racks (not wall cards).
 */
export const ARCH_NODE_SIZE: Record<
  Application3DArchitectureKind,
  { width: number; height: number; depth: number }
> = {
  system: { width: 0.48, height: 0.76, depth: 0.36 },
  application: { width: 0.42, height: 0.54, depth: 0.34 },
  host: { width: 0.32, height: 0.72, depth: 0.26 },
};

/** Previous cabinet size — style pass bumps one step so they read as racks. */
export const ARCH_PREVIOUS_NODE_SIZE = {
  application: { width: 0.32, height: 0.52, depth: 0.26 },
  host: { width: 0.26, height: 0.42, depth: 0.22 },
} as const;

/** Inverted family we flipped: application used to be taller than host. */
export const ARCH_INVERTED_NODE_SIZE = {
  application: { width: 0.42, height: 0.68, depth: 0.34 },
  host: { width: 0.34, height: 0.55, depth: 0.28 },
} as const;

/**
 * Center-to-center Y gap between the two platform surfaces.
 * App-wall-screen used planeGap=3; two floors stay distinct without the
 * old 4.2 air gap that made the stack feel sparse.
 */
export const ARCH_PLANE_GAP = 3.2;

/**
 * World Y of the lower (应用) platform surface (top face of the frustum).
 * Both boards are horizontal XZ, same orientation as the grid floor, stacked
 * along +Y. Lower / closer to the floor = 应用; upper = 主机. No 系统 plane.
 */
export const ARCH_STACK_ORIGIN = 1.8;

export const ARCH_PLANE_Y = {
  application: ARCH_STACK_ORIGIN,
  host: ARCH_STACK_ORIGIN + ARCH_PLANE_GAP,
} as const;

export type Application3DArchitecturePlaneKind = keyof typeof ARCH_PLANE_Y;
export type Application3DArchitecturePlaneShape = 'frustum' | 'plane';

/** Same tilt as the grid floor: PlaneGeometry XY → world XZ. */
export const ARCH_PLANE_ROTATION_X = -Math.PI / 2;
export const ARCH_PLANE_ORIENTATION = 'xz' as const;

/**
 * Previous fill-the-page cinematic glass (≈27.6×19.2). The locked landed
 * frame uses a much tighter world size so both slabs sit in the middle.
 */
export const ARCH_PREVIOUS_FILL_PLANE_WIDTH = 27.6;
export const ARCH_PREVIOUS_FILL_PLANE_DEPTH = 19.2;

/**
 * Compact XZ platforms — two distinct slabs, not a viewport-filling sheet.
 * Slightly roomier than the first landed pass so small cabinets have air,
 * still well under the old 27.6×19.2 fill-the-page glass.
 */
export const ARCH_PLANE_WORLD_WIDTH = 12.8;
export const ARCH_PLANE_WORLD_DEPTH = 9.2;
/** Local height of the unrotated PlaneGeometry; equals world Z after −π/2. */
export const ARCH_PLANE_WORLD_HEIGHT = ARCH_PLANE_WORLD_DEPTH;
/** Hairline glass for the TOP host board only. */
export const ARCH_PLANE_THICKNESS = 0.01;
/**
 * Lampshade frustum height. WeOps reference ≈9 on a 28-wide top (≈1/3);
 * match that silhouette on our Y-up stack.
 */
export const ARCH_FRUSTUM_HEIGHT = 4.1;
/**
 * Bottom face / top face. WeOps lampshade is ~3×4 on a ~28×21 top
 * (≈10–15% of top width), not a 70% thick slab.
 */
export const ARCH_FRUSTUM_TAPER = 0.12;
export const ARCH_PLANE_MIN_DEPTH = ARCH_PLANE_WORLD_DEPTH;
export const ARCH_PLANE_MIN_HEIGHT = ARCH_PLANE_WORLD_HEIGHT;
export const ARCH_PLANE_MIN_WIDTH = ARCH_PLANE_WORLD_WIDTH;
export const ARCH_PLANE_PAD = 2.2;
/**
 * Card-veneer fill on TOP faces only. Darker blue you can actually see,
 * still see-through. Opaque plastic would be ≥0.7.
 */
export const ARCH_PLANE_OPACITY = 0.34;
export const ARCH_PLANE_EMISSIVE_INTENSITY = 0.38;
/**
 * Frustum sides + bottom: SAME hue as the top veneer, slightly more
 * see-through, no rim/stroke. 0.1 cyan glass disappeared in the landed pose.
 */
export const ARCH_PLANE_SIDE_OPACITY = 0.22;
export const ARCH_PLANE_SIDE_EMISSIVE_INTENSITY = 0.3;
export const ARCH_PLANE_SIDE_HAS_STROKE = false;
export const ARCH_PLANE_SIDE_MATCHES_TOP_HUE = true;
/**
 * Wall-card face language on the TOP veneer, in WORLD units — not UV %.
 * CSS (unchanged): `border: 1.5px solid rgba(100, 162, 198, 0.74)` plus
 * inset rim shadows (`1px` / `10px` / `18px`) that hug the edge.
 * At landed FOV 34° / radius ~12 / ~1080px, 1.5px ≈ 0.012 and 18px ≈ 0.12.
 * A 12-unit plane with 2% UV (0.022) is a 0.26-unit fat band; these world
 * widths stay hairline + tight inner glow regardless of board size.
 * Normal blending — additive neon is what made the previous halo look fat.
 */
export const ARCH_PLANE_RIM_COLOR = 0x64a2c6;
export const ARCH_PLANE_RIM_STROKE_OPACITY = 0.74;
export const ARCH_PLANE_RIM_OPACITY = 0.4;
export const ARCH_PLANE_RIM_STROKE_WORLD = 0.012;
export const ARCH_PLANE_RIM_HALO_WORLD = 0.12;
export const ARCH_PLANE_RIM_BLENDING = 'normal' as const;
/** UV span on the reference 12.8-wide plane — derived, not the source of truth. */
export const ARCH_PLANE_RIM_INNER = ARCH_PLANE_RIM_STROKE_WORLD / ARCH_PLANE_WORLD_WIDTH;
export const ARCH_PLANE_RIM_OUTER = ARCH_PLANE_RIM_HALO_WORLD / ARCH_PLANE_WORLD_WIDTH;
/** > 1 piles the glow at the rim so the board face stays dark. */
export const ARCH_PLANE_RIM_FALLOFF = 1.65;
export const ARCH_PLANE_RIM_HAS_EDGE_LINES = false;
export const ARCH_PLANE_DEPTH_WRITE = false;
export const ARCH_PLANE_COUNT = ARCHITECTURE_PLANE_COUNT;
/** Center-to-center grid pitch (~2 on the 28-wide WeOps board). */
export const ARCH_GRID_PITCH = 1.85;
export const ARCH_TUBE_RADIUS_INTER = 0.01;
export const ARCH_TUBE_RADIUS_INTRA = 0.015;
/**
 * Idle filament: dim cyan→navy, excluded from glow. The LONG pulse band
 * is what you see. Alarm stays a muted red filament; pulse stays bright.
 */
export const ARCH_TUBE_COLOR = 0x16384c;
export const ARCH_TUBE_ALARM_COLOR = 0x4a2428;
export const ARCH_TUBE_OPACITY = 0.22;
export const ARCH_TUBE_ALARM_OPACITY = 0.28;
export const ARCH_TUBE_EMISSIVE_INTENSITY = 0.1;
export const ARCH_TUBE_ALARM_EMISSIVE_INTENSITY = 0.14;
export const ARCH_TUBE_IN_GLOW_LAYER = false;
/** Idle filament stays a cheap 8-gon; only the glowing band needs smoothness. */
export const ARCH_TUBE_TUBULAR_SEGMENTS = 28;
export const ARCH_TUBE_RADIAL_SEGMENTS = 8;

export const architectureTubeRadius = (intraPlane: boolean) =>
  intraPlane ? ARCH_TUBE_RADIUS_INTRA : ARCH_TUBE_RADIUS_INTER;

export const architectureTubeStyle = (alarming: boolean) =>
  (alarming
    ? {
      color: ARCH_TUBE_ALARM_COLOR,
      opacity: ARCH_TUBE_ALARM_OPACITY,
      emissiveIntensity: ARCH_TUBE_ALARM_EMISSIVE_INTENSITY,
    }
    : {
      color: ARCH_TUBE_COLOR,
      opacity: ARCH_TUBE_OPACITY,
      emissiveIntensity: ARCH_TUBE_EMISSIVE_INTENSITY,
    });
/**
 * Long soft gradient band on the thin filament (WeOps createSegment feel).
 * WORLD LENGTH ~4 slides along the path; on a short inter-layer curve that
 * would cover the whole tube, trail is capped so it stays a band.
 * Head opaque, tail near 0 — additive 1.0→0.5 on black still reads as a
 * solid bar. Companion at head+1 wraps the seam: the next band starts
 * from the fading tail. RGB follows the band (no 0.45 floor). Halo
 * along-path falls faster than the core so the smear does not relight
 * the faded tail. Additive/glow is on this segment only.
 *
 * Core stays as thin as the idle filament. A pulse-local additive halo
 * (not UnrealBloomPass) smears the bright head onto 2–3 neighbouring
 * pixels so the comet reads at the landed camera. Idle tubes stay
 * out of any glow layer.
 */
export const ARCH_PULSE_WORLD_LENGTH = 4;
export const ARCH_PULSE_TRAIL_MAX = 0.68;
/** Near 0 so additive blending still reads a dark tail, not a 0.5 brick. */
export const ARCH_PULSE_TAIL_ALPHA = 0.06;
export const ARCH_PULSE_WRAP_OFFSET = 1;
export const ARCH_PULSE_RADIUS = ARCH_TUBE_RADIUS_INTER;
/**
 * WeOps createSegment is radius 0.03 plus GlowLayer (blur 32, intensity
 * 0.05). At landed FOV 34° / ~17wu / ~1080px, 1px ≈ 0.01wu — the core
 * alone aliases. Halo radius 0.03 ≈ 3px, low additive gain, ndotv fade
 * so it hugs the filament instead of reading as a fat pipe.
 */
export const ARCH_PULSE_HALO_RADIUS = 0.03;
export const ARCH_PULSE_HALO_INTENSITY = 0.16;
export const ARCH_PULSE_HALO_FALLOFF = 1.35;
/** Halo along-path power > 1: smear dies before the faded tail. */
export const ARCH_PULSE_HALO_TRAIL_POWER = 2;
export const ARCH_PULSE_HALO_BLENDING = 'additive' as const;
export const ARCH_PULSE_STYLE = 'gradient-trail' as const;
export const ARCH_PULSE_BLENDING = 'additive' as const;
/** Fragment RGB multiplier follows the band — not `0.45 + 0.55 * band`. */
export const ARCH_PULSE_RGB_SCALE = 'band' as const;
/**
 * Pulse core + halo share tessellation so additive stacking doesn't
 * read as offset comb teeth. Radial well above the idle 8-gon;
 * tubular well above 28 so the CatmullRom arc stays round when zoomed.
 */
export const ARCH_PULSE_TUBULAR_SEGMENTS = 128;
export const ARCH_PULSE_RADIAL_SEGMENTS = 32;

export const architecturePulseHaloRadius = (coreRadius = ARCH_PULSE_RADIUS) =>
  Math.max(ARCH_PULSE_HALO_RADIUS, coreRadius * 2.8);

export const architecturePulseTrailForLength = (pathLength: number) => {
  if (pathLength <= 1e-6) return ARCH_PULSE_TRAIL_MAX;
  return Math.min(ARCH_PULSE_TRAIL_MAX, ARCH_PULSE_WORLD_LENGTH / pathLength);
};

/** Default path fraction when the curve length is not yet known. */
export const ARCH_PULSE_TRAIL = ARCH_PULSE_TRAIL_MAX;
/** Full loops along the curve per second. */
export const ARCH_PULSE_SPEED = 0.32;
/** Title sits on the +X (right) side of each layer, not on the board front. */
export const ARCH_PLANE_TITLE_SIDE = 'right' as const;
/** Gap from the platform's right edge to the title mesh center. */
export const ARCH_TITLE_RIGHT_OUTSET = 0.55;
export const ARCH_TITLE_FILL = '#FFFFFF';
export const ARCH_TITLE_SHADOW_COLOR = '#00A3FF';
export const ARCH_TITLE_SHADOW_BLUR = 10;
export const ARCH_LABEL_FILL = '#FFFFFF';
export const ARCH_LABEL_HAS_BACKGROUND = false;
/** Layer titles and node labels always face the camera. */
export const ARCH_LABEL_BILLBOARD = true;
/**
 * Distance from the +Z front edge to the first cabinet row.
 * Low counts pack toward the camera instead of clustering at z=0.
 */
export const ARCH_FRONT_INSET = 1.15;

/**
 * Landed orbit: just above eye-level, looking along −Z into the stack.
 * π/2 − π/8 (~22.5° down) plus a high Y still read as 图1 (flattened
 * planes, empty above/below). Flatten toward the horizon so the two XZ
 * sheets foreshorten, rack fronts read, and both layers fill the frame.
 * Independent of the wall pose — not `wallPhi − π/2.5` (~0.29, overhead).
 */
export const ARCH_PREVIOUS_CAMERA_PHI = Math.PI / 2 - Math.PI / 8;
export const ARCH_CAMERA_PHI = Math.PI / 2 - Math.PI / 18;
export const ARCH_CAMERA_THETA = 0;
/** Floor under the fitted distance; frame-fill must be allowed to pull in. */
export const ARCH_CAMERA_RADIUS = 12;
export const ARCH_CAMERA_TARGET_Z = -0.6;
/**
 * Fraction of the tighter viewport axis the stack should occupy.
 * Most of the view, still below the old 0.92 that swallowed the screen.
 */
export const ARCH_CAMERA_FRAME_FILL = 0.76;

export const ARCH_PLANE_ORDER: Application3DArchitecturePlaneKind[] = [
  'application',
  'host',
];

export const ARCH_PLANE_TITLE: Record<
  Application3DArchitecturePlaneKind,
  { titleKey: string; titleFallback: string }
> = {
  application: {
    titleKey: 'dashboard.application3DKindApplication',
    titleFallback: '应用',
  },
  host: { titleKey: 'dashboard.application3DKindHost', titleFallback: '主机' },
};

export const formatArchitecturePlaneTitle = (name: string) => name.trim();

/** +Z is the near-camera front of the XZ platform. Row 0 sits on that lip. */
export const architectureFrontZ = (rowIndex = 0) =>
  ARCH_PLANE_WORLD_DEPTH / 2 - ARCH_FRONT_INSET - rowIndex * ARCH_GRID_PITCH;

export const architectureTitleLocalX = (planeWidth: number) =>
  planeWidth / 2 + ARCH_TITLE_RIGHT_OUTSET;

export interface Application3DArchitecturePlacedNode {
  id: string;
  kind: Application3DArchitectureKind;
  name: string;
  health?: Application3DHealth;
  x: number;
  y: number;
  z: number;
  width: number;
  height: number;
  depth: number;
}

export interface Application3DArchitecturePlacedEdge {
  id: string;
  sourceId: string;
  targetId: string;
  relation: Application3DArchitectureEdge['relation'];
  start: { x: number; y: number; z: number };
  end: { x: number; y: number; z: number };
  intraPlane: boolean;
}

export interface Application3DArchitecturePlane {
  kind: Application3DArchitecturePlaneKind;
  titleKey: string;
  titleFallback: string;
  titleText: string;
  x: number;
  /** Platform surface (top face). Racks stand on this Y. */
  y: number;
  z: number;
  width: number;
  /** World-Z extent of the XZ sheet. */
  depth: number;
  /** Local PlaneGeometry height (= depth after rotation.x = −π/2). */
  height: number;
  thickness: number;
  shape: Application3DArchitecturePlaneShape;
  /** Bottom-face / top-face for frustum; 1 for the thin host plane. */
  taper: number;
  rotationX: number;
  orientation: typeof ARCH_PLANE_ORIENTATION;
}

export interface Application3DArchitectureLayout {
  nodes: Application3DArchitecturePlacedNode[];
  edges: Application3DArchitecturePlacedEdge[];
  planes: Application3DArchitecturePlane[];
  width: number;
  height: number;
  depth: number;
  stackHeight: number;
  stackBottomY: number;
  stackTopY: number;
  centerY: number;
  centerZ: number;
}

export interface Application3DWallCameraPose {
  position: { x: number; y: number; z: number };
  target: { x: number; y: number; z: number };
}

export interface Application3DCameraSpherical {
  radius: number;
  /** Three.js phi / Babylon beta: 0 = +Y, π/2 = horizontal. */
  phi: number;
  /** Three.js theta (Y-azimuth). Wall pose is 0 when the camera sits on +Z. */
  theta: number;
}

const kindOrder: Record<Application3DArchitectureKind, number> = {
  application: 0,
  host: 1,
  system: 2,
};

const spreadOnPitch = (count: number, pitch: number): number[] => {
  if (count <= 0) return [];
  if (count === 1) return [0];
  const origin = -((count - 1) * pitch) / 2;
  return Array.from({ length: count }, (_, index) => origin + index * pitch);
};

const resolveOverlaps = (xs: number[], minDistance: number): number[] => {
  if (xs.length <= 1) return xs;
  const next = [...xs];
  for (let index = 1; index < next.length; index += 1) {
    next[index] = Math.max(next[index], next[index - 1] + minDistance);
  }
  const shift = (next[0] + next[next.length - 1]) / 2;
  return next.map((value) => value - shift);
};

const planeSurfaceLift = (kind: Application3DArchitectureKind) =>
  kind === 'application' ? 0 : ARCH_PLANE_THICKNESS / 2;

/** Rack center sits ON the platform surface (frustum top / thin-plane face). */
const rackStandY = (planeY: number, height: number, kind: Application3DArchitectureKind) =>
  planeY + planeSurfaceLift(kind) + height / 2;

const hostGridPitch = () => ({
  x: ARCH_GRID_PITCH,
  z: ARCH_GRID_PITCH,
});

const isolatedHostGrid = (count: number): Array<{ x: number; z: number }> => {
  if (count <= 0) return [];
  const cols = Math.min(count, Math.max(1, Math.ceil(Math.sqrt(count))));
  const pitch = hostGridPitch();
  const originX = -((cols - 1) * pitch.x) / 2;
  return Array.from({ length: count }, (_, index) => {
    const row = Math.floor(index / cols);
    const col = index % cols;
    return {
      x: originX + col * pitch.x,
      z: architectureFrontZ(row),
    };
  });
};

export const offsetToSpherical = (
  dx: number,
  dy: number,
  dz: number,
): Application3DCameraSpherical => {
  const radius = Math.hypot(dx, dy, dz);
  if (radius < 1e-6) return { radius: 0, phi: Math.PI / 2, theta: 0 };
  return {
    radius,
    phi: Math.acos(Math.min(1, Math.max(-1, dy / radius))),
    theta: Math.atan2(dx, dz),
  };
};

export const sphericalToOffset = (
  radius: number,
  phi: number,
  theta: number,
) => ({
  x: radius * Math.sin(phi) * Math.sin(theta),
  y: radius * Math.cos(phi),
  z: radius * Math.sin(phi) * Math.cos(theta),
});

export const architectureRimUvWidth = (
  world: number,
  planeSize = ARCH_PLANE_WORLD_WIDTH,
) => world / Math.max(planeSize, 1e-6);

/** Soft inward bloom weight at a WORLD-unit edge distance (0 = rim). */
export const architectureRimBloomWeight = (worldEdge: number) => {
  if (worldEdge <= ARCH_PLANE_RIM_STROKE_WORLD) return 1;
  if (worldEdge >= ARCH_PLANE_RIM_HALO_WORLD) return 0;
  const t = (worldEdge - ARCH_PLANE_RIM_STROKE_WORLD)
    / (ARCH_PLANE_RIM_HALO_WORLD - ARCH_PLANE_RIM_STROKE_WORLD);
  return (1 - t) ** ARCH_PLANE_RIM_FALLOFF;
};

export const architecturePulseCompanionHead = (head: number) =>
  head + ARCH_PULSE_WRAP_OFFSET;

export const architecturePulseBandIntensity = (
  pathU: number,
  head: number,
  trail = ARCH_PULSE_TRAIL,
) => {
  const behind = head - pathU;
  if (behind < 0 || behind > trail + 1e-9) return 0;
  const t = Math.min(1, Math.max(0, behind / trail));
  return 1 - t * (1 - ARCH_PULSE_TAIL_ALPHA);
};

/** Linear RGB scale along the band. Head = 1, tail ≈ TAIL_ALPHA — not 0.45+0.55*band. */
export const architecturePulseRgbScale = (band: number) => band;

/** Halo along-path weight. Power > 1 so the smear does not relight the tail. */
export const architecturePulseHaloAlong = (band: number) => {
  if (band <= 0) return 0;
  return band ** ARCH_PULSE_HALO_TRAIL_POWER;
};

/** Additive src.rgb * src.alpha, relative to uColor, for the core filament. */
export const architecturePulseCoreBlend = (band: number) =>
  architecturePulseRgbScale(band) * band;

/** Additive halo contribution relative to uColor, before the radial term. */
export const architecturePulseHaloBlend = (band: number, radial = 1) =>
  architecturePulseRgbScale(band)
  * architecturePulseHaloAlong(band)
  * ARCH_PULSE_HALO_INTENSITY
  * radial;

export const architecturePulseIntensity = (
  pathU: number,
  head: number,
  trail = ARCH_PULSE_TRAIL,
) => Math.max(
  architecturePulseBandIntensity(pathU, head, trail),
  architecturePulseBandIntensity(
    pathU,
    architecturePulseCompanionHead(head),
    trail,
  ),
);

/** Peak comet intensity anywhere on the path — 0 would be a dead loop frame. */
export const architecturePulsePathLit = (
  head: number,
  trail = ARCH_PULSE_TRAIL,
  steps = 32,
) => {
  let max = architecturePulseIntensity(head, head, trail);
  for (let index = 0; index <= steps; index += 1) {
    max = Math.max(max, architecturePulseIntensity(index / steps, head, trail));
  }
  return max;
};

export const describeWallCameraSpherical = (
  wall: Application3DWallCameraPose,
): Application3DCameraSpherical =>
  offsetToSpherical(
    wall.position.x - wall.target.x,
    wall.position.y - wall.target.y,
    wall.position.z - wall.target.z,
  );

export const layoutApplication3DArchitecture = (
  data: Application3DArchitectureData,
): Application3DArchitectureLayout => {
  const nodesById = new Map(data.nodes.map((node) => [node.id, node]));
  const applications = data.nodes.filter((node) => node.kind === 'application');
  const hosts = data.nodes.filter((node) => node.kind === 'host');

  const placed = new Map<string, Application3DArchitecturePlacedNode>();
  const place = (
    node: Application3DArchitectureNode,
    x: number,
    z = 0,
    planeY = ARCH_PLANE_Y[node.kind as Application3DArchitecturePlaneKind],
  ) => {
    if (node.kind === 'system') return;
    const size = ARCH_NODE_SIZE[node.kind];
    placed.set(node.id, {
      id: node.id,
      kind: node.kind,
      name: node.name,
      health: node.health,
      x,
      y: rackStandY(planeY, size.height, node.kind),
      z,
      ...size,
    });
  };

  const appXs = spreadOnPitch(applications.length, ARCH_GRID_PITCH);
  const appFrontZ = architectureFrontZ(0);
  applications.forEach((node, index) => place(node, appXs[index] ?? 0, appFrontZ));

  const parentsByHost = new Map<string, string[]>();
  data.edges
    .filter((edge) => edge.relation === 'application_run_host')
    .forEach((edge) => {
      const parents = parentsByHost.get(edge.targetId) ?? [];
      parents.push(edge.sourceId);
      parentsByHost.set(edge.targetId, parents);
    });

  const connectedHosts: Application3DArchitectureNode[] = [];
  const isolatedHosts: Application3DArchitectureNode[] = [];
  hosts.forEach((node) => {
    if (parentsByHost.get(node.id)?.length) connectedHosts.push(node);
    else isolatedHosts.push(node);
  });

  const connectedDraft = connectedHosts.map((node) => {
    const parentXs = (parentsByHost.get(node.id) ?? [])
      .map((parentId) => placed.get(parentId)?.x)
      .filter((value): value is number => typeof value === 'number');
    const x = parentXs.length
      ? parentXs.reduce((sum, value) => sum + value, 0) / parentXs.length
      : 0;
    return { node, x };
  });
  connectedDraft.sort((left, right) => left.x - right.x || left.node.id.localeCompare(right.node.id));
  const connectedXs = resolveOverlaps(
    connectedDraft.map((item) => item.x),
    ARCH_GRID_PITCH,
  );
  const hostFrontZ = architectureFrontZ(0);
  connectedDraft.forEach((item, index) => {
    place(item.node, connectedXs[index] ?? item.x, hostFrontZ);
  });

  const isolatedCells = isolatedHostGrid(isolatedHosts.length);
  let isolatedShiftX = 0;
  if (connectedDraft.length && isolatedCells.length) {
    const connectedMax = Math.max(
      ...connectedDraft.map((item, index) => (connectedXs[index] ?? item.x) + ARCH_NODE_SIZE.host.width / 2),
    );
    const isolatedMin = Math.min(...isolatedCells.map((cell) => cell.x - ARCH_NODE_SIZE.host.width / 2));
    isolatedShiftX = connectedMax + (ARCH_GRID_PITCH - ARCH_NODE_SIZE.host.width) - isolatedMin;
  }
  isolatedHosts.forEach((node, index) => {
    const cell = isolatedCells[index] ?? { x: 0, z: 0 };
    place(node, cell.x + isolatedShiftX, cell.z, ARCH_PLANE_Y.host);
  });

  const placedNodes = [...placed.values()].sort(
    (left, right) => kindOrder[left.kind] - kindOrder[right.kind] || left.x - right.x || left.z - right.z,
  );
  const placedEdges: Application3DArchitecturePlacedEdge[] = data.edges.flatMap((edge) => {
    const source = placed.get(edge.sourceId);
    const target = placed.get(edge.targetId);
    if (!source || !target || !nodesById.has(edge.sourceId) || !nodesById.has(edge.targetId)) {
      return [];
    }
    const intraPlane = Math.abs(source.y - target.y) < 1e-6;
    return [{
      id: edge.id,
      sourceId: edge.sourceId,
      targetId: edge.targetId,
      relation: edge.relation,
      intraPlane,
      start: { x: source.x, y: source.y, z: source.z },
      end: { x: target.x, y: target.y, z: target.z },
    }];
  });

  const xs = placedNodes.flatMap((node) => [node.x - node.width / 2, node.x + node.width / 2]);
  const zs = placedNodes.flatMap((node) => [node.z - node.depth / 2, node.z + node.depth / 2]);
  const minX = xs.length ? Math.min(...xs) : -1;
  const maxX = xs.length ? Math.max(...xs) : 1;
  const minZ = zs.length ? Math.min(...zs) : -1;
  const maxZ = zs.length ? Math.max(...zs) : 1;
  const contentWidth = Math.max(maxX - minX + ARCH_PLANE_PAD * 2, ARCH_PLANE_MIN_WIDTH);
  const contentDepth = Math.max(maxZ - minZ + ARCH_PLANE_PAD * 2, ARCH_PLANE_MIN_DEPTH);

  const planes: Application3DArchitecturePlane[] = ARCH_PLANE_ORDER.map((kind) => {
    const title = ARCH_PLANE_TITLE[kind];
    const isBase = kind === 'application';
    return {
      kind,
      titleKey: title.titleKey,
      titleFallback: title.titleFallback,
      titleText: formatArchitecturePlaneTitle(title.titleFallback),
      x: 0,
      y: ARCH_PLANE_Y[kind],
      z: 0,
      width: contentWidth,
      depth: contentDepth,
      height: contentDepth,
      thickness: isBase ? ARCH_FRUSTUM_HEIGHT : ARCH_PLANE_THICKNESS,
      shape: isBase ? 'frustum' : 'plane',
      taper: isBase ? ARCH_FRUSTUM_TAPER : 1,
      rotationX: ARCH_PLANE_ROTATION_X,
      orientation: ARCH_PLANE_ORIENTATION,
    };
  });

  const stackBottomY = ARCH_PLANE_Y.application - ARCH_FRUSTUM_HEIGHT;
  const stackTopY = ARCH_PLANE_Y.host + ARCH_NODE_SIZE.host.height;

  return {
    nodes: placedNodes,
    edges: placedEdges,
    planes,
    width: Math.max(contentWidth, maxX - minX),
    height: ARCH_PLANE_Y.host - ARCH_PLANE_Y.application,
    depth: contentDepth,
    stackHeight: stackTopY - stackBottomY,
    stackBottomY,
    stackTopY,
    centerY: (ARCH_PLANE_Y.application + ARCH_PLANE_Y.host) / 2,
    centerZ: 0,
  };
};

export const fitArchitectureCameraDistance = (
  layout: Application3DArchitectureLayout,
  viewportAspect: number,
  fovDeg = APPLICATION3D_CAMERA_FOV,
): number => {
  const halfFov = ((fovDeg * Math.PI) / 180) / 2;
  const tan = Math.tan(halfFov);
  const aspect = Math.max(viewportAspect, 0.1);
  const titledWidth = layout.width + ARCH_TITLE_RIGHT_OUTSET * 2;
  const distanceForWidth = titledWidth / (2 * tan * aspect);
  const distanceForHeight = layout.stackHeight / (2 * tan);
  const fitted = Math.max(distanceForWidth, distanceForHeight) / ARCH_CAMERA_FRAME_FILL;
  return Math.max(ARCH_CAMERA_RADIUS, fitted);
};

export const describeArchitectureLandedFrame = (
  layout: Application3DArchitectureLayout,
  pose: Application3DArchitectureCameraPose,
) => ({
  camera: {
    position: pose.position,
    target: pose.target,
    phi: pose.phi,
    radius: pose.radius,
    theta: pose.theta,
    beta: pose.beta,
  },
  planes: layout.planes.map((plane) => ({
    kind: plane.kind,
    origin: { x: plane.x, y: plane.y, z: plane.z },
    orientation: plane.orientation,
    rotationX: plane.rotationX,
    size: { width: plane.width, depth: plane.depth, height: plane.height },
    thickness: plane.thickness,
    shape: plane.shape,
    taper: plane.taper,
  })),
  frustum: {
    height: ARCH_FRUSTUM_HEIGHT,
    taper: ARCH_FRUSTUM_TAPER,
    topWidth: layout.planes[0]?.width ?? ARCH_PLANE_WORLD_WIDTH,
    topDepth: layout.planes[0]?.depth ?? ARCH_PLANE_WORLD_DEPTH,
    bottomWidth: (layout.planes[0]?.width ?? ARCH_PLANE_WORLD_WIDTH) * ARCH_FRUSTUM_TAPER,
    bottomDepth: (layout.planes[0]?.depth ?? ARCH_PLANE_WORLD_DEPTH) * ARCH_FRUSTUM_TAPER,
  },
  glass: {
    opacity: ARCH_PLANE_OPACITY,
    emissiveIntensity: ARCH_PLANE_EMISSIVE_INTENSITY,
    depthWrite: ARCH_PLANE_DEPTH_WRITE,
    rimColor: ARCH_PLANE_RIM_COLOR,
    rimOpacity: ARCH_PLANE_RIM_OPACITY,
    rimStrokeOpacity: ARCH_PLANE_RIM_STROKE_OPACITY,
    rimInner: ARCH_PLANE_RIM_INNER,
    rimOuter: ARCH_PLANE_RIM_OUTER,
    rimStrokeWorld: ARCH_PLANE_RIM_STROKE_WORLD,
    rimHaloWorld: ARCH_PLANE_RIM_HALO_WORLD,
    rimBlending: ARCH_PLANE_RIM_BLENDING,
    rimFalloff: ARCH_PLANE_RIM_FALLOFF,
    rimHasEdgeLines: ARCH_PLANE_RIM_HAS_EDGE_LINES,
  },
  glassSides: {
    opacity: ARCH_PLANE_SIDE_OPACITY,
    emissiveIntensity: ARCH_PLANE_SIDE_EMISSIVE_INTENSITY,
    hasStroke: ARCH_PLANE_SIDE_HAS_STROKE,
    matchesTopHue: ARCH_PLANE_SIDE_MATCHES_TOP_HUE,
  },
  titles: {
    side: ARCH_PLANE_TITLE_SIDE,
    arrow: '',
    fill: ARCH_TITLE_FILL,
    glow: ARCH_TITLE_SHADOW_COLOR,
    glowBlur: ARCH_TITLE_SHADOW_BLUR,
  },
  tubes: {
    interRadius: ARCH_TUBE_RADIUS_INTER,
    intraRadius: ARCH_TUBE_RADIUS_INTRA,
    opacity: ARCH_TUBE_OPACITY,
    emissiveIntensity: ARCH_TUBE_EMISSIVE_INTENSITY,
    inGlowLayer: ARCH_TUBE_IN_GLOW_LAYER,
    tubularSegments: ARCH_TUBE_TUBULAR_SEGMENTS,
    radialSegments: ARCH_TUBE_RADIAL_SEGMENTS,
  },
  pulse: {
    length: ARCH_PULSE_WORLD_LENGTH,
    worldLength: ARCH_PULSE_WORLD_LENGTH,
    radius: ARCH_PULSE_RADIUS,
    haloRadius: ARCH_PULSE_HALO_RADIUS,
    haloIntensity: ARCH_PULSE_HALO_INTENSITY,
    haloFalloff: ARCH_PULSE_HALO_FALLOFF,
    haloTrailPower: ARCH_PULSE_HALO_TRAIL_POWER,
    haloBlending: ARCH_PULSE_HALO_BLENDING,
    rgbScale: ARCH_PULSE_RGB_SCALE,
    speed: ARCH_PULSE_SPEED,
    trail: ARCH_PULSE_TRAIL,
    trailMax: ARCH_PULSE_TRAIL_MAX,
    tailAlpha: ARCH_PULSE_TAIL_ALPHA,
    wrapOffset: ARCH_PULSE_WRAP_OFFSET,
    style: ARCH_PULSE_STYLE,
    blending: ARCH_PULSE_BLENDING,
    tubularSegments: ARCH_PULSE_TUBULAR_SEGMENTS,
    radialSegments: ARCH_PULSE_RADIAL_SEGMENTS,
  },
  rackScale: ARCH_NODE_SIZE,
  gridPitch: ARCH_GRID_PITCH,
  stack: {
    height: layout.stackHeight,
    bottomY: layout.stackBottomY,
    topY: layout.stackTopY,
    width: layout.width,
    depth: layout.depth,
  },
  frameFill: ARCH_CAMERA_FRAME_FILL,
});

export interface Application3DArchitectureCameraPose {
  position: { x: number; y: number; z: number };
  target: { x: number; y: number; z: number };
  radius: number;
  /** Three.js phi of the landed pose; same axis as Babylon beta. */
  phi: number;
  theta: number;
  /** Alias of phi so reports can keep the Babylon beta name. */
  beta: number;
}

const clampPhi = (phi: number) => Math.min(Math.PI - 0.08, Math.max(0.08, phi));

/**
 * Architecture camera is a dedicated just-above-eye-level look into the stack.
 * It is NOT `wallPhi + (−π/2.5)` — that overhead pitch crushed the layers.
 * Target sits between the two XZ platforms; camera stays on +Z looking −Z.
 */
export const resolveArchitectureCameraPose = (
  layout: Application3DArchitectureLayout,
  _wall: Application3DWallCameraPose,
  viewportAspect: number,
  fovDeg = APPLICATION3D_CAMERA_FOV,
): Application3DArchitectureCameraPose => {
  const fitted = fitArchitectureCameraDistance(layout, viewportAspect, fovDeg);
  const radius = fitted * ARCHITECTURE_MOTION.cameraRadiusScale;
  const phi = clampPhi(ARCH_CAMERA_PHI);
  const theta = ARCH_CAMERA_THETA;
  const target = {
    x: 0,
    y: layout.centerY + ARCHITECTURE_MOTION.cameraTargetLift,
    z: layout.centerZ + ARCH_CAMERA_TARGET_Z + ARCHITECTURE_MOTION.cameraTargetForward,
  };
  const offset = sphericalToOffset(radius, phi, theta);
  return {
    target,
    radius,
    phi,
    theta,
    beta: phi,
    position: {
      x: target.x + offset.x,
      y: target.y + offset.y,
      z: target.z + offset.z,
    },
  };
};
