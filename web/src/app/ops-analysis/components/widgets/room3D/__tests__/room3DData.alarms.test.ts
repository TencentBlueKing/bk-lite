import { describe, expect, it } from "vitest";

import {
  aggregateRackAlarmSummary,
  deviceHasAlarmGlow,
  formatRoom3DDeviceAlarmCountValue,
  formatRoom3DSeverityLabel,
  shouldShowRoom3DDeviceHighestSeverity,
  validateRoom3DData,
  type Room3DDevice,
} from "../room3DData";

const identity = (id: string) => id;

const baseDevice = {
  device_id: "dev-1",
  device_name: "server-1",
  rack_u_start: 1,
  u_size: 2,
};

const validateDevices = (devices: unknown[]) => {
  const result = validateRoom3DData(
    {
      room: { id: "room-1", name: "Room A" },
      racks: [
        {
          rack_id: "rack-1",
          rack_name: "R1",
          row: 1,
          col: 1,
          devices,
        },
      ],
    },
    identity,
  );
  expect(result.ok).toBe(true);
  if (!result.ok) {
    throw new Error(
      "error" in result ? String(result.error) : "validation failed",
    );
  }
  return result.data.racks[0].devices ?? [];
};

describe("room3D device alarm fields", () => {
  it("defaults missing alarm fields to unbound-like values for backward compatibility", () => {
    const [device] = validateDevices([baseDevice]);
    expect(device.monitor_bound).toBe(false);
    expect(device.alarm_unavailable).toBe(false);
    expect(device.active_alarm_count).toBeNull();
    expect(device.highest_severity).toBeNull();
    expect(deviceHasAlarmGlow(device)).toBe(false);
  });

  it("passthroughs valid alarm fields and coerces illegal combinations", () => {
    const [ok, badSeverity, badCount, unavailableWithCount, unboundWithCount] =
      validateDevices([
        {
          ...baseDevice,
          device_id: "ok",
          monitor_bound: true,
          alarm_unavailable: false,
          active_alarm_count: 3,
          highest_severity: "critical",
        },
        {
          ...baseDevice,
          device_id: "bad-sev",
          monitor_bound: true,
          alarm_unavailable: false,
          active_alarm_count: 1,
          highest_severity: "info",
        },
        {
          ...baseDevice,
          device_id: "bad-count",
          monitor_bound: true,
          alarm_unavailable: false,
          active_alarm_count: -1,
          highest_severity: "warning",
        },
        {
          ...baseDevice,
          device_id: "unavailable-count",
          monitor_bound: true,
          alarm_unavailable: true,
          active_alarm_count: 5,
          highest_severity: "critical",
        },
        {
          ...baseDevice,
          device_id: "unbound-count",
          monitor_bound: false,
          alarm_unavailable: false,
          active_alarm_count: 2,
          highest_severity: "error",
        },
      ]);

    expect(ok).toMatchObject({
      monitor_bound: true,
      alarm_unavailable: false,
      active_alarm_count: 3,
      highest_severity: "critical",
    });
    expect(badSeverity).toMatchObject({
      monitor_bound: true,
      alarm_unavailable: false,
      active_alarm_count: 1,
      highest_severity: null,
    });
    expect(badCount).toMatchObject({
      monitor_bound: true,
      alarm_unavailable: true,
      active_alarm_count: null,
      highest_severity: null,
    });
    expect(unavailableWithCount).toMatchObject({
      monitor_bound: true,
      alarm_unavailable: true,
      active_alarm_count: null,
      highest_severity: null,
    });
    expect(unboundWithCount).toMatchObject({
      monitor_bound: false,
      alarm_unavailable: false,
      active_alarm_count: null,
      highest_severity: null,
    });
    expect(deviceHasAlarmGlow(unavailableWithCount)).toBe(false);
    expect(deviceHasAlarmGlow(unboundWithCount)).toBe(false);
  });

  it("glows only when available and active_alarm_count > 0", () => {
    const glowing: Room3DDevice = {
      ...baseDevice,
      monitor_bound: true,
      alarm_unavailable: false,
      active_alarm_count: 2,
      highest_severity: "error",
    };
    const zero: Room3DDevice = {
      ...glowing,
      active_alarm_count: 0,
      highest_severity: null,
    };
    const unavailable: Room3DDevice = {
      ...glowing,
      alarm_unavailable: true,
      active_alarm_count: null,
      highest_severity: null,
    };

    expect(deviceHasAlarmGlow(glowing)).toBe(true);
    expect(deviceHasAlarmGlow(zero)).toBe(false);
    expect(deviceHasAlarmGlow(unavailable)).toBe(false);
    expect(deviceHasAlarmGlow({ active_alarm_count: null })).toBe(false);
    expect(
      deviceHasAlarmGlow({
        alarm_unavailable: true,
        active_alarm_count: 9,
      }),
    ).toBe(false);
  });

  it("aggregates rack alarm count and highest severity with critical > error > warning", () => {
    const summary = aggregateRackAlarmSummary([
      {
        ...baseDevice,
        device_id: "a",
        active_alarm_count: 2,
        highest_severity: "warning",
      },
      {
        ...baseDevice,
        device_id: "b",
        active_alarm_count: null,
        highest_severity: "critical",
      },
      {
        ...baseDevice,
        device_id: "c",
        active_alarm_count: 1,
        highest_severity: "error",
      },
      {
        ...baseDevice,
        device_id: "d",
        active_alarm_count: 4,
        highest_severity: "warning",
      },
    ]);

    expect(summary).toEqual({
      count: 7,
      highest_severity: "error",
    });
  });

  it("returns zero aggregate when no device contributes alarms", () => {
    expect(
      aggregateRackAlarmSummary([
        {
          ...baseDevice,
          monitor_bound: false,
          active_alarm_count: null,
          highest_severity: null,
        },
        {
          ...baseDevice,
          device_id: "u",
          alarm_unavailable: true,
          active_alarm_count: null,
          highest_severity: null,
        },
      ]),
    ).toEqual({ count: 0, highest_severity: null });
  });

  it("formats sidebar alarm value and severity row for four states", () => {
    expect(
      formatRoom3DDeviceAlarmCountValue(
        {
          monitor_bound: false,
          alarm_unavailable: false,
          active_alarm_count: null,
        },
        identity,
      ),
    ).toBe("dashboard.room3DMonitorUnbound");
    expect(
      formatRoom3DDeviceAlarmCountValue(
        {
          monitor_bound: true,
          alarm_unavailable: true,
          active_alarm_count: null,
        },
        identity,
      ),
    ).toBe("dashboard.room3DAlarmUnavailable");
    expect(
      formatRoom3DDeviceAlarmCountValue(
        {
          monitor_bound: true,
          alarm_unavailable: false,
          active_alarm_count: 0,
        },
        identity,
      ),
    ).toBe("dashboard.room3DNoAlarms");
    expect(
      formatRoom3DDeviceAlarmCountValue(
        {
          monitor_bound: true,
          alarm_unavailable: false,
          active_alarm_count: 3,
        },
        identity,
      ),
    ).toBe("3dashboard.room3DCountUnit");

    expect(
      shouldShowRoom3DDeviceHighestSeverity({
        monitor_bound: true,
        alarm_unavailable: false,
        active_alarm_count: 2,
        highest_severity: "warning",
      }),
    ).toBe(true);
    expect(
      shouldShowRoom3DDeviceHighestSeverity({
        monitor_bound: true,
        alarm_unavailable: false,
        active_alarm_count: 0,
        highest_severity: null,
      }),
    ).toBe(false);
    expect(
      shouldShowRoom3DDeviceHighestSeverity({
        monitor_bound: true,
        alarm_unavailable: true,
        active_alarm_count: null,
        highest_severity: "critical",
      }),
    ).toBe(false);
    expect(formatRoom3DSeverityLabel("error", identity)).toBe(
      "dashboard.application3DSeverity_error",
    );
    expect(formatRoom3DSeverityLabel(null, identity)).toBe("");
  });
});
