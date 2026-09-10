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
  ROOM3D_FRONT_AISLE_EXTRA,
  ROOM3D_RACK_DEPTH,
  ROOM3D_RACK_HEIGHT,
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
  ROOM3D_COL_GAP,
  ROOM3D_DEVICE_PULL_OUT_DISTANCE,
  ROOM3D_RACK_DEPTH,
  ROOM3D_ROW_GAP,
} from "./room3DMeshes";

export interface Room3DSceneCallbacks {
  onHover: (state: { rack: Room3DRack; x: number; y: number } | null) => void;
  onSelect: (rack: Room3DRack | null) => void;
  onFirstRender?: () => void;
  onDeviceSelect?: (
    state: { rack: Room3DRack; device: Room3DRenderableDevice } | null,
  ) => void;
}

export interface Room3DSceneController {
  resetView: () => void;
  resize: () => void;
  dispose: () => void;
}

interface RackInteractionState {
  selectedRackId: string;
  openRackId: string;
  selectedDeviceId?: string;
}

interface PickedRoomObject {
  rackId: string;
  deviceId?: string;
  target?: "rack" | "device";
}

interface PointerCoordinates {
  clientX: number;
  clientY: number;
}

interface HoverNotification {
  rackId: string;
  x: number;
  y: number;
}

const READABLE_RACK_CAMERA_DISTANCE = 6.4;
const HOVER_POSITION_EPSILON = 0.5;
const ROOM3D_VIEW_CENTERING_ITERATIONS = 6;
const ROOM3D_VIEW_CENTERING_EPSILON = 0.001;
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

const ROOM3D_MAX_DEPTH_TO_WIDTH_RATIO = 2.8;
const ROOM3D_FLOOR_WIDTH_PADDING = 3.4;
const ROOM3D_FLOOR_DEPTH_PADDING = 5.0;
const ROOM3D_MIN_FLOOR_WIDTH = 4.5;
const ROOM3D_MIN_FLOOR_DEPTH = 4.0;

export const buildRoomFloorSize = (maxRow: number, maxCol: number) => {
  const rackMatrixWidth = Math.max(
    (maxCol - 1) * ROOM3D_COL_GAP + ROOM3D_RACK_WIDTH,
    ROOM3D_RACK_WIDTH,
  );
  const rackMatrixDepth = Math.max(
    (maxRow - 1) * ROOM3D_ROW_GAP + ROOM3D_RACK_DEPTH,
    ROOM3D_RACK_DEPTH,
  );
  const frontAisleExtra = maxRow >= 1 ? ROOM3D_FRONT_AISLE_EXTRA : 0;
  const baseWidth = Math.max(
    rackMatrixWidth + ROOM3D_FLOOR_WIDTH_PADDING,
    ROOM3D_MIN_FLOOR_WIDTH,
  );
  const baseDepth = Math.max(
    rackMatrixDepth + ROOM3D_FLOOR_DEPTH_PADDING + frontAisleExtra,
    ROOM3D_MIN_FLOOR_DEPTH + frontAisleExtra,
  );
  const rowDominant =
    maxRow > maxCol && rackMatrixDepth > rackMatrixWidth * 1.35;

  if (rowDominant) {
    return {
      floorWidth: Math.max(
        baseWidth,
        baseDepth / ROOM3D_MAX_DEPTH_TO_WIDTH_RATIO,
      ),
      floorDepth: baseDepth,
    };
  }

  return {
    floorWidth: baseWidth,
    floorDepth: baseDepth,
  };
};

const buildInitialCameraPosition = (
  maxRow: number,
  maxCol: number,
  floorWidth: number,
  floorDepth: number,
) => {
  if (floorDepth > floorWidth * 1.35) {
    const span = Math.max(floorDepth * 0.68, floorWidth * 1.25, 9);
    return new THREE.Vector3(span * 0.9, span * 0.38 + 2.5, span * 1.14);
  }

  const rackSpan = Math.max(maxRow * ROOM3D_ROW_GAP, maxCol * ROOM3D_COL_GAP);
  const roomSpan = Math.max(floorWidth, floorDepth) * 0.72;
  const span = Math.max(rackSpan, roomSpan, 9);
  return new THREE.Vector3(span * 0.95, span * 0.5 + 2.5, span * 1.05);
};

export const buildRoom3DSceneLayout = (
  racks: Array<Pick<Room3DRack, "row" | "col">>,
) => {
  const maxRow = Math.max(...racks.map((rack) => rack.row), 1);
  const maxCol = Math.max(...racks.map((rack) => rack.col), 1);
  const { floorWidth, floorDepth } = buildRoomFloorSize(maxRow, maxCol);

  return {
    maxRow,
    maxCol,
    floorWidth,
    floorDepth,
    initialCameraPosition: buildInitialCameraPosition(
      maxRow,
      maxCol,
      floorWidth,
      floorDepth,
    ),
  };
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

export const buildRoom3DInitialView = (
  layout: Pick<
    ReturnType<typeof buildRoom3DSceneLayout>,
    "floorWidth" | "floorDepth" | "initialCameraPosition"
  >,
  aspect: number,
) => {
  const safeAspect = Math.max(aspect, 0.1);
  const cameraPosition = getResponsiveCameraPosition(
    layout.initialCameraPosition,
    safeAspect,
  );
  const camera = new THREE.PerspectiveCamera(42, safeAspect, 0.1, 1000);
  camera.position.copy(cameraPosition);
  const target = new THREE.Vector3(0, 0, 0);

  for (
    let iteration = 0;
    iteration < ROOM3D_VIEW_CENTERING_ITERATIONS;
    iteration += 1
  ) {
    camera.lookAt(target);
    camera.updateMatrixWorld(true);
    const projectedBounds = [-1, 1].flatMap((xDirection) =>
      [0, ROOM3D_RACK_HEIGHT].flatMap((height) =>
        [-1, 1].map((zDirection) =>
          new THREE.Vector3(
            (xDirection * layout.floorWidth) / 2,
            height,
            (zDirection * layout.floorDepth) / 2,
          ).project(camera),
        ),
      ),
    );
    const projectedX = projectedBounds.map((point) => point.x);
    const projectedY = projectedBounds.map((point) => point.y);
    const centerX = (Math.min(...projectedX) + Math.max(...projectedX)) / 2;
    const centerY = (Math.min(...projectedY) + Math.max(...projectedY)) / 2;

    if (
      Math.abs(centerX) <= ROOM3D_VIEW_CENTERING_EPSILON &&
      Math.abs(centerY) <= ROOM3D_VIEW_CENTERING_EPSILON
    ) {
      break;
    }

    const targetDistance = camera.position.distanceTo(target);
    const halfHeightAtTarget =
      Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * targetDistance;
    const halfWidthAtTarget = halfHeightAtTarget * safeAspect;
    const cameraRight = new THREE.Vector3(1, 0, 0).applyQuaternion(
      camera.quaternion,
    );
    const cameraUp = new THREE.Vector3(0, 1, 0).applyQuaternion(
      camera.quaternion,
    );
    target
      .addScaledVector(cameraRight, centerX * halfWidthAtTarget)
      .addScaledVector(cameraUp, centerY * halfHeightAtTarget);
  }

  return { cameraPosition, target };
};

export const getRoom3DRackScenePosition = (
  rack: Pick<Room3DRack, "row" | "col">,
  bounds: { maxRow: number; maxCol: number },
) => {
  const centerX = ((bounds.maxCol - 1) * ROOM3D_COL_GAP) / 2;
  const frontAisleExtra = bounds.maxRow >= 1 ? ROOM3D_FRONT_AISLE_EXTRA : 0;
  const centerZ =
    ((bounds.maxRow - 1) * ROOM3D_ROW_GAP) / 2 + frontAisleExtra / 2;
  return {
    x: (rack.col - 1) * ROOM3D_COL_GAP - centerX,
    z: (bounds.maxRow - rack.row) * ROOM3D_ROW_GAP - centerZ,
  };
};

export const createRoom3DScene = (
  mountNode: HTMLDivElement,
  roomData: Room3DResponse,
  callbacks: Room3DSceneCallbacks,
): Room3DSceneController => {
  const sceneRacks = getRoom3DSceneRacks(roomData);
  const sceneLayout = buildRoom3DSceneLayout(sceneRacks);
  const { maxRow, maxCol, floorWidth, floorDepth } = sceneLayout;
  const scene = new THREE.Scene();

  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 1000);
  const initialView = buildRoom3DInitialView(sceneLayout, camera.aspect);
  camera.position.copy(initialView.cameraPosition);
  camera.lookAt(initialView.target);

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: true,
  });
  renderer.setClearColor(0x000000, 0);
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
  controls.target.copy(initialView.target);
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
    const { x, z } = getRoom3DRackScenePosition(rack, { maxRow, maxCol });
    const visual = createRackVisual(rack, x, z);
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
  let pendingRenderFrameId: number | null = null;
  let pendingPointerFrameId: number | null = null;
  let pendingPointerCoordinates: PointerCoordinates | null = null;
  let hoverNotification: HoverNotification | null = null;
  let disposed = false;
  let isIntersecting = true;
  let hasRenderedFirstFrame = false;
  let viewportWidth = 0;
  let viewportHeight = 0;
  let viewportPixelRatio = 0;
  let pixelRatioMediaQuery: MediaQueryList | null = null;

  const cancelPendingRender = () => {
    if (pendingRenderFrameId === null) {
      return;
    }
    window.cancelAnimationFrame(pendingRenderFrameId);
    pendingRenderFrameId = null;
  };

  const cancelPendingPointerMove = () => {
    pendingPointerCoordinates = null;
    if (pendingPointerFrameId === null) {
      return;
    }
    window.cancelAnimationFrame(pendingPointerFrameId);
    pendingPointerFrameId = null;
  };

  const requestRender = () => {
    if (
      disposed ||
      document.visibilityState === "hidden" ||
      (!isIntersecting && hasRenderedFirstFrame) ||
      pendingRenderFrameId !== null
    ) {
      return;
    }
    pendingRenderFrameId = window.requestAnimationFrame(renderFrame);
  };

  const handleVisibilityChange = () => {
    if (document.visibilityState === "hidden") {
      cancelPendingRender();
      return;
    }
    requestRender();
  };
  document.addEventListener("visibilitychange", handleVisibilityChange);
  const intersectionObserver =
    typeof IntersectionObserver === "undefined"
      ? null
      : new IntersectionObserver(([entry]) => {
        if (!entry) {
          return;
        }
        isIntersecting = entry.isIntersecting;
        if (!isIntersecting) {
          if (hasRenderedFirstFrame) {
            cancelPendingRender();
          }
          return;
        }
        requestRender();
      });
  intersectionObserver?.observe(mountNode);

  const animateCamera = () => {
    if (!desiredCameraPosition || !desiredTarget) {
      return false;
    }

    camera.position.lerp(desiredCameraPosition, 0.08);
    controls.target.lerp(desiredTarget, 0.1);
    if (
      camera.position.distanceTo(desiredCameraPosition) < 0.02 &&
      controls.target.distanceTo(desiredTarget) < 0.02
    ) {
      camera.position.copy(desiredCameraPosition);
      controls.target.copy(desiredTarget);
      desiredCameraPosition = null;
      desiredTarget = null;
      return false;
    }
    return true;
  };

  function renderFrame() {
    pendingRenderFrameId = null;
    let rackVisualAnimating = false;
    visuals.forEach((visual) => {
      rackVisualAnimating = animateRackVisual(visual) || rackVisualAnimating;
    });
    const cameraAnimating = animateCamera();
    const controlsAnimating = controls.update();
    renderer.render(scene, camera);
    if (!hasRenderedFirstFrame) {
      hasRenderedFirstFrame = true;
      callbacks.onFirstRender?.();
    }
    if (rackVisualAnimating || cameraAnimating || controlsAnimating) {
      requestRender();
    }
  }

  const handleControlsStart = () => {
    hasUserInteracted = true;
    desiredCameraPosition = null;
    desiredTarget = null;
  };
  controls.addEventListener("start", handleControlsStart);
  controls.addEventListener("change", requestRender);

  const updateVisualStates = () => {
    visuals.forEach((visual, rackId) => {
      setRackVisualState(visual, {
        hovered: rackId === hoveredRackId,
        selected: rackId === selectedRackId,
        selectedDeviceId,
      });
    });
    requestRender();
  };

  const pickRack = ({ clientX, clientY }: PointerCoordinates) => {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(pickTargets, false);
    const firstHit = hits[0];
    const deviceHit = hits.find((item) => Boolean(item.object.userData?.device));
    const hit = deviceHit || firstHit;
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

  const projectScreenPoint = (worldPoint: THREE.Vector3) => {
    const rect = renderer.domElement.getBoundingClientRect();
    const projected = worldPoint.clone().project(camera);
    if (projected.z < -1 || projected.z > 1) {
      return null;
    }

    return {
      x: rect.left + ((projected.x + 1) / 2) * rect.width,
      y: rect.top + ((1 - projected.y) / 2) * rect.height,
    };
  };

  const getRackScreenPoint = (rack: Room3DRack) => {
    const visual = visuals.get(rack.rack_id);
    const rect = renderer.domElement.getBoundingClientRect();
    if (!visual) {
      return { x: rect.left, y: rect.top };
    }

    return (
      projectScreenPoint(
        visual.root.position.clone().add(
          new THREE.Vector3(
            ROOM3D_RACK_WIDTH / 2 + 0.18,
            ROOM3D_RACK_HEIGHT * 0.58,
            0,
          ),
        ),
      ) || { x: rect.left, y: rect.top }
    );
  };

  const notifyHover = (rack: Room3DRack | null) => {
    if (!rack) {
      if (hoverNotification) {
        hoverNotification = null;
        callbacks.onHover(null);
      }
      return;
    }
    const point = getRackScreenPoint(rack);
    if (
      hoverNotification?.rackId === rack.rack_id &&
      Math.abs(hoverNotification.x - point.x) < HOVER_POSITION_EPSILON &&
      Math.abs(hoverNotification.y - point.y) < HOVER_POSITION_EPSILON
    ) {
      return;
    }
    hoverNotification = { rackId: rack.rack_id, ...point };
    callbacks.onHover({ rack, ...point });
  };

  const processPointerMove = () => {
    pendingPointerFrameId = null;
    const coordinates = pendingPointerCoordinates;
    pendingPointerCoordinates = null;
    if (!coordinates || disposed) {
      return;
    }
    const rack = pickRack(coordinates);
    const nextHoveredRackId = rack?.rack.rack_id || "";
    if (nextHoveredRackId !== hoveredRackId) {
      hoveredRackId = nextHoveredRackId;
      updateVisualStates();
    }
    if (!rack) {
      notifyHover(null);
      renderer.domElement.style.cursor = "grab";
      return;
    }
    renderer.domElement.style.cursor = "pointer";
    if (openRackId) {
      notifyHover(null);
      return;
    }
    notifyHover(rack.rack);
  };

  const handlePointerMove = (event: PointerEvent) => {
    pendingPointerCoordinates = {
      clientX: event.clientX,
      clientY: event.clientY,
    };
    if (pendingPointerFrameId === null) {
      pendingPointerFrameId = window.requestAnimationFrame(processPointerMove);
    }
  };

  const handlePointerLeave = () => {
    cancelPendingPointerMove();
    if (hoveredRackId) {
      hoveredRackId = "";
      updateVisualStates();
    }
    notifyHover(null);
    renderer.domElement.style.cursor = "grab";
  };

  const handleClick = (event: PointerEvent) => {
    cancelPendingPointerMove();
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
    callbacks.onSelect(selectedRackId ? rack.rack : null);
    callbacks.onDeviceSelect?.(
      rack.device && selectedDeviceId
        ? { rack: rack.rack, device: rack.device }
        : null,
    );
    if (openRackId) {
      notifyHover(null);
    }
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
    const visualRect = mountNode.getBoundingClientRect();
    const width = Math.max(Math.round(visualRect.width), 1);
    const height = Math.max(Math.round(visualRect.height), 1);
    const pixelRatio = Math.min(Math.max(window.devicePixelRatio || 1, 1), 2);
    const sizeChanged = width !== viewportWidth || height !== viewportHeight;
    const pixelRatioChanged = pixelRatio !== viewportPixelRatio;
    if (!sizeChanged && !pixelRatioChanged) {
      return;
    }
    viewportWidth = width;
    viewportHeight = height;
    viewportPixelRatio = pixelRatio;
    if (pixelRatioChanged) {
      renderer.setPixelRatio(pixelRatio);
    }
    if (sizeChanged) {
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      if (!hasUserInteracted && !desiredCameraPosition) {
        const responsiveView = buildRoom3DInitialView(
          sceneLayout,
          camera.aspect,
        );
        camera.position.copy(responsiveView.cameraPosition);
        controls.target.copy(responsiveView.target);
        controls.update();
      }
    }
    requestRender();
  };

  const handleWindowResize = () => resize();
  const handlePixelRatioChange = () => {
    resize();
    observePixelRatio();
  };
  function observePixelRatio() {
    pixelRatioMediaQuery?.removeEventListener(
      "change",
      handlePixelRatioChange,
    );
    pixelRatioMediaQuery =
      typeof window.matchMedia === "function"
        ? window.matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`)
        : null;
    pixelRatioMediaQuery?.addEventListener("change", handlePixelRatioChange);
  }

  const resetView = () => {
    selectedRackId = "";
    openRackId = "";
    hoveredRackId = "";
    selectedDeviceId = "";
    hasUserInteracted = false;
    const initialView = buildRoom3DInitialView(sceneLayout, camera.aspect);
    desiredCameraPosition = initialView.cameraPosition;
    desiredTarget = initialView.target;
    hoverNotification = null;
    callbacks.onHover(null);
    callbacks.onSelect(null);
    callbacks.onDeviceSelect?.(null);
    updateVisualStates();
  };

  renderer.domElement.addEventListener("pointermove", handlePointerMove);
  renderer.domElement.addEventListener("pointerleave", handlePointerLeave);
  renderer.domElement.addEventListener("click", handleClick);

  const handlePreparePrint = () => {
    if (disposed) {
      return;
    }
    renderer.render(scene, camera);
  };
  window.addEventListener("bk-dashboard-prepare-print", handlePreparePrint);

  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(mountNode);
  window.addEventListener("resize", handleWindowResize);
  observePixelRatio();
  resize();
  updateVisualStates();

  return {
    resetView,
    resize,
    dispose: () => {
      disposed = true;
      cancelPendingRender();
      cancelPendingPointerMove();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      intersectionObserver?.disconnect();
      resizeObserver.disconnect();
      window.removeEventListener("resize", handleWindowResize);
      window.removeEventListener("bk-dashboard-prepare-print", handlePreparePrint);
      pixelRatioMediaQuery?.removeEventListener(
        "change",
        handlePixelRatioChange,
      );
      renderer.domElement.removeEventListener("pointermove", handlePointerMove);
      renderer.domElement.removeEventListener(
        "pointerleave",
        handlePointerLeave,
      );
      renderer.domElement.removeEventListener("click", handleClick);
      controls.removeEventListener("start", handleControlsStart);
      controls.removeEventListener("change", requestRender);
      controls.dispose();
      disposeObject3D(scene);
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
};
