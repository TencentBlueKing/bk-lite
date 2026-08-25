import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { normalizeParamInputChangeValue } from '../src/app/ops-analysis/components/normalizeParamInputChangeValue';
import {
  buildWidgetRequestParams,
  processDataSourceParams,
  sanitizeUnifiedFilterDefinition,
} from '../src/app/ops-analysis/utils/widgetDataTransform';
import { coerceValueForMultiple } from '../src/app/ops-analysis/utils/stringParamMultipleMigrate';
import type { FilterValue, UnifiedFilterDefinition } from '../src/app/ops-analysis/types/dashBoard';

const departmentFilter: UnifiedFilterDefinition = {
  id: 'department__string',
  key: 'department',
  name: '使用部门',
  type: 'string',
  order: 0,
  enabled: true,
};

assert.equal(
  normalizeParamInputChangeValue({ target: { value: '数据部' } }),
  '数据部',
);
assert.equal(normalizeParamInputChangeValue('数据部'), '数据部');
assert.equal(normalizeParamInputChangeValue(''), '');
assert.equal(normalizeParamInputChangeValue(1), 1);
assert.equal(normalizeParamInputChangeValue(null), null);

const buildRequest = (department: string | null) =>
  processDataSourceParams({
    sourceParams: [
      {
        name: 'department',
        alias_name: '使用部门',
        type: 'string',
        filterType: 'filter',
        value: null,
      },
    ],
    unifiedFilterValues: { [departmentFilter.id]: department },
    filterBindings: { [departmentFilter.id]: true },
    filterDefinitions: [departmentFilter],
  });

assert.deepEqual(buildRequest('数据部'), { department: '数据部' });
assert.deepEqual(buildRequest(''), {});
assert.deepEqual(buildRequest(null), {});

const timeFilter: UnifiedFilterDefinition = {
  id: 'time__timeRange',
  key: 'time',
  name: '时间范围',
  type: 'timeRange',
  order: 0,
  enabled: true,
};
const sourceTopRequest = buildWidgetRequestParams({
  config: {
    dataSourceParams: [
      { name: 'limit', type: 'string', value: '5', filterType: 'params' },
      { name: 'time', type: 'timeRange', value: 10080, filterType: 'filter' },
    ],
  },
  unifiedFilterValues: {
    [timeFilter.id]: ['2026-07-28T00:00:00.000Z', '2026-08-04T00:00:00.000Z'],
  },
  filterBindings: { [timeFilter.id]: true },
  filterDefinitions: [timeFilter],
});
assert.equal(sourceTopRequest.limit, '5');
assert.deepEqual(sourceTopRequest.time, [
  '2026-07-28T00:00:00.000Z',
  '2026-08-04T00:00:00.000Z',
]);

const yamlPresetTime = { selectValue: 15, rangePickerVaule: null };
const presetTimeRequest = buildWidgetRequestParams({
  config: {
    dataSourceParams: [
      { name: 'time', type: 'timeRange', value: 360, filterType: 'filter' },
    ],
  },
  unifiedFilterValues: {
    [timeFilter.id]: yamlPresetTime,
  },
  filterBindings: { [timeFilter.id]: true },
  filterDefinitions: [timeFilter],
});
assert.deepEqual(
  presetTimeRequest.time,
  { selectValue: 15 },
  '筛选栏 {selectValue:15} 必须按统一协议发给网关，而不是组件默认 360 或前端回落 7 天',
);

const editorSource = readFileSync(
  new URL('../src/app/ops-analysis/components/paramInputConfigEditor.tsx', import.meta.url),
  'utf8',
);
const controlSource = readFileSync(
  new URL('../src/app/ops-analysis/components/paramInputControl.tsx', import.meta.url),
  'utf8',
);
const filterBindingPanelSource = readFileSync(
  new URL('../src/app/ops-analysis/components/unifiedFilter/filterBindingPanel.tsx', import.meta.url),
  'utf8',
);

assert.match(
  filterBindingPanelSource,
  /<Switch[\s\S]{0,160}checked=\{canBind && isEnabled\}[\s\S]{0,80}disabled/,
  'filter 类型参数应仅展示当前画布联动状态，开关不可关闭',
);
assert.doesNotMatch(
  filterBindingPanelSource,
  /onChange=\{\(checked\).*handleBindingChange/,
  'filter 联动开关不应再向组件层暴露关闭交互',
);

assert.match(
  editorSource,
  /value: 'table'/,
  'select 控件应允许配置表格勾选模式',
);
assert.match(
  editorSource,
  /void fetchDynamicPreview\(dynamicSourceId\);/,
  '选择动态数据源后应自动拉取预览字段，不能要求用户再手动刷新',
);
assert.match(
  controlSource,
  /picker === 'table'/,
  '运行时 select 应按 picker=table 打开表格勾选，而不是只有下拉',
);
assert.match(
  editorSource,
  /setDynamicPreview\(extractDataSourceItems\(data\)\.slice\(0, 5\)\)/,
  '动态选项预览最多展示前 5 条样本数据',
);
assert.match(
  editorSource,
  /dataSource=\{dynamicPreview\}/,
  '动态选项预览应在数据加载后展示样本数据，辅助用户选择字段',
);
assert.match(
  editorSource,
  /columns=\{dynamicPreviewColumns\}/,
  '动态选项预览应展示全字段表格列',
);
assert.match(
  editorSource,
  /scroll=\{\{ x: 'max-content' \}\}/,
  '动态选项预览字段较多时应支持横向滚动',
);
assert.match(
  editorSource,
  /const \[form\] = Form\.useForm\(\)/,
  '动态选项必填校验应使用 Ant Design Form 实例',
);
assert.match(
  editorSource,
  /await form\.validateFields\(\[\s*'dynamicSourceId',\s*'dynamicValueField',\s*'dynamicLabelField',\s*\]\)/,
  '动态选项确认时应使用 Form 原生校验',
);
assert.match(
  editorSource,
  /form\.setFieldValue\('dynamicSourceId', resolvedSourceId\)/,
  'sourceRef 解析出数据源后应同步 Form 字段，保证默认绑定可回显并通过校验',
);
assert.match(
  editorSource,
  /sourceRef[\s\S]{0,240}selectedSource\.rest_api/,
  '动态选项保存时应优先保留 rest_api 引用，避免跨环境数据源 ID 不一致',
);
assert.match(
  editorSource,
  /name="dynamicSourceId"[\s\S]*?rules=\{\[/,
  '动态数据源缺失应由表单项原生校验提示',
);
assert.match(
  editorSource,
  /name="dynamicValueField"[\s\S]*?rules=\{\[/,
  '动态值字段缺失应由表单项原生校验提示',
);
assert.match(
  editorSource,
  /name="dynamicLabelField"[\s\S]*?rules=\{\[/,
  '动态展示字段缺失应由表单项原生校验提示',
);
assert.doesNotMatch(
  editorSource,
  /dynamicFieldErrors/,
  '动态选项必填校验不应使用手写错误状态',
);
assert.doesNotMatch(
  editorSource,
  /message\.warning\(t\('paramInput\.dynamic\.incomplete'\)\)/,
  '动态选项必填校验不应再使用全局提示',
);
assert.doesNotMatch(
  controlSource,
  /state\.status !== 'success' \|\| state\.options\.length === 0\) return <>\{renderFallback\(\)\}<\/>/,
  '下拉/单选配置已确认后，即使动态选项为空也不能回退成普通输入框',
);

const hostFilter: UnifiedFilterDefinition = {
  id: 'instance_ids__string',
  key: 'instance_ids',
  name: '主机',
  type: 'string',
  order: 0,
  enabled: true,
  inputConfig: {
    control: 'select',
    multiple: true,
    optionsSource: {
      type: 'static',
      staticItems: [],
    },
  },
};

const buildHostRequest = (hosts: FilterValue) =>
  processDataSourceParams({
    sourceParams: [
      {
        name: 'instance_ids',
        alias_name: '主机',
        type: 'string',
        filterType: 'filter',
        value: null,
        inputConfig: {
          control: 'select',
          multiple: true,
          optionsSource: {
            type: 'static',
            staticItems: [],
          },
        },
      },
    ],
    unifiedFilterValues: { [hostFilter.id]: hosts },
    filterBindings: { [hostFilter.id]: true },
    filterDefinitions: [hostFilter],
  });

assert.deepEqual(
  buildHostRequest(['host-a', 'host-b']),
  { instance_ids: ['host-a', 'host-b'] },
  'string + multiple 多选应把 ID 数组写入绑定组件请求',
);
assert.deepEqual(
  buildHostRequest(['host-a']),
  { instance_ids: ['host-a'] },
  'string + multiple 单选也应传单元素数组，不能拆成标量',
);
assert.deepEqual(buildHostRequest([]), {}, '空数组应省略参数，不能传空列表');
assert.deepEqual(buildHostRequest(null), {}, '未选择应省略参数');

assert.deepEqual(
  processDataSourceParams({
    sourceParams: [
      {
        name: 'instance_ids',
        alias_name: '主机',
        type: 'string',
        filterType: 'filter',
        value: null,
        inputConfig: {
          control: 'select',
          multiple: true,
          optionsSource: {
            type: 'static',
            staticItems: [],
          },
        },
      },
      {
        name: 'department',
        alias_name: '使用部门',
        type: 'string',
        filterType: 'filter',
        value: null,
      },
    ],
    unifiedFilterValues: {
      [hostFilter.id]: ['host-a'],
      [departmentFilter.id]: '数据部',
    },
    filterBindings: {
      [hostFilter.id]: true,
      [departmentFilter.id]: true,
    },
    filterDefinitions: [hostFilter, departmentFilter],
  }),
  { instance_ids: ['host-a'], department: '数据部' },
  'string 筛选仍传标量，不能和 multiple 字符串混绑成同一种值',
);

const scalarHostFilter: UnifiedFilterDefinition = {
  id: 'instance_ids__string',
  key: 'instance_ids',
  name: '主机',
  type: 'string',
  order: 0,
  enabled: true,
  inputConfig: {
    control: 'select',
    multiple: false,
    optionsSource: {
      type: 'static',
      staticItems: [],
    },
  },
};

assert.deepEqual(
  processDataSourceParams({
    sourceParams: [
      {
        name: 'instance_ids',
        alias_name: '主机',
        type: 'string',
        filterType: 'filter',
        value: null,
      },
    ],
    unifiedFilterValues: { [scalarHostFilter.id]: 'host-a' },
    filterBindings: { [scalarHostFilter.id]: true },
    filterDefinitions: [scalarHostFilter],
  }),
  { instance_ids: 'host-a' },
  '关闭 multiple 后请求必须发标量，不得暗中回数组',
);

{
  const residualArray = ['h1', 'h2'];
  assert.deepEqual(
    processDataSourceParams({
      sourceParams: [
        {
          name: 'instance_ids',
          alias_name: '主机',
          type: 'string',
          filterType: 'filter',
          value: null,
          inputConfig: {
            control: 'select',
            multiple: true,
            optionsSource: { type: 'static', staticItems: [] },
          },
        },
      ],
      unifiedFilterValues: { [hostFilter.id]: residualArray },
      filterBindings: { [hostFilter.id]: true },
      filterDefinitions: [hostFilter],
    }),
    { instance_ids: ['h1', 'h2'] },
    'multiple=true 时残留数组请求仍为数组',
  );

  assert.deepEqual(
    processDataSourceParams({
      sourceParams: [
        {
          name: 'instance_ids',
          alias_name: '主机',
          type: 'string',
          filterType: 'filter',
          value: null,
        },
      ],
      unifiedFilterValues: { [scalarHostFilter.id]: residualArray },
      filterBindings: { [scalarHostFilter.id]: true },
      filterDefinitions: [scalarHostFilter],
    }),
    { instance_ids: 'h1' },
    '关闭 multiple 后即使 applied 残留数组，请求也只能是首元素标量',
  );

  assert.deepEqual(
    processDataSourceParams({
      sourceParams: [
        {
          name: 'instance_ids',
          alias_name: '主机',
          type: 'string',
          filterType: 'filter',
          value: null,
        },
      ],
      unifiedFilterValues: { [scalarHostFilter.id]: [] },
      filterBindings: { [scalarHostFilter.id]: true },
      filterDefinitions: [scalarHostFilter],
    }),
    {},
    '关闭 multiple 后清空应省略参数',
  );

  assert.deepEqual(
    processDataSourceParams({
      sourceParams: [
        {
          name: 'instance_ids',
          alias_name: '主机',
          type: 'string',
          filterType: 'params',
          value: null,
          inputConfig: {
            control: 'select',
            multiple: false,
            optionsSource: { type: 'static', staticItems: [] },
          },
        },
      ],
      userParams: { instance_ids: ['h1', 'h2'] },
    }),
    { instance_ids: 'h1' },
    '组件私有参数关闭 multiple 后残留数组也必须降为标量',
  );

  assert.deepEqual(
    processDataSourceParams({
      sourceParams: [
        {
          name: 'instance_ids',
          alias_name: '主机',
          type: 'string',
          filterType: 'params',
          value: null,
          inputConfig: {
            control: 'select',
            multiple: true,
            optionsSource: { type: 'static', staticItems: [] },
          },
        },
      ],
      userParams: { instance_ids: ['h1', 'h2'] },
    }),
    { instance_ids: ['h1', 'h2'] },
    '组件私有参数开启 multiple 时请求为数组',
  );

  assert.deepEqual(
    processDataSourceParams({
      sourceParams: [
        {
          name: 'instance_ids',
          alias_name: '主机',
          type: 'string',
          filterType: 'filter',
          value: null,
        },
      ],
      unifiedFilterValues: { [scalarHostFilter.id]: residualArray },
      filterBindings: { [scalarHostFilter.id]: true },
      filterDefinitions: [scalarHostFilter],
    }),
    { instance_ids: 'h1' },
    'instance_ids 不得因特殊 key 暗中恢复为数组',
  );
}

assert.match(
  controlSource,
  /mode=\{inputConfig\.multiple \? 'multiple' : undefined\}/,
  '下拉控件应按 inputConfig.multiple 进入多选',
);
assert.match(
  editorSource,
  /t\('paramInput\.multiple'\)/,
  '参数输入配置应提供多选开关',
);
assert.match(
  editorSource,
  /disabled=\{componentSwitch\}/,
  '已开 componentSwitch 时应禁用多选',
);
assert.match(
  editorSource,
  /multiple[\s\S]{0,80}disabled/,
  'multiple 与 componentSwitch 应互斥禁用',
);

assert.deepEqual(
  sanitizeUnifiedFilterDefinition({
    ...hostFilter,
    inputMode: 'select',
    defaultValue: ['host-a', 'host-b'],
    inputConfig: {
      control: 'select',
      multiple: true,
      optionsSource: {
        type: 'static',
        staticItems: [
          { label: 'A', value: 'host-a' },
          { label: 'B', value: 'host-b' },
        ],
      },
    },
  }).defaultValue,
  ['host-a', 'host-b'],
  'string + multiple 默认值应保留数组，不能因对象比较失败被清掉',
);

assert.equal(
  coerceValueForMultiple(['host-a', 'host-b'], false),
  'host-a',
  '关多选时多值应静默保留第一个',
);
assert.deepEqual(
  coerceValueForMultiple('host-a', true),
  ['host-a'],
  '开多选时标量应升为单元素数组',
);

console.log('ops analysis unified filter input tests passed');
