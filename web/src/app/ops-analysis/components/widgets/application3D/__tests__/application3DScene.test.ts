// @vitest-environment jsdom

import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Application3DArchitectureData, Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';
import {
  ARCH_CAMERA_PHI,
  ARCH_PLANE_Y,
  ARCH_PREVIOUS_CAMERA_PHI,
  describeWallCameraSpherical,
  layoutApplication3DArchitecture,
  resolveArchitectureCameraPose,
} from '../application3DArchitecture';
import { APPLICATION3D_WALL_GROUP_NAME, createApplication3DScene } from '../application3DScene';

const captured = vi.hoisted(() => ({
  scene: null as THREE.Scene | null,
  camera: null as THREE.PerspectiveCamera | null,
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
      { position: { x: 0, y: wallY, z: 20 }, target: { x: 0, y: 0, z: 0 } },
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
});
