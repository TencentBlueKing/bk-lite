import assert from 'node:assert/strict';
import {
  CANVAS_PAD_X,
  COL_STRIDE,
  DEFAULT_LANE_WIDTH,
  LAYER_KEYS,
  LAYOUT_NODE,
  ORIGIN_X,
  columnsForLaneWidth,
  packLayeredNodes,
  resolveBandIndex,
} from '../src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/layerLayout';

assert.equal(columnsForLaneWidth(200), 1);
assert.equal(columnsForLaneWidth(576), 2);
assert.equal(columnsForLaneWidth(848), 3);
assert.equal(ORIGIN_X - LAYOUT_NODE.width / 2, CANVAS_PAD_X);
assert.ok(columnsForLaneWidth(DEFAULT_LANE_WIDTH) >= 3);

const twoCol = packLayeredNodes({
  layers: {
    root: [{ id: 'sys' }],
    service: [{ id: 'app-a' }, { id: 'app-b' }, { id: 'app-c' }],
    host: Array.from({ length: 5 }, (_, index) => ({ id: `host-${index}` })),
    appService: [],
    infrastructure: [],
  },
  laneWidth: 600,
});

assert.deepEqual(twoCol.bands.map((band) => band.key), [...LAYER_KEYS]);
assert.equal(twoCol.bands.length, 5);

const hosts = twoCol.positions.filter((node) => node.layer === 'host');
assert.equal(hosts.length, 5);
assert.equal(new Set(hosts.map((node) => node.x)).size, 2);
assert.equal(new Set(hosts.map((node) => node.y)).size, 3);
assert.ok(Math.max(...hosts.map((node) => node.x)) - Math.min(...hosts.map((node) => node.x)) === COL_STRIDE);

const root = twoCol.positions.find((node) => node.id === 'sys');
assert.ok(root);
assert.equal(root.x, ORIGIN_X + COL_STRIDE / 2);

const hostBand = twoCol.bands.find((band) => band.key === 'host');
assert.ok(hostBand);
hosts.forEach((host) => {
  assert.equal(resolveBandIndex(host.y, twoCol.bands), LAYER_KEYS.indexOf('host'));
  assert.ok(host.y >= hostBand.top && host.y <= hostBand.bottom);
});

const sysEcom = packLayeredNodes({
  layers: {
    root: [{ id: 'sys-ecom' }],
    service: Array.from({ length: 6 }, (_, index) => ({ id: `app-${index}` })),
    host: Array.from({ length: 30 }, (_, index) => ({ id: `host-${index}` })),
    appService: [],
    infrastructure: [],
  },
  laneWidth: 1400,
});

const ecomHosts = sysEcom.positions.filter((node) => node.layer === 'host');
const maxX = Math.max(...sysEcom.positions.map((node) => node.x));
const hostRows = new Set(ecomHosts.map((node) => node.y)).size;
assert.equal(ecomHosts.length, 30);
assert.ok(hostRows >= 5, `expected wrapped host rows, got ${hostRows}`);
assert.ok(maxX < 1600, `expected packed width under 1600px, got ${maxX}`);

console.log('cmdb-app-topology-layer-layout test passed');
