import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  CANDIDATE_OCCUPIED,
  CANDIDATE_SELECTABLE,
  DEVICE_LOCKED_ATTR_IDS,
  PLACEABLE_DEVICE_MODELS,
  RACK_LOCKED_ATTR_IDS,
  RACK_ROOM_ASSET_PERMISSION_PATH,
  buildDeviceDrawerRows,
  buildInstanceDetailPath,
  buildPlaceCreatePayload,
  buildPlaceExistingPayload,
  buildUnplacePayload,
  canPlaceOnEmpty,
  canUnplaceFromLayout,
  candidateIsSelectable,
  candidateOpensDetail,
  formatRackLocationLabel,
  formatDeviceAttrDisplay,
  hasInstanceOperate,
  isPlaceableDeviceModel,
  listDeviceDrawerAttrs,
  normalizeDeviceUSize,
  occupiedUSet,
  unplaceClearsDeviceStartOnly,
} from '../src/app/cmdb/(pages)/assetData/detail/relationships/rackRoomEdit';
import { U_PX } from '../src/app/cmdb/utils/rackRoomLayout';

assert.ok(U_PX >= 28, 'each rack U must be tall enough for a 1U device label');

assert.equal(RACK_ROOM_ASSET_PERMISSION_PATH, '/cmdb/assetData');
assert.ok(!PLACEABLE_DEVICE_MODELS.includes('host' as never));
assert.equal(isPlaceableDeviceModel('switch'), true);
assert.equal(isPlaceableDeviceModel('host'), false);
assert.equal(isPlaceableDeviceModel('physcial_server'), true);

assert.equal(formatRackLocationLabel(2, 1), 'A02');
assert.equal(formatRackLocationLabel(1, 3), 'C01');
assert.equal(normalizeDeviceUSize(undefined), 1);
assert.equal(normalizeDeviceUSize(4), 4);
assert.equal(normalizeDeviceUSize(0), 1);

const occupied = occupiedUSet([
  { rack_u_start: 10, u_size: 2, u_end: 11 },
  { rack_u_start: 1, u_size: 1, u_end: 1 },
]);
assert.deepEqual([...occupied].sort((a, b) => a - b), [1, 10, 11]);

assert.equal(canPlaceOnEmpty({ hasAdd: true, hasEdit: false }), true);
assert.equal(canPlaceOnEmpty({ hasAdd: false, hasEdit: true }), true);
assert.equal(canPlaceOnEmpty({ hasAdd: false, hasEdit: false }), false);
assert.equal(canUnplaceFromLayout({ hasEdit: true, instOperate: true }), true);
assert.equal(canUnplaceFromLayout({ hasEdit: true, instOperate: false }), false);
assert.equal(canUnplaceFromLayout({ hasEdit: false, instOperate: true }), false);
assert.equal(hasInstanceOperate(undefined), false);
assert.equal(hasInstanceOperate(['View']), false);
assert.equal(hasInstanceOperate(['View', 'Operate']), true);

assert.equal(candidateIsSelectable(CANDIDATE_SELECTABLE), true);
assert.equal(candidateOpensDetail(CANDIDATE_OCCUPIED), true);
assert.equal(candidateOpensDetail(CANDIDATE_SELECTABLE), false);

const detailPath = buildInstanceDetailPath({
  modelId: 'rack',
  instUuid: 'rack-8',
  instName: 'A01',
});
assert.match(detailPath, /\/cmdb\/assetData\/detail\/baseInfo\?/);
assert.match(detailPath, /inst_uuid=rack-8/);
assert.ok(!detailPath.includes('rack_room_layout'));

assert.deepEqual(
  buildPlaceCreatePayload({
    scope: 'room',
    containerInstUuid: 'room-1',
    modelId: 'rack',
    instanceInfo: { inst_name: 'R1' },
    row: 2,
    col: 1,
  }),
  {
    action: 'place_create',
    scope: 'room',
    container_inst_uuid: 'room-1',
    model_id: 'rack',
    instance_info: { inst_name: 'R1' },
    row: 2,
    col: 1,
    u_start: undefined,
    u_size: undefined,
  }
);

assert.equal(
  buildPlaceExistingPayload({
    scope: 'rack',
    containerInstUuid: 'rack-9',
    instUuid: 'sw-1',
    uStart: 10,
    uSize: 2,
  }).action,
  'place_existing'
);

const unplace = buildUnplacePayload({
  scope: 'rack',
  containerInstUuid: 'rack-9',
  instUuid: 'sw-1',
});
assert.equal(unplace.action, 'unplace');
assert.ok(!('u_size' in unplace));
assert.equal(unplaceClearsDeviceStartOnly({ rack_u_start: '' }), true);
assert.equal(unplaceClearsDeviceStartOnly({ rack_u_start: '', u_size: 2 }), false);
assert.deepEqual([...RACK_LOCKED_ATTR_IDS], ['location']);
assert.deepEqual([...DEVICE_LOCKED_ATTR_IDS], ['rack_u_start']);

const drawerAttrs = listDeviceDrawerAttrs([
  { attr_id: 'inst_name', attr_name: '名称' },
  { attr_id: 'organization', attr_name: '组织', attr_type: 'organization' },
  { attr_id: 'rack_u_start', attr_name: '起始U' },
  { attr_id: 'u_size', attr_name: '占用U' },
  { attr_id: 'mgmt_ip', attr_name: '管理IP' },
  { attr_id: 'hidden', attr_name: '隐藏', is_display_field: true },
  { attr_id: 'ports', attr_name: '端口', attr_type: 'table' },
]);
assert.deepEqual(
  drawerAttrs.map((item) => item.attr_id),
  ['organization', 'mgmt_ip']
);

const drawerRows = buildDeviceDrawerRows({
  attrs: drawerAttrs,
  detail: { organization: [1], mgmt_ip: '' },
});
assert.equal(drawerRows.length, 2);
assert.equal(drawerRows.find((row) => row.key === 'mgmt_ip')?.value, '--');
assert.equal(formatDeviceAttrDisplay({ attr_id: 'sn', attr_name: '序列号' }, ''), '--');
assert.equal(
  formatDeviceAttrDisplay(
    { attr_id: 'role', attr_type: 'enum', option: [{ id: 'core', name: '核心' }] },
    'core'
  ),
  '核心'
);

const here = dirname(fileURLToPath(import.meta.url));
const floorPlan = readFileSync(
  resolve(here, '../src/app/cmdb/(pages)/assetData/detail/relationships/roomFloorPlan.tsx'),
  'utf8'
);
const elevation = readFileSync(
  resolve(here, '../src/app/cmdb/(pages)/assetData/detail/relationships/rackElevation.tsx'),
  'utf8'
);
const placeModal = readFileSync(
  resolve(here, '../src/app/cmdb/(pages)/assetData/detail/relationships/layoutPlaceModal.tsx'),
  'utf8'
);
const drawer = readFileSync(
  resolve(here, '../src/app/cmdb/(pages)/assetData/detail/relationships/deviceDetailDrawer.tsx'),
  'utf8'
);
const fieldModal = readFileSync(
  resolve(here, '../src/app/cmdb/(pages)/assetData/list/fieldModal.tsx'),
  'utf8'
);
const zhLocale = readFileSync(resolve(here, '../src/app/cmdb/locales/zh.json'), 'utf8');
const enLocale = readFileSync(resolve(here, '../src/app/cmdb/locales/en.json'), 'utf8');

assert.equal(floorPlan.includes("return <Empty description={t('Model.emptyRoom')} />"), false);
assert.match(floorPlan, /rf-cell--empty/);
assert.match(floorPlan, /LayoutPlaceModal/);
assert.match(floorPlan, /layoutUnplace/);
assert.match(floorPlan, /layoutUnplaceRackContent/);
assert.match(floorPlan, /<Tooltip/);
assert.match(floorPlan, /rd-unplace/);
assert.match(floorPlan, /\.rd-hd:hover/);
assert.match(floorPlan, /\.rf-rack:hover \.rf-rack-unplace/);
assert.match(floorPlan, /canUnplaceFromLayout/);
assert.equal(floorPlan.includes('onRackSelect &&'), false);
const assoList = readFileSync(
  resolve(here, '../src/app/cmdb/(pages)/assetData/detail/relationships/list.tsx'),
  'utf8'
);
const selectInstance = readFileSync(
  resolve(here, '../src/app/cmdb/(pages)/assetData/detail/relationships/selectInstance.tsx'),
  'utf8'
);
assert.match(assoList, /permissionPath=\{RACK_ROOM_ASSET_PERMISSION_PATH\}/);
assert.match(selectInstance, /isRelated \? 'Delete Associate' : 'Add Associate'/);
assert.match(elevation, /empty-u-/);
assert.match(elevation, /LayoutPlaceModal/);
assert.equal(elevation.includes('overflow-y: auto'), false);
assert.equal(elevation.includes('max-height: calc(100vh'), false);
assert.equal(elevation.includes('MIN_U = 9'), false);
assert.equal(elevation.includes('window.innerHeight'), false);
assert.match(elevation, /svgId\(/);
assert.match(elevation, /compare \? alerts/);
assert.match(placeModal, /openInstanceDetail/);
assert.match(placeModal, /CANDIDATE_OCCUPIED/);
assert.match(placeModal, /lockedAttrIds/);
assert.match(placeModal, /hideAssociate: true/);
assert.equal(placeModal.includes('formInfo.row'), false);
assert.equal(placeModal.includes('formInfo.col'), false);
assert.match(placeModal, /delete instanceInfo.row/);
assert.match(drawer, /layoutUnplace/);
assert.match(drawer, /buildUnplacePayload/);
assert.match(drawer, /buildDeviceDrawerRows/);
assert.match(drawer, /getOrganizationDisplayText/);
assert.equal(drawer.includes("t('Model.noRackLayout')"), false);
assert.match(drawer, /deviceDrawerLoadFailed/);
assert.equal(drawer.includes('getInstanceDetail(device.inst_uuid || device.inst_id)'), false);
assert.doesNotMatch(drawer, /\bInput\b/);
assert.doesNotMatch(drawer, /\bForm\b/);
assert.match(fieldModal, /lockedAttrIds/);
assert.match(fieldModal, /createHandler/);
assert.match(zhLocale, /"layoutUnplace": "移出布局"/);
assert.match(enLocale, /"layoutUnplace": "Remove from layout"/);
assert.match(zhLocale, /"deviceDrawerLoadFailed": "无法加载实例详情"/);
assert.match(enLocale, /"deviceDrawerLoadFailed": "Unable to load instance details"/);

console.log('PASS cmdb-rack-room-layout');
