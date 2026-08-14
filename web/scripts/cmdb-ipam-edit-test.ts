import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  IPAM_ASSET_PERMISSION_PATH,
  buildIpamEditPayload,
  canPerformIpamEdit,
  decideManualIpAction,
  defaultAllocStatus,
  enumName,
  enumOptionsFromAttr,
  findModelAttr,
  firstEnum,
  formatAttrDisplay,
  hasInstanceOperate,
  isEditableIpAttr,
  isPersistedIp,
  listDrawerIpAttrs,
  listReadonlyIpAttrs,
  requiredMenuPermission,
} from '../src/app/cmdb/(pages)/assetData/detail/ipView/ipamEdit';

assert.equal(firstEnum(['allocated']), 'allocated');
assert.equal(firstEnum('reserved'), 'reserved');
assert.equal(firstEnum([]), undefined);

assert.equal(decideManualIpAction({ hasInstance: false, allocatedStatus: 'allocated' }), 'create');
assert.equal(decideManualIpAction({ hasInstance: true, allocatedStatus: 'reserved' }), 'update');
assert.equal(decideManualIpAction({ hasInstance: true, allocatedStatus: 'available' }), 'delete');
assert.equal(decideManualIpAction({ hasInstance: false, allocatedStatus: 'available' }), 'noop');

assert.equal(requiredMenuPermission('create'), 'Add');
assert.equal(requiredMenuPermission('update'), 'Edit');
assert.equal(requiredMenuPermission('delete'), 'Delete');
assert.equal(requiredMenuPermission('noop'), null);

assert.equal(hasInstanceOperate(undefined), true);
assert.equal(hasInstanceOperate(['View', 'Operate']), true);
assert.equal(hasInstanceOperate(['View']), false);
assert.equal(hasInstanceOperate([]), false);

assert.equal(
  canPerformIpamEdit({
    action: 'create',
    hasAdd: true,
    hasEdit: false,
    hasDelete: false,
    instOperate: true,
  }),
  true
);
assert.equal(
  canPerformIpamEdit({
    action: 'create',
    hasAdd: false,
    hasEdit: true,
    hasDelete: true,
    instOperate: true,
  }),
  false
);
assert.equal(
  canPerformIpamEdit({
    action: 'update',
    hasAdd: true,
    hasEdit: true,
    hasDelete: true,
    instOperate: false,
  }),
  false
);
assert.equal(
  canPerformIpamEdit({
    action: 'delete',
    hasAdd: false,
    hasEdit: true,
    hasDelete: true,
    instOperate: true,
  }),
  true
);

assert.equal(isPersistedIp({ ip_addr: '10.11.27.1', inst_uuid: 'abc' }), true);
assert.equal(isPersistedIp({ ip_addr: '10.11.27.1' }), false);

const allocAttr = {
  attr_id: 'ip_allocated_status',
  attr_name: 'IP分配状态',
  attr_type: 'enum',
  option: [
    { id: 'available', name: '可分配' },
    { id: 'allocated', name: '已分配' },
    { id: 'reserved', name: '预留' },
  ],
};
assert.equal(findModelAttr([allocAttr], 'ip_allocated_status')?.attr_name, 'IP分配状态');
assert.deepEqual(enumOptionsFromAttr(allocAttr), [
  { id: 'available', name: '可分配' },
  { id: 'allocated', name: '已分配' },
  { id: 'reserved', name: '预留' },
]);
assert.equal(enumOptionsFromAttr({ attr_id: 'description', option: { widget_type: 'multi_line' } }).length, 0);
assert.equal(enumName(enumOptionsFromAttr(allocAttr), 'allocated'), '已分配');
assert.equal(defaultAllocStatus(enumOptionsFromAttr(allocAttr)), 'allocated');

assert.deepEqual(
  buildIpamEditPayload({
    subnetInstUuid: 'subnet-1',
    ipAddr: '10.11.27.10',
    allocatedStatus: 'allocated',
    ipStatus: 'offline',
    ipType: 'static',
    ipUser: ['u1'],
    mac: 'AA:BB:CC:DD:EE:FF',
    description: 'web vip',
  }),
  {
    subnet_inst_uuid: 'subnet-1',
    ip_addr: '10.11.27.10',
    ip_allocated_status: 'allocated',
    ip_status: 'offline',
    ip_type: 'static',
    ip_user: ['u1'],
    mac: 'AA:BB:CC:DD:EE:FF',
    description: 'web vip',
  }
);

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const matrixSrc = fs.readFileSync(
  path.join(webRoot, 'src/app/cmdb/(pages)/assetData/detail/ipView/ipamMatrix.tsx'),
  'utf8'
);
const drawerSrc = fs.readFileSync(
  path.join(webRoot, 'src/app/cmdb/(pages)/assetData/detail/ipView/IpDetailDrawer.tsx'),
  'utf8'
);
const apiSrc = fs.readFileSync(
  path.join(webRoot, 'src/app/cmdb/api/instance.ts'),
  'utf8'
);

assert.match(apiSrc, /saveIpamIp/);
assert.match(apiSrc, /\/cmdb\/api\/instance\/ipam_ip\//);
assert.match(matrixSrc, /IPAM_ASSET_PERMISSION_PATH/);
assert.match(matrixSrc, /hasPermission\(\['Add'\]\)/);
assert.match(drawerSrc, /permissionPath=\{IPAM_ASSET_PERMISSION_PATH\}/);
assert.match(drawerSrc, /requiredPermissions=\{savePermission\}/);
assert.match(drawerSrc, /getModelAttrList\('ip'\)/);
assert.match(drawerSrc, /listDrawerIpAttrs/);
assert.match(drawerSrc, /isEditableIpAttr/);
assert.match(drawerSrc, /layout="vertical"/);
assert.match(drawerSrc, /span=\{12\}/);
assert.match(drawerSrc, /Input\.TextArea/);
assert.match(drawerSrc, /IPAM_DESC_ATTR_ID/);
assert.doesNotMatch(drawerSrc, /t\('Model\.ipViewAllocated'\)/);
assert.doesNotMatch(drawerSrc, /auto_collect/);
assert.doesNotMatch(drawerSrc, /ip_table/);
assert.equal(IPAM_ASSET_PERMISSION_PATH, '/cmdb/assetData');

assert.equal(isEditableIpAttr('ip_type'), true);
assert.equal(isEditableIpAttr('ip_user'), true);
assert.equal(isEditableIpAttr('ip_status'), true);
assert.equal(isEditableIpAttr('mac'), true);
assert.equal(isEditableIpAttr('ip_allocated_status'), true);
assert.equal(isEditableIpAttr('description'), true);

assert.deepEqual(
  listDrawerIpAttrs([
    { attr_id: 'ip_addr', attr_name: 'IP' },
    { attr_id: 'ip_allocated_status', attr_name: '分配状态' },
    { attr_id: 'description', attr_name: '描述' },
    { attr_id: 'ip_status', attr_name: 'IP状态' },
    { attr_id: 'ip_type', attr_name: 'IP类型', attr_type: 'enum' },
    { attr_id: 'organization', attr_name: '组织', attr_type: 'organization' },
    { attr_id: 'node_id', attr_name: '节点' },
    { attr_id: 'ip_table', attr_name: '主机表格', attr_type: 'table' },
    { attr_id: 'auto_collect', attr_name: '自动采集', attr_type: 'bool', is_system_link: true },
    { attr_id: 'inst_name', attr_name: '实例名称' },
    { attr_id: 'ip_user', attr_name: '使用人', attr_type: 'user' },
    { attr_id: 'mac', attr_name: 'MAC' },
  ]).map((item) => item.attr_id),
  ['ip_allocated_status', 'description', 'ip_status', 'ip_type', 'organization', 'inst_name', 'ip_user', 'mac']
);

assert.deepEqual(
  listReadonlyIpAttrs([
    { attr_id: 'ip_addr', attr_name: 'IP' },
    { attr_id: 'ip_allocated_status', attr_name: '分配状态' },
    { attr_id: 'description', attr_name: '描述' },
    { attr_id: 'ip_status', attr_name: 'IP状态' },
    { attr_id: 'ip_type', attr_name: 'IP类型', attr_type: 'enum' },
    { attr_id: 'organization', attr_name: '组织', attr_type: 'organization' },
    { attr_id: 'node_id', attr_name: '节点' },
    { attr_id: 'auto_collect', attr_name: '自动采集', attr_type: 'bool', is_system_link: true },
    { attr_id: 'inst_name', attr_name: '实例名称' },
  ]).map((item) => item.attr_id),
  ['organization', 'inst_name']
);

assert.equal(
  formatAttrDisplay(
    { attr_id: 'ip_type', attr_type: 'enum', option: [{ id: 'gateway', name: '网关' }] },
    ['gateway']
  ),
  '网关'
);
assert.equal(formatAttrDisplay({ attr_id: 'secret', attr_type: 'pwd' }, 'x'), '***');
assert.equal(
  formatAttrDisplay({ attr_id: 'auto_collect', attr_type: 'bool' }, true, { yes: '是', no: '否' }),
  '是'
);
assert.equal(formatAttrDisplay({ attr_id: 'remark', attr_type: 'str' }, ''), '--');

const zhSrc = fs.readFileSync(path.join(webRoot, 'src/app/cmdb/locales/zh.json'), 'utf8');
const enSrc = fs.readFileSync(path.join(webRoot, 'src/app/cmdb/locales/en.json'), 'utf8');
const publicZhSrc = fs.readFileSync(path.join(webRoot, 'public/locales/zh.json'), 'utf8');
const publicEnSrc = fs.readFileSync(path.join(webRoot, 'public/locales/en.json'), 'utf8');
assert.match(zhSrc, /"ipViewLiveStatusHint": "现网状态由对账刷新，不可在此修改"/);
assert.match(zhSrc, /"ipViewUnallocateHint": "改回可分配将删除该 IP 台账，格子恢复为空闲"/);
assert.match(enSrc, /"ipViewLiveStatusHint": "Live status is refreshed by reconciliation and cannot be edited here"/);
assert.match(enSrc, /"ipViewUnallocateHint": "Setting this IP back to free deletes the record and returns the cell to unused"/);
assert.match(publicZhSrc, /"Model.ipViewLiveStatusHint": "现网状态由对账刷新，不可在此修改"/);
assert.match(publicZhSrc, /"Model.ipViewUnallocateHint": "改回可分配将删除该 IP 台账，格子恢复为空闲"/);
assert.match(publicEnSrc, /"Model.ipViewLiveStatusHint": "Live status is refreshed by reconciliation and cannot be edited here"/);
assert.match(publicEnSrc, /"Model.ipViewUnallocateHint": "Setting this IP back to free deletes the record and returns the cell to unused"/);
assert.match(drawerSrc, /listDrawerIpAttrs/);
assert.match(drawerSrc, /getInstanceDetail/);
assert.match(drawerSrc, /layout="vertical"/);
assert.match(drawerSrc, /span=\{12\}/);
assert.doesNotMatch(drawerSrc, /Model\.ipViewLiveStatusHint/);
assert.doesNotMatch(drawerSrc, /现网状态由对账刷新，不可在此修改/);

console.log('cmdb ipam edit test passed');
