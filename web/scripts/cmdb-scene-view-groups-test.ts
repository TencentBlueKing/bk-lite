import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  groupSceneViews,
  type SceneViewRecord,
} from '../src/app/cmdb/(pages)/views/scene/groupScenes';

const scene = (
  id: number,
  visibility: SceneViewRecord['visibility'],
  name = `s${id}`
): SceneViewRecord => ({
  id,
  name,
  visibility,
  model_ids: ['host'],
  tags: ['env:test'],
  tag_match: 'and',
});

const grouped = groupSceneViews([
  scene(3, 'global'),
  scene(1, 'personal'),
  scene(2, 'organization'),
  scene(4, 'personal'),
]);

assert.deepEqual(
  grouped.map((item) => item.key),
  ['personal', 'organization', 'global']
);
assert.deepEqual(
  grouped.map((item) => item.items.map((row) => row.id)),
  [[1, 4], [2], [3]]
);

const onlyMine = groupSceneViews([scene(1, 'personal')]);
assert.deepEqual(
  onlyMine.map((item) => item.key),
  ['personal']
);

assert.deepEqual(groupSceneViews([]), []);

const pageSrc = fs.readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), '../src/app/cmdb/(pages)/views/scene/page.tsx'),
  'utf8'
);
assert.equal(pageSrc.includes('ViewsWorkspaceShell'), false);
assert.equal(pageSrc.includes('ViewInstancePicker'), false);
assert.match(pageSrc, /groupSceneViews/);
assert.match(pageSrc, /buildBaseInfoPath/);
assert.match(pageSrc, /target="_blank"/);
assert.match(pageSrc, /rel="noopener noreferrer"/);
assert.match(pageSrc, /text-\[var\(--color-primary\)\]/);
assert.match(pageSrc, /ModelResultSection/);
assert.match(pageSrc, /ViewSummary/);
assert.equal(pageSrc.includes('onRow'), false);
assert.equal(pageSrc.includes('router.push'), false);

const sectionSrc = fs.readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), '../src/app/cmdb/(pages)/views/scene/modelResultSection.tsx'),
  'utf8'
);
assert.match(sectionSrc, /showSizeChanger/);
assert.match(sectionSrc, /SceneView.expand/);
assert.match(sectionSrc, /SceneView.collapse/);
assert.match(sectionSrc, /ModelAttrSearch/);
assert.equal(sectionSrc.includes('Math.max('), false);

const zhMenu = JSON.parse(
  fs.readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), '../src/app/cmdb/constants/menu.json'),
    'utf8'
  )
);
const views = zhMenu.zh.find((item: { url?: string }) => item.url === '/cmdb/assetOverview');
const tagView = (views.children || []).find((item: { name: string }) => item.name === 'asset_views_scene');
assert.equal(tagView.title, '标签视图');

const zhLocale = JSON.parse(
  fs.readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), '../src/app/cmdb/locales/zh.json'),
    'utf8'
  )
);
assert.equal(zhLocale.SceneView.title, '标签视图');
assert.equal(zhLocale.SceneView.create, '新建视图');
assert.equal(zhLocale.SceneView.edit, '编辑视图');
assert.doesNotMatch(JSON.stringify(zhLocale.SceneView), /场景/);

console.log('cmdb-scene-view-groups-test: PASS');
