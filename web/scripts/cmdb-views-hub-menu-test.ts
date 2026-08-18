import assert from 'node:assert/strict';
import fs from 'node:fs';

const menu = JSON.parse(fs.readFileSync('src/app/cmdb/constants/menu.json', 'utf8'));
for (const locale of ['zh', 'en']) {
  const views = menu[locale].find((item: { url?: string }) => item.url === '/cmdb/assetOverview');
  assert.ok(views, `${locale}: 视图父项存在`);
  assert.equal(views.name, 'asset_info');
  assert.ok(!views.hasDetail, `${locale}: 视图不得 hasDetail`);
  const names = (views.children || []).map((c: { name: string }) => c.name);
  assert.deepEqual(names, [
    'asset_views_overview',
    'asset_views_application',
    'asset_views_k8s',
    'asset_views_network',
    'asset_views_ip',
    'asset_views_rack_room',
  ]);
  const urls = (views.children || []).map((c: { url: string }) => c.url);
  assert.deepEqual(urls, [
    '/cmdb/assetOverview',
    '/cmdb/views/application',
    '/cmdb/views/k8s',
    '/cmdb/views/network',
    '/cmdb/views/ip',
    '/cmdb/views/rack-room',
  ]);
  for (const child of views.children) {
    assert.equal(child.withParentPermission, true);
  }
}
console.log('cmdb-views-hub-menu-test: PASS');
