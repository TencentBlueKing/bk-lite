import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const assetPage = readFileSync(
  resolve('src/app/monitor/(pages)/integration/asset/page.tsx'),
  'utf8'
);
const menuItems = readFileSync(
  resolve('src/app/monitor/hooks/integration/common/assetMenuItems.tsx'),
  'utf8'
);
const zh = JSON.parse(readFileSync(resolve('src/app/monitor/locales/zh.json'), 'utf8'));
const en = JSON.parse(readFileSync(resolve('src/app/monitor/locales/en.json'), 'utf8'));

assert.match(menuItems, /key: 'batchDelete'/, '资产操作菜单应提供批量删除入口');
assert.match(
  menuItems,
  /requiredPermissions=\{\['Delete'\]\}/,
  '批量删除入口应受删除权限控制'
);
assert.match(
  assetPage,
  /instance_ids: instanceIds/,
  '批量删除应一次提交全部选中实例 ID'
);
assert.match(
  assetPage,
  /okButtonProps: \{ danger: true \}/,
  '批量删除确认按钮应使用危险操作样式'
);
assert.match(
  assetPage,
  /modal\.confirm\(/,
  '批量删除应使用当前页面上下文中的确认框'
);
assert.match(
  assetPage,
  /onOk: batchDeleteInstConfirm/,
  '确认框应等待异步删除完成并阻止重复提交'
);
assert.match(
  assetPage,
  /setSelectedRowKeys\(\[\]\)/,
  '批量删除成功后应清空选择'
);

for (const locale of [zh, en]) {
  assert.match(
    locale.monitor.integrations.assetBatchDeleteConfirm,
    /\{count\}/,
    '批量删除确认文案应展示选中数量'
  );
  assert.match(
    locale.monitor.integrations.assetBatchDeleteSuccess,
    /\{count\}/,
    '批量删除成功反馈应展示删除数量'
  );
}

console.log('monitor asset batch delete validation passed');
