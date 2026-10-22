// @vitest-environment jsdom

import React from "react";
import "@ant-design/v5-patch-for-react-19";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { IntlProvider } from "react-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ValueConfig } from "@/app/ops-analysis/types/dashBoard";

const testState = vi.hoisted(() => ({
  render: vi.fn(),
  setPixelRatio: vi.fn(),
  setSize: vi.fn(),
  intersectObjects: vi.fn(),
  controlsTarget: null as {
    set: (x: number, y: number, z: number) => unknown;
  } | null,
  emitControlEvent: null as ((type: string) => void) | null,
  controlsUpdateResults: [] as boolean[],
  rendererOptions: null as Record<string, unknown> | null,
  intersectionCallbacks: [] as IntersectionObserverCallback[],
}));

vi.mock("three", async (importOriginal) => {
  const actual = await importOriginal<typeof import("three")>();

  class WebGLRendererMock {
    domElement = document.createElement("canvas");
    shadowMap = { enabled: false, type: actual.BasicShadowMap };
    outputColorSpace = actual.SRGBColorSpace;
    toneMapping = actual.NoToneMapping;
    toneMappingExposure = 1;

    constructor(options: Record<string, unknown>) {
      testState.rendererOptions = options;
      this.domElement.getBoundingClientRect = () => ({
        x: 0,
        y: 0,
        top: 0,
        left: 0,
        right: 100,
        bottom: 100,
        width: 100,
        height: 100,
        toJSON: () => ({}),
      });
    }

    setClearColor() {}
    setPixelRatio = testState.setPixelRatio;
    setSize = testState.setSize;
    render = testState.render;
    dispose() {}
    forceContextLoss() {}
  }

  class RaycasterMock {
    setFromCamera() {}
    intersectObjects(targets: import("three").Object3D[]) {
      return testState.intersectObjects(targets);
    }
  }

  return {
    ...actual,
    Raycaster: RaycasterMock,
    WebGLRenderer: WebGLRendererMock,
  };
});

vi.mock("@/app/ops-analysis/api/room3D", () => ({
  useRoom3DApi: () => ({
    getRooms: vi.fn(),
    getLayout: vi.fn(),
  }),
}));

vi.mock("next/navigation", () => ({ useParams: () => ({}) }));

vi.mock("three/examples/jsm/controls/OrbitControls.js", () => {
  class ControlsTargetMock {
    x = 0;
    y = 0;
    z = 0;

    set(x: number, y: number, z: number) {
      this.x = x;
      this.y = y;
      this.z = z;
      return this;
    }

    copy(target: ControlsTargetMock) {
      return this.set(target.x, target.y, target.z);
    }

    lerp(target: ControlsTargetMock, alpha: number) {
      this.x += (target.x - this.x) * alpha;
      this.y += (target.y - this.y) * alpha;
      this.z += (target.z - this.z) * alpha;
      return this;
    }

    distanceTo(target: ControlsTargetMock) {
      return Math.hypot(
        this.x - target.x,
        this.y - target.y,
        this.z - target.z,
      );
    }
  }

  class OrbitControlsMock {
    enableDamping = false;
    dampingFactor = 0;
    minDistance = 0;
    maxDistance = Infinity;
    target = new ControlsTargetMock();
    private listeners = new Map<string, Set<() => void>>();

    constructor() {
      testState.controlsTarget = this.target;
      testState.emitControlEvent = (type) => this.dispatchEvent(type);
    }

    addEventListener(type: string, listener: () => void) {
      const listeners = this.listeners.get(type) || new Set<() => void>();
      listeners.add(listener);
      this.listeners.set(type, listeners);
    }
    removeEventListener(type: string, listener: () => void) {
      this.listeners.get(type)?.delete(listener);
    }
    private dispatchEvent(type: string) {
      this.listeners.get(type)?.forEach((listener) => listener());
    }
    update() {
      const changed = testState.controlsUpdateResults.shift() ?? false;
      if (changed) {
        this.dispatchEvent("change");
      }
      return changed;
    }
    dispose() {}
  }

  return { OrbitControls: OrbitControlsMock };
});

import { createRoom3DScene } from "../room3DScene";
import Room3D from "../index";

const roomData = {
  room: { id: "room-1", name: "Room 1" },
  racks: [{ rack_id: "rack-1", rack_name: "Rack 1", row: 1, col: 1 }],
};

describe("room3D scene rendering", () => {
  let nextFrameId: number;
  let queuedFrames: Map<number, FrameRequestCallback>;

  beforeEach(() => {
    nextFrameId = 1;
    queuedFrames = new Map();
    testState.render.mockClear();
    testState.setPixelRatio.mockClear();
    testState.setSize.mockClear();
    testState.intersectObjects.mockReset();
    testState.intersectObjects.mockImplementation(
      (targets: import("three").Object3D[]) =>
        targets.length ? [{ object: targets[0] }] : [],
    );
    testState.controlsTarget = null;
    testState.emitControlEvent = null;
    testState.controlsUpdateResults.length = 0;
    testState.rendererOptions = null;
    testState.intersectionCallbacks.length = 0;
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });

    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(callback: IntersectionObserverCallback) {
          testState.intersectionCallbacks.push(callback);
        }
        observe() {}
        disconnect() {}
      },
    );
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      const frameId = nextFrameId;
      nextFrameId += 1;
      queuedFrames.set(frameId, callback);
      return frameId;
    });
    vi.stubGlobal("cancelAnimationFrame", (frameId: number) => {
      queuedFrames.delete(frameId);
    });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  const createMountNode = (visualWidth = 1920, visualHeight = 1080) => {
    const mountNode = document.createElement("div");
    Object.defineProperties(mountNode, {
      clientWidth: { configurable: true, value: 1920 },
      clientHeight: { configurable: true, value: 1080 },
    });
    mountNode.getBoundingClientRect = () => ({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: visualWidth,
      bottom: visualHeight,
      width: visualWidth,
      height: visualHeight,
      toJSON: () => ({}),
    });
    return mountNode;
  };

  const runNextFrame = (time: number) => {
    const nextFrame = queuedFrames.entries().next().value as
      | [number, FrameRequestCallback]
      | undefined;
    if (!nextFrame) {
      return false;
    }
    const [frameId, callback] = nextFrame;
    queuedFrames.delete(frameId);
    callback(time);
    return true;
  };

  const createController = (
    mountNode = createMountNode(),
    callbacks: {
      onFirstRender?: () => void;
      onHover?: (state: unknown) => void;
    } = {},
  ) =>
    createRoom3DScene(mountNode, roomData, {
      onHover: callbacks.onHover || vi.fn(),
      onSelect: vi.fn(),
      onFirstRender: callbacks.onFirstRender,
    });

  it("stops requesting frames once the scene is idle", () => {
    const controller = createController();

    for (let frame = 0; frame < 120; frame += 1) {
      if (!runNextFrame(frame * (1000 / 60))) {
        break;
      }
    }

    const renderCountWhileIdle = testState.render.mock.calls.length;
    const pendingFrameCount = queuedFrames.size;
    controller.dispose();

    expect(renderCountWhileIdle).toBe(1);
    expect(pendingFrameCount).toBe(0);
  });

  it("reports the first render exactly once after drawing the frame", () => {
    const onFirstRender = vi.fn();
    const controller = createController(createMountNode(), { onFirstRender });

    expect(onFirstRender).not.toHaveBeenCalled();
    runNextFrame(0);
    expect(onFirstRender).toHaveBeenCalledTimes(1);

    controller.resize();
    runNextFrame(16);
    expect(onFirstRender).toHaveBeenCalledTimes(1);
    controller.dispose();
  });

  it("sizes the canvas against its visual viewport", () => {
    const controller = createController(createMountNode(960, 540));

    expect(testState.setSize).toHaveBeenCalledWith(960, 540, false);
    controller.dispose();
  });

  it("resynchronizes the canvas after the screen fit scale changes", () => {
    const mountNode = createMountNode(1920, 1080);
    let visualWidth = 1920;
    let visualHeight = 1080;
    mountNode.getBoundingClientRect = () => ({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: visualWidth,
      bottom: visualHeight,
      width: visualWidth,
      height: visualHeight,
      toJSON: () => ({}),
    });
    const controller = createController(mountNode);

    visualWidth = 960;
    visualHeight = 540;
    controller.resize();

    expect(testState.setSize).toHaveBeenLastCalledWith(960, 540, false);
    controller.dispose();
  });

  it("synchronizes DPR changes without reallocating an unchanged viewport", () => {
    let devicePixelRatio = 2;
    let pixelRatioChangeListener: (() => void) | null = null;
    const removePixelRatioListener = vi.fn();
    vi.stubGlobal(
      "matchMedia",
      vi.fn(
        () =>
          ({
            addEventListener: (
              _type: string,
              listener: EventListenerOrEventListenerObject,
            ) => {
              pixelRatioChangeListener = () => {
                if (typeof listener === "function") {
                  listener(new Event("change"));
                  return;
                }
                listener.handleEvent(new Event("change"));
              };
            },
            removeEventListener: removePixelRatioListener,
          }) as unknown as MediaQueryList,
      ),
    );
    Object.defineProperty(window, "devicePixelRatio", {
      configurable: true,
      get: () => devicePixelRatio,
    });
    const controller = createController(createMountNode(960, 540));

    expect(testState.setPixelRatio).toHaveBeenCalledTimes(1);
    expect(testState.setPixelRatio).toHaveBeenLastCalledWith(2);
    expect(testState.setSize).toHaveBeenCalledTimes(1);

    controller.resize();
    expect(testState.setPixelRatio).toHaveBeenCalledTimes(1);
    expect(testState.setSize).toHaveBeenCalledTimes(1);

    devicePixelRatio = 1;
    pixelRatioChangeListener?.();
    expect(testState.setPixelRatio).toHaveBeenCalledTimes(2);
    expect(testState.setPixelRatio).toHaveBeenLastCalledWith(1);
    expect(testState.setSize).toHaveBeenCalledTimes(1);
    expect(removePixelRatioListener).toHaveBeenCalledTimes(1);

    controller.resize();
    expect(testState.setPixelRatio).toHaveBeenCalledTimes(2);
    expect(testState.setSize).toHaveBeenCalledTimes(1);
    controller.dispose();
    expect(removePixelRatioListener).toHaveBeenCalledTimes(2);
  });

  it("keeps rendering a camera transition until it settles", () => {
    const controller = createController();
    runNextFrame(0);
    testState.render.mockClear();

    testState.controlsTarget?.set(5, 0, 0);
    controller.resetView();
    for (let frame = 0; frame < 240; frame += 1) {
      if (!runNextFrame(frame * (1000 / 60))) {
        break;
      }
    }

    const transitionRenderCount = testState.render.mock.calls.length;
    const pendingFrameCount = queuedFrames.size;
    controller.dispose();

    expect(transitionRenderCount).toBeGreaterThan(1);
    expect(pendingFrameCount).toBe(0);
  });

  it("renders OrbitControls damping frames and returns to idle", () => {
    const controller = createController();
    runNextFrame(0);
    testState.render.mockClear();
    testState.controlsUpdateResults.push(true, true, false);

    testState.emitControlEvent?.("change");
    for (let frame = 0; frame < 10; frame += 1) {
      if (!runNextFrame(frame * (1000 / 60))) {
        break;
      }
    }

    expect(testState.render).toHaveBeenCalledTimes(3);
    expect(queuedFrames.size).toBe(0);

    controller.dispose();
    testState.emitControlEvent?.("change");
    expect(queuedFrames.size).toBe(0);
  });

  it("does not force the browser to select the high-performance GPU", () => {
    const controller = createController();

    expect(testState.rendererOptions).not.toHaveProperty(
      "powerPreference",
      "high-performance",
    );
    expect(testState.rendererOptions).toMatchObject({
      preserveDrawingBuffer: true,
    });
    controller.dispose();
  });

  it("redraws the preserved buffer when print preparation starts", () => {
    const controller = createController();
    for (let frame = 0; frame < 120; frame += 1) {
      if (!runNextFrame(frame * (1000 / 60))) {
        break;
      }
    }
    const idleRenders = testState.render.mock.calls.length;

    window.dispatchEvent(
      new CustomEvent("bk-dashboard-prepare-print", {
        detail: { phase: "prepare-print" },
      }),
    );

    expect(testState.render.mock.calls.length).toBe(idleRenders + 1);
    controller.dispose();
  });

  it("pauses queued work while the browser tab is hidden and resumes on return", () => {
    let visibilityState: DocumentVisibilityState = "visible";
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => visibilityState,
    });
    const controller = createController();
    expect(queuedFrames.size).toBe(1);

    visibilityState = "hidden";
    document.dispatchEvent(new Event("visibilitychange"));
    expect(queuedFrames.size).toBe(0);

    visibilityState = "visible";
    document.dispatchEvent(new Event("visibilitychange"));
    expect(queuedFrames.size).toBe(1);
    controller.dispose();
  });

  it("draws one readiness frame offscreen, then pauses until return", () => {
    const mountNode = createMountNode();
    const controller = createController(mountNode);
    expect(queuedFrames.size).toBe(1);

    const notifyIntersection = (isIntersecting: boolean) => {
      testState.intersectionCallbacks[0](
        [
          { isIntersecting, target: mountNode } as unknown as IntersectionObserverEntry,
        ],
        {} as IntersectionObserver,
      );
    };
    notifyIntersection(false);
    expect(queuedFrames.size).toBe(1);
    runNextFrame(0);
    expect(queuedFrames.size).toBe(0);

    notifyIntersection(true);
    expect(queuedFrames.size).toBe(1);
    controller.dispose();
  });

  it("restores a deferred first frame while the canvas remains offscreen", () => {
    let visibilityState: DocumentVisibilityState = "hidden";
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => visibilityState,
    });
    const mountNode = createMountNode();
    const onFirstRender = vi.fn();
    const controller = createController(mountNode, { onFirstRender });
    expect(queuedFrames.size).toBe(0);

    testState.intersectionCallbacks[0](
      [
        {
          isIntersecting: false,
          target: mountNode,
        } as unknown as IntersectionObserverEntry,
      ],
      {} as IntersectionObserver,
    );
    visibilityState = "visible";
    document.dispatchEvent(new Event("visibilitychange"));
    expect(queuedFrames.size).toBe(1);

    runNextFrame(0);
    expect(onFirstRender).toHaveBeenCalledTimes(1);
    expect(queuedFrames.size).toBe(0);
    controller.dispose();
  });

  it("coalesces pointer movement and skips duplicate hover notifications", () => {
    const mountNode = createMountNode();
    const onHover = vi.fn();
    const controller = createController(mountNode, { onHover });
    runNextFrame(0);
    testState.render.mockClear();
    testState.intersectObjects.mockClear();
    const canvas = mountNode.querySelector("canvas");

    for (let index = 0; index < 20; index += 1) {
      canvas?.dispatchEvent(
        new PointerEvent("pointermove", {
          clientX: 50 + index,
          clientY: 50 + index,
        }),
      );
    }
    expect(testState.intersectObjects).not.toHaveBeenCalled();
    expect(onHover).not.toHaveBeenCalled();

    runNextFrame(16);
    expect(testState.intersectObjects).toHaveBeenCalledTimes(1);
    expect(onHover).toHaveBeenCalledTimes(1);

    runNextFrame(24);
    canvas?.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 55, clientY: 55 }),
    );
    runNextFrame(32);

    expect(testState.intersectObjects).toHaveBeenCalledTimes(2);
    expect(onHover).toHaveBeenCalledTimes(1);
    expect(testState.render).toHaveBeenCalledTimes(1);
    controller.dispose();
  });

  it("reports a device hover after the rack opens and skips conflict placeholders", () => {
    const mountNode = createMountNode();
    const onHover = vi.fn();
    const onDeviceSelect = vi.fn();
    const device = {
      device_id: "dev-1",
      device_name: "srv-1",
      rack_u_start: 1,
      u_size: 1,
    };
    const data = {
      room: { id: "room-1", name: "Room 1" },
      racks: [
        {
          rack_id: "rack-1",
          rack_name: "Rack 1",
          row: 1,
          col: 1,
          devices: [device],
        },
      ],
    };
    testState.intersectObjects.mockImplementation(
      (targets: import("three").Object3D[]) => {
        const deviceTarget = targets.find((item) => item.userData?.device);
        const target = deviceTarget || targets[0];
        return target ? [{ object: target }] : [];
      },
    );
    const controller = createRoom3DScene(mountNode, data, {
      onHover,
      onSelect: vi.fn(),
      onDeviceSelect,
    });
    runNextFrame(0);
    const canvas = mountNode.querySelector("canvas");
    canvas?.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 40, clientY: 40 }),
    );
    runNextFrame(16);
    const closedHover = onHover.mock.calls.at(-1)?.[0] as {
      device?: unknown;
      x: number;
      y: number;
    };
    expect(closedHover.device).toBeUndefined();
    expect(closedHover.x).not.toBe(40);
    expect(closedHover.y).not.toBe(40);

    canvas?.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 80, clientY: 24, buttons: 1 }),
    );
    runNextFrame(24);
    expect(onHover.mock.calls.at(-1)?.[0]).toMatchObject({
      x: closedHover.x,
      y: closedHover.y,
    });
    expect(onHover).not.toHaveBeenCalledWith(null);

    canvas?.dispatchEvent(
      new PointerEvent("click", { clientX: 40, clientY: 40 }),
    );
    expect(onDeviceSelect).toHaveBeenCalledWith(
      expect.objectContaining({
        device: expect.objectContaining({ device_id: "dev-1" }),
      }),
    );

    onHover.mockClear();
    canvas?.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 48, clientY: 52 }),
    );
    runNextFrame(32);
    runNextFrame(33);
    expect(onHover).not.toHaveBeenCalled();
    controller.dispose();

    const conflictHover = vi.fn();
    const conflictMount = createMountNode();
    const conflict = createRoom3DScene(
      conflictMount,
      {
        room: { id: "room-1", name: "Room 1" },
        racks: [
          {
            rack_id: "rack-2",
            rack_name: "Conflict",
            row: 1,
            col: 1,
            is_conflict: true,
            devices: [device],
          },
        ],
      },
      { onHover: conflictHover, onSelect: vi.fn() },
    );
    runNextFrame(48);
    conflictMount.querySelector("canvas")?.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 30, clientY: 30 }),
    );
    runNextFrame(56);
    runNextFrame(57);
    const conflictState = conflictHover.mock.calls.at(-1)?.[0];
    expect(conflictState?.device).toBeUndefined();
    expect(conflictState?.rack?.is_conflict).toBe(true);
    conflict.dispose();
  });

  it("anchors the closed-rack hover card and hides it while the rack is open", async () => {
    const device = {
      device_id: "dev-1",
      device_name: "srv-1",
      rack_u_start: 1,
      u_size: 1,
    };
    const data = {
      room: { id: "room-1", name: "Room 1" },
      racks: [
        {
          rack_id: "rack-1",
          rack_name: "Rack 1",
          row: 1,
          col: 1,
          u_count: 42,
          devices: [device],
        },
      ],
    };
    const linkConfig: ValueConfig = {
      chartType: "room3D",
      sceneWidgetType: "room3D",
      interaction: {
        kind: "data",
        name: "查看 CMDB 详情",
        url: "/cmdb/detail",
        openMode: "newTab",
      },
    };
    let hit: "device" | "shell" = "device";
    testState.intersectObjects.mockImplementation(
      (targets: import("three").Object3D[]) => {
        const deviceTarget = targets.find((item) => item.userData?.device);
        const shellTarget = targets.find(
          (item) => item.userData?.rack && !item.userData?.device,
        );
        const target = hit === "device" ? deviceTarget : shellTarget;
        return target ? [{ object: target }] : [];
      },
    );

    render(
      <IntlProvider locale="zh" messages={{}}>
        <Room3D rawData={data} config={linkConfig} />
      </IntlProvider>,
    );
    const canvas = await waitFor(() => {
      const node = document.querySelector("canvas");
      expect(node).toBeTruthy();
      return node as HTMLCanvasElement;
    });

    const flushFrames = () => {
      act(() => {
        for (let guard = 0; guard < 6 && queuedFrames.size > 0; guard += 1) {
          runNextFrame(16 + guard);
        }
      });
    };
    const move = (x: number, y: number, buttons = 0) => {
      act(() => {
        canvas.dispatchEvent(
          new PointerEvent("pointermove", {
            clientX: x,
            clientY: y,
            buttons,
            bubbles: true,
          }),
        );
      });
      flushFrames();
    };
    const card = () =>
      screen.queryByText("Rack 1")?.parentElement as HTMLElement | undefined;

    move(40, 40);
    await waitFor(() => expect(card()).toBeTruthy());
    const anchorLeft = card()?.style.left;
    const anchorTop = card()?.style.top;
    expect(anchorLeft).not.toBe("");
    expect(screen.queryByText("srv-1")).toBeNull();
    expect(document.body.textContent).not.toContain("右键打开链接");

    move(88, 22);
    expect(card()?.style.left).toBe(anchorLeft);
    expect(card()?.style.top).toBe(anchorTop);

    hit = "shell";
    move(12, 70);
    expect(card()?.style.left).toBe(anchorLeft);
    expect(card()?.style.top).toBe(anchorTop);

    hit = "device";
    move(61, 33, 1);
    expect(card()?.style.left).toBe(anchorLeft);
    expect(card()?.style.top).toBe(anchorTop);

    act(() => {
      canvas.dispatchEvent(
        new PointerEvent("pointerdown", {
          button: 2,
          clientX: 40,
          clientY: 40,
          bubbles: true,
        }),
      );
      canvas.dispatchEvent(
        new MouseEvent("contextmenu", {
          button: 2,
          clientX: 41,
          clientY: 41,
          bubbles: true,
          cancelable: true,
        }),
      );
    });
    expect(screen.getByRole("menuitem", { name: "查看 CMDB 详情" })).toBeTruthy();

    hit = "shell";
    act(() => {
      canvas.dispatchEvent(
        new PointerEvent("click", { clientX: 12, clientY: 70, bubbles: true }),
      );
    });
    expect(screen.queryByText("Rack 1")).toBeNull();

    hit = "device";
    move(40, 40);
    move(90, 18, 1);
    expect(screen.queryByText("Rack 1")).toBeNull();
  });
});
