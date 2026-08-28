import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import type { Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';
import {
  APPLICATION3D_CAMERA_FOV,
  buildApplication3DLayout,
  defaultApplication3DTranslate,
  fitApplication3DCameraDistance,
  formatApplication3DCardTitle,
  resolveApplication3DCardVisual,
  type Application3DCardTone,
  type Application3DTranslate,
} from './application3DLayout';
import {
  CARD_GLASS,
  CARD_HOVER,
  CARD_THICKNESS,
  paintApplication3DCard,
  paintApplication3DCardSide,
} from './application3DCardStyle';
import {
  APPLICATION3D_ASSETS,
  CARD_TEXTURE_HEIGHT,
  CARD_TEXTURE_WIDTH,
  LEGACY_PARTICLE,
  durationFromSpeed,
  easeInOutCubic,
  prefersReducedMotion,
} from './application3DVisual';
import {
  WALL_ENTRANCE,
  WALL_FILTER_MOTION,
  cardStaggerDelayMs,
  easeOutEntrance,
} from './application3DMotion';

export interface Application3DFocusChromeLayout {
  centerX: number;
  bottom: number;
  width: number;
}

export interface Application3DSceneController {
  reconcile: (
    items: Application3DWallItem[],
    options?: { playIntro?: boolean; playFilter?: boolean; forceRepaint?: boolean },
  ) => void;
  focus: (applicationId: string) => void;
  restoreWall: () => void;
  resize: () => void;
  getFocusChromeLayout: () => Application3DFocusChromeLayout | null;
  setActive: (active: boolean) => void;
  dispose: () => void;
}

interface ApplicationCardVisual {
  item: Application3DWallItem;
  root: THREE.Group;
  mesh: THREE.Mesh;
  frontPlane: THREE.Mesh;
  material: THREE.MeshBasicMaterial;
  sideMaterial: THREE.MeshBasicMaterial;
  texture: THREE.CanvasTexture;
  sideTexture: THREE.CanvasTexture;
  homePosition: THREE.Vector3;
  homeScale: THREE.Vector3;
  cardTone: Application3DCardTone;
  hoverAmount: number;
}

const setCardOpacity = (visual: ApplicationCardVisual, opacity: number) => {
  visual.material.opacity = opacity;
  visual.sideMaterial.opacity = opacity;
};

const setCardBrightness = (visual: ApplicationCardVisual, value: number) => {
  visual.material.color.setScalar(value);
};

const FOCUS_DISTANCE = 8.4;
const FOCUS_SCALE = 0.78;

type ScenePhase = 'initializing' | 'wall' | 'focusing' | 'focused' | 'returning';

interface Tween {
  id: number;
  duration: number;
  delay: number;
  elapsed: number;
  ease: (t: number) => number;
  update: (t: number) => void;
  complete?: () => void;
}

const CLICK_DRAG_THRESHOLD_PX = 6;
const RESIZE_LAYOUT_DEBOUNCE_MS = 120;

const paintCardTexture = (
  item: Application3DWallItem,
  visual: ReturnType<typeof resolveApplication3DCardVisual>,
) => {
  const canvas = document.createElement('canvas');
  canvas.width = CARD_TEXTURE_WIDTH;
  canvas.height = CARD_TEXTURE_HEIGHT;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D context unavailable');
  paintApplication3DCard(context, visual, item.id, 'front');
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
};

const createCardTextures = (
  item: Application3DWallItem,
  translate: Application3DTranslate,
) => {
  const visual = resolveApplication3DCardVisual(item, translate);
  return {
    texture: paintCardTexture(item, visual),
    cardTone: visual.cardTone,
  };
};

const createGlassFaceMaterial = (map: THREE.CanvasTexture) =>
  new THREE.MeshBasicMaterial({
    map,
    color: 0xffffff,
    transparent: true,
    opacity: 1,
    toneMapped: false,
    depthWrite: false,
    side: THREE.DoubleSide,
  });

const paintCardSideTexture = (tone: Application3DCardTone) => {
  const canvas = document.createElement('canvas');
  canvas.width = 48;
  canvas.height = 256;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D context unavailable');
  paintApplication3DCardSide(context, tone);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
};

const applyCardSideMaterial = (
  material: THREE.MeshBasicMaterial,
  map: THREE.CanvasTexture,
) => {
  material.map = map;
  material.color.setScalar(1);
  material.transparent = true;
  material.opacity = 1;
  material.toneMapped = false;
  material.side = THREE.DoubleSide;
  material.depthWrite = false;
  material.needsUpdate = true;
};

const createGlassSideMaterial = (map: THREE.CanvasTexture) => {
  const material = new THREE.MeshBasicMaterial();
  applyCardSideMaterial(material, map);
  return material;
};

/**
 * Legacy ParticleSystem port:
 * color1/color2/colorDead, min/max size, min/max life, emit box, +Y emit, ADD blend.
 * Per-particle size via shader (Babylon minSize–maxSize).
 */
const createLegacyParticleMaterial = (map: THREE.Texture, sizeScale: number) => {
  const { color1, color2, colorDead } = LEGACY_PARTICLE;
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uMap: { value: map },
      uSizeScale: { value: sizeScale },
      uColor1: { value: new THREE.Vector4(color1.r, color1.g, color1.b, color1.a) },
      uColor2: { value: new THREE.Vector4(color2.r, color2.g, color2.b, color2.a) },
      uColorDead: {
        value: new THREE.Vector4(colorDead.r, colorDead.g, colorDead.b, colorDead.a),
      },
    },
    vertexShader: `
      attribute float aSize;
      attribute float aLife;
      attribute float aMaxLife;
      varying float vLifeT;
      uniform float uSizeScale;
      void main() {
        vLifeT = clamp(aLife / max(aMaxLife, 0.0001), 0.0, 1.0);
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = aSize * uSizeScale * (300.0 / max(-mv.z, 1.0));
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: `
      uniform sampler2D uMap;
      uniform vec4 uColor1;
      uniform vec4 uColor2;
      uniform vec4 uColorDead;
      varying float vLifeT;
      void main() {
        vec2 centered = gl_PointCoord - vec2(0.5);
        float radius = length(centered) * 2.0;
        float circle = 1.0 - smoothstep(0.85, 1.0, radius);
        if (circle < 0.01) discard;
        vec4 tex = texture2D(uMap, gl_PointCoord);
        // Live: mix color1→color2; near end fade toward colorDead (a→0).
        vec4 live = mix(uColor1, uColor2, vLifeT);
        float fade = 1.0 - smoothstep(0.65, 1.0, vLifeT);
        vec4 color = mix(live, uColorDead, 1.0 - fade);
        color.a *= tex.a * fade * circle;
        if (color.a < 0.01) discard;
        gl_FragColor = vec4(color.rgb * color.a, color.a);
      }
    `,
  });
};

const disposeVisual = (visual: ApplicationCardVisual) => {
  visual.texture.dispose();
  visual.sideTexture.dispose();
  visual.material.dispose();
  visual.sideMaterial.dispose();
  visual.root.removeFromParent();
};

const CARD_CORNER_RADIUS_X = CARD_GLASS.radius / CARD_TEXTURE_WIDTH;
const CARD_CORNER_RADIUS_Y = CARD_GLASS.radius / CARD_TEXTURE_HEIGHT;
const CARD_CORNER_SEGMENTS = 8;

const roundedRectOutline = (
  radiusX = CARD_CORNER_RADIUS_X,
  radiusY = CARD_CORNER_RADIUS_Y,
  cornerSegments = CARD_CORNER_SEGMENTS,
) => {
  const hw = 0.5;
  const hh = 0.5;
  const rx = Math.min(radiusX, hw - 0.001);
  const ry = Math.min(radiusY, hh - 0.001);
  const corners = [
    { cx: -hw + rx, cy: -hh + ry, start: Math.PI, end: Math.PI * 1.5 },
    { cx: hw - rx, cy: -hh + ry, start: Math.PI * 1.5, end: Math.PI * 2 },
    { cx: hw - rx, cy: hh - ry, start: 0, end: Math.PI / 2 },
    { cx: -hw + rx, cy: hh - ry, start: Math.PI / 2, end: Math.PI },
  ];
  const points: Array<{ x: number; y: number }> = [];
  corners.forEach((corner) => {
    for (let i = 0; i < cornerSegments; i += 1) {
      const t = corner.start + ((corner.end - corner.start) * i) / cornerSegments;
      points.push({
        x: corner.cx + Math.cos(t) * rx,
        y: corner.cy + Math.sin(t) * ry,
      });
    }
  });
  return points;
};

const createRoundedCardShellGeometry = (outline: Array<{ x: number; y: number }>) => {
  const count = outline.length;
  const positions: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];
  const lengths = outline.map((point, index) => {
    const next = outline[(index + 1) % count];
    return Math.hypot(next.x - point.x, next.y - point.y);
  });
  const perimeter = lengths.reduce((sum, length) => sum + length, 0);
  let dist = 0;
  for (let i = 0; i < count; i += 1) {
    const a = outline[i];
    const b = outline[(i + 1) % count];
    const u0 = dist / perimeter;
    dist += lengths[i];
    const u1 = i === count - 1 ? 1 : dist / perimeter;
    const base = i * 4;
    positions.push(a.x, a.y, -0.5, a.x, a.y, 0.5, b.x, b.y, 0.5, b.x, b.y, -0.5);
    uvs.push(u0, 0, u0, 1, u1, 1, u1, 0);
    indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
};

const createRoundedCardFaceGeometry = (outline: Array<{ x: number; y: number }>) => {
  const shape = new THREE.Shape();
  shape.moveTo(outline[0].x, outline[0].y);
  for (let i = 1; i < outline.length; i += 1) shape.lineTo(outline[i].x, outline[i].y);
  shape.closePath();
  const geometry = new THREE.ShapeGeometry(shape);
  const position = geometry.getAttribute('position');
  const uv = new Float32Array(position.count * 2);
  for (let i = 0; i < position.count; i += 1) {
    uv[i * 2] = position.getX(i) + 0.5;
    uv[i * 2 + 1] = position.getY(i) + 0.5;
  }
  geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  return geometry;
};

export const createApplication3DScene = (
  mountNode: HTMLDivElement,
  options: {
    interactive: boolean;
    active?: boolean;
    translate?: Application3DTranslate;
    onSelect: (item: Application3DWallItem) => void;
    onFocusSettled?: (item: Application3DWallItem) => void;
    onBackground?: () => void;
    onFirstRender?: () => void;
  },
): Application3DSceneController => {
  const reducedMotion = prefersReducedMotion();
  const translate = options.translate ?? defaultApplication3DTranslate;
  const scene = new THREE.Scene();

  const camera = new THREE.PerspectiveCamera(APPLICATION3D_CAMERA_FOV, 1, 0.1, 500);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.12;
  renderer.domElement.style.display = 'block';
  renderer.domElement.style.width = '100%';
  renderer.domElement.style.height = '100%';
  renderer.domElement.style.touchAction = 'none';
  mountNode.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 6;
  controls.maxDistance = 80;
  controls.minPolarAngle = Math.PI * 0.28;
  controls.maxPolarAngle = Math.PI * 0.72;
  controls.enabled = false;

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  // Legacy GlowLayer intensity ~0.8 — keep moderate for widget.
  const bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.34, 0.42, 0.86);
  bloomPass.enabled = !reducedMotion;
  composer.addPass(bloomPass);
  composer.addPass(new OutputPass());

  const textureLoader = new THREE.TextureLoader();

  // Legacy: HemisphericLight(direction 5,5,-9).
  scene.add(new THREE.HemisphereLight(0xc8d6e6, 0x121820, 0.55));
  const hemiKey = new THREE.DirectionalLight(0xe8f0f8, 0.18);
  hemiKey.position.set(5, 5, 9);
  scene.add(hemiKey);

  const flareTexture = textureLoader.load(APPLICATION3D_ASSETS.flare);
  let particlePoints: THREE.Points | null = null;
  let particleMaterial: THREE.ShaderMaterial | null = null;
  let particlePositions: Float32Array | null = null;
  let particleVelocities: Float32Array | null = null;
  let particleAges: Float32Array | null = null;
  let particleMaxLives: Float32Array | null = null;
  let particleSizes: Float32Array | null = null;
  let particleSizeScale = 1;

  const syncParticleScale = () => {
    // Widget is smaller than fullscreen legacy — scale sizes with camera distance.
    particleSizeScale = THREE.MathUtils.clamp(wallCameraPosition.z / 28, 0.85, 2.4);
    if (particleMaterial) {
      particleMaterial.uniforms.uSizeScale.value = particleSizeScale;
    }
  };

  const respawnParticle = (i: number, box: number) => {
    if (!particlePositions || !particleVelocities || !particleAges || !particleMaxLives || !particleSizes) {
      return;
    }
    particlePositions[i * 3] = (Math.random() * 2 - 1) * box;
    particlePositions[i * 3 + 1] = (Math.random() * 2 - 1) * box;
    particlePositions[i * 3 + 2] = (Math.random() * 2 - 1) * box;
    const power =
      LEGACY_PARTICLE.minEmitPower +
      Math.random() * (LEGACY_PARTICLE.maxEmitPower - LEGACY_PARTICLE.minEmitPower);
    // Babylon default emit direction ≈ +Y with jitter.
    particleVelocities[i * 3] = (Math.random() - 0.5) * 0.35 * power;
    particleVelocities[i * 3 + 1] = (0.65 + Math.random() * 0.7) * power;
    particleVelocities[i * 3 + 2] = (Math.random() - 0.5) * 0.35 * power;
    particleMaxLives[i] =
      LEGACY_PARTICLE.minLifeTime +
      Math.random() * (LEGACY_PARTICLE.maxLifeTime - LEGACY_PARTICLE.minLifeTime);
    particleAges[i] = Math.random() * particleMaxLives[i];
    particleSizes[i] =
      LEGACY_PARTICLE.minSize +
      Math.random() * (LEGACY_PARTICLE.maxSize - LEGACY_PARTICLE.minSize);
  };

  const rebuildParticles = () => {
    if (reducedMotion) return;
    if (particlePoints) {
      scene.remove(particlePoints);
      particlePoints.geometry.dispose();
      particleMaterial?.dispose();
      particlePoints = null;
      particleMaterial = null;
    }
    const count = LEGACY_PARTICLE.capacity;
    const box = LEGACY_PARTICLE.emitBox;
    particlePositions = new Float32Array(count * 3);
    particleVelocities = new Float32Array(count * 3);
    particleAges = new Float32Array(count);
    particleMaxLives = new Float32Array(count);
    particleSizes = new Float32Array(count);
    for (let i = 0; i < count; i += 1) respawnParticle(i, box);

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
    geometry.setAttribute('aSize', new THREE.BufferAttribute(particleSizes, 1));
    geometry.setAttribute('aLife', new THREE.BufferAttribute(particleAges, 1));
    geometry.setAttribute('aMaxLife', new THREE.BufferAttribute(particleMaxLives, 1));

    particleMaterial = createLegacyParticleMaterial(flareTexture, particleSizeScale);
    particlePoints = new THREE.Points(geometry, particleMaterial);
    scene.add(particlePoints);
  };

  const cardOutline = roundedRectOutline();
  const cardGeometry = createRoundedCardShellGeometry(cardOutline);
  const cardFaceGeometry = createRoundedCardFaceGeometry(cardOutline);
  const visuals = new Map<string, ApplicationCardVisual>();
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();

  let wallCameraPosition = new THREE.Vector3(0, 0, 20);
  const desiredCameraPosition = wallCameraPosition.clone();
  const desiredTarget = new THREE.Vector3();
  let cameraAnimating = false;
  let selectedId = '';
  let phase: ScenePhase = 'initializing';
  let frameId: number | null = null;
  let disposed = false;
  let active = options.active !== false;
  let firstRender = true;
  let viewportWidth = 0;
  let viewportHeight = 0;
  let lastFrameTime = performance.now();
  let tweenIdSeq = 1;
  const tweens = new Map<number, Tween>();
  let pointerDown: { x: number; y: number } | null = null;
  let hoveredId = '';
  let introSafetyTimer: number | null = null;
  let introTimeouts: number[] = [];
  let resizeLayoutTimer: number | null = null;
  let particlesBuilt = false;
  let entrancePlayed = false;

  const requestRender = () => {
    if (!disposed && active && frameId === null) {
      frameId = window.requestAnimationFrame(render);
    }
  };

  const setOrbitEnabled = (enabled: boolean) => {
    controls.enabled = Boolean(enabled && options.interactive && active && !reducedMotion);
  };

  const startTween = (
    duration: number,
    update: (t: number) => void,
    complete?: () => void,
    ease: (t: number) => number = easeInOutCubic,
    delay = 0,
    forceAnimate = false,
  ) => {
    if ((!forceAnimate && reducedMotion) || duration <= 0) {
      update(1);
      complete?.();
      requestRender();
      return -1;
    }
    const id = tweenIdSeq;
    tweenIdSeq += 1;
    tweens.set(id, { id, duration, delay, elapsed: 0, ease, update, complete });
    requestRender();
    return id;
  };

  const cancelTweens = () => {
    tweens.clear();
  };

  const clearIntroTimers = () => {
    if (introSafetyTimer !== null) {
      window.clearTimeout(introSafetyTimer);
      introSafetyTimer = null;
    }
    introTimeouts.forEach((id) => window.clearTimeout(id));
    introTimeouts = [];
  };

  const finishIntro = () => {
    clearIntroTimers();
    cancelTweens();
    phase = 'wall';
    cameraAnimating = false;
    desiredCameraPosition.copy(wallCameraPosition);
    camera.position.copy(wallCameraPosition);
    controls.target.set(0, 0, 0);
    controls.update();
    controls.saveState();
    setOrbitEnabled(true);
    renderer.domElement.style.opacity = '1';
    renderer.domElement.style.transition = '';
    visuals.forEach((visual) => {
      visual.root.position.copy(visual.homePosition);
      visual.root.rotation.set(0, 0, 0);
      visual.root.scale.copy(visual.homeScale);
      setCardOpacity(visual, 1);
      setCardBrightness(visual, 1);
    });
    requestRender();
  };

  const updateParticles = (dt: number) => {
    if (
      !particlePoints ||
      !particlePositions ||
      !particleVelocities ||
      !particleAges ||
      !particleMaxLives ||
      !particleSizes
    ) {
      return;
    }
    const box = LEGACY_PARTICLE.emitBox;
    for (let i = 0; i < particleAges.length; i += 1) {
      particleAges[i] += dt;
      if (particleAges[i] >= particleMaxLives[i]) {
        respawnParticle(i, box);
        continue;
      }
      // gravity = (0,0,0) — only emit velocity.
      particlePositions[i * 3] += particleVelocities[i * 3] * dt;
      particlePositions[i * 3 + 1] += particleVelocities[i * 3 + 1] * dt;
      particlePositions[i * 3 + 2] += particleVelocities[i * 3 + 2] * dt;
    }
    particlePoints.geometry.getAttribute('position').needsUpdate = true;
    particlePoints.geometry.getAttribute('aLife').needsUpdate = true;
    particlePoints.geometry.getAttribute('aMaxLife').needsUpdate = true;
    particlePoints.geometry.getAttribute('aSize').needsUpdate = true;
  };

  function render(now?: number) {
    frameId = null;
    const current = now ?? performance.now();
    const dt = Math.min((current - lastFrameTime) / 1000, 0.05);
    lastFrameTime = current;

    if (tweens.size) {
      const finished: number[] = [];
      tweens.forEach((tween) => {
        tween.elapsed += dt;
        if (tween.elapsed < tween.delay) return;
        const raw = Math.min((tween.elapsed - tween.delay) / tween.duration, 1);
        tween.update(tween.ease(raw));
        if (raw >= 1) finished.push(tween.id);
      });
      finished.forEach((id) => {
        const tween = tweens.get(id);
        tweens.delete(id);
        tween?.complete?.();
      });
    }

    const hoverEnabled =
      phase === 'wall' && !selectedId && tweens.size === 0 && !pointerDown;
    visuals.forEach((visual) => {
      const want = hoverEnabled && !reducedMotion && visual.item.id === hoveredId ? 1 : 0;
      visual.hoverAmount = THREE.MathUtils.lerp(visual.hoverAmount, want, CARD_HOVER.lerp);
      if (visual.hoverAmount < 0.004) visual.hoverAmount = 0;
      if (!hoverEnabled && visual.hoverAmount === 0) return;
      if (!hoverEnabled) return;
      const lift = visual.hoverAmount * CARD_HOVER.liftZ;
      const scaleMul = 1 + visual.hoverAmount * (CARD_HOVER.scale - 1);
      visual.root.position.z = visual.homePosition.z + lift;
      visual.root.scale.set(
        visual.homeScale.x * scaleMul,
        visual.homeScale.y * scaleMul,
        visual.homeScale.z,
      );
      setCardBrightness(visual, 1 + visual.hoverAmount * CARD_HOVER.emissiveBoost * 2.2);
    });

    updateParticles(dt);

    if (cameraAnimating) {
      camera.position.lerp(desiredCameraPosition, 0.12);
      controls.target.lerp(desiredTarget, 0.14);
      camera.lookAt(controls.target);
      if (
        camera.position.distanceTo(desiredCameraPosition) < 0.04 &&
        controls.target.distanceTo(desiredTarget) < 0.04
      ) {
        camera.position.copy(desiredCameraPosition);
        controls.target.copy(desiredTarget);
        cameraAnimating = false;
      }
    } else if (controls.enabled) {
      controls.update();
    }

    composer.render();
    if (firstRender) {
      firstRender = false;
      options.onFirstRender?.();
    }
    if (tweens.size > 0 || cameraAnimating || particlePoints || phase === 'wall' || controls.enabled) {
      requestRender();
    }
  }

  const fitCameraDistance = (layout: ReturnType<typeof buildApplication3DLayout>) =>
    fitApplication3DCameraDistance(
      layout.wallWidth,
      layout.wallHeight,
      camera.aspect,
      camera.fov,
    );

  const fadeSceneCanvas = (durationMs: number) => {
    renderer.domElement.style.opacity = '0';
    renderer.domElement.style.transition = `opacity ${durationMs}ms ease-out`;
    window.requestAnimationFrame(() => {
      renderer.domElement.style.opacity = '1';
    });
  };

  /**
   * First-open wall: cards rise from slightly farther/below with a short
   * left-to-right stagger. Camera stays at the wall-facing pose.
   */
  const playEntrance = () => {
    clearIntroTimers();
    cancelTweens();
    phase = 'initializing';
    setOrbitEnabled(false);
    cameraAnimating = false;
    camera.position.copy(wallCameraPosition);
    controls.target.set(0, 0, 0);
    desiredCameraPosition.copy(wallCameraPosition);
    desiredTarget.set(0, 0, 0);
    controls.update();

    const entries = Array.from(visuals.values());
    if (!entries.length) {
      finishIntro();
      return;
    }

    fadeSceneCanvas(reducedMotion ? WALL_ENTRANCE.reducedMotionMs : WALL_ENTRANCE.sceneFadeMs);

    if (reducedMotion) {
      entries.forEach((visual) => {
        visual.root.position.copy(visual.homePosition);
        visual.root.rotation.set(0, 0, 0);
        visual.root.scale.copy(visual.homeScale);
        setCardOpacity(visual, 0);
        setCardBrightness(visual, 1);
      });
      let remaining = entries.length;
      entries.forEach((visual) => {
        startTween(WALL_ENTRANCE.reducedMotionMs / 1000, (t) => {
          setCardOpacity(visual, t);
        }, () => {
          setCardOpacity(visual, 1);
          remaining -= 1;
          if (remaining <= 0) finishIntro();
        }, easeOutEntrance, 0, true);
      });
      introSafetyTimer = window.setTimeout(() => {
        if (phase === 'initializing' && !disposed) finishIntro();
      }, 800);
      return;
    }

    const rotateX = THREE.MathUtils.degToRad(WALL_ENTRANCE.rotateXDeg);
    entries.forEach((visual) => {
      visual.root.position.set(
        visual.homePosition.x,
        visual.homePosition.y + WALL_ENTRANCE.offsetY,
        visual.homePosition.z + WALL_ENTRANCE.offsetZ,
      );
      visual.root.rotation.set(rotateX, 0, 0);
      visual.root.scale.copy(visual.homeScale).multiplyScalar(WALL_ENTRANCE.startScale);
      setCardOpacity(visual, 0);
      setCardBrightness(visual, 0.72);
    });

    const duration = WALL_ENTRANCE.cardDurationMs / 1000;
    let remaining = entries.length;
    entries.forEach((visual, index) => {
      const delay =
        WALL_ENTRANCE.cardStartMs / 1000 +
        cardStaggerDelayMs(index, entries.length) / 1000;
      const fromPos = visual.root.position.clone();
      const fromScale = visual.root.scale.clone();
      const fromRotX = visual.root.rotation.x;
      const fromGlow = 0.72;
      const toGlow = 1;
      startTween(duration, (t) => {
        visual.root.position.lerpVectors(fromPos, visual.homePosition, t);
        visual.root.rotation.x = fromRotX * (1 - t);
        visual.root.scale.lerpVectors(fromScale, visual.homeScale, t);
        setCardOpacity(visual, t);
        setCardBrightness(visual, fromGlow + (toGlow - fromGlow) * t);
      }, () => {
        visual.root.position.copy(visual.homePosition);
        visual.root.rotation.set(0, 0, 0);
        visual.root.scale.copy(visual.homeScale);
        setCardOpacity(visual, 1);
        setCardBrightness(visual, 1);
        remaining -= 1;
        if (remaining <= 0) finishIntro();
      }, easeOutEntrance, delay);
    });

    introSafetyTimer = window.setTimeout(() => {
      if (phase === 'initializing' && !disposed) finishIntro();
    }, 2000);
  };

  const playFilterTransition = () => {
    cancelTweens();
    const entries = Array.from(visuals.values());
    if (!entries.length) return;
    const duration = (reducedMotion
      ? WALL_ENTRANCE.reducedMotionMs
      : WALL_FILTER_MOTION.durationMs) / 1000;
    const startScale = reducedMotion ? 1 : WALL_FILTER_MOTION.startScale;
    entries.forEach((visual) => {
      visual.root.position.copy(visual.homePosition);
      visual.root.rotation.set(0, 0, 0);
      visual.root.scale.copy(visual.homeScale).multiplyScalar(startScale);
      setCardOpacity(visual, 0);
      const fromScale = visual.root.scale.clone();
      startTween(duration, (t) => {
        setCardOpacity(visual, t);
        visual.root.scale.lerpVectors(fromScale, visual.homeScale, t);
      }, () => {
        setCardOpacity(visual, 1);
        visual.root.scale.copy(visual.homeScale);
      }, easeOutEntrance, 0, reducedMotion);
    });
  };

  const layoutVisuals = (layoutOptions?: {
    snapCamera?: boolean;
    playIntro?: boolean;
    playFilter?: boolean;
  }) => {
    const layout = buildApplication3DLayout(
      visuals.size,
      viewportWidth / Math.max(viewportHeight, 1),
    );

    let row = 0;
    let column = 0;
    Array.from(visuals.values()).forEach((visual) => {
      const rowCardCount = layout.rowCardCounts[row];
      visual.homeScale.set(layout.cardWidth, layout.cardHeight, CARD_THICKNESS);
      const rowWidth =
        rowCardCount * layout.cardWidth + Math.max(0, rowCardCount - 1) * layout.gapX;
      const x = -rowWidth / 2 + layout.cardWidth / 2 + column * (layout.cardWidth + layout.gapX);
      const y =
        layout.wallHeight / 2 -
        row * (layout.cardHeight + layout.gapY) -
        layout.cardHeight / 2;
      visual.homePosition.set(x, y, 0);
      const isFocusedCard =
        selectedId !== '' &&
        visual.root.userData.applicationId === selectedId &&
        (phase === 'focusing' || phase === 'focused');
      if (!isFocusedCard) {
        visual.root.scale.copy(visual.homeScale);
      }
      if (
        !selectedId &&
        phase !== 'focusing' &&
        phase !== 'focused' &&
        phase !== 'initializing' &&
        !layoutOptions?.playIntro &&
        !layoutOptions?.playFilter
      ) {
        visual.root.position.copy(visual.homePosition);
        visual.root.rotation.set(0, 0, 0);
      }
      column += 1;
      if (column === rowCardCount) {
        row += 1;
        column = 0;
      }
    });

    wallCameraPosition = new THREE.Vector3(0, 0, fitCameraDistance(layout));
    controls.minDistance = Math.max(wallCameraPosition.z * 0.45, 6);
    controls.maxDistance = wallCameraPosition.z * 2.2;
    syncParticleScale();

    if (!selectedId) {
      desiredTarget.set(0, 0, 0);
      if (layoutOptions?.playIntro) {
        playEntrance();
      } else if (layoutOptions?.playFilter) {
        playFilterTransition();
        desiredCameraPosition.copy(wallCameraPosition);
        if (phase === 'initializing') {
          phase = 'wall';
          setOrbitEnabled(true);
        }
      } else {
        desiredCameraPosition.copy(wallCameraPosition);
        if (layoutOptions?.snapCamera) {
          camera.position.copy(desiredCameraPosition);
          controls.target.copy(desiredTarget);
          cameraAnimating = false;
        }
        if (phase === 'initializing') {
          phase = 'wall';
          setOrbitEnabled(true);
        }
      }
    }
    requestRender();
  };

  const applyFaceMaterial = (material: THREE.MeshBasicMaterial) => {
    material.color.setScalar(1);
    material.toneMapped = false;
    material.needsUpdate = true;
  };

  const reconcile = (
    items: Application3DWallItem[],
    reconcileOptions?: { playIntro?: boolean; playFilter?: boolean; forceRepaint?: boolean },
  ) => {
    const playIntro =
      Boolean(reconcileOptions?.playIntro) &&
      items.length > 0 &&
      !selectedId &&
      !entrancePlayed;
    const playFilter =
      Boolean(reconcileOptions?.playFilter) &&
      items.length > 0 &&
      !selectedId &&
      !playIntro;
    const forceRepaint = Boolean(reconcileOptions?.forceRepaint);
    if (playIntro) {
      entrancePlayed = true;
      clearIntroTimers();
      cancelTweens();
      phase = 'initializing';
      setOrbitEnabled(false);
    } else if (playFilter) {
      clearIntroTimers();
      cancelTweens();
    }

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
          !forceRepaint &&
          previous.item.name === item.name &&
          JSON.stringify(previous.item.health) === JSON.stringify(item.health)
        ) {
          previous.item = item;
          return;
        }
        previous.item = item;
        previous.texture.dispose();
        const next = createCardTextures(item, translate);
        previous.texture = next.texture;
        previous.cardTone = next.cardTone;
        previous.material.map = previous.texture;
        applyFaceMaterial(previous.material);
        previous.sideTexture.dispose();
        previous.sideTexture = paintCardSideTexture(next.cardTone);
        applyCardSideMaterial(previous.sideMaterial, previous.sideTexture);
        return;
      }
      const painted = createCardTextures(item, translate);
      const material = createGlassFaceMaterial(painted.texture);
      applyFaceMaterial(material);
      const sideTexture = paintCardSideTexture(painted.cardTone);
      const sideMaterial = createGlassSideMaterial(sideTexture);
      const mesh = new THREE.Mesh(cardGeometry, sideMaterial);
      const frontPlane = new THREE.Mesh(cardFaceGeometry, material);
      frontPlane.position.z = 0.51;
      mesh.add(frontPlane);
      mesh.userData.applicationId = item.id;
      frontPlane.userData.applicationId = item.id;
      const root = new THREE.Group();
      root.userData.applicationId = item.id;
      root.add(mesh);
      scene.add(root);
      visuals.set(item.id, {
        item,
        root,
        mesh,
        frontPlane,
        material,
        sideMaterial,
        texture: painted.texture,
        sideTexture,
        homePosition: new THREE.Vector3(),
        homeScale: new THREE.Vector3(1, 1, CARD_THICKNESS),
        cardTone: painted.cardTone,
        hoverAmount: 0,
      });
    });
    if (selectedId && !nextIds.has(selectedId)) selectedId = '';

    if (!particlesBuilt) {
      rebuildParticles();
      particlesBuilt = true;
    }
    syncParticleScale();
    layoutVisuals({ playIntro, playFilter });
  };

  const getWallFacingFocusPosition = () => {
    const dir = new THREE.Vector3().subVectors(new THREE.Vector3(0, 0, 0), wallCameraPosition);
    if (dir.lengthSq() < 0.0001) dir.set(0, 0, -1);
    dir.normalize();
    return wallCameraPosition.clone().add(dir.multiplyScalar(FOCUS_DISTANCE));
  };

  const resetCameraToWall = (duration: number) => {
    const fromPos = camera.position.clone();
    const fromTarget = controls.target.clone();
    const toPos = wallCameraPosition.clone();
    const toTarget = new THREE.Vector3(0, 0, 0);
    const fromOffset = fromPos.clone().sub(fromTarget);
    const toOffset = toPos.clone().sub(toTarget);
    const fromSph = new THREE.Spherical().setFromVector3(fromOffset);
    const toSph = new THREE.Spherical().setFromVector3(toOffset);
    let deltaTheta = toSph.theta - fromSph.theta;
    while (deltaTheta > Math.PI) deltaTheta -= Math.PI * 2;
    while (deltaTheta < -Math.PI) deltaTheta += Math.PI * 2;
    const sph = new THREE.Spherical();
    const offset = new THREE.Vector3();

    cameraAnimating = false;
    startTween(duration, (t) => {
      sph.set(
        fromSph.radius + (toSph.radius - fromSph.radius) * t,
        fromSph.phi + (toSph.phi - fromSph.phi) * t,
        fromSph.theta + deltaTheta * t,
      );
      controls.target.lerpVectors(fromTarget, toTarget, t);
      camera.position.copy(controls.target).add(offset.setFromSpherical(sph));
      camera.lookAt(controls.target);
      desiredCameraPosition.copy(camera.position);
      desiredTarget.copy(controls.target);
    }, () => {
      camera.position.copy(toPos);
      controls.target.copy(toTarget);
      camera.lookAt(controls.target);
      desiredCameraPosition.copy(toPos);
      desiredTarget.copy(toTarget);
      controls.update();
    });
  };

  const flyCardHome = (
    visual: ApplicationCardVisual,
    duration: number,
    onComplete?: () => void,
  ) => {
    const fromPos = visual.root.position.clone();
    const fromRot = visual.root.rotation.y;
    const fromScale = visual.root.scale.clone();
    startTween(duration, (t) => {
      visual.root.position.lerpVectors(fromPos, visual.homePosition, t);
      visual.root.rotation.y = fromRot * (1 - t);
      visual.root.scale.lerpVectors(fromScale, visual.homeScale, t);
    }, () => {
      visual.root.position.copy(visual.homePosition);
      visual.root.rotation.set(0, 0, 0);
      visual.root.scale.copy(visual.homeScale);
      onComplete?.();
    });
  };

  const flyCardToFocus = (applicationId: string, returningId = '') => {
    const selected = visuals.get(applicationId);
    if (!selected) {
      phase = 'wall';
      setOrbitEnabled(true);
      return;
    }
    selectedId = applicationId;
    phase = 'focusing';
    setOrbitEnabled(false);
    cameraAnimating = false;
    renderer.domElement.style.cursor = 'default';

    const duration = durationFromSpeed(1);
    resetCameraToWall(duration);
    const focusPos = getWallFacingFocusPosition();
    const fromPos = selected.root.position.clone();
    const fromRot = selected.root.rotation.y;
    const fromScale = selected.root.scale.clone();
    const toScale = selected.homeScale.clone().multiplyScalar(FOCUS_SCALE);
    setCardOpacity(selected, 1);
    hoveredId = '';

    visuals.forEach((visual, id) => {
      if (id === applicationId || id === returningId) return;
      const fromOpacity = visual.material.opacity;
      startTween(duration * 0.55, (t) => {
        setCardOpacity(visual, fromOpacity + (0.5 - fromOpacity) * t);
      }, () => {
        setCardOpacity(visual, 0.5);
      });
    });

    startTween(duration, (t) => {
      selected.root.position.lerpVectors(fromPos, focusPos, t);
      selected.root.rotation.y = fromRot + Math.PI * 2 * t;
      selected.root.scale.lerpVectors(fromScale, toScale, t);
    }, () => {
      selected.root.position.copy(focusPos);
      selected.root.rotation.y = fromRot + Math.PI * 2;
      selected.root.scale.copy(toScale);
      phase = 'focused';
      renderer.domElement.style.cursor = 'default';
      options.onFocusSettled?.(selected.item);
    });
  };

  const focus = (applicationId: string) => {
    if (!visuals.has(applicationId)) return;
    if (applicationId === selectedId && (phase === 'focused' || phase === 'focusing')) {
      return;
    }
    clearIntroTimers();
    const outgoingId = selectedId && selectedId !== applicationId ? selectedId : '';
    const outgoing = outgoingId ? visuals.get(outgoingId) : undefined;
    cancelTweens();

    if (outgoing) {
      setCardOpacity(outgoing, 1);
      const duration = durationFromSpeed(1);
      const fromOpacity = outgoing.material.opacity;
      startTween(duration, (t) => {
        setCardOpacity(outgoing, fromOpacity + (0.5 - fromOpacity) * t);
      }, () => {
        setCardOpacity(outgoing, 0.5);
      });
      flyCardHome(outgoing, duration);
    }
    flyCardToFocus(applicationId, outgoingId);
  };

  const restoreWall = () => {
    cancelTweens();
    const outgoingId = selectedId;
    selectedId = '';
    phase = 'returning';
    setOrbitEnabled(false);
    cameraAnimating = false;
    renderer.domElement.style.cursor = 'default';
    const duration = durationFromSpeed(1);
    resetCameraToWall(duration);
    const outgoing = outgoingId ? visuals.get(outgoingId) : undefined;

    visuals.forEach((visual) => {
      const fromOpacity = visual.material.opacity;
      startTween(duration, (t) => {
        setCardOpacity(visual, fromOpacity + (1 - fromOpacity) * t);
      }, () => {
        setCardOpacity(visual, 1);
      });
    });

    const finish = () => {
      phase = 'wall';
      setOrbitEnabled(true);
      renderer.domElement.style.cursor = 'grab';
    };
    if (outgoing) {
      flyCardHome(outgoing, duration, finish);
    } else {
      finish();
    }
  };

  const pickApplicationId = (clientX: number, clientY: number) => {
    const rect = renderer.domElement.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return undefined;
    pointer.set(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -((clientY - rect.top) / rect.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(
      Array.from(visuals.values(), (visual) => visual.mesh),
      true,
    )[0];
    return hit?.object.userData.applicationId as string | undefined;
  };

  const idleCursor = () => {
    if (phase === 'focused' || phase === 'focusing' || phase === 'returning') return 'default';
    return 'grab';
  };

  const syncCursor = (clientX: number, clientY: number) => {
    if (!active || !options.interactive) return;
    renderer.domElement.style.cursor = pickApplicationId(clientX, clientY)
      ? 'pointer'
      : idleCursor();
  };

  const handlePointerDown = (event: PointerEvent) => {
    if (!active || !options.interactive) return;
    pointerDown = { x: event.clientX, y: event.clientY };
    if (controls.enabled) renderer.domElement.style.cursor = 'grabbing';
  };

  const handlePointerMove = (event: PointerEvent) => {
    syncCursor(event.clientX, event.clientY);
    if (!active || !options.interactive || pointerDown || phase !== 'wall' || selectedId) {
      if (hoveredId) {
        hoveredId = '';
        requestRender();
      }
      return;
    }
    const next = pickApplicationId(event.clientX, event.clientY) ?? '';
    if (next === hoveredId) return;
    hoveredId = next;
    const hovered = next ? visuals.get(next) : undefined;
    renderer.domElement.title = hovered
      ? formatApplication3DCardTitle(hovered.item.name)
      : '';
    requestRender();
  };

  const handlePointerLeave = () => {
    if (!hoveredId) return;
    hoveredId = '';
    renderer.domElement.title = '';
    requestRender();
  };

  const handlePointerUp = (event: PointerEvent) => {
    if (!active || !options.interactive || !pointerDown) return;
    const dx = event.clientX - pointerDown.x;
    const dy = event.clientY - pointerDown.y;
    pointerDown = null;
    if (Math.hypot(dx, dy) > CLICK_DRAG_THRESHOLD_PX) {
      syncCursor(event.clientX, event.clientY);
      return;
    }
    if (phase === 'initializing') finishIntro();
    const applicationId = pickApplicationId(event.clientX, event.clientY);
    const visual = applicationId ? visuals.get(applicationId) : undefined;
    if (visual) {
      options.onSelect(visual.item);
      renderer.domElement.style.cursor = 'pointer';
      return;
    }
    if (phase === 'focused' || phase === 'focusing') {
      options.onBackground?.();
    }
    renderer.domElement.style.cursor = idleCursor();
  };

  let resizeRaf: number | null = null;

  const applyRendererSize = (width: number, height: number) => {
    const pixelRatio = Math.min(Math.max(window.devicePixelRatio || 1, 1), 2);
    viewportWidth = width;
    viewportHeight = height;
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(width, height, false);
    composer.setSize(width, height);
    bloomPass.resolution.set(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    syncParticleScale();
  };

  const resizeNow = () => {
    const width = Math.max(
      Math.round(mountNode.clientWidth || mountNode.getBoundingClientRect().width),
      1,
    );
    const height = Math.max(
      Math.round(mountNode.clientHeight || mountNode.getBoundingClientRect().height),
      1,
    );
    if (width === viewportWidth && height === viewportHeight) return;
    applyRendererSize(width, height);
    requestRender();
    if (resizeLayoutTimer !== null) window.clearTimeout(resizeLayoutTimer);
    resizeLayoutTimer = window.setTimeout(() => {
      resizeLayoutTimer = null;
      if (disposed) return;
      if (phase === 'initializing' || phase === 'focusing' || phase === 'returning') return;
      layoutVisuals({ snapCamera: !selectedId });
    }, RESIZE_LAYOUT_DEBOUNCE_MS);
  };

  const resize = () => {
    if (resizeRaf !== null) return;
    resizeRaf = window.requestAnimationFrame(() => {
      resizeRaf = null;
      if (!disposed) resizeNow();
    });
  };

  if (options.interactive) {
    renderer.domElement.addEventListener('pointerdown', handlePointerDown);
    renderer.domElement.addEventListener('pointermove', handlePointerMove);
    renderer.domElement.addEventListener('pointerup', handlePointerUp);
    renderer.domElement.addEventListener('pointerleave', handlePointerLeave);
    renderer.domElement.style.cursor = 'grab';
  }
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(mountNode);
  resizeNow();
  requestRender();

  const getFocusChromeLayout = (): Application3DFocusChromeLayout | null => {
    if (phase !== 'focused' || !selectedId) return null;
    const visual = visuals.get(selectedId);
    if (!visual) return null;
    const origin = visual.root.position;
    const halfW = visual.root.scale.x / 2;
    const halfH = visual.root.scale.y / 2;
    const frontZ = origin.z + 0.51 * visual.root.scale.z;
    const bottomLeft = new THREE.Vector3(origin.x - halfW, origin.y - halfH, frontZ);
    const bottomRight = new THREE.Vector3(origin.x + halfW, origin.y - halfH, frontZ);
    bottomLeft.project(camera);
    bottomRight.project(camera);
    const widthPx = renderer.domElement.clientWidth;
    const heightPx = renderer.domElement.clientHeight;
    if (widthPx <= 0 || heightPx <= 0) return null;
    const toX = (ndc: THREE.Vector3) => ((ndc.x + 1) / 2) * widthPx;
    const toY = (ndc: THREE.Vector3) => ((-ndc.y + 1) / 2) * heightPx;
    const leftX = toX(bottomLeft);
    const rightX = toX(bottomRight);
    return {
      centerX: (leftX + rightX) / 2,
      bottom: Math.max(toY(bottomLeft), toY(bottomRight)),
      width: Math.abs(rightX - leftX),
    };
  };

  return {
    reconcile,
    focus,
    restoreWall,
    resize,
    getFocusChromeLayout,
    setActive: (nextActive) => {
      if (disposed || active === nextActive) return;
      active = nextActive;
      if (!active) {
        setOrbitEnabled(false);
        if (frameId !== null) window.cancelAnimationFrame(frameId);
        if (resizeRaf !== null) window.cancelAnimationFrame(resizeRaf);
        frameId = null;
        resizeRaf = null;
        renderer.domElement.style.pointerEvents = 'none';
        return;
      }
      renderer.domElement.style.pointerEvents = options.interactive ? 'auto' : 'none';
      setOrbitEnabled(phase === 'wall' && !selectedId);
      resizeNow();
      requestRender();
    },
    dispose: () => {
      disposed = true;
      cancelTweens();
      clearIntroTimers();
      if (resizeLayoutTimer !== null) window.clearTimeout(resizeLayoutTimer);
      if (frameId !== null) window.cancelAnimationFrame(frameId);
      if (resizeRaf !== null) window.cancelAnimationFrame(resizeRaf);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener('pointerdown', handlePointerDown);
      renderer.domElement.removeEventListener('pointermove', handlePointerMove);
      renderer.domElement.removeEventListener('pointerup', handlePointerUp);
      renderer.domElement.removeEventListener('pointerleave', handlePointerLeave);
      controls.dispose();
      visuals.forEach(disposeVisual);
      visuals.clear();
      if (particlePoints) {
        scene.remove(particlePoints);
        particlePoints.geometry.dispose();
        particleMaterial?.dispose();
      }
      flareTexture.dispose();
      if (scene.background instanceof THREE.Texture) scene.background.dispose();
      cardGeometry.dispose();
      cardFaceGeometry.dispose();
      composer.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
};
