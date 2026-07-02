import assert from 'assert/strict';
import { readFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  resolve(here, '../src/app/cmdb/(pages)/assetData/detail/ipView/ipamMatrix.tsx'),
  'utf8'
);

const heightMatch = source.match(/const CELL_H = (\d+);/);
assert.ok(heightMatch, 'IPAM /24 grid should keep an explicit CELL_H constant');

const cellHeight = Number(heightMatch[1]);
assert.ok(
  cellHeight >= 34 && cellHeight <= 40,
  `IPAM /24 grid cell height should be 34-40px for readable vertical density, got ${cellHeight}px`
);

assert.match(
  source,
  /height: CELL_H/,
  'IPAM /24 grid cells should use fixed height so wide screens do not become square-cell layouts'
);
assert.doesNotMatch(
  source,
  /aspectRatio:\s*['"]1 \/ 1['"]/,
  'IPAM /24 grid cells should not use square aspect ratio'
);

console.log('cmdb ipam grid height test passed');
