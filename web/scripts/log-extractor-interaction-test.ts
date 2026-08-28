import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  buildInstanceExtractorPath,
  buildTypeExtractorPath,
  extractorCreateSampleKey,
  extractorTypeLabelKey,
  flattenExtractorPaths,
  moveExtractorItem,
  normalizeExtractorSamples,
  reorderExtractorItem,
  resolveExtractorCreateTarget,
  shouldShowExtractorHeaderAdd,
  shouldShowExtractorPublicationAlert
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

assert.equal(
  shouldShowExtractorPublicationAlert('published'),
  false,
  '发布成功时不应持续占用列表空间'
);
for (const status of ['pending', 'generating', 'failed'] as const) {
  assert.equal(
    shouldShowExtractorPublicationAlert(status),
    true,
    `${status} 状态应保留可见反馈`
  );
}

assert.deepEqual(
  resolveExtractorCreateTarget({
    collect_type: 'syslog',
    instance_id: 'base'
  }),
  { kind: 'type', collectType: 'syslog' },
  'syslog 即使带有 instance_id=base 也走类型级提取器'
);
assert.deepEqual(
  resolveExtractorCreateTarget({
    collect_type: 'snmp_trap',
    instance_id: 'base'
  }),
  { kind: 'type', collectType: 'snmp_trap' },
  'snmp_trap 忽略采集侧写死的 base 实例'
);
assert.deepEqual(
  resolveExtractorCreateTarget({ collect_type: 'file' }),
  { kind: 'unavailable', reason: 'missing_instance' },
  '非被动接收类型缺少 instance_id 时不能创建'
);
assert.deepEqual(
  resolveExtractorCreateTarget({
    collect_type: 'file',
    instance_id: 'base'
  }),
  { kind: 'unavailable', reason: 'missing_instance' },
  '采集侧写死的 base 不能当作其余类型的业务实例'
);
assert.equal(
  extractorCreateSampleKey({ kind: 'type', id: 'syslog' }),
  'bk-lite.log-extractor.create-sample:type:syslog',
  '类型级创建样本应按采集类型隔离'
);
assert.equal(
  extractorCreateSampleKey({ kind: 'instance', id: 'nginx-1' }),
  'bk-lite.log-extractor.create-sample:instance:nginx-1',
  '实例级创建样本应按实例隔离'
);
assert.deepEqual(
  resolveExtractorCreateTarget({
    collect_type: 'file',
    instance_id: 'nginx-1'
  }),
  { kind: 'instance', instanceId: 'nginx-1' },
  '其余采集类型使用事件上的 instance_id'
);
assert.match(
  buildTypeExtractorPath(
    {
      id: 3,
      name: 'syslog',
      collector: 'Vector',
      icon: 'syslog',
      display_name: 'Syslog'
    },
    { create: true }
  ),
  /\/log\/integration\/list\/detail\/extractor\?.*name=syslog.*create=1/,
  '类型级创建应落到接入详情提取器页'
);
assert.equal(
  buildInstanceExtractorPath('nginx-1', { create: true }),
  '/log/integration/receive?extractor=nginx-1&create=1',
  '实例级创建应打开日志接收页现有抽屉'
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

assert.doesNotMatch(
  drawerSource,
  /<Form\.List name="conditions">/,
  '本期不展示附加条件编辑'
);
assert.doesNotMatch(
  drawerSource,
  /title: t\('log\.extractor\.condition'\)/,
  '列表不应再展示附加条件列'
);
assert.match(
  drawerSource,
  /name="target_field"[\s\S]{0,80}label=\{t\('log\.extractor\.targetField'\)\}/,
  '所有类型都应展示通用目标属性'
);
assert.match(
  drawerSource,
  /label: t\(extractorTypeLabelKey\(value\)\)/,
  '类型下拉应使用双语标签'
);
assert.equal(extractorTypeLabelKey('copy'), 'log.extractor.typeCopy');
assert.equal(extractorTypeLabelKey('regex_replace'), 'log.extractor.typeRegexReplace');
for (const key of [
  'typeCopy',
  'typeSplit',
  'typeKv',
  'typeRegex',
  'typeRegexReplace',
  'typeJson'
]) {
  assert.ok(zhLocale.log.extractor[key], `中文应提供 ${key}`);
  assert.ok(enLocale.log.extractor[key], `英文应提供 ${key}`);
}

assert.doesNotMatch(
  drawerSource,
  /publication\.published_generation\}\s*\/\s*\{publication\.desired_generation/,
  '发布状态不应使用容易被误解为规则条数的斜杠版本号'
);
for (const key of [
  'publicationDetails',
  'publishedVersion',
  'targetVersion',
  'rulesTitle'
]) {
  assert.match(drawerSource, new RegExp(`log\\.extractor\\.${key}`));
  assert.ok(zhLocale.log.extractor[key], `中文应提供 ${key} 状态标签`);
  assert.ok(enLocale.log.extractor[key], `英文应提供 ${key} 状态标签`);
}
for (const key of [
  'pendingTitle',
  'generatingTitle',
  'failedTitle',
  'pendingHint',
  'generatingHint',
  'failedHint'
]) {
  assert.ok(zhLocale.log.extractor[key], `中文应提供 ${key} 状态文案`);
  assert.ok(enLocale.log.extractor[key], `英文应提供 ${key} 状态文案`);
}
assert.match(drawerSource, /log\.extractor\.\$\{publication\.status\}Title/);
assert.match(drawerSource, /log\.extractor\.\$\{publication\.status\}Hint/);
assert.match(
  drawerSource,
  /<Popover[\s\S]{0,180}trigger=\{\['hover', 'focus', 'click'\]\}/,
  '状态详情应支持悬停、键盘焦点和点击访问'
);
assert.match(
  drawerSource,
  /shouldShowExtractorPublicationAlert\(publication\.status\)/,
  '发布成功时应隐藏常驻提示，异常和过程状态继续展示'
);
assert.match(
  drawerSource,
  /log\.extractor\.rulesTitle'[\s\S]{0,180}\(\{rules\.length\}\)/,
  '当前实例规则数应归入列表标题'
);
assert.match(
  drawerSource,
  /action=\{[\s\S]{0,320}publication\.status === 'failed'[\s\S]{0,320}void retry\(\)/,
  '发布失败提示应直接提供重试入口'
);

const searchPageSource = readFileSync(
  new URL('../src/app/log/(pages)/search/page.tsx', import.meta.url),
  'utf8'
);
const typeExtractorPageSource = readFileSync(
  new URL(
    '../src/app/log/(pages)/integration/list/detail/extractor/page.tsx',
    import.meta.url
  ),
  'utf8'
);
const receivePageSource = readFileSync(
  new URL('../src/app/log/(pages)/integration/receive/page.tsx', import.meta.url),
  'utf8'
);

assert.match(
  searchPageSource,
  /list\.can_operate !== true/,
  '搜索页创建实例提取器必须确认当前团队对该实例有编辑权限'
);
assert.match(
  typeExtractorPageSource,
  /consumeExtractorCreateSample\(\{\s*kind: 'type'/,
  '类型级创建页应按采集类型读取搜索页写入的样本'
);
assert.match(
  receivePageSource,
  /list\.can_operate === true/,
  '日志接收页不能在实例不在当前表格页时默认放开编辑'
);
assert.match(
  receivePageSource,
  /consumeExtractorCreateSample\(\{\s*kind: 'instance'/,
  '实例级创建抽屉应按实例读取搜索页写入的样本'
);

console.log('log-extractor-interaction tests passed');
