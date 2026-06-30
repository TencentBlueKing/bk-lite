import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(__dirname, '..');
const sidebarTsx = fs.readFileSync(
  path.join(root, 'src/app/monitor/dashboards/components/dashboard-sidebar.tsx'),
  'utf8',
);
const sidebarScss = fs.readFileSync(
  path.join(root, 'src/app/monitor/dashboards/components/dashboard-sidebar.module.scss'),
  'utf8',
);

assert.match(sidebarTsx, /components\/treeSelector/);
assert.match(sidebarTsx, /<TreeSelector\b/);
assert.doesNotMatch(sidebarTsx, /styles\.groupHeader/);
assert.doesNotMatch(sidebarTsx, /styles\.item\b/);

assert.doesNotMatch(sidebarScss, /\.groupHeader\b/);
assert.doesNotMatch(sidebarScss, /\.itemIcon\b/);
assert.doesNotMatch(sidebarScss, /\.active\b/);
assert.match(sidebarScss, /padding:\s*20px 10px 10px 10px/);
