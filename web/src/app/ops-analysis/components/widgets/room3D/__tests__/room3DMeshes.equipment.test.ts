// @vitest-environment jsdom

import * as THREE from "three";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createRackVisual,
  disposeObject3D,
  ROOM3D_RACK_HEIGHT,
  ROOM3D_RACK_WIDTH,
  setRackVisualState,
} from "../room3DMeshes";
import type { Room3DRack } from "../room3DData";

interface RecordedFill {
  style: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

interface CanvasWithFills extends HTMLCanvasElement {
  __fills?: RecordedFill[];
}

const createRecordingContext = (canvas: CanvasWithFills) => {
  const fills: RecordedFill[] = [];
  canvas.__fills = fills;
  const context: Record<string, unknown> = {
    canvas,
    fillStyle: "",
    strokeStyle: "",
    font: "",
    textAlign: "left",
    textBaseline: "alphabetic",
    lineWidth: 1,
    fillRect: (x: number, y: number, w: number, h: number) => {
      fills.push({
        style: String(context.fillStyle),
        x,
        y,
        w,
        h,
      });
    },
    fill: () => {
      fills.push({
        style: String(context.fillStyle),
        x: 0,
        y: 0,
        w: 0,
        h: 0,
      });
    },
    createLinearGradient: () => ({ addColorStop: () => undefined }),
    createRadialGradient: () => ({ addColorStop: () => undefined }),
  };
  return new Proxy(context, {
    get: (target, prop) => {
      if (prop in target) {
        return target[prop as string];
      }
      return () => undefined;
    },
    set: (target, prop, value) => {
      target[prop as string] = value;
      return true;
    },
  }) as unknown as CanvasRenderingContext2D;
};

const buildRack = (): Room3DRack => ({
  rack_id: "rack-led-1",
  rack_name: "RACK-B",
  row: 1,
  col: 1,
  u_count: 42,
  devices: [
    {
      device_id: "d-1u",
      device_name: "1U switch",
      rack_u_start: 10,
      u_size: 1,
    },
    {
      device_id: "d-4u",
      device_name: "4U server",
      rack_u_start: 20,
      u_size: 4,
    },
  ],
});

const getFrontMaterial = (mesh: THREE.Mesh) => {
  const materials = mesh.material as THREE.MeshStandardMaterial[];
  return materials[4];
};

const getSideMaterial = (mesh: THREE.Mesh) => {
  const materials = mesh.material as THREE.MeshStandardMaterial[];
  return materials[0];
};

const RACK_USABLE_HEIGHT = ROOM3D_RACK_HEIGHT - 0.12 - 0.1;

const expectedDeviceHeight = (uSize: number, uCount = 42) =>
  Math.min(
    RACK_USABLE_HEIGHT * 0.36,
    Math.max(
      0.075,
      RACK_USABLE_HEIGHT * (Math.max(uSize, 1) / Math.max(uCount, 1)),
    ),
  );

describe("room3D equipment front-panel port LEDs", () => {
  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
      function (this: HTMLCanvasElement, type?: string) {
        if (type && type !== "2d") {
          return null;
        }
        return createRecordingContext(this);
      },
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("paints port LEDs onto the shared 320x96 face map and a black emissiveMap", () => {
    const visual = createRackVisual(buildRack(), 0, 0);
    const device = visual.deviceMeshes[0];
    const front = getFrontMaterial(device);
    const side = getSideMaterial(device);
    const mapCanvas = front.map?.image as CanvasWithFills;
    const emissiveCanvas = front.emissiveMap?.image as CanvasWithFills;
    const mapFills = mapCanvas.__fills ?? [];
    const emissiveFills = emissiveCanvas.__fills ?? [];

    expect(mapCanvas.width).toBe(320);
    expect(mapCanvas.height).toBe(96);
    expect(emissiveCanvas.width).toBe(320);
    expect(emissiveCanvas.height).toBe(96);

    expect(mapFills.some((fill) => fill.style === "#829db2")).toBe(true);
    expect(mapFills.some((fill) => fill.style === "#3dff68" && fill.w === 3 && fill.h === 2)).toBe(
      true,
    );
    expect(mapFills.some((fill) => fill.style === "#ff9c1c" && fill.w === 3 && fill.h === 2)).toBe(
      true,
    );
    expect(
      mapFills.some(
        (fill) =>
          fill.style === "rgba(61, 255, 104, 0.24)" && fill.w === 7 && fill.h === 6,
      ),
    ).toBe(true);
    expect(mapFills.some((fill) => fill.style === "#47e8ff")).toBe(false);
    expect(mapFills.some((fill) => fill.style === "rgba(91, 234, 255, 0.42)")).toBe(
      false,
    );
    expect(
      mapFills.some(
        (fill) => fill.style === "#3dff68" && fill.w === 3 && fill.h === 34,
      ),
    ).toBe(true);
    expect(
      mapFills.some(
        (fill) =>
          fill.style === "rgba(61, 255, 104, 0.24)" && fill.w === 7 && fill.h === 38,
      ),
    ).toBe(true);
    expect(mapFills.some((fill) => fill.style === "#3dff68" && fill.w === 0)).toBe(
      true,
    );
    expect(mapFills.some((fill) => fill.style === "#ff9c1c" && fill.w === 0)).toBe(
      true,
    );

    const greenCores = mapFills.filter(
      (fill) => fill.style === "#3dff68" && fill.w === 3 && fill.h === 2,
    );
    const amberCores = mapFills.filter(
      (fill) => fill.style === "#ff9c1c" && fill.w === 3 && fill.h === 2,
    );
    const offCores = mapFills.filter(
      (fill) => fill.style === "rgba(6, 12, 18, 0.92)" && fill.w === 3 && fill.h === 2,
    );
    expect(greenCores.length + amberCores.length + offCores.length).toBe(112);
    expect(greenCores.length).toBeGreaterThan(amberCores.length);
    expect(greenCores.length).toBeGreaterThan(offCores.length);

    expect(emissiveFills[0]).toMatchObject({
      style: "#000000",
      x: 0,
      y: 0,
      w: 320,
      h: 96,
    });
    expect(
      emissiveFills.some((fill) => fill.style === "#f3fff5" && fill.w === 3 && fill.h === 2),
    ).toBe(true);
    expect(
      emissiveFills.some((fill) => fill.style === "#fff3e2" && fill.w === 3 && fill.h === 2),
    ).toBe(true);
    expect(emissiveFills.some((fill) => fill.style === "#829db2")).toBe(false);
    expect(emissiveFills.some((fill) => fill.style === "#47e8ff")).toBe(false);
    expect(emissiveFills.some((fill) => fill.style === "#1b536c")).toBe(false);
    expect(
      emissiveFills.some(
        (fill) => fill.style === "#f3fff5" && fill.w === 3 && fill.h === 34,
      ),
    ).toBe(true);
    expect(emissiveFills.some((fill) => fill.style === "#f3fff5" && fill.w === 0)).toBe(
      true,
    );
    expect(emissiveFills.some((fill) => fill.style === "#fff3e2" && fill.w === 0)).toBe(
      true,
    );

    expect(front.emissive.getHexString()).toBe("ffffff");
    expect(front.emissiveIntensity).toBeGreaterThanOrEqual(1);
    expect(front.emissiveIntensity).toBeLessThanOrEqual(1.3);
    expect(front.emissiveIntensity).toBe(front.userData.baseEmissiveIntensity);
    expect(side.emissive.getHexString()).toBe("182838");
    expect(side.emissiveIntensity).toBe(0.1);

    disposeObject3D(visual.root);
  });

  it("keeps cabinet and device BoxGeometry on the current U-scale", () => {
    const visual = createRackVisual(buildRack(), 0, 0);
    const oneU = visual.deviceMeshes[0];
    const fourU = visual.deviceMeshes[1];
    const oneUGeometry = oneU.geometry as THREE.BoxGeometry;
    const fourUGeometry = fourU.geometry as THREE.BoxGeometry;
    const rackBody = visual.root.getObjectByName("rack-back") as THREE.Mesh;
    const rackBodyGeometry = rackBody.geometry as THREE.BoxGeometry;

    expect(oneUGeometry.parameters.width).toBeCloseTo(ROOM3D_RACK_WIDTH - 0.08);
    expect(oneUGeometry.parameters.depth).toBeCloseTo(0.34);
    expect(oneUGeometry.parameters.height).toBeCloseTo(expectedDeviceHeight(1));
    expect(fourUGeometry.parameters.height).toBeCloseTo(expectedDeviceHeight(4));
    expect(fourUGeometry.parameters.height).toBeGreaterThan(
      oneUGeometry.parameters.height,
    );
    expect(rackBodyGeometry.parameters.width).toBeCloseTo(ROOM3D_RACK_WIDTH);
    expect(rackBodyGeometry.parameters.height).toBeCloseTo(ROOM3D_RACK_HEIGHT);
    expect(visual.root.getObjectByName("rack-u-scale")).toBeTruthy();
    expect(visual.root.getObjectByName("rack-door")).toBeUndefined();

    setRackVisualState(visual, {
      hovered: false,
      selected: true,
      selectedDeviceId: "d-1u",
    });
    expect(getFrontMaterial(oneU).emissiveIntensity).toBeGreaterThanOrEqual(1);
    expect(getFrontMaterial(oneU).emissive.getHexString()).toBe("ffffff");
    expect(getSideMaterial(oneU).emissiveIntensity).toBe(0.72);

    disposeObject3D(visual.root);
  });

  it("adds a unified interior red alarm glow when active_alarm_count > 0", () => {
    const visual = createRackVisual(
      {
        rack_id: "rack-alarm",
        rack_name: "RACK-A",
        row: 1,
        col: 1,
        u_count: 42,
        devices: [
          {
            device_id: "alarming",
            device_name: "alarming server",
            rack_u_start: 5,
            u_size: 2,
            monitor_bound: true,
            alarm_unavailable: false,
            active_alarm_count: 3,
            highest_severity: "critical",
          },
          {
            device_id: "quiet",
            device_name: "quiet server",
            rack_u_start: 12,
            u_size: 1,
            monitor_bound: true,
            alarm_unavailable: false,
            active_alarm_count: 0,
            highest_severity: null,
          },
        ],
      },
      0,
      0,
    );

    const alarming = visual.deviceMeshes[0];
    const quiet = visual.deviceMeshes[1];
    const glow = alarming.getObjectByName("rack-device-alarm-glow");
    const core = alarming.getObjectByName("rack-device-alarm-core");
    const halo = alarming.getObjectByName("rack-device-alarm-halo");
    const frontSpill = alarming.getObjectByName("rack-device-alarm-front-spill");

    expect(glow).toBeInstanceOf(THREE.PointLight);
    expect((glow as THREE.PointLight).color.getHexString()).toBe("ff2a2a");
    expect((glow as THREE.PointLight).position.z).toBeGreaterThan(0);
    expect(core).toBeInstanceOf(THREE.Mesh);
    expect(halo).toBeInstanceOf(THREE.Mesh);
    expect(frontSpill).toBeInstanceOf(THREE.Mesh);
    const deviceWidth = ROOM3D_RACK_WIDTH - 0.08;
    const deviceHeight = alarming.userData.height as number;
    const haloSize = new THREE.Vector3();
    ((halo as THREE.Mesh).geometry as THREE.BoxGeometry).computeBoundingBox();
    (halo as THREE.Mesh).geometry.boundingBox?.getSize(haloSize);
    // Wrap may grow in Y/Z for envelope feel, but width must stay ≤ device.
    expect(haloSize.x).toBeLessThanOrEqual(deviceWidth + 1e-6);
    expect(haloSize.y).toBeGreaterThan(deviceHeight);
    const haloMaterial = (halo as THREE.Mesh).material as THREE.MeshBasicMaterial;
    expect(haloMaterial.blending).toBe(THREE.AdditiveBlending);
    expect(haloMaterial.map).toBeTruthy();
    expect(getSideMaterial(alarming).emissive.getHexString()).toBe("5a1a1a");
    expect(getFrontMaterial(alarming).emissive.getHexString()).toBe("ffffff");
    expect(quiet.getObjectByName("rack-device-alarm-glow")).toBeUndefined();
    expect(quiet.getObjectByName("rack-device-alarm-core")).toBeUndefined();
    expect(quiet.getObjectByName("rack-device-alarm-halo")).toBeUndefined();
    expect(quiet.getObjectByName("rack-device-alarm-front-spill")).toBeUndefined();
    // Front-panel LED maps remain attached; alarm mode paints every lamp red.
    expect(getFrontMaterial(alarming).emissiveMap).toBeTruthy();
    const alarmMapFills =
      (getFrontMaterial(alarming).map?.image as CanvasWithFills).__fills ?? [];
    expect(
      alarmMapFills.some((fill) => fill.style === "#ff2a2a" && fill.w === 3 && fill.h === 2),
    ).toBe(true);
    expect(
      alarmMapFills.some((fill) => fill.style === "#3dff68" && fill.w === 3 && fill.h === 2),
    ).toBe(false);
    expect(
      alarmMapFills.some((fill) => fill.style === "#ff9c1c" && fill.w === 3 && fill.h === 2),
    ).toBe(false);

    disposeObject3D(visual.root);
  });
});
