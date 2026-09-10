import * as THREE from "three";
import {
  deviceHasAlarmGlow,
  getRoom3DPositionLabel,
  getRoom3DRackDevices,
  type Room3DRack,
  type Room3DRenderableDevice,
} from "./room3DData";

export interface RackVisual {
  rack: Room3DRack;
  root: THREE.Group;
  outline: THREE.LineSegments;
  interiorShield: THREE.Mesh;
  pickTargets: THREE.Object3D[];
  deviceMeshes: THREE.Mesh[];
}

export const ROOM3D_COL_GAP = 1.18;
export const ROOM3D_ROW_GAP = 5.4;
export const ROOM3D_FRONT_AISLE_EXTRA = 1.5;
export const ROOM3D_RACK_WIDTH = 1.05;
export const ROOM3D_RACK_DEPTH = 1.2;
export const ROOM3D_RACK_HEIGHT = 1.95;
export const ROOM3D_DEVICE_PULL_OUT_DISTANCE = 0.32;

const WALL_HEIGHT = ROOM3D_RACK_HEIGHT;
const WALL_THICKNESS = 0.1;
const WALL_OPACITY = 0.98;
const RACK_USABLE_BOTTOM = 0.12;
const RACK_USABLE_TOP_PADDING = 0.1;
const RACK_USABLE_HEIGHT =
  ROOM3D_RACK_HEIGHT - RACK_USABLE_BOTTOM - RACK_USABLE_TOP_PADDING;
const ROOM3D_ANIMATION_EPSILON = 0.001;

const interpolateRoom3DValue = (
  current: number,
  target: number,
  factor: number,
) => {
  const next = current + (target - current) * factor;
  return Math.abs(target - next) <= ROOM3D_ANIMATION_EPSILON ? target : next;
};

const createCanvasTexture = (
  width: number,
  height: number,
  draw: (context: CanvasRenderingContext2D) => void,
) => {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (context) {
    draw(context);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
};

const EQUIPMENT_FRONT_MAP_WIDTH = 320;
const EQUIPMENT_FRONT_MAP_HEIGHT = 96;
const EQUIPMENT_FACE_EMISSIVE_INTENSITY = 1.22;
/** Unified interior red warning glow for devices with active alarms. */
const EQUIPMENT_ALARM_GLOW_COLOR = "#ff2a2a";
const EQUIPMENT_ALARM_GLOW_INTENSITY = 1.7;
const EQUIPMENT_ALARM_GLOW_DISTANCE = 0.9;
const EQUIPMENT_ALARM_CORE_OPACITY = 0.22;
const EQUIPMENT_ALARM_HALO_OPACITY = 0.85;
/** Keep chassis mostly textured; only a hint of warm red, not a full paint. */
const EQUIPMENT_ALARM_SIDE_EMISSIVE_INTENSITY = 0.16;
const EQUIPMENT_ALARM_FRONT_EMISSIVE_INTENSITY = EQUIPMENT_FACE_EMISSIVE_INTENSITY;

/** Soft alpha falloff so the envelope reads as fog, not a hard red slab. */
const createAlarmGlowTexture = () =>
  createCanvasTexture(64, 64, (context) => {
    const gradient = context.createRadialGradient(32, 32, 1, 32, 32, 31);
    gradient.addColorStop(0, "rgba(255, 42, 42, 0.95)");
    gradient.addColorStop(0.4, "rgba(255, 42, 42, 0.42)");
    gradient.addColorStop(0.75, "rgba(255, 42, 42, 0.12)");
    gradient.addColorStop(1, "rgba(255, 42, 42, 0)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 64, 64);
  });

const createAlarmGlowMaterial = (opacity: number) =>
  new THREE.MeshBasicMaterial({
    color: "#ffffff",
    map: createAlarmGlowTexture(),
    transparent: true,
    opacity,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });

type EquipmentPortLedKind = "green" | "amber" | "red" | "off";

const EQUIPMENT_PORT_LED_PAINT: Record<
  Exclude<EquipmentPortLedKind, "off">,
  {
    core: string;
    innerHalo: string;
    outerHalo: string;
    emissiveCore: string;
    emissiveInnerHalo: string;
    emissiveOuterHalo: string;
  }
> = {
  green: {
    core: "#3dff68",
    innerHalo: "rgba(61, 255, 104, 0.58)",
    outerHalo: "rgba(61, 255, 104, 0.24)",
    emissiveCore: "#f3fff5",
    emissiveInnerHalo: "rgba(110, 255, 150, 0.9)",
    emissiveOuterHalo: "rgba(50, 255, 110, 0.4)",
  },
  amber: {
    core: "#ff9c1c",
    innerHalo: "rgba(255, 156, 28, 0.6)",
    outerHalo: "rgba(255, 156, 28, 0.26)",
    emissiveCore: "#fff3e2",
    emissiveInnerHalo: "rgba(255, 180, 70, 0.9)",
    emissiveOuterHalo: "rgba(255, 150, 30, 0.42)",
  },
  red: {
    core: "#ff2a2a",
    innerHalo: "rgba(255, 42, 42, 0.62)",
    outerHalo: "rgba(255, 42, 42, 0.28)",
    emissiveCore: "#fff0f0",
    emissiveInnerHalo: "rgba(255, 120, 120, 0.92)",
    emissiveOuterHalo: "rgba(255, 40, 40, 0.48)",
  },
};

const getEquipmentPortLedKind = (
  bay: number,
  row: number,
  col: number,
): EquipmentPortLedKind => {
  const slot = (bay * 7 + row * 3 + col * 5 + 2) % 12;
  if (slot === 0) {
    return "off";
  }
  if (slot === 3 || slot === 9) {
    return "amber";
  }
  return "green";
};

const paintEquipmentPortLed = (
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  kind: EquipmentPortLedKind,
  target: "map" | "emissive",
) => {
  if (kind === "off") {
    if (target === "map") {
      context.fillStyle = "rgba(6, 12, 18, 0.92)";
      context.fillRect(x, y, 3, 2);
    }
    return;
  }

  const paint = EQUIPMENT_PORT_LED_PAINT[kind];
  context.fillStyle = target === "map" ? paint.outerHalo : paint.emissiveOuterHalo;
  context.fillRect(x - 2, y - 2, 7, 6);
  context.fillStyle = target === "map" ? paint.innerHalo : paint.emissiveInnerHalo;
  context.fillRect(x - 1, y - 1, 5, 4);
  context.fillStyle = target === "map" ? paint.core : paint.emissiveCore;
  context.fillRect(x, y, 3, 2);
  context.fillStyle =
    target === "map" ? "rgba(255, 255, 255, 0.42)" : "rgba(255, 255, 255, 0.85)";
  context.fillRect(x + 1, y, 1, 1);
};

const forEachEquipmentPortLed = (
  callback: (x: number, y: number, kind: EquipmentPortLedKind) => void,
) => {
  for (let bay = 0; bay < 4; bay += 1) {
    const left = 18 + bay * 68;
    let row = 0;
    for (let y = 35; y < 55; y += 6) {
      let col = 0;
      for (let x = left + 5; x < left + 48; x += 7) {
        callback(x, y, getEquipmentPortLedKind(bay, row, col));
        col += 1;
      }
      row += 1;
    }
  }
};

const paintEquipmentPortLeds = (
  context: CanvasRenderingContext2D,
  target: "map" | "emissive",
  alarmMode = false,
) => {
  forEachEquipmentPortLed((x, y, kind) => {
    paintEquipmentPortLed(
      context,
      x,
      y,
      alarmMode ? "red" : kind,
      target,
    );
  });
};

const EQUIPMENT_STATUS_DOTS: Array<{
  x: number;
  y: number;
  kind: EquipmentPortLedKind;
}> = [
  { x: 286, y: 48, kind: "green" },
  { x: 294, y: 48, kind: "amber" },
  { x: 302, y: 48, kind: "green" },
];

const paintEquipmentStatusBar = (
  context: CanvasRenderingContext2D,
  target: "map" | "emissive",
  alarmMode = false,
) => {
  const paint = alarmMode
    ? EQUIPMENT_PORT_LED_PAINT.red
    : EQUIPMENT_PORT_LED_PAINT.green;
  context.fillStyle = target === "map" ? paint.outerHalo : paint.emissiveOuterHalo;
  context.fillRect(274, 29, 7, 38);
  context.fillStyle = target === "map" ? paint.innerHalo : paint.emissiveInnerHalo;
  context.fillRect(275, 30, 5, 36);
  context.fillStyle = target === "map" ? paint.core : paint.emissiveCore;
  context.fillRect(276, 31, 3, 34);
  context.fillStyle =
    target === "map" ? "rgba(255, 255, 255, 0.42)" : "rgba(255, 255, 255, 0.85)";
  context.fillRect(277, 36, 1, 8);
};

const paintEquipmentStatusDot = (
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  kind: EquipmentPortLedKind,
  target: "map" | "emissive",
) => {
  const fillDot = (style: string, radius: number) => {
    context.fillStyle = style;
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.fill();
  };

  if (kind === "off") {
    if (target === "map") {
      fillDot("rgba(6, 12, 18, 0.92)", 2.4);
    }
    return;
  }

  const paint = EQUIPMENT_PORT_LED_PAINT[kind];
  fillDot(target === "map" ? paint.outerHalo : paint.emissiveOuterHalo, 4.4);
  fillDot(target === "map" ? paint.innerHalo : paint.emissiveInnerHalo, 3.3);
  fillDot(target === "map" ? paint.core : paint.emissiveCore, 2.4);
  fillDot(
    target === "map" ? "rgba(255, 255, 255, 0.42)" : "rgba(255, 255, 255, 0.85)",
    0.9,
  );
};

const paintEquipmentStatusLights = (
  context: CanvasRenderingContext2D,
  target: "map" | "emissive",
  alarmMode = false,
) => {
  paintEquipmentStatusBar(context, target, alarmMode);
  EQUIPMENT_STATUS_DOTS.forEach((dot) => {
    paintEquipmentStatusDot(
      context,
      dot.x,
      dot.y,
      alarmMode ? "red" : dot.kind,
      target,
    );
  });
};

const createEquipmentTexture = (alarmMode = false) => {
  const map = createCanvasTexture(
    EQUIPMENT_FRONT_MAP_WIDTH,
    EQUIPMENT_FRONT_MAP_HEIGHT,
    (context) => {
      context.fillStyle = "#829db2";
      context.fillRect(0, 0, 320, 96);
      const gradient = context.createLinearGradient(0, 0, 0, 96);
      gradient.addColorStop(0, "rgba(255,255,255,0.28)");
      gradient.addColorStop(0.5, "rgba(31,45,58,0.08)");
      gradient.addColorStop(1, "rgba(6,16,26,0.25)");
      context.fillStyle = gradient;
      context.fillRect(0, 0, 320, 96);
      context.fillStyle = "rgba(18, 30, 42, 0.32)";
      context.fillRect(0, 0, 320, 12);
      context.fillRect(0, 84, 320, 12);
      context.fillStyle = "rgba(230, 239, 246, 0.42)";
      context.fillRect(12, 16, 296, 2);
      context.fillRect(12, 78, 296, 2);
      context.fillStyle = "rgba(8, 18, 28, 0.54)";
      for (let bay = 0; bay < 4; bay += 1) {
        const left = 18 + bay * 68;
        context.fillRect(left, 26, 52, 34);
        context.fillStyle = "rgba(190, 203, 214, 0.28)";
        context.fillRect(left + 4, 29, 44, 2);
        context.fillStyle = "rgba(8, 18, 28, 0.54)";
      }
      paintEquipmentPortLeds(context, "map", alarmMode);
      paintEquipmentStatusLights(context, "map", alarmMode);
    },
  );
  const emissiveMap = createCanvasTexture(
    EQUIPMENT_FRONT_MAP_WIDTH,
    EQUIPMENT_FRONT_MAP_HEIGHT,
    (context) => {
      context.fillStyle = "#000000";
      context.fillRect(0, 0, 320, 96);
      paintEquipmentPortLeds(context, "emissive", alarmMode);
      paintEquipmentStatusLights(context, "emissive", alarmMode);
    },
  );
  return { map, emissiveMap };
};

const createRackTopTexture = (label: string, category?: string) =>
  createCanvasTexture(192, 128, (context) => {
    const gradient = context.createLinearGradient(0, 0, 192, 128);
    gradient.addColorStop(0, "#7e858b");
    gradient.addColorStop(0.55, "#5d656c");
    gradient.addColorStop(1, "#8d9398");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 192, 128);
    context.strokeStyle = "rgba(96, 218, 255, 0.42)";
    context.strokeRect(8, 8, 176, 112);
    context.fillStyle = "rgba(255,255,255,0.72)";
    context.font = "700 30px sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    if (category) {
      context.fillText(label.slice(0, 5), 96, 50);
      context.fillStyle = "rgba(219,236,246,0.78)";
      context.font = "600 22px sans-serif";
      context.fillText(category.slice(0, 8), 96, 84);
    } else {
      context.fillText(label.slice(0, 5), 96, 64);
    }
    context.fillStyle = "rgba(95, 234, 255, 0.22)";
    for (let x = 56; x < 136; x += 10) {
      context.fillRect(x, 26, 4, 2);
      context.fillRect(x, 100, 4, 2);
    }
  });

const createEquipmentSideTexture = () =>
  createCanvasTexture(64, 64, (context) => {
    context.fillStyle = "#6b7b89";
    context.fillRect(0, 0, 64, 64);
    context.strokeStyle = "rgba(235, 244, 252, 0.2)";
    for (let y = 10; y < 60; y += 10) {
      context.beginPath();
      context.moveTo(6, y);
      context.lineTo(58, y);
      context.stroke();
    }
  });

const createRackSideTexture = () =>
  createCanvasTexture(128, 256, (context) => {
    const gradient = context.createLinearGradient(0, 0, 128, 256);
    gradient.addColorStop(0, "#9aa0a5");
    gradient.addColorStop(0.48, "#7b8288");
    gradient.addColorStop(1, "#a5aaaf");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 128, 256);
    context.strokeStyle = "rgba(248, 251, 253, 0.24)";
    for (let y = 18; y < 240; y += 14) {
      context.beginPath();
      context.moveTo(14, y);
      context.lineTo(114, y);
      context.stroke();
    }
    context.fillStyle = "rgba(34, 42, 50, 0.36)";
    for (let y = 32; y < 228; y += 20) {
      context.fillRect(22, y, 84, 5);
    }
    context.fillStyle = "rgba(104, 219, 255, 0.2)";
    for (let y = 38; y < 220; y += 40) {
      context.fillRect(18, y, 92, 2);
    }
  });

const createTileTexture = () =>
  createCanvasTexture(256, 256, (context) => {
    context.fillStyle = "#f8fafc";
    context.fillRect(0, 0, 256, 256);
    context.strokeStyle = "rgba(82, 99, 116, 0.3)";
    context.lineWidth = 1.4;
    for (let x = 0; x <= 256; x += 48) {
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, 256);
      context.stroke();
    }
    for (let y = 0; y <= 256; y += 48) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(256, y);
      context.stroke();
    }
    context.strokeStyle = "rgba(255, 255, 255, 0.45)";
    context.strokeRect(2, 2, 252, 252);
  });

const createWallTexture = () =>
  createCanvasTexture(384, 256, (context) => {
    const gradient = context.createLinearGradient(0, 0, 0, 256);
    gradient.addColorStop(0, "#ffffff");
    gradient.addColorStop(0.58, "#f7fafc");
    gradient.addColorStop(1, "#e9eff5");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 384, 256);
    context.strokeStyle = "rgba(82, 99, 116, 0.12)";
    context.lineWidth = 1;
    for (let y = 38; y < 256; y += 38) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(384, y);
      context.stroke();
    }
    context.strokeStyle = "rgba(255, 255, 255, 0.28)";
    for (let x = 34; x < 384; x += 68) {
      context.beginPath();
      context.moveTo(x, 8);
      context.lineTo(x, 248);
      context.stroke();
    }
    context.fillStyle = "rgba(67, 89, 109, 0.06)";
    context.fillRect(0, 210, 384, 22);
    context.fillStyle = "rgba(104, 181, 218, 0.035)";
    context.fillRect(0, 0, 384, 12);
  });

const getRackUnitY = (unit: number, uCount: number) => {
  const normalized = Math.min(
    1,
    Math.max(0, (unit - 0.5) / Math.max(uCount, 1)),
  );
  return RACK_USABLE_BOTTOM + normalized * RACK_USABLE_HEIGHT;
};

const getRackUnitCenterY = (uStart: number, uSize: number, uCount: number) =>
  getRackUnitY(uStart + (Math.max(uSize, 1) - 1) / 2, uCount);

const createRackScaleTexture = (uCount: number) =>
  createCanvasTexture(128, 1024, (context) => {
    const textureTop = 40;
    const textureBottom = 990;
    const textureHeight = textureBottom - textureTop;
    const maxU = Math.max(uCount, 1);
    const getTextureY = (unit: number) => {
      const normalized = Math.min(1, Math.max(0, (unit - 0.5) / maxU));
      return textureBottom - normalized * textureHeight;
    };
    const labelUnits = [1];
    for (let unit = 10; unit < maxU; unit += 10) {
      labelUnits.push(unit);
    }
    if (!labelUnits.includes(maxU)) {
      labelUnits.push(maxU);
    }
    const drawnY: number[] = [];

    context.clearRect(0, 0, 128, 1024);
    context.strokeStyle = "rgba(172, 183, 193, 0.34)";
    context.lineWidth = 3;
    context.beginPath();
    context.moveTo(94, textureTop);
    context.lineTo(94, textureBottom);
    context.stroke();
    context.font = "900 30px sans-serif";
    context.textAlign = "right";
    context.textBaseline = "middle";
    labelUnits.forEach((unit) => {
      const y = getTextureY(unit);
      if (drawnY.some((item) => Math.abs(item - y) < 42)) {
        return;
      }
      drawnY.push(y);
      context.strokeStyle = "rgba(194, 201, 208, 0.62)";
      context.lineWidth = 3;
      context.beginPath();
      context.moveTo(82, y);
      context.lineTo(112, y);
      context.stroke();
      context.lineWidth = 4;
      context.strokeStyle = "rgba(3, 8, 13, 0.72)";
      context.strokeText(String(unit), 58, y);
      context.fillStyle = "rgba(207, 214, 221, 0.92)";
      context.fillText(String(unit), 58, y);
    });
  });

export const buildRoomShell = (
  scene: THREE.Scene,
  floorWidth: number,
  floorDepth: number,
) => {
  const shell = new THREE.Group();
  shell.name = "room-shell";

  const tileTexture = createTileTexture();
  tileTexture.wrapS = THREE.RepeatWrapping;
  tileTexture.wrapT = THREE.RepeatWrapping;
  tileTexture.repeat.set(
    Math.max(2, floorWidth / 2.4),
    Math.max(2, floorDepth / 2.4),
  );

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(floorWidth, floorDepth),
    new THREE.MeshStandardMaterial({
      color: "#f8fafc",
      map: tileTexture,
      side: THREE.DoubleSide,
      metalness: 0.03,
      roughness: 0.88,
    }),
  );
  floor.name = "room-floor";
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -0.035;
  floor.receiveShadow = true;
  shell.add(floor);

  const floorSlab = new THREE.Mesh(
    new THREE.BoxGeometry(floorWidth, 0.16, floorDepth),
    new THREE.MeshStandardMaterial({
      color: "#d5dde5",
      metalness: 0.08,
      roughness: 0.72,
    }),
  );
  floorSlab.name = "room-floor-slab";
  floorSlab.position.y = -0.12;
  floorSlab.receiveShadow = true;
  shell.add(floorSlab);

  const wallTexture = createWallTexture();
  const wallMaterial = new THREE.MeshStandardMaterial({
    color: "#f8fbfd",
    map: wallTexture,
    transparent: true,
    opacity: WALL_OPACITY,
    metalness: 0.05,
    roughness: 0.68,
  });
  const trimMaterial = new THREE.MeshStandardMaterial({
    color: "#f8fafc",
    metalness: 0.12,
    roughness: 0.32,
  });
  const darkTrimMaterial = new THREE.MeshStandardMaterial({
    color: "#dbe4ec",
    emissive: "#eef6fb",
    emissiveIntensity: 0.08,
    metalness: 0.08,
    roughness: 0.3,
  });
  const columnMaterial = new THREE.MeshStandardMaterial({
    color: "#ffffff",
    emissive: "#eef5f9",
    emissiveIntensity: 0.04,
    metalness: 0.04,
    roughness: 0.62,
  });
  const doorMaterial = new THREE.MeshStandardMaterial({
    color: "#8fa6b8",
    emissive: "#20384a",
    emissiveIntensity: 0.1,
    metalness: 0.18,
    roughness: 0.38,
  });
  const utilityCabinetMaterial = new THREE.MeshStandardMaterial({
    color: "#9aa3aa",
    emissive: "#3f474d",
    emissiveIntensity: 0.08,
    metalness: 0.18,
    roughness: 0.56,
  });
  const glassMaterial = new THREE.MeshStandardMaterial({
    color: "#c2efff",
    transparent: true,
    opacity: 0.68,
    emissive: "#2aa7ff",
    emissiveIntensity: 0.1,
    metalness: 0.08,
    roughness: 0.12,
    side: THREE.DoubleSide,
  });
  const accentMaterial = new THREE.MeshStandardMaterial({
    color: "#7ccce8",
    emissive: "#256b93",
    emissiveIntensity: 0.12,
    transparent: true,
    opacity: 0.28,
    metalness: 0.15,
    roughness: 0.36,
  });
  const floorEdgeMaterial = new THREE.MeshStandardMaterial({
    color: "#a7c7d8",
    emissive: "#2a6888",
    emissiveIntensity: 0.08,
    transparent: true,
    opacity: 0.22,
    metalness: 0.08,
    roughness: 0.42,
  });
  const addFeatureFrame = (
    name: string,
    width: number,
    height: number,
    position: THREE.Vector3,
    rotationY = 0,
  ) => {
    const frame = new THREE.Group();
    frame.name = name;
    frame.position.copy(position);
    frame.rotation.y = rotationY;
    const horizontal = new THREE.BoxGeometry(width + 0.12, 0.035, 0.035);
    const vertical = new THREE.BoxGeometry(0.035, height + 0.1, 0.035);
    [
      new THREE.Vector3(0, height / 2 + 0.035, 0),
      new THREE.Vector3(0, -height / 2 - 0.035, 0),
    ].forEach((offset) => {
      const rail = new THREE.Mesh(horizontal, darkTrimMaterial);
      rail.position.copy(offset);
      frame.add(rail);
    });
    [
      new THREE.Vector3(-width / 2 - 0.035, 0, 0),
      new THREE.Vector3(width / 2 + 0.035, 0, 0),
      new THREE.Vector3(0, 0, 0),
    ].forEach((offset) => {
      const rail = new THREE.Mesh(vertical, darkTrimMaterial);
      rail.position.copy(offset);
      frame.add(rail);
    });
    const middleRail = new THREE.Mesh(horizontal, darkTrimMaterial);
    middleRail.position.set(0, 0, 0);
    frame.add(middleRail);
    shell.add(frame);
    return frame;
  };
  const addWallColumn = (
    name: string,
    x: number,
    z: number,
    width = 0.42,
    depth = width,
  ) => {
    const column = new THREE.Mesh(
      new THREE.BoxGeometry(width, WALL_HEIGHT + 0.22, depth),
      columnMaterial,
    );
    column.name = name;
    column.position.set(x, (WALL_HEIGHT + 0.22) / 2, z);
    column.castShadow = false;
    column.receiveShadow = true;
    shell.add(column);
    return column;
  };
  const addUtilityCabinet = (
    name: string,
    x: number,
    z: number,
    rotationY = 0,
  ) => {
    const cabinet = new THREE.Group();
    cabinet.name = name;
    cabinet.position.set(x, 0, z);
    cabinet.rotation.y = rotationY;

    const body = new THREE.Mesh(
      new THREE.BoxGeometry(0.84, 1.28, 0.38),
      utilityCabinetMaterial,
    );
    body.name = `${name}-body`;
    body.position.y = 0.64;
    body.castShadow = true;
    body.receiveShadow = true;
    cabinet.add(body);

    [-1, 1].forEach((side) => {
      const doorPanel = new THREE.Mesh(
        new THREE.BoxGeometry(0.34, 1.1, 0.018),
        new THREE.MeshStandardMaterial({
          color: "#c6cdd3",
          metalness: 0.16,
          roughness: 0.5,
        }),
      );
      doorPanel.name = `${name}-door-panel`;
      doorPanel.position.set(side * 0.18, 0.66, 0.2);
      cabinet.add(doorPanel);

      const handle = new THREE.Mesh(
        new THREE.BoxGeometry(0.018, 0.28, 0.022),
        darkTrimMaterial,
      );
      handle.name = `${name}-handle`;
      handle.position.set(side * 0.05, 0.64, 0.212);
      cabinet.add(handle);
    });

    const vent = new THREE.Mesh(
      new THREE.BoxGeometry(0.52, 0.045, 0.02),
      darkTrimMaterial,
    );
    vent.name = `${name}-vent`;
    vent.position.set(0, 1.1, 0.225);
    cabinet.add(vent);

    shell.add(cabinet);
    return cabinet;
  };
  const wallSpecs: Array<[number, number, number, number, number]> = [
    [floorWidth, WALL_HEIGHT, WALL_THICKNESS, 0, -floorDepth / 2],
    [floorWidth, WALL_HEIGHT, WALL_THICKNESS, 0, floorDepth / 2],
    [WALL_THICKNESS, WALL_HEIGHT, floorDepth, -floorWidth / 2, 0],
    [WALL_THICKNESS, WALL_HEIGHT, floorDepth, floorWidth / 2, 0],
  ];
  wallSpecs.forEach(([width, height, depth, x, z], index) => {
    const wall = new THREE.Mesh(
      new THREE.BoxGeometry(width, height, depth),
      wallMaterial,
    );
    wall.name = `room-wall-${index}`;
    wall.position.set(x, height / 2, z);
    wall.castShadow = false;
    wall.receiveShadow = true;
    shell.add(wall);
  });

  [
    [-floorWidth / 2, -floorDepth / 2],
    [floorWidth / 2, -floorDepth / 2],
    [-floorWidth / 2, floorDepth / 2],
    [floorWidth / 2, floorDepth / 2],
  ].forEach(([x, z], index) => {
    addWallColumn(`room-column-${index}`, x, z, 0.44);
  });

  (
    [
      [-floorWidth * 0.3, floorDepth / 2 - 0.1, 0.36, 0.28],
      [floorWidth * 0.3, floorDepth / 2 - 0.1, 0.36, 0.28],
      [-floorWidth / 2 + 0.1, -floorDepth * 0.2, 0.28, 0.5],
      [floorWidth / 2 - 0.1, floorDepth * 0.2, 0.28, 0.5],
    ] as Array<[number, number, number, number]>
  ).forEach(([x, z, width, depth], index) => {
    addWallColumn(`room-structure-column-${index}`, x, z, width, depth);
  });

  const frontTrim = new THREE.Mesh(
    new THREE.BoxGeometry(floorWidth, 0.06, 0.055),
    trimMaterial,
  );
  frontTrim.name = "room-front-trim";
  frontTrim.position.set(0, WALL_HEIGHT + 0.04, -floorDepth / 2 - 0.015);
  shell.add(frontTrim);

  const backTrim = frontTrim.clone();
  backTrim.name = "room-back-trim";
  backTrim.position.z = floorDepth / 2 + 0.015;
  shell.add(backTrim);

  [
    [floorWidth - 0.7, 0, -floorDepth / 2 - 0.06, 0],
    [floorWidth - 0.7, 0, floorDepth / 2 + 0.06, 0],
    [floorDepth - 0.7, -floorWidth / 2 - 0.06, 0, Math.PI / 2],
    [floorDepth - 0.7, floorWidth / 2 + 0.06, 0, Math.PI / 2],
  ].forEach(([length, x, z, rotation], index) => {
    const accent = new THREE.Mesh(
      new THREE.BoxGeometry(length, 0.018, 0.018),
      accentMaterial,
    );
    accent.name = `room-wall-accent-${index}`;
    accent.position.set(x, WALL_HEIGHT + 0.11, z);
    accent.rotation.y = rotation;
    shell.add(accent);
  });

  [
    [floorWidth, 0.035, 0.035, 0, -floorDepth / 2, 0],
    [floorWidth, 0.035, 0.035, 0, floorDepth / 2, 0],
    [floorDepth, 0.035, 0.035, -floorWidth / 2, 0, Math.PI / 2],
    [floorDepth, 0.035, 0.035, floorWidth / 2, 0, Math.PI / 2],
  ].forEach(([length, height, depth, x, z, rotation], index) => {
    const edge = new THREE.Mesh(
      new THREE.BoxGeometry(length, height, depth),
      floorEdgeMaterial,
    );
    edge.name = `room-floor-edge-${index}`;
    edge.position.set(x, 0.015, z);
    edge.rotation.y = rotation;
    shell.add(edge);
  });

  const mainDoorGroup = new THREE.Group();
  mainDoorGroup.name = "room-main-door";
  mainDoorGroup.position.set(-floorWidth * 0.32, 0, -floorDepth / 2 - 0.062);
  const mainDoorWidth = 1.72;
  const mainDoorHeight = 1.42;

  const doorBackplate = new THREE.Mesh(
    new THREE.BoxGeometry(mainDoorWidth + 0.34, mainDoorHeight + 0.24, 0.045),
    new THREE.MeshStandardMaterial({
      color: "#eef3f7",
      metalness: 0.06,
      roughness: 0.52,
    }),
  );
  doorBackplate.name = "room-main-door-backplate";
  doorBackplate.position.set(0, mainDoorHeight / 2, -0.012);
  mainDoorGroup.add(doorBackplate);

  [-1, 1].forEach((side) => {
    const panel = new THREE.Mesh(
      new THREE.BoxGeometry(mainDoorWidth / 2 - 0.035, mainDoorHeight, 0.05),
      doorMaterial,
    );
    panel.name = `room-main-door-panel-${side}`;
    panel.position.set(side * (mainDoorWidth / 4), mainDoorHeight / 2, 0.025);
    panel.castShadow = false;
    panel.receiveShadow = true;
    mainDoorGroup.add(panel);

    const handle = new THREE.Mesh(
      new THREE.BoxGeometry(0.026, 0.28, 0.025),
      darkTrimMaterial,
    );
    handle.name = `room-main-door-handle-${side}`;
    handle.position.set(side * 0.08, mainDoorHeight * 0.52, 0.065);
    mainDoorGroup.add(handle);
  });

  const doorCenterLine = new THREE.Mesh(
    new THREE.BoxGeometry(0.024, mainDoorHeight, 0.065),
    darkTrimMaterial,
  );
  doorCenterLine.name = "room-main-door-center-line";
  doorCenterLine.position.set(0, mainDoorHeight / 2, 0.06);
  mainDoorGroup.add(doorCenterLine);

  const doorHeader = new THREE.Mesh(
    new THREE.BoxGeometry(mainDoorWidth + 0.42, 0.1, 0.1),
    darkTrimMaterial,
  );
  doorHeader.name = "room-main-door-header";
  doorHeader.position.set(0, mainDoorHeight + 0.075, 0.04);
  mainDoorGroup.add(doorHeader);
  [-1, 1].forEach((side) => {
    const jamb = new THREE.Mesh(
      new THREE.BoxGeometry(0.1, mainDoorHeight + 0.22, 0.1),
      darkTrimMaterial,
    );
    jamb.name = `room-main-door-jamb-${side}`;
    jamb.position.set(
      side * (mainDoorWidth / 2 + 0.11),
      mainDoorHeight / 2,
      0.04,
    );
    mainDoorGroup.add(jamb);
  });
  const threshold = new THREE.Mesh(
    new THREE.BoxGeometry(mainDoorWidth + 0.48, 0.04, 0.38),
    new THREE.MeshStandardMaterial({
      color: "#cbd5e1",
      metalness: 0.1,
      roughness: 0.5,
    }),
  );
  threshold.name = "room-main-door-threshold";
  threshold.position.set(0, 0.02, 0.14);
  mainDoorGroup.add(threshold);
  shell.add(mainDoorGroup);

  const sideEntranceGroup = new THREE.Group();
  sideEntranceGroup.name = "room-visible-main-door";
  sideEntranceGroup.position.set(-floorWidth * 0.26, 0, floorDepth / 2 + 0.066);
  const sideDoorWidth = 1.94;
  const sideDoorHeight = 1.56;
  const visibleDoorFrameMaterial = new THREE.MeshStandardMaterial({
    color: "#5e7484",
    emissive: "#233744",
    emissiveIntensity: 0.08,
    metalness: 0.18,
    roughness: 0.44,
  });
  const visibleDoorPanelMaterial = new THREE.MeshStandardMaterial({
    color: "#7891a3",
    emissive: "#314f61",
    emissiveIntensity: 0.1,
    metalness: 0.16,
    roughness: 0.48,
  });
  const visibleDoorRecessMaterial = new THREE.MeshStandardMaterial({
    color: "#8ea1ad",
    emissive: "#405866",
    emissiveIntensity: 0.06,
    metalness: 0.08,
    roughness: 0.62,
  });
  const visibleDoorHandleMaterial = new THREE.MeshStandardMaterial({
    color: "#f0f5f8",
    emissive: "#8095a5",
    emissiveIntensity: 0.12,
    metalness: 0.42,
    roughness: 0.28,
  });
  const visibleDoorGlassMaterial = new THREE.MeshStandardMaterial({
    color: "#b7e9f8",
    transparent: true,
    opacity: 0.76,
    emissive: "#5cc2e1",
    emissiveIntensity: 0.12,
    metalness: 0.04,
    roughness: 0.16,
  });

  const sideDoorRecess = new THREE.Mesh(
    new THREE.BoxGeometry(sideDoorWidth + 0.44, sideDoorHeight + 0.34, 0.06),
    visibleDoorRecessMaterial,
  );
  sideDoorRecess.name = "room-visible-main-door-recess";
  sideDoorRecess.position.set(0, sideDoorHeight / 2, -0.02);
  sideEntranceGroup.add(sideDoorRecess);

  const addDoorFace = (suffix: string, z: number, direction: 1 | -1) => {
    [-1, 1].forEach((side) => {
      const panel = new THREE.Mesh(
        new THREE.BoxGeometry(sideDoorWidth / 2 - 0.055, sideDoorHeight, 0.05),
        visibleDoorPanelMaterial,
      );
      panel.name = `room-visible-main-door-${suffix}-panel-${side}`;
      panel.position.set(side * (sideDoorWidth / 4), sideDoorHeight / 2, z);
      panel.castShadow = false;
      panel.receiveShadow = true;
      sideEntranceGroup.add(panel);

      const glass = new THREE.Mesh(
        new THREE.BoxGeometry(sideDoorWidth / 2 - 0.28, 0.42, 0.018),
        visibleDoorGlassMaterial,
      );
      glass.name = `room-visible-main-door-${suffix}-window-${side}`;
      glass.position.set(
        side * (sideDoorWidth / 4),
        sideDoorHeight * 0.68,
        z + direction * 0.035,
      );
      sideEntranceGroup.add(glass);

      const kickPlate = new THREE.Mesh(
        new THREE.BoxGeometry(sideDoorWidth / 2 - 0.16, 0.18, 0.018),
        visibleDoorFrameMaterial,
      );
      kickPlate.name = `room-visible-main-door-${suffix}-kick-plate-${side}`;
      kickPlate.position.set(
        side * (sideDoorWidth / 4),
        0.22,
        z + direction * 0.037,
      );
      sideEntranceGroup.add(kickPlate);

      const handle = new THREE.Mesh(
        new THREE.BoxGeometry(0.034, 0.42, 0.034),
        visibleDoorHandleMaterial,
      );
      handle.name = `room-visible-main-door-${suffix}-handle-${side}`;
      handle.position.set(
        side * 0.085,
        sideDoorHeight * 0.48,
        z + direction * 0.055,
      );
      sideEntranceGroup.add(handle);
    });

    const centerLine = new THREE.Mesh(
      new THREE.BoxGeometry(0.034, sideDoorHeight + 0.02, 0.056),
      visibleDoorFrameMaterial,
    );
    centerLine.name = `room-visible-main-door-${suffix}-center-line`;
    centerLine.position.set(0, sideDoorHeight / 2, z + direction * 0.045);
    sideEntranceGroup.add(centerLine);
  };

  addDoorFace("front", 0.034, 1);
  addDoorFace("back", -0.128, -1);

  const sideDoorHeader = new THREE.Mesh(
    new THREE.BoxGeometry(sideDoorWidth + 0.46, 0.14, 0.12),
    visibleDoorFrameMaterial,
  );
  sideDoorHeader.name = "room-visible-main-door-header";
  sideDoorHeader.position.set(0, sideDoorHeight + 0.09, 0.06);
  sideEntranceGroup.add(sideDoorHeader);

  [-1, 1].forEach((side) => {
    const jamb = new THREE.Mesh(
      new THREE.BoxGeometry(0.14, sideDoorHeight + 0.26, 0.12),
      visibleDoorFrameMaterial,
    );
    jamb.name = `room-visible-main-door-jamb-${side}`;
    jamb.position.set(
      side * (sideDoorWidth / 2 + 0.12),
      sideDoorHeight / 2,
      0.06,
    );
    sideEntranceGroup.add(jamb);
  });

  const sideDoorThreshold = new THREE.Mesh(
    new THREE.BoxGeometry(sideDoorWidth + 0.24, 0.035, 0.22),
    new THREE.MeshStandardMaterial({
      color: "#64717c",
      emissive: "#1f2f3a",
      emissiveIntensity: 0.08,
      metalness: 0.18,
      roughness: 0.5,
    }),
  );
  sideDoorThreshold.name = "room-visible-main-door-threshold";
  sideDoorThreshold.position.set(0, 0.018, 0.1);
  sideEntranceGroup.add(sideDoorThreshold);
  shell.add(sideEntranceGroup);

  [-0.46, 0.46].forEach((offset, index) => {
    addUtilityCabinet(
      `room-utility-cabinet-back-${index}`,
      -floorWidth * 0.34 + offset,
      -floorDepth / 2 + 0.3,
      0,
    );
  });

  [-1, 1].forEach((side) => {
    const windowPanel = new THREE.Mesh(
      new THREE.BoxGeometry(1.24, 0.64, 0.032),
      glassMaterial,
    );
    windowPanel.name = "room-window";
    windowPanel.position.set(
      side * floorWidth * 0.27,
      1.05,
      floorDepth / 2 + 0.035,
    );
    shell.add(windowPanel);
    addFeatureFrame(
      "room-window-frame",
      1.3,
      0.7,
      new THREE.Vector3(side * floorWidth * 0.27, 1.05, floorDepth / 2 + 0.052),
    );
    const innerWindowPanel = new THREE.Mesh(
      new THREE.BoxGeometry(1.24, 0.64, 0.032),
      glassMaterial,
    );
    innerWindowPanel.name = "room-window-inner";
    innerWindowPanel.position.set(
      side * floorWidth * 0.27,
      1.05,
      floorDepth / 2 - 0.055,
    );
    shell.add(innerWindowPanel);
    addFeatureFrame(
      "room-window-inner-frame",
      1.3,
      0.7,
      new THREE.Vector3(side * floorWidth * 0.27, 1.05, floorDepth / 2 - 0.072),
    );
  });

  scene.add(shell);
  return shell;
};

const createEquipmentLayer = (
  device: Room3DRenderableDevice,
  rackUCount: number,
) => {
  const uStart = device.rack_u_start as number;
  const uSize = device.u_size as number;
  const height = Math.min(
    RACK_USABLE_HEIGHT * 0.36,
    Math.max(
      0.075,
      RACK_USABLE_HEIGHT * (Math.max(uSize, 1) / Math.max(rackUCount, 1)),
    ),
  );
  const geometry = new THREE.BoxGeometry(
    ROOM3D_RACK_WIDTH - 0.08,
    height,
    0.34,
  );
  const deviceWidth = ROOM3D_RACK_WIDTH - 0.08;
  const deviceDepth = 0.34;
  const alarmMode = deviceHasAlarmGlow(device);
  const { map, emissiveMap } = createEquipmentTexture(alarmMode);
  const frontMaterial = new THREE.MeshStandardMaterial({
    color: "#7893a8",
    map,
    emissive: "#ffffff",
    emissiveMap,
    emissiveIntensity: EQUIPMENT_FACE_EMISSIVE_INTENSITY,
    metalness: 0.28,
    roughness: 0.38,
  });
  const sideMaterial = new THREE.MeshStandardMaterial({
    color: "#6b7b89",
    map: createEquipmentSideTexture(),
    emissive: "#182838",
    emissiveIntensity: 0.1,
    metalness: 0.3,
    roughness: 0.42,
  });
  frontMaterial.userData.baseEmissiveIntensity = EQUIPMENT_FACE_EMISSIVE_INTENSITY;
  sideMaterial.userData.baseEmissiveIntensity = 0.1;
  const layer = new THREE.Mesh(geometry, [
    sideMaterial,
    sideMaterial,
    sideMaterial,
    sideMaterial,
    frontMaterial,
    frontMaterial,
  ]);
  layer.name = "rack-device";
  layer.position.set(
    0,
    getRackUnitCenterY(uStart, uSize, rackUCount),
    ROOM3D_RACK_DEPTH / 2 - 0.18,
  );
  layer.userData.device = device;
  layer.userData.baseZ = layer.position.z;
  layer.userData.targetZ = layer.position.z;
  layer.userData.height = height;
  layer.castShadow = true;

  if (alarmMode) {
    // Opaque chassis cannot transmit PointLight. Build a soft envelope that wraps
    // the device in Y/Z while keeping X ≤ device width so posts are not pierced.
    sideMaterial.emissive = new THREE.Color("#5a1a1a");
    sideMaterial.emissiveIntensity = EQUIPMENT_ALARM_SIDE_EMISSIVE_INTENSITY;
    sideMaterial.userData.baseEmissiveIntensity =
      EQUIPMENT_ALARM_SIDE_EMISSIVE_INTENSITY;
    // Keep front LED map on a white emissive so status lights stay readable.
    frontMaterial.emissive = new THREE.Color("#ffffff");
    frontMaterial.emissiveIntensity = EQUIPMENT_ALARM_FRONT_EMISSIVE_INTENSITY;
    frontMaterial.userData.baseEmissiveIntensity =
      EQUIPMENT_ALARM_FRONT_EMISSIVE_INTENSITY;

    const alarmCore = new THREE.Mesh(
      new THREE.BoxGeometry(
        Math.max(0.08, deviceWidth * 0.72),
        Math.max(0.04, height * 0.62),
        deviceDepth * 0.48,
      ),
      createAlarmGlowMaterial(EQUIPMENT_ALARM_CORE_OPACITY),
    );
    alarmCore.name = "rack-device-alarm-core";
    alarmCore.position.set(0, 0, -0.02);
    layer.add(alarmCore);

    // Envelope: slightly taller/deeper for wrap feeling; width stays inside device.
    const alarmHalo = new THREE.Mesh(
      new THREE.BoxGeometry(
        Math.max(0.1, deviceWidth * 0.98),
        Math.max(0.06, height * 1.14),
        deviceDepth * 1.08,
      ),
      createAlarmGlowMaterial(EQUIPMENT_ALARM_HALO_OPACITY),
    );
    alarmHalo.name = "rack-device-alarm-halo";
    alarmHalo.position.set(0, 0, 0.02);
    layer.add(alarmHalo);

    // Soft front spill plane — width clamped to device so it stays between posts.
    const alarmFrontSpill = new THREE.Mesh(
      new THREE.PlaneGeometry(
        Math.max(0.12, deviceWidth * 0.92),
        Math.max(0.06, height * 1.2),
      ),
      createAlarmGlowMaterial(0.55),
    );
    alarmFrontSpill.name = "rack-device-alarm-front-spill";
    alarmFrontSpill.position.set(0, 0, deviceDepth * 0.52);
    layer.add(alarmFrontSpill);

    const alarmLight = new THREE.PointLight(
      EQUIPMENT_ALARM_GLOW_COLOR,
      EQUIPMENT_ALARM_GLOW_INTENSITY,
      EQUIPMENT_ALARM_GLOW_DISTANCE,
      1.6,
    );
    alarmLight.name = "rack-device-alarm-glow";
    // Slightly in front of the face, still inside the rack mouth.
    alarmLight.position.set(0, 0, deviceDepth * 0.22);
    layer.add(alarmLight);
  }

  return layer;
};

export const createRackVisual = (
  rack: Room3DRack,
  x: number,
  z: number,
): RackVisual => {
  const isConflict = Boolean(rack.is_conflict);
  const root = new THREE.Group();
  root.name = "rack";
  root.position.set(x, 0, z);
  root.userData.rack = rack;

  const bodyMaterial = new THREE.MeshStandardMaterial({
    color: "#82878b",
    emissive: "#555b60",
    emissiveIntensity: 0.28,
    metalness: 0.24,
    roughness: 0.48,
  });
  const sideMaterial = new THREE.MeshStandardMaterial({
    color: "#969ca2",
    map: createRackSideTexture(),
    emissive: "#555c62",
    emissiveIntensity: 0.24,
    metalness: 0.26,
    roughness: 0.48,
  });
  const pickMaterial = new THREE.MeshBasicMaterial({
    color: "#000000",
    transparent: true,
    opacity: 0.02,
    depthWrite: false,
  });
  const pickBody = new THREE.Mesh(
    new THREE.BoxGeometry(
      ROOM3D_RACK_WIDTH,
      ROOM3D_RACK_HEIGHT,
      ROOM3D_RACK_DEPTH,
    ),
    pickMaterial,
  );
  pickBody.name = "rack-pick-body";
  pickBody.position.y = ROOM3D_RACK_HEIGHT / 2;
  pickBody.userData.rack = rack;
  pickBody.userData.clickTarget = "rack";
  root.add(pickBody);

  const interiorShield = new THREE.Mesh(
    new THREE.PlaneGeometry(
      ROOM3D_RACK_WIDTH - 0.14,
      ROOM3D_RACK_HEIGHT - 0.18,
    ),
    new THREE.MeshBasicMaterial({
      color: "#000000",
      transparent: true,
      opacity: 0,
      depthWrite: false,
      side: THREE.DoubleSide,
    }),
  );
  interiorShield.name = "rack-interior-shield";
  interiorShield.position.set(
    0,
    ROOM3D_RACK_HEIGHT / 2,
    ROOM3D_RACK_DEPTH / 2 + 0.015,
  );
  interiorShield.userData.rack = rack;
  interiorShield.userData.clickTarget = "rack";
  root.add(interiorShield);

  const back = new THREE.Mesh(
    new THREE.BoxGeometry(ROOM3D_RACK_WIDTH, ROOM3D_RACK_HEIGHT, 0.055),
    bodyMaterial,
  );
  back.name = "rack-back";
  back.position.set(0, ROOM3D_RACK_HEIGHT / 2, -ROOM3D_RACK_DEPTH / 2 + 0.03);
  back.castShadow = true;
  back.receiveShadow = true;
  back.userData.rack = rack;
  root.add(back);

  const sideGeometry = new THREE.BoxGeometry(
    0.07,
    ROOM3D_RACK_HEIGHT,
    ROOM3D_RACK_DEPTH,
  );
  [-1, 1].forEach((side) => {
    const sidePanel = new THREE.Mesh(sideGeometry, sideMaterial);
    sidePanel.name = "rack-side";
    sidePanel.position.set(
      side * (ROOM3D_RACK_WIDTH / 2 - 0.035),
      ROOM3D_RACK_HEIGHT / 2,
      0,
    );
    sidePanel.castShadow = true;
    sidePanel.receiveShadow = true;
    sidePanel.userData.rack = rack;
    root.add(sidePanel);
  });

  const capGeometry = new THREE.BoxGeometry(
    ROOM3D_RACK_WIDTH,
    0.08,
    ROOM3D_RACK_DEPTH,
  );
  [0.04, ROOM3D_RACK_HEIGHT - 0.04].forEach((y) => {
    const cap = new THREE.Mesh(capGeometry, sideMaterial);
    cap.name = "rack-cap";
    cap.position.y = y;
    cap.castShadow = true;
    cap.receiveShadow = true;
    cap.userData.rack = rack;
    root.add(cap);
  });

  const railMaterial = new THREE.MeshStandardMaterial({
    color: "#c0c6cb",
    emissive: "#5d666d",
    emissiveIntensity: 0.12,
    metalness: 0.32,
    roughness: 0.34,
  });
  [-1, 1].forEach((side) => {
    const frontRail = new THREE.Mesh(
      new THREE.BoxGeometry(0.055, ROOM3D_RACK_HEIGHT - 0.1, 0.055),
      railMaterial,
    );
    frontRail.name = "rack-front-rail";
    frontRail.position.set(
      side * (ROOM3D_RACK_WIDTH / 2 - 0.04),
      ROOM3D_RACK_HEIGHT / 2,
      ROOM3D_RACK_DEPTH / 2 - 0.03,
    );
    frontRail.castShadow = true;
    frontRail.userData.rack = rack;
    root.add(frontRail);
  });

  const plinth = new THREE.Mesh(
    new THREE.BoxGeometry(
      ROOM3D_RACK_WIDTH + 0.06,
      0.08,
      ROOM3D_RACK_DEPTH + 0.06,
    ),
    new THREE.MeshStandardMaterial({
      color: "#687078",
      emissive: "#3d454d",
      emissiveIntensity: 0.12,
      metalness: 0.24,
      roughness: 0.5,
    }),
  );
  plinth.name = "rack-plinth";
  plinth.position.y = 0.02;
  plinth.userData.rack = rack;
  root.add(plinth);

  const top = new THREE.Mesh(
    new THREE.BoxGeometry(ROOM3D_RACK_WIDTH, 0.035, ROOM3D_RACK_DEPTH),
    new THREE.MeshStandardMaterial({
      color: "#7d858c",
      map: createRackTopTexture(
        getRoom3DPositionLabel(rack) || rack.rack_name,
        typeof rack.rack_type_name === "string"
          ? rack.rack_type_name.trim()
          : undefined,
      ),
      emissive: "#5a6268",
      emissiveIntensity: 0.24,
      metalness: 0.22,
      roughness: 0.46,
    }),
  );
  top.name = "rack-label";
  top.position.y = ROOM3D_RACK_HEIGHT + 0.025;
  top.userData.rack = rack;
  top.userData.clickTarget = "rack";
  root.add(top);

  const devices = getRoom3DRackDevices(rack);
  const rackUCount = Math.max(rack.u_count ?? 42, 1);
  const scaleMaterial = new THREE.MeshBasicMaterial({
    map: createRackScaleTexture(rackUCount),
    transparent: true,
    opacity: 0.88,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const scaleGeometry = new THREE.PlaneGeometry(0.085, RACK_USABLE_HEIGHT);
  [-1, 1].forEach((side) => {
    const scale = new THREE.Mesh(scaleGeometry, scaleMaterial);
    scale.name = "rack-u-scale";
    scale.position.set(
      side * (ROOM3D_RACK_WIDTH / 2 - 0.03),
      RACK_USABLE_BOTTOM + RACK_USABLE_HEIGHT / 2,
      ROOM3D_RACK_DEPTH / 2 + 0.014,
    );
    scale.userData.rack = rack;
    root.add(scale);
  });
  const deviceMeshes: THREE.Mesh[] = [];
  devices.forEach((device) => {
    const equipment = createEquipmentLayer(device, rackUCount);
    equipment.userData.rack = rack;
    equipment.userData.device = device;
    equipment.userData.clickTarget = "device";
    deviceMeshes.push(equipment);
    root.add(equipment);

    const shelf = new THREE.Mesh(
      new THREE.BoxGeometry(ROOM3D_RACK_WIDTH - 0.14, 0.014, 0.045),
      railMaterial,
    );
    shelf.name = "rack-device-shelf";
    shelf.position.set(
      0,
      Math.max(
        0.13,
        equipment.position.y -
          Number(equipment.userData.height || 0) / 2 -
          0.018,
      ),
      ROOM3D_RACK_DEPTH / 2 - 0.035,
    );
    shelf.userData.rack = rack;
    root.add(shelf);
  });

  const outline = new THREE.LineSegments(
    new THREE.EdgesGeometry(
      new THREE.BoxGeometry(
        ROOM3D_RACK_WIDTH + 0.07,
        ROOM3D_RACK_HEIGHT + 0.08,
        ROOM3D_RACK_DEPTH + 0.08,
      ),
    ),
    new THREE.LineBasicMaterial({
      color: isConflict ? "#ff3b30" : "#39f871",
      transparent: true,
      opacity: isConflict ? 0.78 : 0,
    }),
  );
  outline.name = "rack-outline";
  outline.position.y = ROOM3D_RACK_HEIGHT / 2;
  root.add(outline);

  if (isConflict) {
    const glowOutline = new THREE.LineSegments(
      new THREE.EdgesGeometry(
        new THREE.BoxGeometry(
          ROOM3D_RACK_WIDTH + 0.12,
          ROOM3D_RACK_HEIGHT + 0.13,
          ROOM3D_RACK_DEPTH + 0.13,
        ),
      ),
      new THREE.LineBasicMaterial({
        color: "#ff6b5f",
        transparent: true,
        opacity: 0.42,
      }),
    );
    glowOutline.name = "rack-conflict-outline-glow";
    glowOutline.position.y = ROOM3D_RACK_HEIGHT / 2;
    root.add(glowOutline);
  }

  return {
    rack,
    root,
    outline,
    interiorShield,
    pickTargets: [pickBody, interiorShield, top, ...deviceMeshes],
    deviceMeshes,
  };
};

export const setRackVisualState = (
  visual: RackVisual,
  options: {
    hovered: boolean;
    selected: boolean;
    selectedDeviceId?: string;
  },
) => {
  const outlineMaterial = visual.outline.material as THREE.LineBasicMaterial;
  if (visual.rack.is_conflict) {
    outlineMaterial.opacity = options.selected
      ? 1
      : options.hovered
        ? 0.92
        : 0.78;
  } else {
    outlineMaterial.opacity = options.selected
      ? 0.95
      : options.hovered
        ? 0.55
        : 0;
  }
  visual.deviceMeshes.forEach((mesh) => {
    const device = mesh.userData.device as Room3DRenderableDevice | undefined;
    const selected = Boolean(
      device && device.device_id === options.selectedDeviceId,
    );
    mesh.userData.targetZ =
      mesh.userData.baseZ + (selected ? ROOM3D_DEVICE_PULL_OUT_DISTANCE : 0);
    const materials = Array.isArray(mesh.material)
      ? mesh.material
      : [mesh.material];
    materials.forEach((material) => {
      if (material instanceof THREE.MeshStandardMaterial) {
        const baseEmissiveIntensity =
          typeof material.userData.baseEmissiveIntensity === "number"
            ? material.userData.baseEmissiveIntensity
            : 0.24;
        material.emissiveIntensity = selected
          ? Math.max(baseEmissiveIntensity, 0.72)
          : baseEmissiveIntensity;
      }
    });
  });
};

export const animateRackVisual = (visual: RackVisual) => {
  let isAnimating = false;
  visual.deviceMeshes.forEach((mesh) => {
    const targetZ =
      typeof mesh.userData.targetZ === "number"
        ? mesh.userData.targetZ
        : mesh.position.z;
    mesh.position.z = interpolateRoom3DValue(mesh.position.z, targetZ, 0.22);
    isAnimating = mesh.position.z !== targetZ || isAnimating;
  });

  return isAnimating;
};

export const disposeObject3D = (object: THREE.Object3D) => {
  object.traverse((child) => {
    if (child instanceof THREE.Mesh || child instanceof THREE.LineSegments) {
      child.geometry?.dispose();
      const material = child.material;
      const materials = Array.isArray(material) ? material : [material];
      materials.forEach((item) => {
        Object.values(item).forEach((value) => {
          if (value instanceof THREE.Texture) {
            value.dispose();
          }
        });
        item.dispose();
      });
    }
  });
};
