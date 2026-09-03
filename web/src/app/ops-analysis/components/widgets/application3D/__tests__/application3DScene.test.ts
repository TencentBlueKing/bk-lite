// @vitest-environment jsdom

import * as THREE from 'three';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Application3DArchitectureData, Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';
import {
  ARCH_CAMERA_PHI,
  ARCH_PLANE_Y,
  describeWallCameraSpherical,
  layoutApplication3DArchitecture,
  resolveArchitectureCameraPose,
} from '../application3DArchitecture';
import { resolveApplication3DWallCamera } from '../application3DLayout';
import {
  expandArchitectureCabinetWorldBox,
  overlayScreenRect,
  projectWorldBoxToScreenRect,
  screenRectsIntersect,
} from '../application3DArchitectureOverlay';
import {
  APPLICATION3D_ORBIT_PAN,
  APPLICATION3D_USER_POLAR,
  APPLICATION3D_WALL_GROUP_NAME,
  createApplication3DScene,
} from '../application3DScene';

/** Rejected overhead pitch — fence only; production uses ARCH_CAMERA_PHI. */
const ARCH_PREVIOUS_CAMERA_PHI = Math.PI / 2 - Math.PI / 8;

const captured = vi.hoisted(() => ({
  scene: null as THREE.Scene | null,
  camera: null as THREE.PerspectiveCamera | null,
  controls: null as {
    enablePan: boolean;
    screenSpacePanning: boolean;
    minPolarAngle: number;
    maxPolarAngle: number;
    minDistance: number;
    maxDistance: number;
    enabled: boolean;
    target: THREE.Vector3;
  } | null,
  raf: [] as FrameRequestCallback[],
  now: 0,
}));

vi.mock('three', async (importOriginal) => {
  const actual = await importOriginal<typeof import('three')>();
  class WebGLRendererMock {
    domElement = document.createElement('canvas');
    outputColorSpace = actual.SRGBColorSpace;
    toneMapping = actual.NoToneMapping;
    toneMappingExposure = 1;
    constructor() {
      this.domElement.getBoundingClientRect = () => ({
        x: 0,
        y: 0,
        top: 0,
        left: 0,
        right: 320,
        bottom: 180,
        width: 320,
        height: 180,
        toJSON: () => ({}),
      });
      this.domElement.setPointerCapture = () => undefined;
      this.domElement.releasePointerCapture = () => undefined;
    }
    setClearColor() {}
    setPixelRatio() {}
    setSize() {}
    getPixelRatio() { return 1; }
    dispose() {}
    forceContextLoss() {}
  }
  return {
    ...actual,
    WebGLRenderer: WebGLRendererMock,
    Scene: class extends actual.Scene {
      constructor() {
        super();
        captured.scene = this;
      }
    },
    PerspectiveCamera: class extends actual.PerspectiveCamera {
      constructor(fov: number, aspect: number, near: number, far: number) {
        super(fov, aspect, near, far);
        captured.camera = this;
      }
    },
    TextureLoader: class {
      load() {
        return new actual.Texture();
      }
    },
  };
});

vi.mock('three/examples/jsm/controls/OrbitControls.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('three/examples/jsm/controls/OrbitControls.js')>();
  return {
    OrbitControls: class extends actual.OrbitControls {
      constructor(object: THREE.Camera, domElement?: HTMLElement) {
        super(object, domElement);
        captured.controls = this;
      }
    },
  };
});

vi.mock('three/examples/jsm/postprocessing/EffectComposer.js', () => ({
  EffectComposer: class {
    addPass() {}
    setSize() {}
    render() {}
    dispose() {}
  },
}));
vi.mock('three/examples/jsm/postprocessing/RenderPass.js', () => ({
  RenderPass: class {
    clearAlpha = 0;
  },
}));
vi.mock('three/examples/jsm/postprocessing/UnrealBloomPass.js', () => ({
  UnrealBloomPass: class {
    enabled = false;
    resolution = { set() {} };
  },
}));
vi.mock('three/examples/jsm/postprocessing/OutputPass.js', () => ({
  OutputPass: class {},
}));

const health = {
  state: 'normal' as const,
  reason: 'no_active_alarm' as const,
  activeAlarmCount: 0,
  severityCounts: { critical: 0, error: 0, warning: 0, info: 0 },
  noDataAlarmCount: 0,
  highestSeverity: { id: 'normal' as const, label: '正常', rank: 0 as const, color: 'success' as const },
  stale: false,
};

const wallItem: Application3DWallItem = {
  id: 'sys-1',
  name: '门户系统',
  health,
};

const makeWallItems = (count: number): Application3DWallItem[] =>
  Array.from({ length: count }, (_, index) => ({
    id: `sys-${index + 1}`,
    name: `系统${index + 1}`,
    health,
  }));

const architecture: Application3DArchitectureData = {
  systemId: 'sys-1',
  refreshedAt: '2026-09-01T00:00:00Z',
  nodes: [
    { id: 'sys-1', kind: 'system', name: '门户系统', health },
    { id: 'app-1', kind: 'application', name: '门户', health },
    { id: 'host-1', kind: 'host', name: 'web-1', health },
  ],
  edges: [
    { id: 'e1', sourceId: 'sys-1', targetId: 'app-1', relation: 'system_contains_application' },
    { id: 'e2', sourceId: 'app-1', targetId: 'host-1', relation: 'application_run_host' },
  ],
};

const flushFrames = (ms = 16) => {
  const queue = captured.raf.splice(0, captured.raf.length);
  captured.now += ms;
  queue.forEach((callback) => callback(captured.now));
};

describe('application3D architecture scene', () => {
  let mount: HTMLDivElement;

  beforeEach(() => {
    captured.scene = null;
    captured.camera = null;
    captured.controls = null;
    captured.raf = [];
    captured.now = 1_000;
    mount = document.createElement('div');
    Object.defineProperty(mount, 'clientWidth', { configurable: true, value: 320 });
    Object.defineProperty(mount, 'clientHeight', { configurable: true, value: 180 });
    document.body.appendChild(mount);
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      captured.raf.push(callback);
      return captured.raf.length;
    });
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      captured.raf.splice(id - 1, 1);
    });
    vi.spyOn(performance, 'now').mockImplementation(() => captured.now);
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      disconnect() {}
    });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function (
      this: HTMLCanvasElement,
    ) {
      const context: Record<string, unknown> = {
        canvas: this,
        fillStyle: '',
        strokeStyle: '',
        font: '',
        filter: '',
        textAlign: 'center',
        textBaseline: 'middle',
        lineWidth: 1,
        lineJoin: 'round',
        lineCap: 'round',
        globalAlpha: 1,
        createLinearGradient: () => ({ addColorStop: () => undefined }),
        createRadialGradient: () => ({ addColorStop: () => undefined }),
        measureText: (text: string) => ({ width: text.length * 8 }),
      };
      return new Proxy(context, {
        get: (target, prop) => {
          if (prop in target) return target[prop as string];
          return () => undefined;
        },
        set: (target, prop, value) => {
          target[prop as string] = value;
          return true;
        },
      }) as unknown as CanvasRenderingContext2D;
    });
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent() { return false; },
      onchange: null,
    }));
  });

  afterEach(() => {
    mount.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const mountScene = () => {
    const controller = createApplication3DScene(mount, {
      interactive: true,
      translate: (_id, fallback = '') => fallback,
      onSelect: () => undefined,
    });
    controller.reconcile([wallItem], { playIntro: false });
    flushFrames();
    return controller;
  };

  const wallGroup = () => captured.scene?.getObjectByName(APPLICATION3D_WALL_GROUP_NAME);
  const architectureGroup = () => captured.scene?.getObjectByName('application3d-architecture');
  const planeGroups = () => (architectureGroup()?.children ?? []).filter(
    (child) => child.userData.archRole === 'plane',
  );

  it('hides the wall after shrink-fade and expands planes after the camera lands', () => {
    const controller = mountScene();
    const wallY = captured.camera?.position.y ?? 0;
    controller.showArchitecture(architecture);
    flushFrames(16);
    expect(wallGroup()?.parent).toBe(captured.scene);
    expect(wallGroup()?.children.length).toBeGreaterThan(0);
    const planesBefore = planeGroups();
    expect(planesBefore).toHaveLength(2);
    expect(planesBefore.every((plane) => plane.scale.x < 0.2)).toBe(true);
    expect((captured.camera?.position.y ?? 0)).toBeGreaterThan(wallY);

    for (let step = 0; step < 30; step += 1) flushFrames(20);
    expect(wallGroup()?.visible).toBe(false);

    for (let step = 0; step < 110; step += 1) flushFrames(20);
    expect(planeGroups().every((plane) => plane.scale.x < 0.2)).toBe(true);
    expect(wallGroup()?.visible).toBe(false);

    for (let step = 0; step < 80; step += 1) flushFrames(20);
    expect(wallGroup()?.visible).toBe(false);
    const planesAfter = planeGroups();
    expect(planesAfter).toHaveLength(2);
    expect(planesAfter.every((plane) => Math.abs(plane.scale.x - 1) < 0.02)).toBe(true);
    expect(planesAfter[0].position.y).toBeCloseTo(ARCH_PLANE_Y.application);
    expect(planesAfter[1].position.y).toBeCloseTo(ARCH_PLANE_Y.host);
    expect(planesAfter[0].position.y).toBeLessThan(planesAfter[1].position.y);
    expect(planesAfter[0].userData.planeShape).toBe('frustum');
    expect(planesAfter[1].userData.planeShape).toBe('plane');
    const planeMesh = planesAfter[0].children.find(
      (child) => child.userData.archRole === 'plane-mesh',
    );
    expect(planeMesh?.userData.planeShape).toBe('frustum');
    expect(planeMesh?.rotation.x).toBeCloseTo(0);
    const layout = layoutApplication3DArchitecture(architecture);
    const wallSpherical = describeWallCameraSpherical({
      position: { x: 0, y: wallY, z: 20 },
      target: { x: 0, y: 0, z: 0 },
    });
    const pose = resolveArchitectureCameraPose(
      layout,
      16 / 9,
    );
    expect(pose.phi).toBeCloseTo(ARCH_CAMERA_PHI);
    expect(pose.phi).toBeGreaterThan(ARCH_PREVIOUS_CAMERA_PHI);
    expect(pose.phi).not.toBeCloseTo(wallSpherical.phi - Math.PI / 2.5, 1);
    expect(captured.camera?.position.y).toBeCloseTo(pose.position.y, 0);
    expect(captured.camera?.position.y).toBeLessThan(
      pose.target.y + pose.radius * Math.cos(ARCH_PREVIOUS_CAMERA_PHI),
    );
    expect(wallGroup()?.visible).toBe(false);
    controller.dispose();
  });

  it('keeps the host plane hidden until the application fly-in finishes', () => {
    const controller = mountScene();
    controller.showArchitecture(architecture);
    for (let step = 0; step < 155; step += 1) flushFrames(20);
    const [app, host] = planeGroups();
    expect(app?.userData.planeKind).toBe('application');
    expect(host?.userData.planeKind).toBe('host');
    const hostRest = (host?.userData.restPosition as THREE.Vector3 | undefined)?.clone();
    expect(hostRest).toBeTruthy();
    expect(app?.scale.x).toBeGreaterThan(0);
    expect(app?.scale.x).toBeLessThan(1);
    expect(host?.scale.x).toBe(0);
    expect(host?.position.distanceTo(hostRest ?? new THREE.Vector3())).toBeLessThan(0.05);

    for (let step = 0; step < 10; step += 1) flushFrames(20);
    expect(app?.scale.x).toBeGreaterThan(0.2);
    expect(app?.scale.x).toBeLessThan(1);
    expect(host?.scale.x).toBe(0);
    expect(host?.position.distanceTo(hostRest ?? new THREE.Vector3())).toBeLessThan(0.05);

    for (let step = 0; step < 16; step += 1) flushFrames(20);
    expect(Math.abs((app?.scale.x ?? 0) - 1)).toBeLessThan(0.02);
    expect(host?.scale.x).toBeGreaterThan(0);
    expect(host?.scale.x).toBeLessThan(1);
    expect(host?.position.distanceTo(hostRest ?? new THREE.Vector3())).toBeGreaterThan(1);

    for (let step = 0; step < 25; step += 1) flushFrames(20);
    expect(Math.abs((app?.scale.x ?? 0) - 1)).toBeLessThan(0.02);
    expect(Math.abs((host?.scale.x ?? 0) - 1)).toBeLessThan(0.02);
    expect(host?.position.distanceTo(hostRest ?? new THREE.Vector3())).toBeLessThan(0.05);
    controller.dispose();
  });

  it('starts hiding the focused wall while the architecture camera flies', () => {
    const controller = mountScene();
    const card = wallGroup()?.children[0];
    const homeZ = card?.position.z ?? 0;
    controller.focus('sys-1');
    for (let step = 0; step < 30; step += 1) flushFrames(20);
    expect(card?.position.z ?? 0).toBeGreaterThan(homeZ + 0.2);
    const wallY = captured.camera?.position.y ?? 0;
    controller.showArchitecture(architecture);
    for (let step = 0; step < 25; step += 1) flushFrames(16);
    expect(planeGroups().every((plane) => plane.scale.x < 0.2)).toBe(true);
    expect((captured.camera?.position.y ?? 0)).toBeGreaterThan(wallY);
    for (let step = 0; step < 20; step += 1) flushFrames(20);
    expect(wallGroup()?.visible).toBe(false);
    controller.dispose();
  });

  it('returns from architecture to the full wall without disposing wall cards', () => {
    const controller = mountScene();
    const wallStart = captured.camera?.position.clone();
    controller.showArchitecture(architecture);
    for (let step = 0; step < 200; step += 1) flushFrames(20);
    expect(architectureGroup()).toBeTruthy();
    controller.hideArchitecture();
    for (let step = 0; step < 80; step += 1) flushFrames(20);
    expect(architectureGroup()).toBeUndefined();
    expect(wallGroup()?.visible).toBe(true);
    expect(wallGroup()?.children.length).toBeGreaterThan(0);
    expect(captured.camera?.position.distanceTo(wallStart ?? new THREE.Vector3())).toBeLessThan(0.2);
    controller.dispose();
  });

  it('lets wall and architecture user orbit pan and reach straight overhead', () => {
    expect(APPLICATION3D_ORBIT_PAN.enablePan).toBe(true);
    expect(APPLICATION3D_ORBIT_PAN.screenSpacePanning).toBe(true);
    expect(APPLICATION3D_USER_POLAR.min).toBeLessThan(0.02);
    expect(APPLICATION3D_USER_POLAR.min).toBeGreaterThanOrEqual(0);
    expect(APPLICATION3D_USER_POLAR.max).toBeLessThan(Math.PI);
    expect(APPLICATION3D_USER_POLAR.max).toBeGreaterThan(Math.PI / 2);

    const controller = mountScene();
    expect(captured.controls?.enablePan).toBe(true);
    expect(captured.controls?.screenSpacePanning).toBe(true);
    expect(captured.controls?.minPolarAngle).toBeCloseTo(APPLICATION3D_USER_POLAR.min);
    expect(captured.controls?.maxPolarAngle).toBeCloseTo(APPLICATION3D_USER_POLAR.max);
    expect(captured.controls?.minPolarAngle).toBeLessThan(0.02);

    controller.showArchitecture(architecture);
    flushFrames(16);
    expect(captured.controls?.enablePan).toBe(true);
    expect(captured.controls?.minPolarAngle).toBeCloseTo(APPLICATION3D_USER_POLAR.min);
    expect(captured.controls?.maxPolarAngle).toBeCloseTo(APPLICATION3D_USER_POLAR.max);
    controller.dispose();
  });

  it('does not assign scene.environment or RoomEnvironment IBL', () => {
    const sceneSrc = readFileSync(
      resolve(process.cwd(), 'src/app/ops-analysis/components/widgets/application3D/application3DScene.ts'),
      'utf8',
    );
    expect(sceneSrc).not.toContain('RoomEnvironment');
    expect(sceneSrc).not.toContain('PMREMGenerator');
    expect(sceneSrc).not.toContain('scene.environment');
    const controller = mountScene();
    expect(captured.scene?.environment).toBeNull();
    expect(captured.scene?.background).toBeNull();
    controller.showArchitecture(architecture);
    expect(captured.scene?.environment).toBeNull();
    controller.dispose();
    expect(captured.scene?.environment).toBeNull();
  });

  it('lets architecture wheel zoom closer than the wall minDistance floor', () => {
    const sceneSrc = readFileSync(
      resolve(process.cwd(), 'src/app/ops-analysis/components/widgets/application3D/application3DScene.ts'),
      'utf8',
    );
    expect(sceneSrc).toContain('controls.minDistance = Math.max(pose.radius * 0.35, 1.5)');
    expect(sceneSrc).not.toContain('controls.minDistance = Math.max(pose.radius * 0.35, 3)');
    expect(sceneSrc).not.toContain('controls.minDistance = Math.max(pose.radius * 0.35, 6)');
    expect(sceneSrc).not.toContain('controls.minDistance = Math.max(pose.radius * 0.35, 8)');
    expect(sceneSrc).toContain('controls.minDistance = Math.max(wallCameraPosition.z * 0.45, 6)');

    const controller = mountScene();
    const wallMin = captured.controls?.minDistance ?? 0;
    expect(wallMin).toBeGreaterThanOrEqual(6);
    controller.showArchitecture(architecture);
    flushFrames(16);
    const layout = layoutApplication3DArchitecture(architecture);
    const pose = resolveArchitectureCameraPose(
      layout,
      16 / 9,
    );
    expect(captured.controls?.minDistance).toBeCloseTo(Math.max(pose.radius * 0.35, 1.5));
    expect(captured.controls?.minDistance).toBeGreaterThanOrEqual(1.5);
    expect(captured.controls?.maxDistance).toBeCloseTo(pose.radius * 2.8);
    controller.dispose();
  });

  it('ignores right-mouse pointer-up so pan never selects a card', () => {
    const onSelect = vi.fn();
    const controller = createApplication3DScene(mount, {
      interactive: true,
      translate: (_id, fallback = '') => fallback,
      onSelect,
    });
    controller.reconcile([wallItem], { playIntro: false });
    flushFrames();
    const canvas = mount.querySelector('canvas');
    expect(canvas).toBeTruthy();

    const contextEvent = new Event('contextmenu', { bubbles: true, cancelable: true });
    canvas?.dispatchEvent(contextEvent);
    expect(contextEvent.defaultPrevented).toBe(true);

    const point = { clientX: 160, clientY: 90, bubbles: true };
    canvas?.dispatchEvent(new PointerEvent('pointerdown', { ...point, button: 2 }));
    canvas?.dispatchEvent(new PointerEvent('pointerup', { ...point, button: 2 }));
    expect(onSelect).not.toHaveBeenCalled();

    canvas?.dispatchEvent(new PointerEvent('pointerdown', { ...point, button: 0 }));
    canvas?.dispatchEvent(new PointerEvent('pointerup', { ...point, button: 0 }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0].id).toBe('sys-1');
    controller.dispose();
  });

  it('parks 1 and 7 cards on the same wall camera and card size', () => {
    const aspect = 320 / 180;
    const parked = resolveApplication3DWallCamera(1, aspect);
    expect(resolveApplication3DWallCamera(7, aspect)).toEqual(parked);

    const one = createApplication3DScene(mount, {
      interactive: true,
      translate: (_id, fallback = '') => fallback,
      onSelect: () => undefined,
    });
    one.reconcile(makeWallItems(1), { playIntro: true });
    expect(captured.camera?.position.x).toBeCloseTo(parked.x, 5);
    expect(captured.camera?.position.y).toBeCloseTo(parked.y, 5);
    expect(captured.camera?.position.z).toBeCloseTo(parked.z, 5);
    one.dispose();

    const seven = createApplication3DScene(mount, {
      interactive: true,
      translate: (_id, fallback = '') => fallback,
      onSelect: () => undefined,
    });
    seven.reconcile(makeWallItems(7), { playIntro: false });
    flushFrames();
    expect(captured.camera?.position.x).toBeCloseTo(parked.x, 5);
    expect(captured.camera?.position.y).toBeCloseTo(parked.y, 5);
    expect(captured.camera?.position.z).toBeCloseTo(parked.z, 5);
    const sevenScale = wallGroup()?.children[0]?.scale.clone();

    seven.reconcile(makeWallItems(1), { playFilter: true });
    expect(captured.camera?.position.x).toBeCloseTo(parked.x, 5);
    expect(captured.camera?.position.y).toBeCloseTo(parked.y, 5);
    expect(captured.camera?.position.z).toBeCloseTo(parked.z, 5);
    for (let step = 0; step < 12; step += 1) flushFrames(20);
    expect(wallGroup()?.children[0]?.scale.x).toBeCloseTo(sevenScale?.x ?? 0, 5);
    expect(wallGroup()?.children[0]?.scale.y).toBeCloseTo(sevenScale?.y ?? 0, 5);
    seven.dispose();
  });

  it('snaps the wall camera on filter even if the user orbited or an ease is in flight', () => {
    const controller = createApplication3DScene(mount, {
      interactive: true,
      translate: (_id, fallback = '') => fallback,
      onSelect: () => undefined,
    });
    controller.reconcile(makeWallItems(7), { playIntro: false });
    flushFrames();
    const parked = resolveApplication3DWallCamera(7, 320 / 180);
    captured.camera?.position.set(12, 8, 42);
    captured.controls?.target.set(3, -2, 1);
    captured.camera?.lookAt(captured.controls?.target ?? new THREE.Vector3());

    controller.reconcile(makeWallItems(1), { playFilter: true });
    expect(captured.camera?.position.x).toBeCloseTo(parked.x, 5);
    expect(captured.camera?.position.y).toBeCloseTo(parked.y, 5);
    expect(captured.camera?.position.z).toBeCloseTo(parked.z, 5);
    expect(captured.controls?.target.x).toBeCloseTo(0, 5);
    expect(captured.controls?.target.y).toBeCloseTo(0, 5);
    expect(captured.controls?.target.z).toBeCloseTo(0, 5);
    expect(wallGroup()?.children).toHaveLength(1);

    captured.camera?.position.set(-6, 11, 30);
    captured.controls?.target.set(2, 1, -1);
    controller.resetCamera();
    expect(captured.camera?.position.distanceTo(
      new THREE.Vector3(parked.x, parked.y, parked.z),
    )).toBeGreaterThan(0.5);

    controller.reconcile(makeWallItems(7), { playFilter: true });
    expect(captured.camera?.position.x).toBeCloseTo(parked.x, 5);
    expect(captured.camera?.position.y).toBeCloseTo(parked.y, 5);
    expect(captured.camera?.position.z).toBeCloseTo(parked.z, 5);
    flushFrames(80);
    expect(captured.camera?.position.x).toBeCloseTo(parked.x, 5);
    expect(captured.camera?.position.y).toBeCloseTo(parked.y, 5);
    expect(captured.camera?.position.z).toBeCloseTo(parked.z, 5);
    expect(wallGroup()?.children[0]?.scale.x).toBeCloseTo(
      wallGroup()?.children[1]?.scale.x ?? 0,
      5,
    );

    captured.camera?.position.set(9, 6, 28);
    captured.controls?.target.set(-2, 2, 1);
    controller.reconcile(makeWallItems(7));
    expect(captured.camera?.position.x).toBeCloseTo(parked.x, 5);
    expect(captured.camera?.position.y).toBeCloseTo(parked.y, 5);
    expect(captured.camera?.position.z).toBeCloseTo(parked.z, 5);
    controller.dispose();
  });

  it('scales cards and camera together when crossing the 16-card density tier', () => {
    const controller = createApplication3DScene(mount, {
      interactive: true,
      translate: (_id, fallback = '') => fallback,
      onSelect: () => undefined,
    });
    controller.reconcile(makeWallItems(16), { playIntro: false });
    flushFrames();
    const sixteenPose = captured.camera?.position.clone();
    const sixteenScale = wallGroup()?.children[0]?.scale.clone();
    const parked16 = resolveApplication3DWallCamera(16, 320 / 180);
    const parked17 = resolveApplication3DWallCamera(17, 320 / 180);
    expect(sixteenPose?.z).toBeCloseTo(parked16.z, 5);

    controller.reconcile(makeWallItems(17), { playFilter: true });
    expect(captured.camera?.position.z).toBeCloseTo(parked17.z, 5);
    expect(captured.camera?.position.z).toBeCloseTo((sixteenPose?.z ?? 0) / 0.82, 5);
    expect(captured.camera?.position.y).toBeCloseTo(sixteenPose?.y ?? 0, 5);
    for (let step = 0; step < 12; step += 1) flushFrames(20);
    expect(wallGroup()?.children[0]?.scale.x).toBeCloseTo((sixteenScale?.x ?? 0) * 0.82, 5);
    controller.dispose();
  });

  it('keeps 0.82 card size past 24 and snaps the camera farther for the actual wall', () => {
    const aspect = 320 / 180;
    const controller = createApplication3DScene(mount, {
      interactive: true,
      translate: (_id, fallback = '') => fallback,
      onSelect: () => undefined,
    });
    controller.reconcile(makeWallItems(24), { playIntro: false });
    flushFrames();
    const twentyFourScale = wallGroup()?.children[0]?.scale.clone();
    const twentyFourPose = resolveApplication3DWallCamera(24, aspect);
    const fortyEightPose = resolveApplication3DWallCamera(48, aspect);
    expect(fortyEightPose.z).toBeGreaterThan(twentyFourPose.z);

    controller.reconcile(makeWallItems(48), { playFilter: true });
    expect(captured.camera?.position.z).toBeCloseTo(fortyEightPose.z, 5);
    expect(captured.camera?.position.y).toBeCloseTo(fortyEightPose.y, 5);
    for (let step = 0; step < 12; step += 1) flushFrames(20);
    expect(wallGroup()?.children[0]?.scale.x).toBeCloseTo(twentyFourScale?.x ?? 0, 5);
    expect(wallGroup()?.children[0]?.scale.y).toBeCloseTo(twentyFourScale?.y ?? 0, 5);
    controller.dispose();
  });
});

describe('application3D architecture host pick', () => {
  let mount: HTMLDivElement;

  beforeEach(() => {
    captured.scene = null;
    captured.camera = null;
    captured.controls = null;
    captured.raf = [];
    captured.now = 1_000;
    mount = document.createElement('div');
    Object.defineProperty(mount, 'clientWidth', { configurable: true, value: 320 });
    Object.defineProperty(mount, 'clientHeight', { configurable: true, value: 180 });
    document.body.appendChild(mount);
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      captured.raf.push(callback);
      return captured.raf.length;
    });
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      captured.raf.splice(id - 1, 1);
    });
    vi.spyOn(performance, 'now').mockImplementation(() => captured.now);
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      disconnect() {}
    });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function (
      this: HTMLCanvasElement,
    ) {
      const context: Record<string, unknown> = {
        canvas: this,
        fillStyle: '',
        strokeStyle: '',
        font: '',
        filter: '',
        textAlign: 'center',
        textBaseline: 'middle',
        lineWidth: 1,
        lineJoin: 'round',
        lineCap: 'round',
        globalAlpha: 1,
        createLinearGradient: () => ({ addColorStop: () => undefined }),
        createRadialGradient: () => ({ addColorStop: () => undefined }),
        measureText: (text: string) => ({ width: text.length * 8 }),
      };
      return new Proxy(context, {
        get: (target, prop) => {
          if (prop in target) return target[prop as string];
          return () => undefined;
        },
        set: (target, prop, value) => {
          target[prop as string] = value;
          return true;
        },
      }) as unknown as CanvasRenderingContext2D;
    });
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent() { return false; },
      onchange: null,
    }));
  });

  afterEach(() => {
    mount.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const alarmingHealth = {
    ...health,
    state: 'alarming' as const,
    reason: 'active_alarm' as const,
    activeAlarmCount: 3,
    highestSeverity: { id: 'critical' as const, label: '严重', rank: 400 as const, color: 'critical' as const },
  };

  const architectureAlarms: Application3DArchitectureData = {
    systemId: 'sys-1',
    refreshedAt: '2026-09-01T00:00:00Z',
    nodes: [
      { id: 'sys-1', kind: 'system', name: '门户系统', health },
      { id: 'app-1', kind: 'application', name: '门户', health },
      { id: 'host-alarm', kind: 'host', name: 'web-alarm', health: alarmingHealth },
      { id: 'host-quiet', kind: 'host', name: 'web-ok', health },
      { id: 'host-alarm-2', kind: 'host', name: 'web-alarm-2', health: alarmingHealth },
    ],
    edges: [
      { id: 'e1', sourceId: 'sys-1', targetId: 'app-1', relation: 'system_contains_application' },
      { id: 'e2', sourceId: 'app-1', targetId: 'host-alarm', relation: 'application_run_host' },
      { id: 'e3', sourceId: 'app-1', targetId: 'host-quiet', relation: 'application_run_host' },
      { id: 'e4', sourceId: 'app-1', targetId: 'host-alarm-2', relation: 'application_run_host' },
    ],
  };

  const architectureGroup = () => captured.scene?.getObjectByName('application3d-architecture');

  const findRackMesh = (nodeId: string) => {
    let mesh: THREE.Object3D | undefined;
    architectureGroup()?.traverse((child) => {
      if (mesh) return;
      if (
        (child as THREE.Mesh).isMesh
        && child.parent?.userData.archRole === 'rack-root'
        && child.parent.userData.nodeId === nodeId
      ) {
        mesh = child;
      }
    });
    return mesh;
  };

  const mockHit = (object: THREE.Object3D | undefined) => {
    vi.spyOn(THREE.Raycaster.prototype, 'intersectObjects').mockImplementation(() => {
      if (!object) return [];
      return [{
        object,
        distance: 1,
        point: new THREE.Vector3(),
        distanceToRay: 0,
      }] as THREE.Intersection[];
    });
  };

  const point = { clientX: 160, clientY: 90, bubbles: true as const };

  const click = (canvas: Element | null, moveX = 0) => {
    canvas?.dispatchEvent(new PointerEvent('pointerdown', { ...point, button: 0 }));
    if (moveX) {
      canvas?.dispatchEvent(new PointerEvent('pointermove', {
        clientX: point.clientX + moveX,
        clientY: point.clientY,
        bubbles: true,
      }));
    }
    canvas?.dispatchEvent(new PointerEvent('pointerup', {
      ...point,
      clientX: point.clientX + moveX,
      button: 0,
    }));
  };

  const mountArchitecture = (onArchitectureHostSelect = vi.fn(), onSelect = vi.fn()) => {
    const controller = createApplication3DScene(mount, {
      interactive: true,
      translate: (_id, fallback = '') => fallback,
      onSelect,
      onArchitectureHostSelect,
    });
    controller.reconcile([wallItem], { playIntro: false });
    flushFrames();
    controller.showArchitecture(architectureAlarms);
    for (let step = 0; step < 40; step += 1) flushFrames(20);
    return { controller, onArchitectureHostSelect, onSelect, canvas: mount.querySelector('canvas') };
  };

  it('selects an alarming host rack on click and ignores drag and quiet racks', () => {
    const { controller, onArchitectureHostSelect, onSelect, canvas } = mountArchitecture();
    const alarmMesh = findRackMesh('host-alarm');
    const quietMesh = findRackMesh('host-quiet');
    const alarm2Mesh = findRackMesh('host-alarm-2');
    expect(alarmMesh).toBeTruthy();
    expect(quietMesh).toBeTruthy();

    mockHit(alarmMesh);
    click(canvas, 12);
    expect(onArchitectureHostSelect).not.toHaveBeenCalled();
    expect(onSelect).not.toHaveBeenCalled();

    click(canvas);
    expect(onArchitectureHostSelect).toHaveBeenCalledTimes(1);
    expect(onArchitectureHostSelect.mock.calls[0][0]?.node.id).toBe('host-alarm');
    expect(onSelect).not.toHaveBeenCalled();

    mockHit(quietMesh);
    click(canvas);
    expect(onArchitectureHostSelect.mock.calls.at(-1)?.[0]).toBeNull();

    mockHit(alarmMesh);
    click(canvas);
    mockHit(alarm2Mesh);
    click(canvas);
    expect(onArchitectureHostSelect.mock.calls.at(-1)?.[0]?.node.id).toBe('host-alarm-2');

    mockHit(undefined);
    click(canvas);
    expect(onArchitectureHostSelect.mock.calls.at(-1)?.[0]).toBeNull();

    mockHit(alarmMesh);
    click(canvas);
    click(canvas, 10);
    expect(onArchitectureHostSelect.mock.calls.at(-1)?.[0]).toBeNull();

    controller.dispose();
  });

  it('uses a pointer cursor only on alarming hosts in architecture', () => {
    const { controller, canvas } = mountArchitecture();
    mockHit(findRackMesh('host-alarm'));
    canvas?.dispatchEvent(new PointerEvent('pointermove', point));
    expect(canvas).toHaveProperty('style.cursor', 'pointer');

    mockHit(findRackMesh('host-quiet'));
    canvas?.dispatchEvent(new PointerEvent('pointermove', point));
    expect(canvas).toHaveProperty('style.cursor', 'grab');

    mockHit(undefined);
    canvas?.dispatchEvent(new PointerEvent('pointermove', point));
    expect(canvas).toHaveProperty('style.cursor', 'grab');
    controller.dispose();
  });

  it('places the host overlay from the cabinet AABB in widget CSS pixels', () => {
    const { controller, onArchitectureHostSelect, canvas } = mountArchitecture();
    const rackRoot = findRackMesh('host-alarm')?.parent;
    expect(rackRoot).toBeTruthy();
    rackRoot?.scale.setScalar(1);
    rackRoot?.traverse((child) => {
      if (child.userData.archRole !== 'node-label') return;
      const scale = child.userData.labelScale as THREE.Vector3 | undefined;
      if (scale) child.scale.copy(scale);
    });
    canvas!.getBoundingClientRect = () => ({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 160,
      bottom: 90,
      width: 160,
      height: 90,
      toJSON: () => ({}),
    });
    mockHit(findRackMesh('host-alarm'));
    click(canvas);
    const selection = onArchitectureHostSelect.mock.calls.at(-1)?.[0];
    expect(selection).toBeTruthy();
    expect(selection.node.id).toBe('host-alarm');
    expect(captured.camera).toBeTruthy();
    const cssViewport = { width: 320, height: 180 };
    const scaledViewport = { width: 160, height: 90 };
    const cabinetBox = expandArchitectureCabinetWorldBox(rackRoot!);
    const fullBox = new THREE.Box3().setFromObject(rackRoot!);
    const cabinetRect = projectWorldBoxToScreenRect(cabinetBox, captured.camera!, cssViewport);
    const fullRect = projectWorldBoxToScreenRect(fullBox, captured.camera!, cssViewport);
    const scaledRect = projectWorldBoxToScreenRect(cabinetBox, captured.camera!, scaledViewport);
    expect(selection.hostScreenRect.left).toBeCloseTo(cabinetRect.left, 1);
    expect(selection.hostScreenRect.right).toBeCloseTo(cabinetRect.right, 1);
    expect(selection.hostScreenRect.right - selection.hostScreenRect.left).toBeLessThan(
      fullRect.right - fullRect.left,
    );
    expect(Math.abs(selection.hostScreenRect.left - scaledRect.left)).toBeGreaterThan(1);
    expect(
      screenRectsIntersect(overlayScreenRect(selection.overlay), selection.hostScreenRect),
    ).toBe(false);
    controller.dispose();
  });
});

