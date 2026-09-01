import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { visibleSearchableFilterAttrs } from '../src/app/cmdb/(pages)/assetData/searchFilterAttrs';

const attrs = [
  { attr_id: 'inst_name', attr_type: 'str', attr_name: '名称' },
  { attr_id: 'sn', attr_type: 'str', attr_name: '序列号' },
  { attr_id: 'ip', attr_type: 'str', attr_name: 'IP' },
  { attr_id: 'photo', attr_type: 'image', attr_name: '图片' },
  { attr_id: 'file', attr_type: 'attachment', attr_name: '附件' },
];

assert.deepEqual(
  visibleSearchableFilterAttrs(attrs),
  [
    { attr_id: 'inst_name', attr_type: 'str', attr_name: '名称' },
    { attr_id: 'sn', attr_type: 'str', attr_name: '序列号' },
    { attr_id: 'ip', attr_type: 'str', attr_name: 'IP' },
  ],
  '未传列设置时保持全量可检索字段',
);

assert.deepEqual(
  visibleSearchableFilterAttrs(attrs, []),
  [
    { attr_id: 'inst_name', attr_type: 'str', attr_name: '名称' },
    { attr_id: 'sn', attr_type: 'str', attr_name: '序列号' },
    { attr_id: 'ip', attr_type: 'str', attr_name: 'IP' },
  ],
  '空列设置视为尚未加载，不裁剪筛选项',
);

assert.deepEqual(
  visibleSearchableFilterAttrs(attrs, ['ip', 'inst_name', 'photo', 'missing']),
  [
    { attr_id: 'ip', attr_type: 'str', attr_name: 'IP' },
    { attr_id: 'inst_name', attr_type: 'str', attr_name: '名称' },
  ],
  '只保留当前显示列且保持列顺序，隐藏列、附件图片与未知列不进下拉',
);

const pageSource = readFileSync(
  resolve(process.cwd(), 'src/app/cmdb/(pages)/assetData/page.tsx'),
  'utf8',
);
assert.match(pageSource, /displayFieldKeys=\{displayFieldKeys\}/);

const filterSource = readFileSync(
  resolve(process.cwd(), 'src/app/cmdb/(pages)/assetData/list/searchFilter.tsx'),
  'utf8',
);
assert.match(filterSource, /visibleSearchableFilterAttrs/);
assert.doesNotMatch(filterSource, /Select\.OptGroup/);
assert.doesNotMatch(filterSource, /FilterBar\.moreFields/);

const zh = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src/app/cmdb/locales/zh.json'), 'utf8'),
);
const en = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src/app/cmdb/locales/en.json'), 'utf8'),
);
assert.equal(zh.FilterBar.moreFields, undefined);
assert.equal(en.FilterBar.moreFields, undefined);

console.log('cmdb asset search filter attrs tests passed');
