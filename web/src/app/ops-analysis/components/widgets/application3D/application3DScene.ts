import * as THREE from 'three';
import type { Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';
import {
  buildApplication3DLayout,
  resolveApplication3DCardVisual,
} from './application3DLayout';

export interface Application3DSceneController {
  reconcile: (items: Application3DWallItem[]) => void;
  focus: (applicationId: string) => void;
  restoreWall: () => void;
  resize: () => void;
  setActive: (active: boolean) => void;
  dispose: () => void;
}

interface ApplicationCardVisual {
  item: Application3DWallItem;
  root: THREE.Group;
  material: THREE.MeshStandardMaterial;
  texture: THREE.CanvasTexture;
}

const readToken = (
  mountNode: HTMLElement,
  token: string,
  fallbackToken = '--color-text-1',
) => {
  const styles = getComputedStyle(mountNode);
  return (
    styles.getPropertyValue(token).trim() ||
    styles.getPropertyValue(fallbackToken).trim()
  );
};

const readFirstToken = (
  mountNode: HTMLElement,
  candidates: string[],
  fallbackToken = '--color-text-1',
) => {
  const styles = getComputedStyle(mountNode);
  for (const token of candidates) {
    const value = styles.getPropertyValue(token).trim();
    if (value) return value;
  }
  return readToken(mountNode, fallbackToken);
};

const splitCssColor = (value: string) => {
  const match = value.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)$/i);
  if (!match) return { color: value, opacity: 1 };
  return {
    color: `rgb(${match[1]}, ${match[2]}, ${match[3]})`,
    opacity: match[4] === undefined ? 1 : Number(match[4]),
  };
};

const createCardTexture = (
  mountNode: HTMLElement,
  item: Application3DWallItem,
) => {
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 360;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D context unavailable');

  const visual = resolveApplication3DCardVisual(item);
  const textColor = readToken(mountNode, '--color-text-1');
  const backgroundColor = readToken(mountNode, '--color-bg-2', '--color-bg-1');
  const elevatedBackgroundColor = readToken(
    mountNode,
    '--color-bg-3',
    '--color-bg-2',
  );
  const accentColor = readFirstToken(
    mountNode,
    visual.accentTokenCandidates,
    '--color-primary',
  );

  const gradient = context.createLinearGradient(0, 0, canvas.width, canvas.height);
  gradient.addColorStop(0, elevatedBackgroundColor);
  gradient.addColorStop(1, backgroundColor);
  context.fillStyle = gradient;
  context.fillRect(0, 0, canvas.width, canvas.height);

  // Soft accent wash so non-normal cards are distinguishable beyond the border.
  context.fillStyle = accentColor;
  context.globalAlpha = item.health.state === 'normal' ? 0.08 : 0.16;
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.globalAlpha = 1;

  context.strokeStyle = accentColor;
  context.lineWidth = 8;
  context.strokeRect(8, 8, canvas.width - 16, canvas.height - 16);

  context.fillStyle = accentColor;
  context.beginPath();
  context.arc(58, 62, 17, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = textColor;
  context.font = '600 42px sans-serif';
  context.fillText(visual.title.slice(0, 16), 95, 78);

  context.fillStyle = accentColor;
  context.font = '700 28px sans-serif';
  context.fillText(visual.statusLabel, 42, 300);

  if (visual.showBadge) {
    context.fillStyle = accentColor;
    context.beginPath();
    context.roundRect(486, 244, 112, 70, 24);
    context.fill();
    context.fillStyle = readFirstToken(mountNode, visual.badgeTextTokenCandidates);
    context.font = '700 32px sans-serif';
    context.textAlign = 'center';
    context.fillText(visual.badgeText, 542, 290);
    context.textAlign = 'left';
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
};

const disposeVisual = (visual: ApplicationCardVisual) => {
  visual.texture.dispose();
  visual.material.dispose();
  visual.root.removeFromParent();
};

export const createApplication3DScene = (
  mountNode: HTMLDivElement,
  options: {
    interactive: boolean;
    active?: boolean;
    onSelect: (item: Application3DWallItem) => void;
    onFirstRender?: () => void;
  },
): Application3DSceneController => {
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(
    splitCssColor(readToken(mountNode, '--color-bg-1')).color,
    0.018,
  );
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 500);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  const clearColor = splitCssColor(readToken(mountNode, '--color-bg-1'));
  renderer.setClearColor(new THREE.Color(clearColor.color), clearColor.opacity * 0.92);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  // Fill the mount via CSS; setSize(..., false) only updates the drawing buffer
  // (same contract as room3D + `.canvas canvas { width/height: 100% }`).
  renderer.domElement.style.display = 'block';
  renderer.domElement.style.width = '100%';
  renderer.domElement.style.height = '100%';
  mountNode.appendChild(renderer.domElement);

  scene.add(
    new THREE.AmbientLight(
      splitCssColor(readToken(mountNode, '--color-text-2')).color,
      1.1,
    ),
  );
  const keyLight = new THREE.PointLight(
    splitCssColor(readToken(mountNode, '--color-primary')).color,
    20,
    80,
  );
  keyLight.position.set(0, 5, 16);
  scene.add(keyLight);

  const grid = new THREE.GridHelper(
    100,
    50,
    splitCssColor(readToken(mountNode, '--color-primary')).color,
    splitCssColor(readToken(mountNode, '--color-border-2')).color,
  );
  grid.rotation.x = Math.PI / 2;
  grid.position.z = -2.5;
  scene.add(grid);

  const cardGeometry = new THREE.BoxGeometry(1, 1, 0.12);
  const visuals = new Map<string, ApplicationCardVisual>();
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let wallCameraPosition = new THREE.Vector3(0, 0, 20);
  const desiredCameraPosition = wallCameraPosition.clone();
  const desiredTarget = new THREE.Vector3();
  const cameraTarget = new THREE.Vector3();
  let selectedId = '';
  let frameId: number | null = null;
  let disposed = false;
  let active = options.active !== false;
  let firstRender = true;
  let viewportWidth = 0;
  let viewportHeight = 0;

  const requestRender = () => {
    if (!disposed && active && frameId === null) {
      frameId = window.requestAnimationFrame(render);
    }
  };

  function render() {
    frameId = null;
    camera.position.lerp(desiredCameraPosition, 0.1);
    cameraTarget.lerp(desiredTarget, 0.12);
    camera.lookAt(cameraTarget);
    renderer.render(scene, camera);
    if (firstRender) {
      firstRender = false;
      options.onFirstRender?.();
    }
    if (
      camera.position.distanceTo(desiredCameraPosition) > 0.01 ||
      cameraTarget.distanceTo(desiredTarget) > 0.01
    ) {
      requestRender();
    }
  }

  const layoutVisuals = (options?: { snapCamera?: boolean }) => {
    const layout = buildApplication3DLayout(
      visuals.size,
      viewportWidth / Math.max(viewportHeight, 1),
    );
    Array.from(visuals.values()).forEach((visual, index) => {
      const column = index % layout.columns;
      const row = Math.floor(index / layout.columns);
      visual.root.scale.set(layout.cardWidth, layout.cardHeight, 1);
      visual.root.position.set(
        column * (layout.cardWidth + layout.gapX) - layout.wallWidth / 2 + layout.cardWidth / 2,
        layout.wallHeight / 2 - row * (layout.cardHeight + layout.gapY) - layout.cardHeight / 2,
        0,
      );
    });
    const verticalFov = THREE.MathUtils.degToRad(camera.fov);
    const distanceForHeight = layout.wallHeight / (2 * Math.tan(verticalFov / 2));
    const distanceForWidth =
      layout.wallWidth /
      (2 * Math.tan(verticalFov / 2) * Math.max(camera.aspect, 0.1));
    wallCameraPosition = new THREE.Vector3(
      0,
      0,
      Math.max(distanceForHeight, distanceForWidth, 8) + 2.5,
    );
    if (!selectedId) {
      desiredCameraPosition.copy(wallCameraPosition);
      desiredTarget.set(0, 0, 0);
      // Widget Rnd resize fires ResizeObserver every frame; lerping the camera
      // each time causes visible flicker. Snap during resize instead.
      if (options?.snapCamera) {
        camera.position.copy(desiredCameraPosition);
        cameraTarget.copy(desiredTarget);
      }
    }
    requestRender();
  };

  const reconcile = (items: Application3DWallItem[]) => {
    const nextIds = new Set(items.map((item) => item.id));
    visuals.forEach((visual, id) => {
      if (!nextIds.has(id)) {
        disposeVisual(visual);
        visuals.delete(id);
      }
    });
    items.forEach((item) => {
      const previous = visuals.get(item.id);
      if (previous) {
        if (
          previous.item.name === item.name &&
          JSON.stringify(previous.item.health) === JSON.stringify(item.health)
        ) {
          previous.item = item;
          return;
        }
        previous.item = item;
        previous.texture.dispose();
        previous.texture = createCardTexture(mountNode, item);
        previous.material.map = previous.texture;
        const accent = resolveApplication3DCardVisual(item);
        previous.material.emissive = new THREE.Color(
          splitCssColor(readFirstToken(
            mountNode,
            accent.accentTokenCandidates,
            '--color-primary',
          )).color,
        );
        previous.material.needsUpdate = true;
        return;
      }
      const texture = createCardTexture(mountNode, item);
      const accent = resolveApplication3DCardVisual(item);
      const accentColor = readFirstToken(
        mountNode,
        accent.accentTokenCandidates,
        '--color-primary',
      );
      const material = new THREE.MeshStandardMaterial({
        map: texture,
        emissive: new THREE.Color(splitCssColor(accentColor).color),
        emissiveIntensity: 0.1,
        roughness: 0.42,
        metalness: 0.25,
      });
      const mesh = new THREE.Mesh(cardGeometry, material);
      mesh.userData.applicationId = item.id;
      const root = new THREE.Group();
      root.add(mesh);
      scene.add(root);
      visuals.set(item.id, { item, root, material, texture });
    });
    if (selectedId && !nextIds.has(selectedId)) selectedId = '';
    layoutVisuals();
  };

  const focus = (applicationId: string) => {
    const selected = visuals.get(applicationId);
    if (!selected) return;
    selectedId = applicationId;
    visuals.forEach((visual, id) => {
      visual.material.opacity = id === selectedId ? 1 : 0.18;
      visual.material.transparent = id !== selectedId;
      visual.root.position.z = id === selectedId ? 1.5 : 0;
    });
    desiredTarget.copy(selected.root.position);
    desiredCameraPosition.copy(selected.root.position).add(new THREE.Vector3(0, 0, 7));
    selected.root.rotation.y = -0.08;
    requestRender();
  };

  const restoreWall = () => {
    selectedId = '';
    visuals.forEach((visual) => {
      visual.material.opacity = 1;
      visual.material.transparent = false;
      visual.root.position.z = 0;
      visual.root.rotation.y = 0;
    });
    desiredTarget.set(0, 0, 0);
    desiredCameraPosition.copy(wallCameraPosition);
    requestRender();
  };

  const handleClick = (event: PointerEvent) => {
    if (!active || !options.interactive) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(
      Array.from(visuals.values(), (visual) => visual.root),
      true,
    )[0];
    const applicationId = hit?.object.userData.applicationId as string | undefined;
    const visual = applicationId ? visuals.get(applicationId) : undefined;
    if (visual) options.onSelect(visual.item);
  };

  let resizeRaf: number | null = null;

  const resizeNow = () => {
    // Prefer layout box (client*) so Screen CSS transform scale does not
    // undersize the drawing buffer relative to the widget design size.
    const width = Math.max(
      Math.round(mountNode.clientWidth || mountNode.getBoundingClientRect().width),
      1,
    );
    const height = Math.max(
      Math.round(mountNode.clientHeight || mountNode.getBoundingClientRect().height),
      1,
    );
    const pixelRatio = Math.min(Math.max(window.devicePixelRatio || 1, 1), 2);
    if (width === viewportWidth && height === viewportHeight) {
      return;
    }
    viewportWidth = width;
    viewportHeight = height;
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    layoutVisuals({ snapCamera: true });
  };

  const resize = () => {
    if (resizeRaf !== null) return;
    resizeRaf = window.requestAnimationFrame(() => {
      resizeRaf = null;
      if (!disposed) resizeNow();
    });
  };

  if (options.interactive) {
    renderer.domElement.addEventListener('click', handleClick);
    renderer.domElement.style.cursor = 'pointer';
  }
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(mountNode);
  resizeNow();
  camera.position.copy(wallCameraPosition).multiplyScalar(
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 1 : 1.35,
  );
  requestRender();

  return {
    reconcile,
    focus,
    restoreWall,
    resize,
    setActive: (nextActive) => {
      if (disposed || active === nextActive) return;
      active = nextActive;
      if (!active) {
        if (frameId !== null) window.cancelAnimationFrame(frameId);
        if (resizeRaf !== null) window.cancelAnimationFrame(resizeRaf);
        frameId = null;
        resizeRaf = null;
        renderer.domElement.style.pointerEvents = 'none';
        return;
      }
      renderer.domElement.style.pointerEvents = options.interactive ? 'auto' : 'none';
      resizeNow();
      requestRender();
    },
    dispose: () => {
      disposed = true;
      if (frameId !== null) window.cancelAnimationFrame(frameId);
      if (resizeRaf !== null) window.cancelAnimationFrame(resizeRaf);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener('click', handleClick);
      visuals.forEach(disposeVisual);
      visuals.clear();
      cardGeometry.dispose();
      grid.geometry.dispose();
      if (Array.isArray(grid.material)) {
        grid.material.forEach((material) => material.dispose());
      } else {
        grid.material.dispose();
      }
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
};
