import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  cellMatchesFilter,
  classifyAlloc,
  classifyLive,
  DEFAULT_IPAM_FILTERS,
  type IpInstance,
} from '../src/app/cmdb/(pages)/assetData/detail/ipView/ipamCells';

const ip = (partial: Partial<IpInstance> = {}): IpInstance => ({
  ip_addr: '10.11.27.40',
  ...partial,
});

assert.equal(classifyAlloc(null), 'free');
assert.equal(classifyAlloc(ip({ ip_allocated_status: ['available'] })), 'free');
assert.equal(classifyAlloc(ip({ ip_allocated_status: ['allocated'] })), 'allocated');
assert.equal(classifyAlloc(ip({ ip_allocated_status: ['reserved'] })), 'reserved');
assert.equal(classifyAlloc(ip({ ip_allocated_status: ['reserved'], ip_status: ['conflict'] })), 'reserved');
assert.equal(classifyAlloc(ip({})), 'allocated');

assert.equal(classifyLive(null), 'none');
assert.equal(classifyLive(ip({ ip_status: ['online'] })), 'online');
assert.equal(classifyLive(ip({ ip_status: ['offline'] })), 'offline');
assert.equal(classifyLive(ip({ ip_status: ['conflict'] })), 'conflict');
assert.equal(classifyLive(ip({ ip_status: ['online', 'conflict'] })), 'conflict');
assert.equal(classifyLive(ip({ ip_status: ['unknown'] })), 'none');

assert.equal(
  cellMatchesFilter({ alloc: 'allocated', live: 'offline' }, DEFAULT_IPAM_FILTERS),
  true
);
assert.equal(
  cellMatchesFilter(
    { alloc: 'allocated', live: 'offline' },
    { ...DEFAULT_IPAM_FILTERS, alloc: { ...DEFAULT_IPAM_FILTERS.alloc, allocated: false } }
  ),
  true,
  '关掉已分配时，仍选中离线的格子应保持高亮'
);
assert.equal(
  cellMatchesFilter(
    { alloc: 'allocated', live: 'offline' },
    {
      alloc: { ...DEFAULT_IPAM_FILTERS.alloc, allocated: false },
      live: { ...DEFAULT_IPAM_FILTERS.live, offline: false },
    }
  ),
  false,
  '管理态和现网态都未选中时才置灰'
);
assert.equal(
  cellMatchesFilter(
    { alloc: 'allocated', live: 'offline' },
    { ...DEFAULT_IPAM_FILTERS, live: { ...DEFAULT_IPAM_FILTERS.live, offline: false } }
  ),
  true,
  '关掉离线时，仍选中已分配的格子应保持高亮'
);
assert.equal(
  cellMatchesFilter(
    { alloc: 'free', live: 'none' },
    { ...DEFAULT_IPAM_FILTERS, live: { online: false, offline: false, conflict: false } }
  ),
  true
);
assert.equal(
  cellMatchesFilter(
    { alloc: 'allocated', live: 'none' },
    { ...DEFAULT_IPAM_FILTERS, alloc: { ...DEFAULT_IPAM_FILTERS.alloc, allocated: false } }
  ),
  false
);
assert.equal(
  cellMatchesFilter(
    { alloc: 'reserved', live: 'online' },
    { ...DEFAULT_IPAM_FILTERS, alloc: { ...DEFAULT_IPAM_FILTERS.alloc, reserved: false } }
  ),
  true
);

const here = path.dirname(fileURLToPath(import.meta.url));
const matrixSrc = fs.readFileSync(
  path.join(here, '../src/app/cmdb/(pages)/assetData/detail/ipView/ipamMatrix.tsx'),
  'utf8'
);
assert.match(matrixSrc, /data-filter-alloc/);
assert.match(matrixSrc, /data-filter-live/);
assert.match(matrixSrc, /classifyAlloc/);
assert.match(matrixSrc, /cellMatchesFilter/);
assert.doesNotMatch(matrixSrc, /allocated_online/);
assert.doesNotMatch(matrixSrc, /KIND_COLOR|ipToCellKind/);

console.log('cmdb ipam cells test passed');
