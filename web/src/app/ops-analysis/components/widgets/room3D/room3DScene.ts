import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type {
  Room3DRenderableDevice,
  Room3DResponse,
  Room3DRack,
} from "./room3DData";
import { getRoom3DSceneRacks } from "./room3DData";
import {
  ROOM3D_COL_GAP,
  ROOM3D_RACK_DEPTH,
  ROOM3D_RACK_HEIGHT,
  ROOM3D_RACK_DOOR_OPEN_ROTATION,
  ROOM3D_RACK_WIDTH,
  ROOM3D_ROW_GAP,
  animateRackVisual,
  buildRoomShell,
  createRackVisual,
  disposeObject3D,
  setRackVisualState,
  type RackVisual,
} from "./room3DMeshes";

export {
  ROOM3D_CELL_GAP,
  ROOM3D_COL_GAP,
  ROOM3D_DEVICE_PULL_OUT_DISTANCE,
  ROOM3D_RACK_DEPTH,
  ROOM3D_ROW_GAP,
} from "./room3DMeshes";

export interface Room3DSceneCallbacks {
  onHover: (state: { rack: Room3DRack; x: number; y: number } | null) => void;
  onSelect: (rack: Room3DRack | null) => void;
  onDeviceSelect?: (
    state: { rack: Room3DRack; device: Room3DRenderableDevice } | null,
  ) => void;
}

export interface Room3DSceneController {
  resetView: () => void;
  dispose: () => void;
}

export interface Room3DSceneOptions {
  transparentScene: boolean;
}

interface RackInteractionState {
  selectedRackId: string;
  openRackId: string;
  selectedDeviceId?: string;
}

interface PickedRoomObject {
  rackId: string;
  deviceId?: string;
  target?: "rack" | "door" | "device";
}

export const getRackDoorOpenRotation = () => ROOM3D_RACK_DOOR_OPEN_ROTATION;

const READABLE_RACK_CAMERA_DISTANCE = 6.4;
const RACK_DEVICE_VIEW_CAMERA_OFFSET = new THREE.Vector3(-2.35, 1.62, 3.25);
const RACK_DEVICE_VIEW_TARGET_OFFSET = new THREE.Vector3(-0.08, 0.88, 0.18);

export const shouldAutoFocusRack = (
  cameraDistance: number,
  readableDistance = READABLE_RACK_CAMERA_DISTANCE,
) => cameraDistance > readableDistance;

export const resolveRackClickState = (
  current: RackInteractionState,
  clickedRackId: string | null,
): RackInteractionState => {
  if (!clickedRackId) {
    return current;
  }

  if (current.selectedRackId === clickedRackId) {
    return {
      selectedRackId: clickedRackId,
      openRackId: current.openRackId === clickedRackId ? "" : clickedRackId,
    };
  }

  return {
    selectedRackId: clickedRackId,
    openRackId: clickedRackId,
  };
};

export const resolveRoomObjectClickState = (
  current: RackInteractionState,
  clicked: PickedRoomObject | null,
): Required<RackInteractionState> => {
  const normalized = {
    selectedRackId: current.selectedRackId,
    openRackId: current.openRackId,
    selectedDeviceId: current.selectedDeviceId || "",
  };

  if (!clicked) {
    return normalized;
  }

  if (clicked.deviceId) {
    return {
      selectedRackId: clicked.rackId,
      openRackId: clicked.rackId,
      selectedDeviceId:
        normalized.selectedDeviceId === clicked.deviceId
          ? ""
          : clicked.deviceId,
    };
  }

  if (
    clicked.target === "door" &&
    normalized.selectedRackId === clicked.rackId
  ) {
    return {
      selectedRackId: clicked.rackId,
      openRackId:
        normalized.openRackId === clicked.rackId ? "" : clicked.rackId,
      selectedDeviceId: "",
    };
  }

  const nextRackState = resolveRackClickState(
    normalized,
    normalized.selectedRackId === clicked.rackId &&
      normalized.openRackId === clicked.rackId
      ? null
      : clicked.rackId,
  );
  return {
    ...nextRackState,
    selectedDeviceId: "",
  };
};

const ROOM3D_ROOM_RECT_ASPECT = 1.38;
const ROOM3D_MIN_ROOM_RECT_ASPECT = 1.08;
const ROOM3D_FLOOR_SIDE_PADDING = 7.2;
const ROOM3D_MIN_FLOOR_WIDTH = 10.5;
const ROOM3D_MIN_FLOOR_DEPTH = 8.8;

const clampRoomRatio = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

const getRoomFloorStretchRatio = (
  dominantCount: number,
  secondaryCount: number,
) => {
  const dominance =
    Math.max(dominantCount - secondaryCount, 0) / Math.max(dominantCount, 1);
  const dominanceScale = clampRoomRatio(dominance / 0.625, 0, 1);
  const secondaryScale = clampRoomRatio(secondaryCount / 3, 0.5, 1);
  return (
    ROOM3D_MIN_ROOM_RECT_ASPECT +
    (ROOM3D_ROOM_RECT_ASPECT - ROOM3D_MIN_ROOM_RECT_ASPECT) *
      dominanceScale *
      secondaryScale
  );
};

export const buildRoomFloorSize = (maxRow: number, maxCol: number) => {
  const rackMatrixWidth = Math.max(
    (maxCol - 1) * ROOM3D_COL_GAP + ROOM3D_RACK_WIDTH,
    ROOM3D_RACK_WIDTH,
  );
  const rackMatrixDepth = Math.max(
    (maxRow - 1) * ROOM3D_ROW_GAP + ROOM3D_RACK_DEPTH,
    ROOM3D_RACK_DEPTH,
  );
  const baseWidth = Math.max(
    rackMatrixWidth + ROOM3D_FLOOR_SIDE_PADDING,
    ROOM3D_MIN_FLOOR_WIDTH,
  );
  const baseDepth = Math.max(
    rackMatrixDepth + ROOM3D_FLOOR_SIDE_PADDING,
    ROOM3D_MIN_FLOOR_DEPTH,
  );
  const rowDominant =
    maxRow > maxCol && rackMatrixDepth > rackMatrixWidth * 1.35;

  if (rowDominant) {
    const stretchRatio = getRoomFloorStretchRatio(maxRow, maxCol);
    return {
      floorWidth: Math.max(baseWidth, baseDepth * stretchRatio),
      floorDepth: baseDepth,
    };
  }

  const stretchRatio = getRoomFloorStretchRatio(maxCol, maxRow);
  return {
    floorWidth: baseWidth,
    floorDepth: Math.max(baseDepth, baseWidth * stretchRatio),
  };
};

const buildInitialCameraPosition = (
  maxRow: number,
  maxCol: number,
  floorWidth: number,
  floorDepth: number,
) => {
  const rackSpan = Math.max(maxRow * ROOM3D_ROW_GAP, maxCol * ROOM3D_COL_GAP);
  const roomSpan = Math.max(floorWidth, floorDepth) * 0.68;
  const span = Math.max(rackSpan, roomSpan, 9);
  return new THREE.Vector3(span * 0.9, span * 0.72 + 4.2, span * 0.95);
};

const getResponsiveCameraPosition = (
  basePosition: THREE.Vector3,
  aspect: number,
) => {
  if (aspect < 0.8) {
    const narrowScale = Math.min(0.8 / Math.max(aspect, 0.1), 2.2);
    return new THREE.Vector3(
      basePosition.x * narrowScale * 0.45,
      basePosition.y * narrowScale * 1.6,
      basePosition.z * narrowScale * 1.6,
    );
  }

  return basePosition.clone();
};

export const createRoom3DScene = (
  mountNode: HTMLDivElement,
  roomData: Room3DResponse,
  options: Room3DSceneOptions,
  callbacks: Room3DSceneCallbacks,
): Room3DSceneController => {
  const sceneRacks = getRoom3DSceneRacks(roomData);
  const maxRow = Math.max(...sceneRacks.map((rack) => rack.row), 1);
  const maxCol = Math.max(...sceneRacks.map((rack) => rack.col), 1);
  const centerX = ((maxCol - 1) * ROOM3D_COL_GAP) / 2;
  const centerZ = ((maxRow - 1) * ROOM3D_ROW_GAP) / 2;
  const { floorWidth, floorDepth } = buildRoomFloorSize(maxRow, maxCol);
  const scene = new THREE.Scene();
  if (!options.transparentScene) {
    scene.background = new THREE.Color("#08111f");
    scene.fog = new THREE.Fog("#08111f", 18, 64);
  }

  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 1000);
  const initialCameraPosition = buildInitialCameraPosition(
    maxRow,
    maxCol,
    floorWidth,
    floorDepth,
  );
  camera.position.copy(initialCameraPosition);
  camera.lookAt(0, 0, 0);

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: options.transparentScene,
    powerPreference: "high-performance",
  });
  if (options.transparentScene) {
    renderer.setClearColor(0x000000, 0);
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.18;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  mountNode.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 1.25;
  controls.maxDistance = Math.max(floorWidth, floorDepth, 10) * 2.8;
  controls.target.set(0, 0, 0);
  controls.update();

  const ambientLight = new THREE.AmbientLight("#dfe9f8", 0.86);
  const hemisphereLight = new THREE.HemisphereLight("#d8f5ff", "#9aa6b4", 0.58);
  const keyLight = new THREE.DirectionalLight("#ffffff", 1.32);
  keyLight.position.set(5, 8, 6);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.width = 1024;
  keyLight.shadow.mapSize.height = 1024;
  keyLight.shadow.radius = 3;
  const fillLight = new THREE.DirectionalLight("#9fdcff", 0.72);
  fillLight.position.set(-7, 5, -4);
  const cyanRoomLight = new THREE.PointLight("#33d8ff", 0.9, 18);
  cyanRoomLight.position.set(0, 3.4, 0);
  scene.add(ambientLight, hemisphereLight, keyLight, fillLight, cyanRoomLight);

  buildRoomShell(scene, floorWidth, floorDepth);

  const visuals = new Map<string, RackVisual>();
  const pickTargets: THREE.Object3D[] = [];
  sceneRacks.forEach((rack) => {
    const visual = createRackVisual(
      rack,
      (rack.col - 1) * ROOM3D_COL_GAP - centerX,
      (rack.row - 1) * ROOM3D_ROW_GAP - centerZ,
    );
    scene.add(visual.root);
    visuals.set(rack.rack_id, visual);
    pickTargets.push(...visual.pickTargets);
  });

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let hoveredRackId = "";
  let selectedRackId = "";
  let openRackId = "";
  let selectedDeviceId = "";
  let hasUserInteracted = false;
  let desiredCameraPosition: THREE.Vector3 | null = null;
  let desiredTarget: THREE.Vector3 | null = null;

  controls.addEventListener("start", () => {
    hasUserInteracted = true;
    desiredCameraPosition = null;
    desiredTarget = null;
  });

  const updateVisualStates = () => {
    visuals.forEach((visual, rackId) => {
      setRackVisualState(visual, {
        hovered: rackId === hoveredRackId,
        selected: rackId === selectedRackId,
        open: rackId === openRackId,
        selectedDeviceId,
      });
    });
  };

  const pickRack = (event: PointerEvent) => {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(pickTargets, false);
    const firstHit = hits[0];
    const deviceHit = hits.find((item) => {
      const rack = item.object.userData?.rack as Room3DRack | undefined;
      return Boolean(
        rack?.rack_id === openRackId && item.object.userData?.device,
      );
    });
    const openRackInteriorHit = hits.find((item) => {
      const rack = item.object.userData?.rack as Room3DRack | undefined;
      return Boolean(
        rack?.rack_id === openRackId &&
        item.object.userData?.clickTarget === "rack",
      );
    });
    const hit =
      deviceHit ||
      (firstHit?.object.userData?.clickTarget === "door"
        ? firstHit
        : openRackInteriorHit || firstHit);
    const rack = hit?.object?.userData?.rack as Room3DRack | undefined;
    const device = hit?.object?.userData?.device as
      | Room3DRenderableDevice
      | undefined;
    const target = hit?.object?.userData?.clickTarget as
      | PickedRoomObject["target"]
      | undefined;
    return rack ? { rack, device, target } : undefined;
  };

  const focusRack = (rack: Room3DRack) => {
    const visual = visuals.get(rack.rack_id);
    if (!visual) {
      return;
    }
    const target = visual.root.position
      .clone()
      .add(RACK_DEVICE_VIEW_TARGET_OFFSET);
    desiredTarget = target;
    desiredCameraPosition = target.clone().add(RACK_DEVICE_VIEW_CAMERA_OFFSET);
  };

  const getRackCameraDistance = (rack: Room3DRack) => {
    const visual = visuals.get(rack.rack_id);
    if (!visual) {
      return Number.POSITIVE_INFINITY;
    }
    return camera.position.distanceTo(visual.root.position);
  };

  const getRackScreenPoint = (rack: Room3DRack) => {
    const visual = visuals.get(rack.rack_id);
    const rect = renderer.domElement.getBoundingClientRect();
    if (!visual) {
      return { x: rect.left, y: rect.top };
    }

    const projected = visual.root.position
      .clone()
      .add(
        new THREE.Vector3(
          ROOM3D_RACK_WIDTH / 2 + 0.18,
          ROOM3D_RACK_HEIGHT * 0.58,
          0,
        ),
      )
      .project(camera);
    return {
      x: rect.left + ((projected.x + 1) / 2) * rect.width,
      y: rect.top + ((1 - projected.y) / 2) * rect.height,
    };
  };

  const handlePointerMove = (event: PointerEvent) => {
    const rack = pickRack(event);
    hoveredRackId = rack?.rack.rack_id || "";
    updateVisualStates();
    if (!rack) {
      callbacks.onHover(null);
      renderer.domElement.style.cursor = "grab";
      return;
    }
    renderer.domElement.style.cursor = "pointer";
    callbacks.onHover({ rack: rack.rack, ...getRackScreenPoint(rack.rack) });
  };

  const handlePointerLeave = () => {
    hoveredRackId = "";
    updateVisualStates();
    callbacks.onHover(null);
    renderer.domElement.style.cursor = "grab";
  };

  const handleClick = (event: PointerEvent) => {
    const rack = pickRack(event);
    if (!rack) {
      if (!openRackId) {
        selectedRackId = "";
        selectedDeviceId = "";
        callbacks.onSelect(null);
        callbacks.onDeviceSelect?.(null);
      }
      updateVisualStates();
      return;
    }

    if (rack.rack.is_conflict) {
      selectedRackId = rack.rack.rack_id;
      openRackId = "";
      selectedDeviceId = "";
      callbacks.onSelect(rack.rack);
      callbacks.onDeviceSelect?.(null);
      updateVisualStates();
      return;
    }

    const previousOpenRackId = openRackId;
    const nextState = resolveRoomObjectClickState(
      { selectedRackId, openRackId, selectedDeviceId },
      {
        rackId: rack.rack.rack_id,
        deviceId: rack.device?.device_id,
        target: rack.device ? "device" : rack.target || "rack",
      },
    );
    selectedRackId = nextState.selectedRackId;
    openRackId = nextState.openRackId;
    selectedDeviceId = nextState.selectedDeviceId;
    callbacks.onSelect(rack.rack);
    callbacks.onDeviceSelect?.(
      rack.device && selectedDeviceId
        ? { rack: rack.rack, device: rack.device }
        : null,
    );
    if (
      openRackId &&
      openRackId !== previousOpenRackId &&
      shouldAutoFocusRack(getRackCameraDistance(rack.rack))
    ) {
      focusRack(rack.rack);
    }
    updateVisualStates();
  };

  const resize = () => {
    const width = mountNode.clientWidth || 1;
    const height = mountNode.clientHeight || 1;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    if (!hasUserInteracted && !desiredCameraPosition) {
      camera.position.copy(
        getResponsiveCameraPosition(initialCameraPosition, camera.aspect),
      );
      controls.target.set(0, 0, 0);
      controls.update();
    }
  };

  const resetView = () => {
    selectedRackId = "";
    openRackId = "";
    hoveredRackId = "";
    selectedDeviceId = "";
    hasUserInteracted = false;
    desiredCameraPosition = getResponsiveCameraPosition(
      initialCameraPosition,
      camera.aspect,
    );
    desiredTarget = new THREE.Vector3(0, 0, 0);
    callbacks.onHover(null);
    callbacks.onSelect(null);
    callbacks.onDeviceSelect?.(null);
    updateVisualStates();
  };

  renderer.domElement.addEventListener("pointermove", handlePointerMove);
  renderer.domElement.addEventListener("pointerleave", handlePointerLeave);
  renderer.domElement.addEventListener("click", handleClick);

  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(mountNode);
  resize();
  updateVisualStates();

  let animationFrame = 0;
  const animate = () => {
    visuals.forEach(animateRackVisual);
    if (desiredCameraPosition && desiredTarget) {
      camera.position.lerp(desiredCameraPosition, 0.08);
      controls.target.lerp(desiredTarget, 0.1);
      if (
        camera.position.distanceTo(desiredCameraPosition) < 0.02 &&
        controls.target.distanceTo(desiredTarget) < 0.02
      ) {
        desiredCameraPosition = null;
        desiredTarget = null;
      }
    }
    controls.update();
    renderer.render(scene, camera);
    animationFrame = window.requestAnimationFrame(animate);
  };
  animate();

  return {
    resetView,
    dispose: () => {
      window.cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointermove", handlePointerMove);
      renderer.domElement.removeEventListener(
        "pointerleave",
        handlePointerLeave,
      );
      renderer.domElement.removeEventListener("click", handleClick);
      controls.dispose();
      disposeObject3D(scene);
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
};
