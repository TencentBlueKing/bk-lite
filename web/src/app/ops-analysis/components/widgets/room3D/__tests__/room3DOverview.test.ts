import { describe, expect, it } from "vitest";

import type { Room3DDevice } from "../room3DData";
import {
  ROOM3D_OVERVIEW_EMPTY,
  ROOM3D_OVERVIEW_REF_HEIGHT,
  ROOM3D_OVERVIEW_REF_WIDTH,
  formatRoom3DOverviewCount,
  formatRoom3DOverviewPercent,
  resolveRoom3DOverviewScale,
  room3DOverviewCoverage,
  summarizeRoom3DOverview,
} from "../room3DOverview";

const device = (
  overrides: Partial<Room3DDevice> = {},
): Room3DDevice => ({
  device_id: "dev-1",
  device_name: "server-1",
  rack_u_start: 1,
  u_size: 2,
  monitor_bound: false,
  alarm_unavailable: false,
  active_alarm_count: null,
  highest_severity: null,
  ...overrides,
});

describe("summarizeRoom3DOverview", () => {
  it("counts racks, devices, U capacity, monitored devices, and alarm devices", () => {
    const stats = summarizeRoom3DOverview([
      {
        device_count: 2,
        u_count: 42,
        used_u: 10,
        free_u: 32,
        devices: [
          device({
            device_id: "a",
            monitor_bound: true,
            active_alarm_count: 2,
            highest_severity: "critical",
          }),
          device({ device_id: "b", monitor_bound: true, active_alarm_count: 0 }),
        ],
      },
      {
        device_count: 1,
        u_count: 42,
        used_u: 0,
        free_u: 42,
        devices: [device({ device_id: "c", monitor_bound: false })],
      },
    ]);

    expect(stats).toEqual({
      rackCount: 2,
      deviceCount: 3,
      usedU: 10,
      totalU: 84,
      freeU: 74,
      usageRatio: 10 / 84,
      monitoredCount: 2,
      alarmDeviceCount: 1,
    });
  });

  it("keeps usage empty when total U is 0 and never reports a negative remainder", () => {
    const stats = summarizeRoom3DOverview([
      {
        device_count: 0,
        u_count: 0,
        used_u: 0,
        free_u: 0,
        devices: [],
      },
    ]);

    expect(stats.totalU).toBe(0);
    expect(stats.usedU).toBe(0);
    expect(stats.freeU).toBe(0);
    expect(stats.usageRatio).toBeNull();
    expect(formatRoom3DOverviewPercent(stats.usageRatio)).toBe(
      ROOM3D_OVERVIEW_EMPTY,
    );
    expect(formatRoom3DOverviewPercent(stats.usageRatio)).not.toBe("0%");
  });

  it("treats missing or partial capacity as unknown instead of zero", () => {
    const missing = summarizeRoom3DOverview([
      { device_count: 1, devices: [device()] },
    ]);
    expect(missing.usedU).toBeNull();
    expect(missing.totalU).toBeNull();
    expect(missing.freeU).toBeNull();
    expect(missing.usageRatio).toBeNull();

    const partial = summarizeRoom3DOverview([
      { device_count: 0, u_count: 42, used_u: 10, free_u: 32, devices: [] },
      { device_count: 0, devices: [] },
    ]);
    expect(partial.totalU).toBeNull();
    expect(partial.usedU).toBeNull();
    expect(partial.usageRatio).toBeNull();
    expect(Number.isNaN(partial.usageRatio)).toBe(false);
  });

  it("clamps the remainder at 0 when used U exceeds total U", () => {
    const stats = summarizeRoom3DOverview([
      { device_count: 0, u_count: 40, used_u: 50, devices: [] },
    ]);

    expect(stats.freeU).toBe(0);
    expect(stats.usageRatio).toBe(50 / 40);
    expect(stats.freeU).toBeGreaterThanOrEqual(0);
  });

  it("ignores a negative free U and falls back to a non-negative remainder", () => {
    const stats = summarizeRoom3DOverview([
      { device_count: 0, u_count: 42, used_u: 10, free_u: -4, devices: [] },
    ]);

    expect(stats.freeU).toBe(32);
  });

  it("uses an explicit non-negative free U when every rack has one", () => {
    const stats = summarizeRoom3DOverview([
      { device_count: 0, u_count: 42, used_u: 10, free_u: 20, devices: [] },
    ]);

    expect(stats.freeU).toBe(20);
    expect(stats.usageRatio).toBe(10 / 42);
  });

  it("counts devices from the device list when device_count is absent", () => {
    const stats = summarizeRoom3DOverview([
      {
        u_count: 10,
        used_u: 2,
        free_u: 8,
        devices: [
          device({ monitor_bound: true, active_alarm_count: 1 }),
          device({ device_id: "b" }),
        ],
      },
    ]);

    expect(stats.deviceCount).toBe(2);
    expect(stats.monitoredCount).toBe(1);
    expect(stats.alarmDeviceCount).toBe(1);
  });

  it("leaves device, monitor, and alarm totals unknown when a rack has neither count nor devices", () => {
    const stats = summarizeRoom3DOverview([
      { u_count: 42, used_u: 0, free_u: 42 },
    ]);

    expect(stats.rackCount).toBe(1);
    expect(stats.deviceCount).toBeNull();
    expect(stats.monitoredCount).toBeNull();
    expect(stats.alarmDeviceCount).toBeNull();
  });

  it("does not invent monitor or alarm totals for devices missing from the list", () => {
    const stats = summarizeRoom3DOverview([
      {
        device_count: 3,
        u_count: 42,
        used_u: 4,
        free_u: 38,
        devices: [
          device({ monitor_bound: true, active_alarm_count: 1 }),
          device({ device_id: "b", monitor_bound: true, active_alarm_count: 0 }),
        ],
      },
    ]);

    expect(stats.deviceCount).toBe(3);
    expect(stats.monitoredCount).toBeNull();
    expect(stats.alarmDeviceCount).toBeNull();
    expect(room3DOverviewCoverage(stats.monitoredCount, stats.deviceCount)).toBeNull();
  });

  it("hides the alarm total when a listed device's alarms are unavailable", () => {
    const stats = summarizeRoom3DOverview([
      {
        device_count: 2,
        u_count: 42,
        used_u: 4,
        free_u: 38,
        devices: [
          device({
            monitor_bound: true,
            alarm_unavailable: true,
            active_alarm_count: null,
          }),
          device({
            device_id: "b",
            monitor_bound: true,
            active_alarm_count: 3,
          }),
        ],
      },
    ]);

    expect(stats.monitoredCount).toBe(2);
    expect(stats.alarmDeviceCount).toBeNull();
  });

  it("treats unbound devices and zero alarm counts as no active alarm", () => {
    const stats = summarizeRoom3DOverview([
      {
        device_count: 2,
        devices: [
          device({ monitor_bound: false, active_alarm_count: null }),
          device({ device_id: "b", monitor_bound: true, active_alarm_count: 0 }),
        ],
      },
    ]);

    expect(stats.monitoredCount).toBe(1);
    expect(stats.alarmDeviceCount).toBe(0);
  });

  it("reports an empty device population as 0 / 0 rather than unknown", () => {
    const stats = summarizeRoom3DOverview([
      { device_count: 0, u_count: 42, used_u: 0, free_u: 42, devices: [] },
    ]);

    expect(stats.deviceCount).toBe(0);
    expect(stats.monitoredCount).toBe(0);
    expect(stats.alarmDeviceCount).toBe(0);
    expect(room3DOverviewCoverage(0, 0)).toBe(0);
  });

  it("returns zeros for an empty rack list without dividing by zero", () => {
    const stats = summarizeRoom3DOverview([]);

    expect(stats.rackCount).toBe(0);
    expect(stats.deviceCount).toBe(0);
    expect(stats.totalU).toBe(0);
    expect(stats.usageRatio).toBeNull();
    expect(stats.freeU).toBe(0);
  });
});

describe("room3D overview scale", () => {
  it("stays at 1 once the widget is at least the reference size", () => {
    expect(resolveRoom3DOverviewScale(1440, 900)).toBe(1);
    expect(
      resolveRoom3DOverviewScale(
        ROOM3D_OVERVIEW_REF_WIDTH,
        ROOM3D_OVERVIEW_REF_HEIGHT,
      ),
    ).toBe(1);
    expect(resolveRoom3DOverviewScale(1600, 420)).toBe(1);
  });

  it("uses the tighter of width and height below the reference", () => {
    expect(resolveRoom3DOverviewScale(480, 240)).toBeCloseTo(480 / 1100, 4);
    expect(resolveRoom3DOverviewScale(1400, 210)).toBeCloseTo(210 / 420, 4);
    expect(resolveRoom3DOverviewScale(550, 300)).toBe(
      Math.min(
        Math.round((550 / ROOM3D_OVERVIEW_REF_WIDTH) * 10000) / 10000,
        Math.round((300 / ROOM3D_OVERVIEW_REF_HEIGHT) * 10000) / 10000,
      ),
    );
  });

  it("does not shrink when the measured box is missing", () => {
    expect(resolveRoom3DOverviewScale(0, 240)).toBe(1);
    expect(resolveRoom3DOverviewScale(480, 0)).toBe(1);
    expect(resolveRoom3DOverviewScale(Number.NaN, 240)).toBe(1);
    expect(resolveRoom3DOverviewScale(480, Number.POSITIVE_INFINITY)).toBe(1);
  });
});

describe("room3D overview formatting", () => {
  it("formats counts and percents, and keeps non-finite values as an em dash", () => {
    expect(formatRoom3DOverviewCount(12.2)).toBe("12");
    expect(formatRoom3DOverviewCount(null)).toBe(ROOM3D_OVERVIEW_EMPTY);
    expect(formatRoom3DOverviewCount(Number.NaN)).toBe(ROOM3D_OVERVIEW_EMPTY);
    expect(formatRoom3DOverviewPercent(0)).toBe("0%");
    expect(formatRoom3DOverviewPercent(0.256)).toBe("26%");
    expect(formatRoom3DOverviewPercent(null)).toBe(ROOM3D_OVERVIEW_EMPTY);
    expect(formatRoom3DOverviewPercent(Number.POSITIVE_INFINITY)).toBe(
      ROOM3D_OVERVIEW_EMPTY,
    );
  });

  it("computes coverage only when both sides are known", () => {
    expect(room3DOverviewCoverage(3, 4)).toBe(0.75);
    expect(room3DOverviewCoverage(null, 4)).toBeNull();
    expect(room3DOverviewCoverage(1, null)).toBeNull();
    expect(room3DOverviewCoverage(0, 0)).toBe(0);
  });
});
