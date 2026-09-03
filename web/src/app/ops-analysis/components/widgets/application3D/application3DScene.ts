import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import type { Application3DArchitectureData, Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';
import {
  APPLICATION3D_CAMERA_FOV,
  buildApplication3DLayout,
  defaultApplication3DTranslate,
  fitApplication3DCameraDistance,
  formatApplication3DCardTitle,
  resolveApplication3DCardVisual,
  WALL_CAMERA_HEIGHT_FACTOR,
  type Application3DCardTone,
  type Application3DTranslate,
} from './application3DLayout';
import {
  CARD_GLASS,
  CARD_HOVER,
  CARD_THICKNESS,
  CARD_TONE,
  paintApplication3DCard,
  paintApplication3DCardSide,
} from './application3DCardStyle';
import {
  APPLICATION3D_ASSETS,
  CARD_TEXTURE_HEIGHT,
  CARD_TEXTURE_WIDTH,
  LEGACY_PARTICLE,
  easeInOutCubic,
  prefersReducedMotion,
} from './application3DVisual';
import {
  WALL_ENTRANCE,
  WALL_FILTER_MOTION,
  FOCUS_MOTION,
  ARCHITECTURE_MOTION,
  architectureLabelDelayMs,
  architectureNodeDelayMs,
  architecturePlaneDelayMs,
  architectureTubeDelayMs,
  cardStaggerDelayMs,
  easeLinear,
  easeOutEntrance,
} from './application3DMotion';
import { createArchitectureTreeGroup, type Application3DArchitectureView } from './application3DArchitectureView';
import {
  ARCH_PLANE_EMISSIVE_INTENSITY,
  ARCH_PLANE_OPACITY,
  ARCH_PLANE_RIM_OPACITY,
  ARCH_PLANE_RIM_STROKE_OPACITY,
  resolveArchitectureCameraPose,
} from './application3DArchitecture';

export const APPLICATION3D_WALL_GROUP_NAME = 'application3d-wall';
/**
 * User orbit polar clamp (OrbitControls: 0 = straight overhead / +Y,
 * π/2 = horizon). Landing poses stay on WALL_CAMERA_HEIGHT_FACTOR and
 * ARCH_CAMERA_PHI — only the *user* clamp opens to zenith.
 */
export const APPLICATION3D_USER_POLAR = {
  min: 1e-3,
  max: Math.PI * 0.72,
} as const;
export const APPLICATION3D_ORBIT_PAN = {
  enablePan: true,
  screenSpacePanning: true,
} as const;
const WALL_POLAR = APPLICATION3D_USER_POLAR;
const ARCH_POLAR = APPLICATION3D_USER_POLAR;

export interface Application3DSceneController {
  reconcile: (
    items: Application3DWallItem[],
    options?: { playIntro?: boolean; playFilter?: boolean; forceRepaint?: boolean },
  ) => void;
  resize: () => void;
  setActive: (active: boolean) => void;
  /** Animate (or snap) the orbit camera back to the fitted wall home pose. */
  resetCamera: () => void;
  focus: (applicationId: string | null) => void;
  showArchitecture: (data: Application3DArchitectureData) => void;
  hideArchitecture: () => void;
  dispose: () => void;
}

interface ApplicationCardVisual {
  item: Application3DWallItem;
  root: THREE.Group;
  mesh: THREE.Mesh;
  frontPlane: THREE.Mesh;
  material: THREE.ShaderMaterial;
  sideMaterial: THREE.MeshBasicMaterial;
  texture: THREE.CanvasTexture;
  sideTexture: THREE.CanvasTexture;
  homePosition: THREE.Vector3;
  homeScale: THREE.Vector3;
  homeRotationY: number;
  cardTone: Application3DCardTone;
  hoverAmount: number;
  glassEl: HTMLDivElement;
  glassOpacity: number;
  isBottomRow: boolean;
  reflection: THREE.Mesh;
  reflectionMaterial: THREE.ShaderMaterial;
  floorGlow: THREE.Mesh;
  floorGlowMaterial: THREE.ShaderMaterial;
}

const cardOpacity = (visual: ApplicationCardVisual) =>
  (visual.material.uniforms.uOpacity.value as number);

const setCardOpacity = (visual: ApplicationCardVisual, opacity: number) => {
  visual.glassOpacity = opacity;
  visual.material.uniforms.uOpacity.value = 0;
  visual.sideMaterial.opacity = opacity * 0.5;
  visual.glassEl.style.opacity = String(opacity);
};

const setCardBrightness = (visual: ApplicationCardVisual, value: number) => {
  visual.material.uniforms.uBright.value = value;
};

type ScenePhase = 'initializing' | 'wall' | 'focused' | 'architecture';

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

const cloneCardChromeCanvas = (source: HTMLCanvasElement) => {
  const chrome = document.createElement('canvas');
  chrome.width = source.width;
  chrome.height = source.height;
  chrome.className = 'app3d-wall-glass-chrome';
  const context = chrome.getContext('2d');
  if (!context) throw new Error('Canvas 2D context unavailable');
  context.drawImage(source, 0, 0);
  return chrome;
};

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
  new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    toneMapped: false,
    side: THREE.DoubleSide,
    uniforms: {
      uMap: { value: map },
      uOpacity: { value: 1 },
      uBright: { value: 1 },
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform sampler2D uMap;
      uniform float uOpacity;
      uniform float uBright;
      varying vec2 vUv;
      void main() {
        vec4 tex = texture2D(uMap, vUv);
        if (tex.a < 0.02) discard;
        gl_FragColor = vec4(tex.rgb * uBright, tex.a * uOpacity);
      }
    `,
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
  material.opacity = 0.5;
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

const createFloorGlowMaterial = (tint: number) =>
  new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    toneMapped: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uColor: { value: new THREE.Color(tint) },
      uOpacity: { value: 0.12 },
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
      uniform float uOpacity;
      varying vec2 vUv;
      void main() {
        vec2 p = vUv - 0.5;
        float d = length(p * vec2(0.9, 1.85));
        float glow = exp(-d * d * 8.0);
        gl_FragColor = vec4(uColor, glow * uOpacity);
      }
    `,
  });

const FLOOR_HOVER_GAP = 0.38;
const CARD_REFLECTION_OPACITY = 0.40;

const createCardReflectionMaterial = (map: THREE.CanvasTexture, tint: number) =>
  new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: false,
    toneMapped: false,
    uniforms: {
      uMap: { value: map },
      uOpacity: { value: CARD_REFLECTION_OPACITY },
      uTint: { value: new THREE.Color(tint) },
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform sampler2D uMap;
      uniform float uOpacity;
      uniform vec3 uTint;
      varying vec2 vUv;
      void main() {
        vec2 uv = vec2(vUv.x, 1.0 - vUv.y);
        vec4 tex = texture2D(uMap, uv);
        float fade = pow(clamp(vUv.y, 0.0, 1.0), 1.35);
        vec3 glass = vec3(0.11, 0.24, 0.38);
        vec3 color = mix(glass * mix(vec3(1.0), uTint, 0.2), tex.rgb, tex.a);
        float edge = min(min(vUv.x, 1.0 - vUv.x), min(vUv.y, 1.0 - vUv.y));
        float rim = 1.0 - smoothstep(0.008, 0.026, edge);
        vec3 rimColor = mix(uTint, vec3(0.7, 0.9, 1.0), 0.4);
        color = mix(color, rimColor, rim * 0.22);
        float alpha = mix(0.16, max(0.16, tex.a * 0.48), tex.a);
        alpha = max(alpha, rim * 0.16);
        gl_FragColor = vec4(color, alpha * fade * uOpacity);
      }
    `,
  });

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
  visual.glassEl.remove();
  visual.texture.dispose();
  visual.sideTexture.dispose();
  visual.material.dispose();
  visual.sideMaterial.dispose();
  visual.reflectionMaterial.dispose();
  visual.reflection.removeFromParent();
  visual.floorGlowMaterial.dispose();
  visual.floorGlow.removeFromParent();
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
  geometry.computeVertexNormals();
  return geometry;
};

export const createApplication3DScene = (
  mountNode: HTMLDivElement,
  options: {
    interactive: boolean;
    active?: boolean;
    translate?: Application3DTranslate;
    onSelect: (item: Application3DWallItem) => void;
    onBackgroundClick?: () => void;
    onFirstRender?: () => void;
  },
): Application3DSceneController => {
  const reducedMotion = prefersReducedMotion();
  const translate = options.translate ?? defaultApplication3DTranslate;
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x0c2138, 0.0035);

  const camera = new THREE.PerspectiveCamera(APPLICATION3D_CAMERA_FOV, 1, 0.1, 1200);
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: true,
  });
  renderer.setClearColor(0x0c2138, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.06;
  renderer.domElement.style.display = 'block';
  renderer.domElement.style.width = '100%';
  renderer.domElement.style.height = '100%';
  renderer.domElement.style.touchAction = 'none';
  mountNode.appendChild(renderer.domElement);
  if (getComputedStyle(mountNode).position === 'static') {
    mountNode.style.position = 'relative';
  }
  const glassLayer = document.createElement('div');
  glassLayer.className = 'app3d-wall-glass-layer';
  const frostCanvas = document.createElement('canvas');
  frostCanvas.className = 'app3d-wall-glass-frost';
  glassLayer.appendChild(frostCanvas);
  mountNode.appendChild(glassLayer);
  const frostCtx = frostCanvas.getContext('2d');
  if (!frostCtx) throw new Error('Canvas 2D context unavailable');
  const glassCorners = [
    new THREE.Vector3(-0.5, 0.5, 0),
    new THREE.Vector3(0.5, 0.5, 0),
    new THREE.Vector3(0.5, -0.5, 0),
    new THREE.Vector3(-0.5, -0.5, 0),
  ];
  const glassProjected = [
    { x: 0, y: 0 },
    { x: 0, y: 0 },
    { x: 0, y: 0 },
    { x: 0, y: 0 },
  ];
  const glassWorld = new THREE.Vector3();

  const createGlassOverlay = (tone: Application3DCardTone, canvas: HTMLCanvasElement) => {
    const el = document.createElement('div');
    el.className = 'app3d-wall-glass';
    el.dataset.tone = tone;
    el.appendChild(cloneCardChromeCanvas(canvas));
    glassLayer.appendChild(el);
    return el;
  };

  const syncGlassOverlays = () => {
    const widthPx = viewportWidth;
    const heightPx = viewportHeight;
    if (widthPx <= 0 || heightPx <= 0) return;
    if (phase === 'architecture' && !wallGroup.visible) {
      visuals.forEach((visual) => {
        visual.glassEl.hidden = true;
      });
      return;
    }
    camera.updateMatrixWorld();
    visuals.forEach((visual) => {
      visual.frontPlane.updateWorldMatrix(true, false);
      for (let i = 0; i < 4; i += 1) {
        glassWorld.copy(glassCorners[i]).applyMatrix4(visual.frontPlane.matrixWorld).project(camera);
        glassProjected[i].x = (glassWorld.x * 0.5 + 0.5) * widthPx;
        glassProjected[i].y = (-glassWorld.y * 0.5 + 0.5) * heightPx;
      }
      const [tl, tr, , bl] = glassProjected;
      const width = Math.hypot(tr.x - tl.x, tr.y - tl.y);
      const height = Math.hypot(bl.x - tl.x, bl.y - tl.y);
      const cx = (glassProjected[0].x + glassProjected[1].x + glassProjected[2].x + glassProjected[3].x) / 4;
      const cy = (glassProjected[0].y + glassProjected[1].y + glassProjected[2].y + glassProjected[3].y) / 4;
      const el = visual.glassEl;
      el.dataset.tone = visual.cardTone;
      el.style.width = `${width}px`;
      el.style.height = `${height}px`;
      el.style.left = `${cx - width / 2}px`;
      el.style.top = `${cy - height / 2}px`;
      el.style.transform = 'none';
      el.style.opacity = String(visual.glassOpacity);
      el.hidden = width < 4 || height < 4 || visual.glassOpacity < 0.02;
    });
  };

  const syncFrost = () => {
    if (frostCanvas.width !== viewportWidth || frostCanvas.height !== viewportHeight) {
      frostCanvas.width = Math.max(viewportWidth, 1);
      frostCanvas.height = Math.max(viewportHeight, 1);
    }
    frostCtx.clearRect(0, 0, frostCanvas.width, frostCanvas.height);
    frostCtx.filter = 'blur(24px) saturate(1.2)';
    const dpr = renderer.getPixelRatio();
    visuals.forEach((visual) => {
      if (visual.glassEl.hidden || visual.glassOpacity < 0.02) return;
      const x = Number.parseFloat(visual.glassEl.style.left);
      const y = Number.parseFloat(visual.glassEl.style.top);
      const width = Number.parseFloat(visual.glassEl.style.width);
      const height = Number.parseFloat(visual.glassEl.style.height);
      if (!(width > 2 && height > 2)) return;
      const pad = 28;
      frostCtx.drawImage(
        renderer.domElement,
        (x - pad) * dpr,
        (y - pad) * dpr,
        (width + pad * 2) * dpr,
        (height + pad * 2) * dpr,
        x - pad,
        y - pad,
        width + pad * 2,
        height + pad * 2,
      );
    });
    frostCtx.filter = 'none';
  };

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = APPLICATION3D_ORBIT_PAN.enablePan;
  controls.screenSpacePanning = APPLICATION3D_ORBIT_PAN.screenSpacePanning;
  controls.minDistance = 6;
  controls.maxDistance = 80;
  controls.minPolarAngle = WALL_POLAR.min;
  controls.maxPolarAngle = WALL_POLAR.max;
  controls.enabled = false;

  const composer = new EffectComposer(renderer);
  const renderPass = new RenderPass(scene, camera);
  renderPass.clearAlpha = 0;
  composer.addPass(renderPass);
  // Legacy GlowLayer intensity ~0.8 — keep moderate for widget.
  const bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.1, 0.35, 0.96);
  // Card neon is painted into the HUD texture. Full-frame bloom turns the
  // perspective floor into a white slab, which the mock never has.
  bloomPass.enabled = false;
  composer.addPass(bloomPass);
  composer.addPass(new OutputPass());

  const textureLoader = new THREE.TextureLoader();

  // Legacy: HemisphericLight(direction 5,5,-9).
  scene.add(new THREE.HemisphereLight(0x8aa0b4, 0x061018, 0.28));
  const hemiKey = new THREE.DirectionalLight(0xd0dce8, 0.11);
  hemiKey.position.set(5, 5, 9);
  scene.add(hemiKey);

  const stageRoot = new THREE.Group();
  scene.add(stageRoot);
  const wallGroup = new THREE.Group();
  wallGroup.name = APPLICATION3D_WALL_GROUP_NAME;
  scene.add(wallGroup);
  let floorY = -6;
  const wallLookTarget = new THREE.Vector3();
  const hoverLift = new THREE.Vector3();
  const floorGridMaterial = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    toneMapped: false,
    uniforms: {
      uColor: { value: new THREE.Color(0x2a7ea0) },
      uFade: { value: 28 },
      uCamera: { value: new THREE.Vector3() },
    },
    vertexShader: `
      varying vec3 vWorld;
      void main() {
        vec4 world = modelMatrix * vec4(position, 1.0);
        vWorld = world.xyz;
        gl_Position = projectionMatrix * viewMatrix * world;
      }
    `,
    fragmentShader: `
      varying vec3 vWorld;
      uniform vec3 uColor;
      uniform float uFade;
      uniform vec3 uCamera;
      float lineDist(float coord, float cell) {
        return abs(fract(coord / cell + 0.5) - 0.5) * cell;
      }
      float axisLine(float coord, float cell, float width) {
        float d = lineDist(coord, cell);
        float aa = min(max(fwidth(coord) * 0.8, 0.01), cell * 0.045);
        return 1.0 - smoothstep(width, width + aa, d);
      }
      float lineGrid(vec2 uv, float cell, float width) {
        return max(axisLine(uv.x, cell, width), axisLine(uv.y, cell, width));
      }
      void main() {
        vec2 xz = vWorld.xz;
        float dist = length(xz);
        float fade = (1.0 - smoothstep(uFade * 0.16, uFade * 1.02, dist)) * smoothstep(0.008, 0.14, dist);
        vec3 viewDir = normalize(uCamera - vWorld);
        float facing = mix(0.55, 1.0, smoothstep(0.008, 0.14, abs(viewDir.y)));
        float fine = lineGrid(xz, 1.15, 0.0048);
        float coarse = lineGrid(xz, 4.6, 0.0076);
        float line = max(fine * 0.34, coarse * 0.46);
        vec3 color = uColor * mix(0.82, 0.98, coarse);
        float wash = (1.0 - line) * fade * facing * 0.055;
        float alpha = max(line * fade * facing * 0.66, wash);
        gl_FragColor = vec4(color, alpha);
      }
    `,
  });
  const floorPlateMaterial = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    toneMapped: false,
    uniforms: {
      uBase: { value: new THREE.Color(0x071c2e) },
      uSpec: { value: new THREE.Color(0x276080) },
      uCamera: { value: new THREE.Vector3() },
    },
    vertexShader: `
      varying vec3 vWorld;
      void main() {
        vec4 world = modelMatrix * vec4(position, 1.0);
        vWorld = world.xyz;
        gl_Position = projectionMatrix * viewMatrix * world;
      }
    `,
    fragmentShader: `
      varying vec3 vWorld;
      uniform vec3 uBase;
      uniform vec3 uSpec;
      uniform vec3 uCamera;
      void main() {
        vec2 xz = vWorld.xz;
        float dist = length(xz);
        vec3 viewDir = normalize(uCamera - vWorld);
        float fresnel = pow(1.0 - clamp(abs(viewDir.y), 0.0, 1.0), 3.2);
        float streak = exp(-xz.x * xz.x * 0.012) * (1.0 - smoothstep(6.0, 40.0, dist));
        vec3 color = mix(uBase, uSpec, fresnel * 0.28 + streak * 0.1);
        float alpha = 0.86 + fresnel * 0.08;
        gl_FragColor = vec4(color, alpha);
      }
    `,
  });
  const floorPlate = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), floorPlateMaterial);
  floorPlate.rotation.x = -Math.PI / 2;
  floorPlate.renderOrder = 0;
  const floorGrid = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), floorGridMaterial);
  floorGrid.rotation.x = -Math.PI / 2;
  floorGrid.position.y = 0.02;
  floorGrid.renderOrder = 2;
  const atmosphereMaterial = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    toneMapped: false,
    uniforms: {
      uInner: { value: new THREE.Color(0x143044) },
      uOuter: { value: new THREE.Color(0x0c2138) },
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 uInner;
      uniform vec3 uOuter;
      varying vec2 vUv;
      void main() {
        vec2 p = vUv - vec2(0.5, 0.42);
        float d = length(p * vec2(1.15, 1.35));
        float t = smoothstep(0.08, 0.78, d);
        vec3 color = mix(uInner, uOuter, t);
        float alpha = mix(0.16, 0.0, smoothstep(0.55, 0.92, d));
        gl_FragColor = vec4(color, alpha);
      }
    `,
  });
  const atmosphere = new THREE.Mesh(new THREE.PlaneGeometry(90, 48), atmosphereMaterial);
  atmosphere.position.set(0, 10, -18);
  atmosphere.visible = false;
  stageRoot.add(floorPlate, floorGrid);

  const applyHomePose = (visual: ApplicationCardVisual) => {
    visual.root.position.copy(visual.homePosition);
    visual.root.rotation.set(0, visual.homeRotationY, 0);
  };

  const syncReflection = (visual: ApplicationCardVisual) => {
    const onWall = phase === 'wall' || phase === 'initializing';
    visual.reflection.visible = onWall && visual.isBottomRow;
    visual.reflection.position.set(0, -1 - FLOOR_HOVER_GAP * 2, 0.5);
    visual.reflectionMaterial.uniforms.uOpacity.value = CARD_REFLECTION_OPACITY * visual.glassOpacity;
    visual.floorGlow.visible = false;
  };

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
  const floorGlowGeometry = new THREE.PlaneGeometry(1, 1);
  const visuals = new Map<string, ApplicationCardVisual>();
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();

  let wallCameraPosition = new THREE.Vector3(0, 0, 20);
  const desiredCameraPosition = wallCameraPosition.clone();
  const desiredTarget = new THREE.Vector3();
  const cameraOrbitOffset = new THREE.Vector3();
  const cameraStartSpherical = new THREE.Spherical();
  const cameraEndSpherical = new THREE.Spherical();
  const cameraStartTarget = new THREE.Vector3();
  let cameraOrbitThetaDelta = 0;
  let cameraOrbitProgress = 0;
  let cameraOrbitDuration = 0.55;
  let cameraAnimating = false;
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
  let focusedId = '';
  let architectureView: Application3DArchitectureView | null = null;
  const focusLift = new THREE.Vector3();
  const architectureCameraPosition = new THREE.Vector3();
  const architectureLookTarget = new THREE.Vector3();
  let cameraComplete: (() => void) | null = null;

  const requestRender = () => {
    if (!disposed && active && frameId === null) {
      frameId = window.requestAnimationFrame(render);
    }
  };

  const applyPolarLimits = (limits: { min: number; max: number }) => {
    controls.minPolarAngle = limits.min;
    controls.maxPolarAngle = limits.max;
  };

  const setOrbitEnabled = (enabled: boolean) => {
    controls.enabled = Boolean(enabled && options.interactive && active && !reducedMotion);
  };

  const orbitAllowed = () => phase === 'wall' || phase === 'architecture';

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
    controls.target.copy(wallLookTarget);
    applyPolarLimits(WALL_POLAR);
    controls.update();
    controls.saveState();
    setOrbitEnabled(true);
    renderer.domElement.style.opacity = '1';
    renderer.domElement.style.transition = '';
    visuals.forEach((visual) => {
      applyHomePose(visual);
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
      phase === 'wall' && !focusedId && tweens.size === 0 && !pointerDown;
    visuals.forEach((visual) => {
      const want = hoverEnabled && !reducedMotion && visual.item.id === hoveredId ? 1 : 0;
      visual.hoverAmount = THREE.MathUtils.lerp(visual.hoverAmount, want, CARD_HOVER.lerp);
      if (visual.hoverAmount < 0.004) visual.hoverAmount = 0;
      if (!hoverEnabled && visual.hoverAmount === 0) return;
      if (!hoverEnabled) return;
      const lift = visual.hoverAmount * CARD_HOVER.liftZ;
      const scaleMul = 1 + visual.hoverAmount * (CARD_HOVER.scale - 1);
      hoverLift.set(0, 0, lift).applyAxisAngle(new THREE.Vector3(0, 1, 0), visual.homeRotationY);
      visual.root.position.copy(visual.homePosition).add(hoverLift);
      visual.root.rotation.set(0, visual.homeRotationY, 0);
      visual.root.scale.set(
        visual.homeScale.x * scaleMul,
        visual.homeScale.y * scaleMul,
        visual.homeScale.z,
      );
      setCardBrightness(visual, 1 + visual.hoverAmount * CARD_HOVER.emissiveBoost * 2.2);
    });

    updateParticles(dt);
    if (architectureView && phase === 'architecture') architectureView.tick(dt, camera);
    visuals.forEach(syncReflection);

    if (cameraAnimating) {
      cameraOrbitProgress = Math.min(1, cameraOrbitProgress + dt / cameraOrbitDuration);
      const t = easeInOutCubic(cameraOrbitProgress);
      controls.target.lerpVectors(cameraStartTarget, desiredTarget, t);
      const radius = THREE.MathUtils.lerp(cameraStartSpherical.radius, cameraEndSpherical.radius, t);
      const phi = THREE.MathUtils.lerp(cameraStartSpherical.phi, cameraEndSpherical.phi, t);
      const theta = cameraStartSpherical.theta + cameraOrbitThetaDelta * t;
      camera.position.copy(controls.target).add(
        cameraOrbitOffset.setFromSphericalCoords(radius, phi, theta),
      );
      camera.up.set(0, 1, 0);
      camera.lookAt(controls.target);
      if (cameraOrbitProgress >= 1) {
        camera.position.copy(desiredCameraPosition);
        controls.target.copy(desiredTarget);
        camera.up.set(0, 1, 0);
        camera.lookAt(controls.target);
        controls.update();
        controls.saveState();
        cameraAnimating = false;
        const done = cameraComplete;
        cameraComplete = null;
        done?.();
      }
    } else if (controls.enabled) {
      controls.update();
    }

    (floorGridMaterial.uniforms.uCamera.value as THREE.Vector3).copy(camera.position);
    (floorPlateMaterial.uniforms.uCamera.value as THREE.Vector3).copy(camera.position);
    composer.render();
    syncGlassOverlays();
    syncFrost();
    if (firstRender) {
      firstRender = false;
      options.onFirstRender?.();
    }
    if (tweens.size > 0 || cameraAnimating || particlePoints || phase !== 'initializing' || controls.enabled) {
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
    controls.target.copy(wallLookTarget);
    desiredCameraPosition.copy(wallCameraPosition);
    desiredTarget.copy(wallLookTarget);
    controls.update();

    const entries = Array.from(visuals.values());
    if (!entries.length) {
      finishIntro();
      return;
    }

    fadeSceneCanvas(reducedMotion ? WALL_ENTRANCE.reducedMotionMs : WALL_ENTRANCE.sceneFadeMs);

    if (reducedMotion) {
      entries.forEach((visual) => {
        applyHomePose(visual);
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
      visual.root.rotation.set(rotateX, visual.homeRotationY, 0);
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
        visual.root.rotation.set(0, visual.homeRotationY, 0);
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
      applyHomePose(visual);
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
      const planarX =
        -layout.wallWidth / 2 +
        layout.cardWidth / 2 +
        column * (layout.cardWidth + layout.gapX);
      const planarY =
        layout.wallHeight / 2 -
        row * (layout.cardHeight + layout.gapY) -
        layout.cardHeight / 2;
      visual.homePosition.set(planarX, planarY, 0);
      visual.homeRotationY = 0;
      visual.root.scale.copy(visual.homeScale);
      if (
        phase !== 'initializing' &&
        !layoutOptions?.playIntro &&
        !layoutOptions?.playFilter
      ) {
        applyHomePose(visual);
      }
      column += 1;
      if (column === rowCardCount) {
        row += 1;
        column = 0;
      }
    });

    let lowestY = Infinity;
    visuals.forEach((visual) => {
      lowestY = Math.min(lowestY, visual.homePosition.y);
    });
    visuals.forEach((visual) => {
      visual.isBottomRow = Math.abs(visual.homePosition.y - lowestY) < 0.05;
      syncReflection(visual);
    });

    floorY = -layout.wallHeight / 2 - layout.cardHeight * FLOOR_HOVER_GAP;
    stageRoot.position.y = floorY;
    floorGridMaterial.uniforms.uFade.value = Math.max(layout.wallWidth * 3.1, 32);
    wallLookTarget.set(0, 0, 0);
    wallCameraPosition = new THREE.Vector3(
      0,
      layout.wallHeight * WALL_CAMERA_HEIGHT_FACTOR,
      fitCameraDistance(layout),
    );
    if (phase !== 'architecture') {
      controls.minDistance = Math.max(wallCameraPosition.z * 0.45, 6);
      controls.maxDistance = wallCameraPosition.z * 2.2;
    }
    syncParticleScale();

    if (phase === 'architecture' || phase === 'focused') {
      if (phase === 'focused') applyFocusPose(false);
      requestRender();
      return;
    }

    desiredTarget.copy(wallLookTarget);
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
      if (layoutOptions?.snapCamera || phase === 'initializing') {
        camera.position.copy(desiredCameraPosition);
        controls.target.copy(desiredTarget);
        camera.up.set(0, 1, 0);
        camera.lookAt(controls.target);
        controls.update();
        controls.saveState();
        cameraAnimating = false;
      }
      if (phase === 'initializing') {
        phase = 'wall';
        setOrbitEnabled(true);
      }
    }
    requestRender();
  };

  const applyFaceMaterial = (material: THREE.ShaderMaterial) => {
    material.uniforms.uBright.value = 1;
    material.needsUpdate = true;
  };

  const reconcile = (
    items: Application3DWallItem[],
    reconcileOptions?: { playIntro?: boolean; playFilter?: boolean; forceRepaint?: boolean },
  ) => {
    const playIntro =
      Boolean(reconcileOptions?.playIntro) &&
      items.length > 0 &&
      !entrancePlayed;
    const playFilter =
      Boolean(reconcileOptions?.playFilter) &&
      items.length > 0 &&
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
        const next = createCardTextures(item, translate);
        previous.texture.dispose();
        previous.texture = next.texture;
        previous.cardTone = next.cardTone;
        previous.material.uniforms.uMap.value = previous.texture;
        applyFaceMaterial(previous.material);
        previous.sideTexture.dispose();
        previous.sideTexture = paintCardSideTexture(next.cardTone);
        applyCardSideMaterial(previous.sideMaterial, previous.sideTexture);
        previous.reflectionMaterial.uniforms.uMap.value = previous.texture;
        previous.reflectionMaterial.uniforms.uTint.value.set(CARD_TONE[next.cardTone].tint);
        previous.floorGlowMaterial.uniforms.uColor.value.set(CARD_TONE[next.cardTone].tint);
        previous.glassEl.replaceChildren();
        previous.glassEl.dataset.tone = next.cardTone;
        previous.glassEl.appendChild(cloneCardChromeCanvas(next.texture.image as HTMLCanvasElement));
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
      wallGroup.add(root);
      const glassEl = createGlassOverlay(painted.cardTone, painted.texture.image as HTMLCanvasElement);
      const reflectionMaterial = createCardReflectionMaterial(
        painted.texture,
        CARD_TONE[painted.cardTone].tint,
      );
      const reflection = new THREE.Mesh(cardFaceGeometry, reflectionMaterial);
      reflection.position.set(0, -1 - FLOOR_HOVER_GAP * 2, 0.5);
      reflection.renderOrder = 1;
      root.add(reflection);
      const floorGlowMaterial = createFloorGlowMaterial(CARD_TONE[painted.cardTone].tint);
      const floorGlow = new THREE.Mesh(floorGlowGeometry, floorGlowMaterial);
      floorGlow.rotation.x = -Math.PI / 2;
      floorGlow.renderOrder = 4;
      floorGlow.visible = false;
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
        homeRotationY: 0,
        cardTone: painted.cardTone,
        hoverAmount: 0,
        glassEl,
        glassOpacity: 1,
        isBottomRow: false,
        reflection,
        reflectionMaterial,
        floorGlow,
        floorGlowMaterial,
      });
    });

    if (!particlesBuilt) {
      rebuildParticles();
      particlesBuilt = true;
    }
    syncParticleScale();
    layoutVisuals({ playIntro, playFilter });
  };

  const shortestAngleDelta = (from: number, to: number) => {
    let delta = to - from;
    while (delta > Math.PI) delta -= Math.PI * 2;
    while (delta < -Math.PI) delta += Math.PI * 2;
    return delta;
  };

  const easeCameraTo = (
    position: THREE.Vector3,
    target: THREE.Vector3,
    duration = 0.55,
    onComplete?: () => void,
  ) => {
    if (disposed) return;
    cameraComplete = onComplete ?? null;
    desiredCameraPosition.copy(position);
    desiredTarget.copy(target);
    if (
      reducedMotion
      || (
        camera.position.distanceTo(position) < 0.08
        && controls.target.distanceTo(target) < 0.08
      )
    ) {
      camera.position.copy(position);
      controls.target.copy(target);
      camera.up.set(0, 1, 0);
      camera.lookAt(controls.target);
      controls.update();
      controls.saveState();
      cameraAnimating = false;
      requestRender();
      const done = cameraComplete;
      cameraComplete = null;
      done?.();
      return;
    }
    cameraStartTarget.copy(controls.target);
    cameraStartSpherical.setFromVector3(
      cameraOrbitOffset.copy(camera.position).sub(controls.target),
    );
    cameraEndSpherical.setFromVector3(
      cameraOrbitOffset.copy(position).sub(target),
    );
    cameraOrbitThetaDelta = shortestAngleDelta(
      cameraStartSpherical.theta,
      cameraEndSpherical.theta,
    );
    cameraStartSpherical.radius = Math.max(cameraStartSpherical.radius, 0.01);
    cameraEndSpherical.radius = Math.max(cameraEndSpherical.radius, 0.01);
    cameraOrbitProgress = 0;
    cameraOrbitDuration = duration;
    cameraAnimating = true;
    requestRender();
  };

  const snapCameraHome = () => {
    camera.position.copy(wallCameraPosition);
    controls.target.copy(wallLookTarget);
    desiredCameraPosition.copy(wallCameraPosition);
    desiredTarget.copy(wallLookTarget);
    camera.up.set(0, 1, 0);
    camera.lookAt(controls.target);
    controls.update();
    controls.saveState();
    cameraAnimating = false;
  };

  const resetCamera = () => {
    if (disposed) return;
    easeCameraTo(wallCameraPosition, wallLookTarget, 0.55);
  };

  const applyFocusPose = (animate: boolean) => {
    const duration = (reducedMotion || !animate ? 0 : FOCUS_MOTION.durationMs) / 1000;
    visuals.forEach((visual) => {
      const selected = Boolean(focusedId) && visual.item.id === focusedId;
      const toPos = visual.homePosition.clone();
      const toScale = visual.homeScale.clone();
      let toOpacity = 1;
      let toBright = 1;
      if (focusedId) {
        if (selected) {
          focusLift.set(0, 0, FOCUS_MOTION.liftZ);
          toPos.add(focusLift);
          toScale.multiplyScalar(FOCUS_MOTION.scale);
          toBright = 1.1;
        } else {
          toOpacity = FOCUS_MOTION.dimOpacity;
          toBright = FOCUS_MOTION.dimBright;
        }
      }
      const fromPos = visual.root.position.clone();
      const fromScale = visual.root.scale.clone();
      const fromOpacity = visual.glassOpacity;
      const fromBright = visual.material.uniforms.uBright.value as number;
      startTween(duration, (t) => {
        visual.root.position.lerpVectors(fromPos, toPos, t);
        visual.root.scale.lerpVectors(fromScale, toScale, t);
        setCardOpacity(visual, fromOpacity + (toOpacity - fromOpacity) * t);
        setCardBrightness(visual, fromBright + (toBright - fromBright) * t);
      }, () => {
        visual.root.position.copy(toPos);
        visual.root.scale.copy(toScale);
        setCardOpacity(visual, toOpacity);
        setCardBrightness(visual, toBright);
      }, easeInOutCubic, 0, true);
    });
  };

  const applyWallOrbitDistance = () => {
    controls.minDistance = Math.max(wallCameraPosition.z * 0.45, 6);
    controls.maxDistance = wallCameraPosition.z * 2.2;
  };

  const setGlassLayerVisible = (visible: boolean) => {
    glassLayer.style.visibility = visible ? '' : 'hidden';
    glassLayer.style.pointerEvents = visible ? '' : 'none';
  };

  const hideWallCards = (animate: boolean) => {
    const duration = (reducedMotion || !animate ? 0 : ARCHITECTURE_MOTION.wallHideMs) / 1000;
    const toScaleMul = ARCHITECTURE_MOTION.wallHideScale;
    if (!visuals.size) {
      wallGroup.visible = false;
      setGlassLayerVisible(false);
      return;
    }
    visuals.forEach((visual) => {
      const fromPos = visual.root.position.clone();
      const fromScale = visual.root.scale.clone();
      const fromOpacity = visual.glassOpacity;
      const toScale = visual.homeScale.clone().multiplyScalar(toScaleMul);
      startTween(duration, (t) => {
        visual.root.position.lerpVectors(fromPos, visual.homePosition, t);
        visual.root.scale.lerpVectors(fromScale, toScale, t);
        setCardOpacity(visual, fromOpacity * (1 - t));
        setCardBrightness(visual, 1);
      }, () => {
        visual.root.position.copy(visual.homePosition);
        visual.root.scale.copy(toScale);
        setCardOpacity(visual, 0);
        wallGroup.visible = false;
        setGlassLayerVisible(false);
      }, easeInOutCubic, 0, true);
    });
  };

  const restoreWallCards = (animate: boolean) => {
    focusedId = '';
    phase = 'wall';
    wallGroup.visible = true;
    setGlassLayerVisible(true);
    applyPolarLimits(WALL_POLAR);
    applyWallOrbitDistance();
    applyFocusPose(animate);
    setOrbitEnabled(true);
  };

  const disposeArchitecture = () => {
    architectureView?.dispose();
    architectureView = null;
  };

  const focus = (applicationId: string | null) => {
    if (disposed) return;
    disposeArchitecture();
    const nextId = applicationId && visuals.has(applicationId) ? applicationId : '';
    if (!nextId) {
      restoreWallCards(true);
      requestRender();
      return;
    }
    focusedId = nextId;
    phase = 'focused';
    setOrbitEnabled(false);
    applyFocusPose(true);
    requestRender();
  };

  const setPlaneReveal = (planeGroup: THREE.Group, t: number) => {
    planeGroup.traverse((child) => {
      const mesh = child as THREE.Mesh;
      const material = mesh.material as THREE.Material | THREE.Material[] | undefined;
      const list = material ? (Array.isArray(material) ? material : [material]) : [];
      list.forEach((item) => {
        if (!('opacity' in item)) return;
        const role = mesh.userData.archRole as string | undefined;
        if (role === 'plane-mesh' || role === 'plane-veneer') {
          const restOpacity = Number(mesh.userData.restOpacity ?? ARCH_PLANE_OPACITY);
          const restEmissive = Number(
            mesh.userData.restEmissiveIntensity ?? ARCH_PLANE_EMISSIVE_INTENSITY,
          );
          item.transparent = true;
          item.opacity = 0.02 + (restOpacity - 0.02) * t;
          if ('emissiveIntensity' in item) {
            (item as THREE.MeshStandardMaterial).emissiveIntensity = restEmissive * t;
          }
        } else if (role === 'plane-rim') {
          item.transparent = true;
          const rim = item as THREE.ShaderMaterial;
          if (rim.uniforms?.uOpacity) {
            rim.uniforms.uOpacity.value = ARCH_PLANE_RIM_OPACITY * t;
          }
          if (rim.uniforms?.uStroke) {
            rim.uniforms.uStroke.value = ARCH_PLANE_RIM_STROKE_OPACITY * t;
          }
          if (!rim.uniforms?.uOpacity) {
            item.opacity = ARCH_PLANE_RIM_OPACITY * t;
          }
        } else if (role === 'plane-title') {
          item.transparent = true;
          item.opacity = t;
        }
      });
    });
  };

  const expandArchitectureNodes = () => {
    if (!architectureView || phase !== 'architecture') return;
    const start = ARCHITECTURE_MOTION.startScale;
    const planeMs = (reducedMotion ? WALL_ENTRANCE.reducedMotionMs : ARCHITECTURE_MOTION.planeMs) / 1000;
    const expandMs = (reducedMotion ? WALL_ENTRANCE.reducedMotionMs : ARCHITECTURE_MOTION.expandMs) / 1000;
    const labelMs = (reducedMotion ? WALL_ENTRANCE.reducedMotionMs : ARCHITECTURE_MOTION.labelMs) / 1000;
    const tubeMs = (reducedMotion ? WALL_ENTRANCE.reducedMotionMs : ARCHITECTURE_MOTION.tubeMs) / 1000;
    const lookDir = architectureLookTarget.clone().sub(architectureCameraPosition).normalize();
    const inFront = architectureCameraPosition.clone().add(
      lookDir.multiplyScalar(ARCHITECTURE_MOTION.planeStartDistance),
    );
    architectureView.group.scale.setScalar(1);
    architectureView.planeGroups.forEach((planeGroup, index) => {
      const rest = (planeGroup.userData.restPosition as THREE.Vector3 | undefined)?.clone()
        ?? new THREE.Vector3();
      const delay = reducedMotion ? 0 : architecturePlaneDelayMs(index) / 1000;
      planeGroup.position.copy(inFront);
      planeGroup.scale.setScalar(start);
      setPlaneReveal(planeGroup, 0);
      startTween(planeMs, (t) => {
        planeGroup.position.lerpVectors(inFront, rest, t);
        planeGroup.scale.setScalar(start + (1 - start) * t);
        setPlaneReveal(planeGroup, t);
      }, () => {
        planeGroup.position.copy(rest);
        planeGroup.scale.setScalar(1);
        setPlaneReveal(planeGroup, 1);
      }, easeLinear, delay, true);
    });
    const nodeDelay = reducedMotion ? 0 : architectureNodeDelayMs() / 1000;
    const labelDelay = reducedMotion ? 0 : architectureLabelDelayMs() / 1000;
    architectureView.nodeGroups.forEach((nodeGroup) => {
      nodeGroup.scale.setScalar(0);
      startTween(expandMs, (t) => {
        nodeGroup.scale.setScalar(t);
      }, () => {
        nodeGroup.scale.setScalar(1);
      }, easeLinear, nodeDelay, true);
    });
    architectureView.nodeLabels.forEach((label) => {
      const targetScale = label.userData.labelScale as THREE.Vector3 | undefined;
      const toX = targetScale?.x ?? 1;
      const toY = targetScale?.y ?? 1;
      label.scale.set(0, 0, 1);
      startTween(labelMs, (t) => {
        label.scale.set(toX * t, toY * t, 1);
      }, () => {
        label.scale.set(toX, toY, 1);
      }, easeLinear, labelDelay, true);
    });
    const tubeDelay = reducedMotion ? 0 : architectureTubeDelayMs() / 1000;
    architectureView.interPlaneTubes.forEach((tube) => {
      tube.scale.setScalar(0);
      startTween(tubeMs, (t) => {
        tube.scale.setScalar(t);
      }, () => {
        tube.scale.setScalar(1);
      }, easeLinear, tubeDelay, true);
    });
    architectureView.intraPlaneTubes.forEach((tube) => {
      tube.scale.setScalar(0);
      startTween(expandMs, (t) => {
        tube.scale.setScalar(t);
      }, () => {
        tube.scale.setScalar(1);
      }, easeLinear, nodeDelay, true);
    });
  };

  const flyArchitectureCameraThenExpand = () => {
    if (!architectureView || phase !== 'architecture' || disposed) return;
    applyPolarLimits(ARCH_POLAR);
    const pose = resolveArchitectureCameraPose(
      architectureView.layout,
      { position: wallCameraPosition, target: wallLookTarget },
      camera.aspect,
      camera.fov,
    );
    architectureLookTarget.set(pose.target.x, pose.target.y, pose.target.z);
    architectureCameraPosition.set(pose.position.x, pose.position.y, pose.position.z);
    controls.minDistance = Math.max(pose.radius * 0.35, 8);
    controls.maxDistance = pose.radius * 2.8;
    const cameraMs = reducedMotion ? WALL_ENTRANCE.reducedMotionMs : ARCHITECTURE_MOTION.cameraMs;
    easeCameraTo(
      architectureCameraPosition,
      architectureLookTarget,
      cameraMs / 1000,
      () => {
        if (phase !== 'architecture' || disposed) return;
        expandArchitectureNodes();
        setOrbitEnabled(true);
      },
    );
  };

  const showArchitecture = (data: Application3DArchitectureData) => {
    if (disposed) return;
    cancelTweens();
    cameraComplete = null;
    disposeArchitecture();
    phase = 'architecture';
    applyPolarLimits(ARCH_POLAR);
    setOrbitEnabled(false);
    focusedId = '';
    hideWallCards(true);
    architectureView = createArchitectureTreeGroup(data, translate);
    architectureView.group.scale.setScalar(1);
    architectureView.planeGroups.forEach((planeGroup) => {
      planeGroup.scale.setScalar(0);
    });
    architectureView.nodeGroups.forEach((nodeGroup) => {
      nodeGroup.scale.setScalar(0);
    });
    architectureView.nodeLabels.forEach((label) => {
      label.scale.set(0, 0, 1);
    });
    architectureView.interPlaneTubes.forEach((tube) => {
      tube.scale.setScalar(0);
    });
    architectureView.intraPlaneTubes.forEach((tube) => {
      tube.scale.setScalar(0);
    });
    scene.add(architectureView.group);
    flyArchitectureCameraThenExpand();
    requestRender();
  };

  const hideArchitecture = () => {
    if (disposed) return;
    cameraComplete = null;
    cancelTweens();
    disposeArchitecture();
    easeCameraTo(wallCameraPosition, wallLookTarget, reducedMotion ? 0.2 : 0.7);
    restoreWallCards(true);
    requestRender();
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

  const idleCursor = () => 'grab';

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
    if (!active || !options.interactive || pointerDown || phase !== 'wall') {
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

  const handleContextMenu = (event: Event) => {
    event.preventDefault();
  };

  const handlePointerUp = (event: PointerEvent) => {
    if (!active || !options.interactive || !pointerDown) return;
    const dx = event.clientX - pointerDown.x;
    const dy = event.clientY - pointerDown.y;
    pointerDown = null;
    if (event.button !== 0) {
      syncCursor(event.clientX, event.clientY);
      return;
    }
    if (Math.hypot(dx, dy) > CLICK_DRAG_THRESHOLD_PX) {
      syncCursor(event.clientX, event.clientY);
      return;
    }
    if (phase === 'initializing') finishIntro();
    const applicationId = pickApplicationId(event.clientX, event.clientY);
    const visual = applicationId ? visuals.get(applicationId) : undefined;
    if (visual) {
      if (phase === 'architecture') return;
      options.onSelect(visual.item);
      renderer.domElement.style.cursor = 'pointer';
      return;
    }
    if (phase === 'focused') {
      options.onBackgroundClick?.();
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
      if (phase === 'initializing') return;
      layoutVisuals({ snapCamera: phase === 'wall' });
      if (phase === 'focused') applyFocusPose(false);
    }, RESIZE_LAYOUT_DEBOUNCE_MS);
  };

  const resize = () => {
    if (resizeRaf !== null) return;
    resizeRaf = window.requestAnimationFrame(() => {
      resizeRaf = null;
      if (!disposed) resizeNow();
    });
  };

  renderer.domElement.addEventListener('contextmenu', handleContextMenu);
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

  return {
    reconcile,
    resize,
    resetCamera,
    focus,
    showArchitecture,
    hideArchitecture,
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
      setOrbitEnabled(orbitAllowed());
      resizeNow();
      requestRender();
    },
    dispose: () => {
      disposed = true;
      cameraComplete = null;
      cancelTweens();
      clearIntroTimers();
      if (resizeLayoutTimer !== null) window.clearTimeout(resizeLayoutTimer);
      if (frameId !== null) window.cancelAnimationFrame(frameId);
      if (resizeRaf !== null) window.cancelAnimationFrame(resizeRaf);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener('contextmenu', handleContextMenu);
      renderer.domElement.removeEventListener('pointerdown', handlePointerDown);
      renderer.domElement.removeEventListener('pointermove', handlePointerMove);
      renderer.domElement.removeEventListener('pointerup', handlePointerUp);
      renderer.domElement.removeEventListener('pointerleave', handlePointerLeave);
      controls.dispose();
      visuals.forEach(disposeVisual);
      visuals.clear();
      disposeArchitecture();
      wallGroup.removeFromParent();
      floorPlate.geometry.dispose();
      floorPlateMaterial.dispose();
      floorGrid.geometry.dispose();
      floorGridMaterial.dispose();
      atmosphere.geometry.dispose();
      atmosphereMaterial.dispose();
      atmosphere.removeFromParent();
      stageRoot.removeFromParent();
      if (particlePoints) {
        scene.remove(particlePoints);
        particlePoints.geometry.dispose();
        particleMaterial?.dispose();
      }
      flareTexture.dispose();
      if (scene.background instanceof THREE.Texture) scene.background.dispose();
      cardGeometry.dispose();
      cardFaceGeometry.dispose();
      floorGlowGeometry.dispose();
      composer.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      glassLayer.remove();
    },
  };
};
