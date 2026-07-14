import * as assert from "node:assert/strict";

import {
  getRoom3DDisplayOptions,
  getRoom3DRackDevices,
  getRoom3DColumnLabel,
  getRoom3DPositionLabel,
  getRoom3DSceneRacks,
  validateRoom3DData,
} from "../src/app/ops-analysis/components/widgets/room3D/room3DData";
import {
  filterChartTypesForSurface,
  hasSupportedChartTypeForSurface,
} from "../src/app/ops-analysis/utils/chartTypeSurface";
import { shouldWaitForInitialWidgetData } from "../src/app/ops-analysis/utils/widgetRequestVersion";
import {
  getDefaultScreenWidgetAppearance,
  normalizeScreenWidgetAppearance,
  addConfiguredScreenWidget,
  createScreenWidgetItem,
} from "../src/app/ops-analysis/(pages)/view/screen/utils/layout";
import {
  ROOM3D_COL_GAP,
  ROOM3D_DEVICE_PULL_OUT_DISTANCE,
  ROOM3D_ROW_GAP,
  buildRoomFloorSize,
  getRoom3DRackScenePosition,
  resolveRoomObjectClickState,
  resolveRackClickState,
  shouldAutoFocusRack,
} from "../src/app/ops-analysis/components/widgets/room3D/room3DScene";
import { createRackVisual } from "../src/app/ops-analysis/components/widgets/room3D/room3DMeshes";

const installCanvasStub = () => {
  const noop = () => undefined;
  const context = {
    arc: noop,
    beginPath: noop,
    clearRect: noop,
    createLinearGradient: () => ({ addColorStop: noop }),
    fill: noop,
    fillRect: noop,
    fillText: (text: string) => {
      context.fillTextCalls.push(text);
    },
    lineTo: noop,
    moveTo: noop,
    stroke: noop,
    strokeRect: noop,
    strokeText: noop,
    fillStyle: "",
    font: "",
    lineWidth: 1,
    strokeStyle: "",
    textAlign: "",
    textBaseline: "",
    fillTextCalls: [] as string[],
  };
  globalThis.document = {
    createElement: (tagName: string) => {
      assert.equal(tagName, "canvas");
      return {
        height: 0,
        width: 0,
        getContext: () => context,
      };
    },
  } as unknown as Document;
  return context;
};

const validRoom = {
  room: { id: "7", name: "一号机房" },
  racks: [
    {
      rack_id: "5",
      rack_name: "A03",
      location: "A03",
      row: 1,
      col: 3,
      rack_type: "2",
      rack_type_name: "网络",
      u_count: 42,
      used_u: 21,
      free_u: 21,
      device_count: 8,
      devices: [
        {
          device_id: "10",
          device_name: "SW-01",
          model_id: "switch",
          rack_u_start: 1,
          u_size: 2,
          status: "running",
        },
        {
          device_id: "11",
          device_name: "Host-01",
          model_id: "host",
          rack_u_start: 8,
          u_size: 4,
          status: null,
        },
      ],
    },
  ],
  notice: "部分设备缺少有效 U 位，未在机柜内展示",
};

const validResult = validateRoom3DData(validRoom);
assert.equal(validResult.ok, true);
assert.equal(validResult.data?.room.name, "一号机房");
assert.equal(validResult.data?.racks[0].rack_id, "5");
assert.equal(validResult.data?.racks[0].location, "A03");
assert.equal(validResult.data?.racks[0].rack_type_name, "网络");
assert.equal(validResult.data?.racks[0].devices?.length, 2);
assert.equal(validResult.data?.notice, "部分设备缺少有效 U 位，未在机柜内展示");
assert.equal(getRoom3DPositionLabel(validResult.data!.racks[0]), "A03");

const realDevices = getRoom3DRackDevices(validResult.data!.racks[0]);
assert.deepEqual(
  realDevices.map((item) => ({
    id: item.device_id,
    name: item.device_name,
    uStart: item.rack_u_start,
    uSize: item.u_size,
  })),
  [
    { id: "10", name: "SW-01", uStart: 1, uSize: 2 },
    { id: "11", name: "Host-01", uStart: 8, uSize: 4 },
  ],
);

const fallbackDevices = getRoom3DRackDevices({
  rack_id: "6",
  rack_name: "A04",
  row: 1,
  col: 4,
  u_count: 42,
  used_u: 12,
  device_count: 3,
});
assert.deepEqual(fallbackDevices, []);

const invalidDevicePosition = validateRoom3DData({
  room: { id: "7", name: "一号机房" },
  racks: [
    {
      rack_id: "5",
      rack_name: "A03",
      row: 1,
      col: 3,
      devices: [
        {
          device_id: "10",
          device_name: "SW-01",
          rack_u_start: null,
          u_size: 2,
        },
      ],
    },
  ],
});
assert.equal(invalidDevicePosition.ok, false);
assert.match(invalidDevicePosition.error || "", /room3DDeviceRequiredError/);

assert.deepEqual(
  resolveRackClickState(
    { selectedRackId: "rack-a", openRackId: "rack-a" },
    null,
  ),
  { selectedRackId: "rack-a", openRackId: "rack-a" },
);
assert.deepEqual(
  resolveRackClickState(
    { selectedRackId: "rack-a", openRackId: "rack-a" },
    "rack-a",
  ),
  { selectedRackId: "rack-a", openRackId: "" },
);
assert.deepEqual(
  resolveRackClickState(
    { selectedRackId: "rack-a", openRackId: "rack-a" },
    "rack-b",
  ),
  { selectedRackId: "rack-b", openRackId: "rack-b" },
);
assert.deepEqual(
  resolveRoomObjectClickState(
    {
      selectedRackId: "rack-a",
      openRackId: "rack-a",
      selectedDeviceId: "device-a",
    },
    null,
  ),
  {
    selectedRackId: "rack-a",
    openRackId: "rack-a",
    selectedDeviceId: "device-a",
  },
);
assert.deepEqual(
  resolveRoomObjectClickState(
    { selectedRackId: "rack-a", openRackId: "", selectedDeviceId: "" },
    { rackId: "rack-a", deviceId: "device-a" },
  ),
  {
    selectedRackId: "rack-a",
    openRackId: "rack-a",
    selectedDeviceId: "device-a",
  },
);
assert.deepEqual(
  resolveRoomObjectClickState(
    {
      selectedRackId: "rack-a",
      openRackId: "rack-a",
      selectedDeviceId: "device-a",
    },
    { rackId: "rack-a", deviceId: "device-a" },
  ),
  { selectedRackId: "rack-a", openRackId: "rack-a", selectedDeviceId: "" },
);
assert.deepEqual(
  resolveRoomObjectClickState(
    {
      selectedRackId: "rack-a",
      openRackId: "rack-a",
      selectedDeviceId: "device-a",
    },
    { rackId: "rack-a" },
  ),
  { selectedRackId: "rack-a", openRackId: "rack-a", selectedDeviceId: "" },
);
assert.deepEqual(
  resolveRoomObjectClickState(
    {
      selectedRackId: "rack-a",
      openRackId: "rack-a",
      selectedDeviceId: "device-a",
    },
    { rackId: "rack-a", target: "door" },
  ),
  { selectedRackId: "rack-a", openRackId: "", selectedDeviceId: "" },
);

const emptyResult = validateRoom3DData({
  room: { id: "8", name: "空机房" },
  racks: [],
});
assert.equal(emptyResult.ok, true);
assert.equal(emptyResult.data?.racks.length, 0);
assert.equal(emptyResult.data?.notice, undefined);

const missingRoom = validateRoom3DData({ racks: [] });
assert.equal(missingRoom.ok, false);
assert.match(missingRoom.error || "", /room3DFormatError/);

const missingRackField = validateRoom3DData({
  room: { id: "7", name: "一号机房" },
  racks: [{ rack_id: "5", rack_name: "A03", row: 1 }],
});
assert.equal(missingRackField.ok, false);
assert.match(missingRackField.error || "", /room3DRackRequiredError/);

const invalidPosition = validateRoom3DData({
  room: { id: "7", name: "一号机房" },
  racks: [{ rack_id: "5", rack_name: "A03", row: 0, col: 1 }],
});
assert.equal(invalidPosition.ok, false);
assert.match(invalidPosition.error || "", /room3DRackRequiredError/);

const duplicatedPosition = validateRoom3DData({
  room: { id: "7", name: "一号机房" },
  racks: [
    { rack_id: "5", rack_name: "A03", location: "A03", row: 1, col: 3 },
    { rack_id: "6", rack_name: "A3", location: "A03", row: 1, col: 3 },
    { rack_id: "7", rack_name: "B03", location: "B03", row: 2, col: 3 },
  ],
});
assert.equal(duplicatedPosition.ok, true);
const duplicatedSceneRacks = getRoom3DSceneRacks(duplicatedPosition.data!);
assert.equal(duplicatedSceneRacks.length, 2);
assert.equal(duplicatedSceneRacks[0].is_conflict, true);
assert.equal(duplicatedSceneRacks[0].location, "A03");
assert.deepEqual(
  duplicatedSceneRacks[0].conflict_racks?.map((rack) => rack.rack_name),
  ["A03", "A3"],
);
assert.equal(duplicatedSceneRacks[1].rack_id, "7");

assert.equal(getRoom3DColumnLabel(1), "A");
assert.equal(getRoom3DColumnLabel(26), "Z");
assert.equal(getRoom3DColumnLabel(27), "AA");
assert.equal(ROOM3D_COL_GAP > 1, true);
assert.equal(ROOM3D_COL_GAP < 1.4, true);
assert.equal(ROOM3D_ROW_GAP > ROOM3D_COL_GAP * 2.5, true);
assert.equal(ROOM3D_DEVICE_PULL_OUT_DISTANCE <= 0.28, true);
const columnDominantFloor = buildRoomFloorSize(3, 8);
assert.equal(
  columnDominantFloor.floorDepth > columnDominantFloor.floorWidth,
  true,
);
const compactColumnFloor = buildRoomFloorSize(1, 4);
const compactColumnAspect =
  compactColumnFloor.floorDepth / compactColumnFloor.floorWidth;
const columnDominantAspect =
  columnDominantFloor.floorDepth / columnDominantFloor.floorWidth;
assert.equal(
  compactColumnFloor.floorDepth > compactColumnFloor.floorWidth,
  true,
);
assert.equal(
  compactColumnFloor.floorDepth < columnDominantFloor.floorDepth,
  true,
);
assert.equal(compactColumnAspect < columnDominantAspect, true);
assert.equal(compactColumnFloor.floorDepth < 18, true);
const frontRackPosition = getRoom3DRackScenePosition(
  { row: 1, col: 1 },
  { maxRow: 4, maxCol: 6 },
);
const rearRackPosition = getRoom3DRackScenePosition(
  { row: 4, col: 1 },
  { maxRow: 4, maxCol: 6 },
);
assert.equal(frontRackPosition.z > rearRackPosition.z, true);

assert.equal(shouldAutoFocusRack(8.1), true);
assert.equal(shouldAutoFocusRack(5.2), false);

const canvasContext = installCanvasStub();
const rackWithManyDevices = createRackVisual(
  {
    rack_id: "dense-rack",
    rack_name: "Dense Rack",
    rack_type: "2",
    rack_type_name: "Network",
    row: 1,
    col: 1,
    u_count: 42,
    devices: Array.from({ length: 20 }, (_, index) => ({
      device_id: `device-${index + 1}`,
      device_name: `Device ${index + 1}`,
      rack_u_start: index + 1,
      u_size: 1,
    })),
  },
  0,
  0,
);
assert.equal(rackWithManyDevices.deviceMeshes.length, 20);
assert.equal(canvasContext.fillTextCalls.includes("A01"), true);
assert.equal(canvasContext.fillTextCalls.includes("Network"), true);

canvasContext.fillTextCalls.length = 0;
createRackVisual(
  {
    rack_id: "raw-type-rack",
    rack_name: "Raw Type Rack",
    rack_type: "2",
    row: 1,
    col: 2,
  },
  0,
  0,
);
assert.equal(canvasContext.fillTextCalls.includes("A02"), true);
assert.equal(canvasContext.fillTextCalls.includes("2"), false);

assert.deepEqual(filterChartTypesForSurface(["line", "room3D"], "screen"), [
  "line",
  "room3D",
]);
assert.deepEqual(filterChartTypesForSurface(["line", "room3D"], "dashboard"), [
  "line",
]);
assert.equal(hasSupportedChartTypeForSurface(["room3D"], "dashboard"), false);
assert.equal(hasSupportedChartTypeForSurface(["room3D"], "screen"), true);
assert.equal(
  hasSupportedChartTypeForSurface(["room3D", "line"], "dashboard"),
  true,
);
assert.equal(
  shouldWaitForInitialWidgetData({
    isSceneWidget: false,
    isTableLikeChart: false,
    hasDataSourceId: true,
    hasResolvedDataSource: false,
    hasRawPayload: false,
    hasDataValidation: false,
    requestEnabled: true,
    hasRequested: false,
  }),
  true,
);
assert.equal(
  shouldWaitForInitialWidgetData({
    isSceneWidget: false,
    isTableLikeChart: false,
    hasDataSourceId: true,
    hasResolvedDataSource: true,
    hasRawPayload: false,
    hasDataValidation: false,
    requestEnabled: false,
    hasRequested: false,
  }),
  false,
);
assert.equal(
  shouldWaitForInitialWidgetData({
    isSceneWidget: false,
    isTableLikeChart: false,
    hasDataSourceId: true,
    hasResolvedDataSource: true,
    hasRawPayload: true,
    hasDataValidation: false,
    requestEnabled: true,
    hasRequested: false,
  }),
  false,
);

assert.deepEqual(normalizeScreenWidgetAppearance(undefined), {
  frame: "panel",
});
assert.deepEqual(normalizeScreenWidgetAppearance({ frame: "bare" }), {
  frame: "bare",
});
assert.deepEqual(
  normalizeScreenWidgetAppearance({ frame: "unknown" as "bare" }),
  { frame: "panel" },
);
assert.deepEqual(getDefaultScreenWidgetAppearance("room3D"), { frame: "bare" });
assert.deepEqual(getDefaultScreenWidgetAppearance("line"), { frame: "panel" });
assert.deepEqual(getRoom3DDisplayOptions({ appearance: { frame: "bare" } }), {
  immersive: true,
  transparentScene: true,
});
assert.deepEqual(getRoom3DDisplayOptions({ appearance: { frame: "panel" } }), {
  immersive: false,
  transparentScene: false,
});

const room3DWidget = createScreenWidgetItem("room3D", []);
assert.deepEqual(room3DWidget.valueConfig.appearance, { frame: "bare" });

const screenWithBareLine = addConfiguredScreenWidget(
  {
    viewport: { width: 1920, height: 1080 },
    decorations: {},
    items: [],
  },
  {
    name: "透明折线",
    chartType: "line",
    dataSource: 1,
    appearance: { frame: "bare" },
  },
);
assert.equal(screenWithBareLine.items[0].chartType, "line");
assert.deepEqual(screenWithBareLine.items[0].valueConfig.appearance, {
  frame: "bare",
});
