import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  EXTRACTOR_CONDITION_OPERATORS,
  buildInstanceExtractorPath,
  buildTypeExtractorPath,
  defaultExtractorConditionItem,
  diffExtractorPreviewFields,
  extractorConditionNeedsValue,
  extractorConditionOperatorLabelKey,
  extractorCreateHandoffKey,
  extractorCreateSampleKey,
  extractorPreviewStatusLabelKey,
  extractorRequiresTargetField,
  extractorTypeLabelKey,
  extractorUsesSingleTargetField,
  flattenExtractorPaths,
  formatExtractorPreviewValue,
  getExtractorConditionSummary,
  moveExtractorItem,
  normalizeExtractorCondition,
  normalizeExtractorSamples,
  parseExtractorCreateHandoff,
  reorderExtractorItem,
  resolveExtractorCreateTarget,
  restoreExtractorEventShape,
  serializeExtractorCreateHandoff,
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
assert.match(
  buildInstanceExtractorPath('nginx-1', {
    create: true,
    handoff: 'abc',
    sourceField: 'message'
  }),
  /extractor=nginx-1.*create=1.*handoff=abc.*source_field=message/,
  '实例级创建应携带一次性 handoff 和源属性'
);
assert.equal(extractorCreateHandoffKey('abc'), 'bk-lite.log-extractor.create-handoff:abc');
assert.deepEqual(
  restoreExtractorEventShape({ message: 'keep', 'http.status': 201 }),
  { message: 'keep', http: { status: 201 } },
  '搜索页点号字段应还原成提取器使用的嵌套事件'
);
assert.deepEqual(
  parseExtractorCreateHandoff(
    serializeExtractorCreateHandoff({
      event: { message: 'deny', 'http.status': 201 },
      source_field: 'message'
    })
  ),
  {
    event: { message: 'deny', http: { status: 201 } },
    source_field: 'message'
  },
  '创建跳转应同时带上还原后的样本和源属性'
);
assert.equal(
  parseExtractorCreateHandoff('{"event":{"message":"x"}}'),
  null,
  '缺少源属性的 handoff 不能当成有效创建上下文'
);
assert.equal(extractorUsesSingleTargetField('copy'), true);
assert.equal(extractorUsesSingleTargetField('json'), true);
assert.equal(extractorUsesSingleTargetField('regex'), false);
assert.equal(extractorUsesSingleTargetField('kv'), false);
assert.equal(extractorRequiresTargetField('copy'), true);
assert.equal(extractorRequiresTargetField('json'), false);
assert.deepEqual(
  diffExtractorPreviewFields(
    { message: 'type=deny', status: 'old' },
    { message: 'type=deny', status: 'deny', firewall_log_type: 'deny' }
  ),
  [
    { path: 'status', kind: 'changed', before: 'old', after: 'deny' },
    { path: 'firewall_log_type', kind: 'added', after: 'deny' }
  ],
  '预览应只列出相对样本新增、变更或删除的叶子字段'
);
assert.deepEqual(
  diffExtractorPreviewFields({ payload: 'raw' }, {}),
  [{ path: 'payload', kind: 'removed', before: 'raw' }],
  '删除源属性应出现在预览效果里'
);
assert.equal(formatExtractorPreviewValue({ ok: true }), '{"ok":true}');
assert.equal(
  extractorPreviewStatusLabelKey('success'),
  'log.extractor.previewStatusSuccess'
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

assert.deepEqual(
  [...EXTRACTOR_CONDITION_OPERATORS],
  ['==', '!=', 'contains', '!contains', 'startswith', 'endswith'],
  '条件编辑器只暴露等于、包含和首尾匹配，不含存在性和正则'
);
assert.equal(
  EXTRACTOR_CONDITION_OPERATORS.includes('exists' as never),
  false,
  '条件编辑器不能提供 exists'
);
assert.equal(
  EXTRACTOR_CONDITION_OPERATORS.includes('!exists' as never),
  false,
  '条件编辑器不能提供 !exists'
);
assert.equal(
  EXTRACTOR_CONDITION_OPERATORS.includes('match' as never),
  false,
  '条件操作符不能包含正则 match'
);
assert.equal(extractorConditionNeedsValue('startswith'), true);
assert.equal(extractorConditionNeedsValue('endswith'), true);
for (const op of EXTRACTOR_CONDITION_OPERATORS) {
  assert.equal(
    extractorConditionNeedsValue(op),
    true,
    `${op} 必须填写比较值`
  );
}
assert.deepEqual(
  defaultExtractorConditionItem(),
  { field: 'message', op: '==', value: '' },
  '新增条件行默认匹配 message 等于'
);
assert.deepEqual(
  normalizeExtractorCondition({
    mode: 'OR',
    conditions: [
      { field: ' message ', op: 'contains', value: '%ASA-' },
      { field: 'hostname', op: 'exists', value: 'ignored' },
      { field: 'app', op: 'startswith', value: 'snmp' },
      { field: 'source', op: 'endswith', value: '.log' },
      { field: '', op: '==', value: 'drop' },
      { field: 'message', op: 'match', value: 'x' }
    ]
  }),
  {
    mode: 'OR',
    conditions: [
      { field: 'message', op: 'contains', value: '%ASA-' },
      { field: 'app', op: 'startswith', value: 'snmp' },
      { field: 'source', op: 'endswith', value: '.log' }
    ]
  },
  '保存时应丢弃存在性、空字段和正则操作符'
);
assert.equal(
  getExtractorConditionSummary({ mode: 'AND', conditions: [] }),
  null,
  '空条件在列表中应显示为无附加条件'
);
assert.deepEqual(
  getExtractorConditionSummary({
    mode: 'OR',
    conditions: [{ field: 'hostname', op: 'startswith', value: 'core-' }]
  }),
  {
    mode: 'OR',
    items: [{ field: 'hostname', op: 'startswith', value: 'core-' }]
  },
  '列表摘要应保留条件关系和比较值'
);

assert.match(
  drawerSource,
  /<Form\.List name="conditions">/,
  '提取器表单应展示附加条件编辑'
);
assert.match(
  drawerSource,
  /title: t\('log\.extractor\.condition'\)/,
  '列表应展示附加条件列'
);
assert.match(
  drawerSource,
  /normalizeExtractorCondition\(\{[\s\S]{0,80}mode: values\.condition_mode/,
  '保存和预览必须使用表单里正在编辑的条件，而不是旧规则上的空条件'
);
assert.match(
  drawerSource,
  /name=\{\[field\.name, 'value'\]\}/,
  '六个可编辑操作符都必须填写比较值'
);
assert.doesNotMatch(
  drawerSource,
  /ExtractorConditionValueInput/,
  '编辑器不再为存在性条件隐藏比较值'
);
assert.match(
  drawerSource,
  /extractorUsesSingleTargetField\(extractorType\)/,
  '目标属性应按提取类型显隐，而不是六种类型共用一格'
);
assert.match(
  drawerSource,
  /extractorRequiresTargetField\(extractorType\)/,
  '只有单值动作才把目标属性设为必填'
);
assert.match(
  drawerSource,
  /extractorUsesSingleTargetField\(values\.extractor_type\)[\s\S]{0,80}\? values\.target_field \|\| null[\s\S]{0,40}: null/,
  '正则和键值对应强制清空单一目标属性，避免沿用表单脏值'
);
assert.match(
  drawerSource,
  /log\.extractor\.regexNamedGroupHint/,
  '正则提取应说明命名捕获组就是字段名'
);
assert.match(
  drawerSource,
  /className="min-w-0 flex-1"/,
  '样本下拉应收缩，给读取样本和运行预览留出同一行空间'
);
assert.match(
  drawerSource,
  /ExtractorPreviewResult/,
  '运行预览应展示状态和写出字段，而不是只丢一份原始 JSON'
);
assert.match(
  drawerSource,
  /log\.extractor\.previewEffect/,
  '预览应单独列出相对样本的字段变化'
);
assert.match(
  drawerSource,
  /label: t\(extractorTypeLabelKey\(value\)\)/,
  '类型下拉应使用双语标签'
);
assert.equal(extractorTypeLabelKey('copy'), 'log.extractor.typeCopy');
assert.equal(extractorTypeLabelKey('regex_replace'), 'log.extractor.typeRegexReplace');
assert.equal(
  extractorConditionOperatorLabelKey('startswith'),
  'log.extractor.conditionOpStartsWith'
);
assert.equal(
  extractorConditionOperatorLabelKey('endswith'),
  'log.extractor.conditionOpEndsWith'
);
for (const key of [
  'typeCopy',
  'typeSplit',
  'typeKv',
  'typeRegex',
  'typeRegexReplace',
  'typeJson',
  'regexNamedGroupHint',
  'kvMappingHint',
  'previewEffect',
  'previewAdded',
  'previewChanged',
  'previewRemoved',
  'previewUnchanged',
  'previewStatusSuccess',
  'previewStatusFailed',
  'popupBlocked',
  'createFromLog',
  'condition',
  'conditionHint',
  'conditionValidate',
  'conditionModeAnd',
  'conditionModeOr',
  'conditionOpEq',
  'conditionOpNe',
  'conditionOpContains',
  'conditionOpNotContains',
  'conditionOpStartsWith',
  'conditionOpEndsWith',
  'addCondition',
  'noCondition'
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
  searchPageSource,
  /storeExtractorCreateHandoff\(\{\s*event,\s*source_field\s*\}\)/,
  '搜索页创建提取器应写入可跨新窗口读取的样本和源属性'
);
assert.match(
  searchPageSource,
  /window\.open\('about:blank', '_blank'\)/,
  '搜索页创建提取器应在用户点击时先打开新窗口，避免 await 后被拦截'
);
assert.match(
  searchPageSource,
  /popup\.location\.replace\([\s\S]{0,80}build(Type|Instance)ExtractorPath/,
  '权限校验通过后再把新窗口导航到提取器页'
);
assert.doesNotMatch(
  searchPageSource,
  /router\.push\(build(Type|Instance)ExtractorPath/,
  '搜索页创建提取器不应再占用当前搜索页'
);
const searchTableSource = readFileSync(
  new URL('../src/app/log/(pages)/search/searchTable.tsx', import.meta.url),
  'utf8'
);
assert.match(
  searchTableSource,
  /onCreateExtractor\(record, String\(item\.label\)\)/,
  '创建提取器应放在属性操作栏并带上当前属性'
);
assert.doesNotMatch(
  searchTableSource,
  /collector[\s\S]{0,400}log\.extractor\.createFromLog/,
  '展开行头部不应再保留创建提取器入口'
);
assert.match(
  typeExtractorPageSource,
  /consumeExtractorCreateHandoff\(searchParams\.get\('handoff'\)\)/,
  '类型级创建页应按一次性 handoff 读取搜索页写入的样本'
);
assert.match(
  typeExtractorPageSource,
  /consumeExtractorCreateSample\(\{\s*kind: 'type'/,
  '类型级创建页可回退读取同页跳转留下的样本'
);
assert.match(
  receivePageSource,
  /list\.can_operate === true/,
  '日志接收页不能在实例不在当前表格页时默认放开编辑'
);
assert.match(
  receivePageSource,
  /consumeExtractorCreateHandoff\(searchParams\.get\('handoff'\)\)/,
  '实例级创建抽屉应按一次性 handoff 读取搜索页写入的样本'
);
assert.match(
  receivePageSource,
  /consumeExtractorCreateSample\(\{\s*kind: 'instance'/,
  '实例级创建抽屉可回退读取同页跳转留下的样本'
);

console.log('log-extractor-interaction tests passed');
