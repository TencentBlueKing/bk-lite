import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  flattenExtractorPaths,
  moveExtractorItem,
  normalizeExtractorSamples,
  reorderExtractorItem,
  shouldShowExtractorHeaderAdd
} from '../src/app/log/(pages)/integration/receive/logExtractorLogic';

assert.deepEqual(
  Array.from(
    flattenExtractorPaths({ http: { status: 200, 'request.id': 'a' } })
  ),
  ['http', 'http.status', 'http["request.id"]'],
  '属性选择器应生成规范嵌套路径和引用段'
);

assert.deepEqual(
  normalizeExtractorSamples({ data: [{ message: 'one' }, null, 'bad'] }),
  [{ message: 'one' }],
  '历史样本响应应只保留事件对象'
);

assert.deepEqual(
  moveExtractorItem([1, 2, 3], 1, -1),
  [2, 1, 3],
  '键盘上移应生成完整新顺序'
);
assert.equal(moveExtractorItem([1, 2, 3], 0, -1), null, '不能越过顺序边界');
assert.deepEqual(
  reorderExtractorItem([1, 2, 3, 4], 0, 2),
  [2, 3, 1, 4],
  '拖拽必须产生完整的新顺序'
);
assert.equal(reorderExtractorItem([1, 2, 3], 1, 1), null, '原地拖拽不提交');

assert.equal(
  shouldShowExtractorHeaderAdd(true, 0),
  false,
  '空状态应只保留表格内的新建入口'
);
assert.equal(
  shouldShowExtractorHeaderAdd(true, 1),
  true,
  '已有规则时应在抽屉头部显示新建入口'
);
assert.equal(
  shouldShowExtractorHeaderAdd(false, 1),
  false,
  '无操作权限时不应显示新建入口'
);

const drawerSource = readFileSync(
  new URL(
    '../src/app/log/(pages)/integration/receive/logExtractorDrawer.tsx',
    import.meta.url
  ),
  'utf8'
);
const zhLocale = JSON.parse(
  readFileSync(new URL('../src/app/log/locales/zh.json', import.meta.url), 'utf8')
) as { log: { extractor: Record<string, string> } };
const enLocale = JSON.parse(
  readFileSync(new URL('../src/app/log/locales/en.json', import.meta.url), 'utf8')
) as { log: { extractor: Record<string, string> } };

assert.match(
  drawerSource,
  /name="source_field"[\s\S]{0,240}extra=\{t\('log\.extractor\.pathSyntaxHint'\)\}/,
  '源属性应解释带引号方括号的规范路径语法'
);
assert.ok(zhLocale.log.extractor.pathSyntaxHint, '中文应提供属性路径语法说明');
assert.ok(enLocale.log.extractor.pathSyntaxHint, '英文应提供属性路径语法说明');

const conditionListSource = drawerSource.match(
  /<Form\.List name="conditions">([\s\S]*?)<\/Form\.List>/
)?.[1];
assert.ok(conditionListSource, '应能定位条件列表');
assert.match(
  conditionListSource,
  /<Row[^>]*gutter=\{8\}[^>]*align="top"[^>]*>/,
  '条件行应使用稳定栅格而不是可收缩的 Space 布局'
);
assert.equal(
  (conditionListSource.match(/<Col xs=\{24\} md=\{8\}>/g) || []).length,
  2,
  '条件属性与比较值在桌面宽度下都应获得稳定列宽'
);
assert.match(conditionListSource, /<Col xs=\{24\} md=\{5\}>/);
assert.match(conditionListSource, /<Col xs=\{24\} md=\{3\}>/);

assert.doesNotMatch(
  drawerSource,
  /publication\.published_generation\}\s*\/\s*\{publication\.desired_generation/,
  '发布状态不应使用容易被误解为规则条数的斜杠版本号'
);
for (const key of ['publishedVersion', 'targetVersion', 'instanceRuleCount']) {
  assert.match(drawerSource, new RegExp(`log\\.extractor\\.${key}`));
  assert.ok(zhLocale.log.extractor[key], `中文应提供 ${key} 状态标签`);
  assert.ok(enLocale.log.extractor[key], `英文应提供 ${key} 状态标签`);
}
assert.match(
  drawerSource,
  /log\.extractor\.instanceRuleCount'[\s\S]{0,120}rules\.length/,
  '状态区应明确展示当前采集实例的规则数量'
);

console.log('log-extractor-interaction tests passed');
