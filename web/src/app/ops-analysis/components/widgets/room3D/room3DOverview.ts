import { deviceHasAlarmGlow, type Room3DDevice, type Room3DRack } from "./room3DData";

export const ROOM3D_OVERVIEW_MOTION_MS = 300;

export const ROOM3D_OVERVIEW_EMPTY = "\u2014";

/**
 * Widget box where the scale-1 overview (240px wide) still fits: the width holds the
 * panel, and the height holds the stack under the room selector.
 * Smaller widgets scale the panel down by the tighter axis. Larger widgets
 * stay at 1.
 */
export const ROOM3D_OVERVIEW_REF_WIDTH = 1100;

export const ROOM3D_OVERVIEW_REF_HEIGHT = 420;

export const resolveRoom3DOverviewScale = (width: number, height: number) => {
  if (
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  ) {
    return 1;
  }
  const scale = Math.min(
    1,
    width / ROOM3D_OVERVIEW_REF_WIDTH,
    height / ROOM3D_OVERVIEW_REF_HEIGHT,
  );
  return Math.round(scale * 10000) / 10000;
};

export const easeRoom3DOverview = (progress: number) => {
  const clamped = Math.min(1, Math.max(0, progress));
  return 1 - (1 - clamped) ** 3;
};

export interface Room3DOverviewStats {
  rackCount: number;
  deviceCount: number | null;
  usedU: number | null;
  totalU: number | null;
  freeU: number | null;
  /** Null when total U is missing or 0. May exceed 1 when used U exceeds total U. */
  usageRatio: number | null;
  monitoredCount: number | null;
  alarmDeviceCount: number | null;
}

type CapacityField = "u_count" | "used_u" | "free_u";

interface CapacitySum {
  complete: boolean;
  value: number;
}

const finiteNonNegative = (value: unknown): number | null => {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return null;
  }
  return value;
};

const sumCapacity = (
  racks: readonly Pick<Room3DRack, CapacityField>[],
  field: CapacityField,
): CapacitySum => {
  let value = 0;
  for (const rack of racks) {
    const next = finiteNonNegative(rack[field]);
    if (next === null) {
      return { complete: false, value: 0 };
    }
    value += next;
  }
  return { complete: true, value };
};

const rackDeviceTotal = (
  rack: Pick<Room3DRack, "device_count" | "devices">,
): number | null => {
  const explicit = finiteNonNegative(rack.device_count);
  if (explicit !== null) {
    return explicit;
  }
  if (Array.isArray(rack.devices)) {
    return rack.devices.length;
  }
  return null;
};

/**
 * Room-level figures derived from the layout already on screen.
 * Unlisted devices (device_count larger than devices) have no monitor_bound
 * or active_alarm_count, so those two totals stay unknown.
 * A listed device with alarm_unavailable also makes the alarm total unknown.
 */
export const summarizeRoom3DOverview = (
  racks: readonly Pick<
    Room3DRack,
    "device_count" | "devices" | "u_count" | "used_u" | "free_u"
  >[],
): Room3DOverviewStats => {
  const total = sumCapacity(racks, "u_count");
  const used = sumCapacity(racks, "used_u");
  const free = sumCapacity(racks, "free_u");

  let deviceCount = 0;
  let deviceCountKnown = true;
  let monitoredCount = 0;
  let monitoredKnown = true;
  let alarmDeviceCount = 0;
  let alarmKnown = true;

  racks.forEach((rack) => {
    const totalDevices = rackDeviceTotal(rack);
    if (totalDevices === null) {
      deviceCountKnown = false;
      monitoredKnown = false;
      alarmKnown = false;
      return;
    }
    deviceCount += totalDevices;

    const devices = Array.isArray(rack.devices) ? rack.devices : null;
    if (!devices) {
      if (totalDevices > 0) {
        monitoredKnown = false;
        alarmKnown = false;
      }
      return;
    }
    if (devices.length !== totalDevices) {
      monitoredKnown = false;
      alarmKnown = false;
    }

    devices.forEach((device: Room3DDevice) => {
      if (device.monitor_bound === true) {
        monitoredCount += 1;
      }
      if (device.alarm_unavailable === true) {
        alarmKnown = false;
        return;
      }
      if (deviceHasAlarmGlow(device)) {
        alarmDeviceCount += 1;
      }
    });
  });

  let freeU: number | null = null;
  if (free.complete) {
    freeU = free.value;
  } else if (total.complete && used.complete) {
    freeU = Math.max(0, total.value - used.value);
  }

  const usageRatio =
    total.complete && used.complete && total.value > 0
      ? used.value / total.value
      : null;

  return {
    rackCount: racks.length,
    deviceCount: deviceCountKnown ? deviceCount : null,
    usedU: used.complete ? used.value : null,
    totalU: total.complete ? total.value : null,
    freeU,
    usageRatio,
    monitoredCount: monitoredKnown ? monitoredCount : null,
    alarmDeviceCount: alarmKnown ? alarmDeviceCount : null,
  };
};

/** Null when coverage cannot be computed. 0 when there are no devices. */
export const room3DOverviewCoverage = (
  monitoredCount: number | null,
  deviceCount: number | null,
): number | null => {
  if (deviceCount === 0) {
    return 0;
  }
  if (
    deviceCount === null ||
    monitoredCount === null ||
    !Number.isFinite(deviceCount) ||
    deviceCount < 0 ||
    !Number.isFinite(monitoredCount) ||
    monitoredCount < 0
  ) {
    return null;
  }
  return monitoredCount / deviceCount;
};

export const formatRoom3DOverviewCount = (value: number | null): string => {
  if (value === null || !Number.isFinite(value)) {
    return ROOM3D_OVERVIEW_EMPTY;
  }
  return String(Math.round(value));
};

export const formatRoom3DOverviewPercent = (ratio: number | null): string => {
  if (ratio === null || !Number.isFinite(ratio)) {
    return ROOM3D_OVERVIEW_EMPTY;
  }
  return `${Math.round(ratio * 100)}%`;
};

/** 面板在组件本地像素下能完整放下的最大缩放，不设上限；编辑态画布被 CSS 缩小时用它压住 readable-scale 的放大。 */
export const resolveRoom3DOverviewFit = (width: number, height: number) => {
  if (
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  ) {
    return 1;
  }
  const fit = Math.min(
    width / ROOM3D_OVERVIEW_REF_WIDTH,
    height / ROOM3D_OVERVIEW_REF_HEIGHT,
  );
  return Math.round(fit * 10000) / 10000;
};
