import * as THREE from "three";
import {
  getRoom3DPositionLabel,
  getRoom3DRackDevices,
  type Room3DRack,
  type Room3DRenderableDevice,
} from "./room3DData";

export interface RackVisual {
  rack: Room3DRack;
  root: THREE.Group;
  doorGroup: THREE.Group;
  outline: THREE.LineSegments;
  interiorShield: THREE.Mesh;
  pickTargets: THREE.Object3D[];
  targetDoorRotation: number;
  deviceMeshes: THREE.Mesh[];
}

export const ROOM3D_COL_GAP = 1.18;
export const ROOM3D_ROW_GAP = 4.6;
export const ROOM3D_RACK_WIDTH = 1.05;
export const ROOM3D_RACK_DEPTH = 1.2;
export const ROOM3D_RACK_HEIGHT = 1.95;
export const ROOM3D_RACK_DOOR_OPEN_ROTATION = Math.PI * 0.62;
export const ROOM3D_DEVICE_PULL_OUT_DISTANCE = 0.26;

const WALL_HEIGHT = ROOM3D_RACK_HEIGHT;
const WALL_THICKNESS = 0.1;
const WALL_OPACITY = 0.98;
const RACK_USABLE_BOTTOM = 0.12;
const RACK_USABLE_TOP_PADDING = 0.1;
const RACK_USABLE_HEIGHT =
  ROOM3D_RACK_HEIGHT - RACK_USABLE_BOTTOM - RACK_USABLE_TOP_PADDING;

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

const createDoorTexture = () =>
  createCanvasTexture(160, 260, (context) => {
    const gradient = context.createLinearGradient(0, 0, 160, 260);
    gradient.addColorStop(0, "#a9aeb3");
    gradient.addColorStop(0.48, "#7b838a");
    gradient.addColorStop(1, "#b4b8bd");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 160, 260);
    context.strokeStyle = "rgba(248,251,253,0.58)";
    context.lineWidth = 2;
    context.strokeRect(8, 8, 144, 244);
    context.fillStyle = "rgba(61,70,78,0.72)";
    context.fillRect(20, 24, 120, 196);
    context.fillStyle = "rgba(224,238,246,0.22)";
    for (let y = 28; y < 216; y += 9) {
      context.fillRect(28, y, 88, 1.2);
    }
    context.fillStyle = "rgba(226,239,247,0.18)";
    for (let x = 30; x < 120; x += 10) {
      context.fillRect(x, 28, 1.2, 188);
    }
    context.fillStyle = "rgba(12,18,24,0.3)";
    for (let y = 34; y < 210; y += 10) {
      for (let x = 36; x < 116; x += 12) {
        context.fillRect(x, y, 3.4, 3.4);
      }
    }
    context.strokeStyle = "rgba(115, 214, 255, 0.32)";
    context.strokeRect(18, 22, 124, 200);
    context.fillStyle = "rgba(248,251,253,0.78)";
    context.fillRect(22, 104, 7, 34);
    context.fillStyle = "rgba(5,10,16,0.86)";
    context.fillRect(24, 108, 3, 26);
  });

const createEquipmentTexture = () =>
  createCanvasTexture(320, 96, (context) => {
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
      for (let y = 35; y < 55; y += 6) {
        for (let x = left + 5; x < left + 48; x += 7) {
          context.fillRect(x, y, 3, 2);
        }
      }
    }
    context.fillStyle = "#47e8ff";
    for (let x = 286; x < 310; x += 8) {
      context.beginPath();
      context.arc(x, 48, 2.4, 0, Math.PI * 2);
      context.fill();
    }
    context.fillStyle = "rgba(91, 234, 255, 0.42)";
    context.fillRect(276, 31, 3, 34);
  });

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
  const frontMaterial = new THREE.MeshStandardMaterial({
    color: "#7893a8",
    map: createEquipmentTexture(),
    emissive: "#1b536c",
    emissiveIntensity: 0.24,
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

  const doorGroup = new THREE.Group();
  doorGroup.name = "rack-door-group";
  doorGroup.position.set(
    ROOM3D_RACK_WIDTH / 2,
    0,
    ROOM3D_RACK_DEPTH / 2 + 0.025,
  );
  doorGroup.userData.rack = rack;
  const door = new THREE.Mesh(
    new THREE.BoxGeometry(ROOM3D_RACK_WIDTH, ROOM3D_RACK_HEIGHT, 0.045),
    new THREE.MeshStandardMaterial({
      color: "#9ca2a8",
      map: createDoorTexture(),
      emissive: "#5d656b",
      emissiveIntensity: 0.24,
      metalness: 0.22,
      roughness: 0.46,
    }),
  );
  door.name = "rack-door";
  door.position.set(-ROOM3D_RACK_WIDTH / 2, ROOM3D_RACK_HEIGHT / 2, 0);
  door.castShadow = true;
  door.userData.rack = rack;
  door.userData.clickTarget = "door";
  doorGroup.add(door);
  root.add(doorGroup);

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
    doorGroup,
    outline,
    interiorShield,
    pickTargets: [pickBody, interiorShield, top, door, ...deviceMeshes],
    targetDoorRotation: 0,
    deviceMeshes,
  };
};

export const setRackVisualState = (
  visual: RackVisual,
  options: {
    hovered: boolean;
    selected: boolean;
    open: boolean;
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
    visual.targetDoorRotation = 0;
  } else {
    outlineMaterial.opacity = options.selected
      ? 0.95
      : options.hovered
        ? 0.55
        : 0;
    visual.targetDoorRotation = options.open
      ? ROOM3D_RACK_DOOR_OPEN_ROTATION
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
        material.emissiveIntensity = selected ? 0.5 : 0.24;
      }
    });
  });
};

export const animateRackVisual = (visual: RackVisual) => {
  visual.doorGroup.rotation.y +=
    (visual.targetDoorRotation - visual.doorGroup.rotation.y) * 0.16;
  visual.deviceMeshes.forEach((mesh) => {
    const targetZ =
      typeof mesh.userData.targetZ === "number"
        ? mesh.userData.targetZ
        : mesh.position.z;
    mesh.position.z += (targetZ - mesh.position.z) * 0.18;
  });
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
