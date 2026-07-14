import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import type { ParamItem } from '../src/app/ops-analysis/types/dataSource';
import { addConfiguredScreenWidget } from '../src/app/ops-analysis/(pages)/view/screen/utils/layout';
import { buildValueConfig } from '../src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils';
import { buildWidgetSubmitConfig } from '../src/app/ops-analysis/components/widgetConfig/utils/submitConfig';
import {
  buildRuntimeParamControlChartTypePatch,
  buildWidgetRuntimeInteractionProps,
  buildWidgetRuntimeParams,
  getRuntimeParamSegmentedOptions,
  getWidgetRuntimeParamCandidates,
  hasRuntimeParamSegmentedValue,
  isTopNContentReady,
  resolveTopNContentState,
  resolveRuntimeParamInitialValue,
  resolveWidgetRuntimeAuthorizationParams,
  validateRuntimeParamControl,
} from '../src/app/ops-analysis/utils/runtimeParamControl';
import {
  buildWidgetExtraParams,
  buildWidgetRequestParams,
  buildWidgetRequestSignatureParams,
  createWidgetRequestHistory,
  decideWidgetRequest,
  hasActiveWidgetRuntimeParams,
  shouldShowInitialWidgetLoading,
} from '../src/app/ops-analysis/utils/widgetDataTransform';
import * as runtimeParamControlModule from '../src/app/ops-analysis/utils/runtimeParamControl';

type ShouldClearRuntimeParamControl = (
  params: ParamItem[] | undefined,
  dataSourceResolved: boolean,
  enabled: boolean | undefined,
  hasControl: boolean,
) => boolean;

const shouldClearRuntimeParamControl = (
  runtimeParamControlModule as Record<string, unknown>
).shouldClearUnavailableRuntimeParamControl;
assert.equal(typeof shouldClearRuntimeParamControl, 'function');
const shouldClear = shouldClearRuntimeParamControl as ShouldClearRuntimeParamControl;

const sourceParams: ParamItem[] = [
  {
    name: 'department',
    alias_name: '部门',
    type: 'string',
    value: '',
    filterType: 'filter',
  },
  {
    name: 'group_by',
    alias_name: '排行主体',
    type: 'string',
    value: 'instance_type',
    filterType: 'widget',
  },
  {
    name: '   ',
    alias_name: '无效参数',
    type: 'string',
    value: '',
    filterType: 'widget',
  },
];

assert.equal(shouldClear([], false, true, true), false);
assert.equal(shouldClear([], true, true, true), true);
assert.equal(shouldClear(sourceParams, true, true, true), false);
assert.equal(shouldClear([], true, false, false), false);

assert.deepEqual(buildRuntimeParamControlChartTypePatch('topN'), {});
assert.deepEqual(buildRuntimeParamControlChartTypePatch('bar'), {
  runtimeParamControlEnabled: false,
  runtimeParamControl: undefined,
});

const widgetConfigSource = readFileSync(
  new URL(
    '../src/app/ops-analysis/components/widgetConfig.tsx',
    import.meta.url,
  ),
  'utf8',
);
assert.match(
  widgetConfigSource,
  /\.\.\.buildRuntimeParamControlChartTypePatch\(newChartType\)/,
);

const editorSource = readFileSync(
  new URL(
    '../src/app/ops-analysis/components/widgetConfig/sections/runtimeParamControlEditor.tsx',
    import.meta.url,
  ),
  'utf8',
);
assert.match(editorSource, /aria-label=\{t\('dashboard\.runtimeParamOptionMoveUp'\)\}/);
assert.match(editorSource, /aria-label=\{t\('dashboard\.runtimeParamOptionMoveDown'\)\}/);
assert.match(editorSource, /aria-label=\{t\('dashboard\.runtimeParamOptionDelete'\)\}/);

for (const localeName of ['zh', 'en']) {
  const locale = JSON.parse(
    readFileSync(
      new URL(`../src/app/ops-analysis/locales/${localeName}.json`, import.meta.url),
      'utf8',
    ),
  );
  assert.equal(typeof locale.dashboard.runtimeParamOptionMoveUp, 'string');
  assert.equal(typeof locale.dashboard.runtimeParamOptionMoveDown, 'string');
  assert.equal(typeof locale.dashboard.runtimeParamOptionDelete, 'string');
}

const control = {
  paramName: 'group_by',
  controlType: 'segmented' as const,
  defaultValue: 'department',
  options: [
    { label: '对象类型', value: 'instance_type' },
    { label: '使用部门', value: 'department' },
  ],
};

assert.deepEqual(getRuntimeParamSegmentedOptions(control), [
  { label: '对象类型', value: 'instance_type' },
  { label: '使用部门', value: 'department' },
]);
assert.deepEqual(getRuntimeParamSegmentedOptions(undefined), []);
assert.equal(hasRuntimeParamSegmentedValue(control, 'department'), true);
assert.equal(hasRuntimeParamSegmentedValue(control, 'unknown'), false);
assert.equal(hasRuntimeParamSegmentedValue(control, undefined), false);
assert.equal(
  hasRuntimeParamSegmentedValue(
    {
      ...control,
      defaultValue: 1,
      options: [{ label: '数字一', value: 1 }],
    },
    '1',
  ),
  false,
);

const runtimeInteractionProps = {
  runtimeParamValue: 'department',
  onRuntimeParamChange: (_value: string | number) => undefined,
  errorMessage: 'request failed',
};
assert.deepEqual(
  buildWidgetRuntimeInteractionProps('topN', runtimeInteractionProps),
  runtimeInteractionProps,
);
assert.deepEqual(
  buildWidgetRuntimeInteractionProps('bar', runtimeInteractionProps),
  {},
);
assert.deepEqual(
  buildWidgetRuntimeInteractionProps(undefined, runtimeInteractionProps),
  {},
);

assert.equal(
  resolveTopNContentState({
    loading: true,
    errorMessage: 'request failed',
    hasRows: true,
  }),
  'loading',
);
assert.equal(
  resolveTopNContentState({
    loading: false,
    errorMessage: 'request failed',
    hasRows: true,
  }),
  'error',
);
assert.equal(
  resolveTopNContentState({ loading: false, hasRows: false }),
  'empty',
);
assert.equal(
  resolveTopNContentState({ loading: false, hasRows: true }),
  'rows',
);
assert.equal(isTopNContentReady('loading'), false);
assert.equal(isTopNContentReady('error'), false);
assert.equal(isTopNContentReady('empty'), false);
assert.equal(isTopNContentReady('rows'), true);

const submitResult = buildWidgetSubmitConfig({
  values: {
    name: '费用分布',
    chartType: 'topN',
    dataSource: 34,
    dataSourceParams: sourceParams,
    topNLabelField: 'key',
    topNValueField: 'total_cost',
    runtimeParamControlEnabled: true,
    runtimeParamControl: control,
  },
  chartType: 'topN',
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: [],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [],
  filterFields: [],
  actions: [],
});
assert.deepEqual(submitResult.config?.runtimeParamControl, control);
assert.equal(
  'runtimeParamControlEnabled' in (submitResult.config || {}),
  false,
);
assert.equal(submitResult.config?.topNValueField, 'total_cost');

const screenResult = addConfiguredScreenWidget(
  {
    viewport: { width: 1920, height: 1080 },
    items: [],
    filters: [],
    decorations: {},
  },
  submitResult.config!,
);
assert.deepEqual(
  screenResult.items[0]?.valueConfig?.runtimeParamControl,
  control,
);

const topologyResult = buildValueConfig({
  name: '费用分布',
  chartType: 'topN',
  dataSource: 34,
  dataSourceParams: sourceParams,
  topNLabelField: 'key',
  topNValueField: 'total_cost',
  runtimeParamControl: control,
});
assert.deepEqual(topologyResult.runtimeParamControl, control);

assert.deepEqual(
  getWidgetRuntimeParamCandidates(sourceParams).map((item) => item.name),
  ['group_by'],
);

assert.equal(validateRuntimeParamControl(control, sourceParams), null);
assert.equal(
  validateRuntimeParamControl(undefined, sourceParams),
  'missingParam',
);
assert.equal(
  validateRuntimeParamControl(
    { ...control, paramName: 'unknown' },
    sourceParams,
  ),
  'missingParam',
);
assert.equal(
  validateRuntimeParamControl({ ...control, options: [] }, sourceParams),
  'emptyOptions',
);
assert.equal(
  validateRuntimeParamControl(
    { ...control, options: [{ label: '  ', value: 'instance_type' }] },
    sourceParams,
  ),
  'emptyLabel',
);
assert.equal(
  validateRuntimeParamControl(
    { ...control, options: [{ label: '对象类型', value: '  ' }] },
    sourceParams,
  ),
  'emptyValue',
);
assert.equal(
  validateRuntimeParamControl(
    { ...control, options: [{ label: '对象类型', value: Number.NaN }] },
    sourceParams,
  ),
  'emptyValue',
);
assert.equal(
  validateRuntimeParamControl(
    {
      ...control,
      options: [
        { label: '对象类型', value: 'instance_type' },
        { label: '重复对象类型', value: 'instance_type' },
      ],
    },
    sourceParams,
  ),
  'duplicateValue',
);
assert.equal(
  validateRuntimeParamControl(
    { ...control, defaultValue: 'user' },
    sourceParams,
  ),
  'invalidDefault',
);
assert.equal(
  validateRuntimeParamControl(
    { ...control, paramName: 'unknown', options: [] },
    sourceParams,
  ),
  'missingParam',
);
assert.equal(
  validateRuntimeParamControl(
    {
      ...control,
      defaultValue: 'unknown',
      options: [
        { label: '  ', value: '  ' },
        { label: 'duplicate', value: '  ' },
      ],
    },
    sourceParams,
  ),
  'emptyLabel',
);
assert.equal(
  validateRuntimeParamControl(
    {
      ...control,
      defaultValue: 'unknown',
      options: [
        { label: 'invalid one', value: '  ' },
        { label: 'invalid two', value: '  ' },
      ],
    },
    sourceParams,
  ),
  'emptyValue',
);

assert.equal(
  resolveRuntimeParamInitialValue(control, sourceParams),
  'department',
);
assert.equal(
  resolveRuntimeParamInitialValue(
    { ...control, defaultValue: 'unknown' },
    sourceParams,
  ),
  'instance_type',
);
assert.equal(
  resolveRuntimeParamInitialValue(
    {
      ...control,
      defaultValue: 'unknown',
      options: [
        { label: '使用部门', value: 'department' },
        { label: '申请人', value: 'applicant' },
      ],
    },
    sourceParams,
  ),
  'department',
);
assert.equal(
  resolveRuntimeParamInitialValue(
    { ...control, paramName: 'unknown' },
    sourceParams,
  ),
  undefined,
);
assert.equal(
  resolveRuntimeParamInitialValue({ ...control, options: [] }, sourceParams),
  undefined,
);
assert.equal(
  resolveRuntimeParamInitialValue(
    { ...control, options: [{ label: ' ', value: 'instance_type' }] },
    sourceParams,
  ),
  undefined,
);
assert.equal(
  resolveRuntimeParamInitialValue(
    { ...control, options: [{ label: 'invalid', value: '  ' }] },
    sourceParams,
  ),
  undefined,
);
assert.equal(
  resolveRuntimeParamInitialValue(
    {
      ...control,
      options: [
        { label: 'one', value: 'instance_type' },
        { label: 'duplicate', value: 'instance_type' },
      ],
    },
    sourceParams,
  ),
  undefined,
);
assert.equal(
  resolveRuntimeParamInitialValue(
    { ...control, options: [{ label: 'invalid number', value: Number.NaN }] },
    sourceParams,
  ),
  undefined,
);

assert.deepEqual(
  buildWidgetRuntimeParams(control, 'instance_type', sourceParams),
  { group_by: 'instance_type' },
);
assert.deepEqual(
  buildWidgetRuntimeParams(control, 'unknown', sourceParams),
  {},
);
assert.deepEqual(
  buildWidgetRuntimeParams(
    { ...control, paramName: 'unknown' },
    'department',
    sourceParams,
  ),
  {},
);
assert.deepEqual(
  buildWidgetRuntimeParams(control, 'department', [
    { ...sourceParams[1], filterType: 'params' },
  ]),
  {},
);

const staleWidgetSnapshot = sourceParams;
const currentParamsWithoutWidget: ParamItem[] = [
  { ...sourceParams[1], filterType: 'params' },
];
const currentRuntimeAuthorizationParams =
  resolveWidgetRuntimeAuthorizationParams(currentParamsWithoutWidget);
assert.equal(
  resolveRuntimeParamInitialValue(control, currentRuntimeAuthorizationParams),
  undefined,
);
const revokedRuntimeParams = buildWidgetRuntimeParams(
  control,
  'department',
  currentRuntimeAuthorizationParams,
);
assert.deepEqual(revokedRuntimeParams, {});
assert.equal(hasActiveWidgetRuntimeParams('topN', revokedRuntimeParams), false);
assert.deepEqual(resolveWidgetRuntimeAuthorizationParams(undefined), []);
assert.equal(
  buildWidgetRequestParams({
    config: {
      dataSourceParams: [
        {
          name: 'page_size',
          alias_name: 'page size',
          type: 'number',
          value: 50,
          filterType: 'params',
        },
      ],
    },
    dataSource: {
      params: [
        {
          name: 'page_size',
          alias_name: 'page size',
          type: 'number',
          value: 20,
          filterType: 'params',
        },
      ],
    },
  }).page_size,
  50,
);

const widgetDataRendererSource = readFileSync(
  new URL(
    '../src/app/ops-analysis/components/widgetDataRenderer.tsx',
    import.meta.url,
  ),
  'utf8',
);
const dashboardCanvasSource = readFileSync(
  new URL(
    '../src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardCanvas.tsx',
    import.meta.url,
  ),
  'utf8',
);
const widgetRendererSource = readFileSync(
  new URL('../src/app/ops-analysis/components/widgetRenderer.tsx', import.meta.url),
  'utf8',
);
const headerLayoutTopNSource = readFileSync(
  new URL('../src/app/ops-analysis/components/widgets/comTopN.tsx', import.meta.url),
  'utf8',
);
const runtimeParamSegmentedSource = readFileSync(
  new URL(
    '../src/app/ops-analysis/components/widgets/runtimeParamSegmented.tsx',
    import.meta.url,
  ),
  'utf8',
);
assert.match(dashboardCanvasSource, /WidgetHeaderRuntimeSlotProvider/);
assert.match(dashboardCanvasSource, /ref=\{runtimeSlotRef\}/);
assert.match(dashboardCanvasSource, /max-w-\[70%\]/);
assert.match(dashboardCanvasSource, /overflow-x-auto/);
assert.match(widgetDataRendererSource, /createPortal/);
assert.match(widgetDataRendererSource, /useWidgetHeaderRuntimeSlot/);
assert.match(widgetDataRendererSource, /runtimeParamControlPlacement/);
assert.match(widgetRendererSource, /runtimeParamControlPlacement/);
assert.match(
  headerLayoutTopNSource,
  /runtimeParamControlPlacement !== ['"]header['"]/,
);
assert.doesNotMatch(headerLayoutTopNSource, /<Segmented/);
assert.match(runtimeParamSegmentedSource, /getRuntimeParamSegmentedOptions/);
assert.match(runtimeParamSegmentedSource, /hasRuntimeParamSegmentedValue/);
assert.match(runtimeParamSegmentedSource, /className="min-w-max"/);
assert.match(
  runtimeParamSegmentedSource,
  /onChange=\{\(nextValue\) =>\s*onChange\?\.\(nextValue as RuntimeParamValue\)\}/,
);
assert.match(
  widgetDataRendererSource,
  /resolveWidgetRuntimeAuthorizationParams\(dataSource\?\.params\)/,
);
assert.doesNotMatch(
  widgetDataRendererSource,
  /resolveWidgetRuntimeAuthorizationParams\(config\?\.dataSourceParams\)/,
);
assert.deepEqual(staleWidgetSnapshot, sourceParams);

const storySource = readFileSync(
  new URL(
    '../src/app/ops-analysis/components/widgets/widgetShowcase.stories.tsx',
    import.meta.url,
  ),
  'utf8',
);
const cloudCostServiceSource = readFileSync(
  new URL(
    '../../server/apps/cmdb/services/cloud_cost/service.py',
    import.meta.url,
  ),
  'utf8',
);
assert.match(cloudCostServiceSource, /"user":\s*"applicant"/);
assert.match(storySource, /label:\s*['"]申请人['"],\s*value:\s*['"]user['"]/);
assert.doesNotMatch(
  storySource,
  /label:\s*['"]申请人['"],\s*value:\s*['"]applicant['"]/,
);

const runtimeParams = buildWidgetRuntimeParams(
  control,
  'department',
  sourceParams,
);
const requestConfig = { dataSource: 34, dataSourceParams: sourceParams };
const extraParams = buildWidgetExtraParams({
  namespaceId: 7,
  isTableLikeChart: false,
  tableQueryParams: { page: 3, page_size: 20 },
  runtimeParams,
});

assert.deepEqual(extraParams, {
  namespace_id: 7,
  group_by: 'department',
});
assert.equal(
  buildWidgetRequestParams({
    config: requestConfig,
    dataSource: { params: sourceParams },
    extraParams,
  }).group_by,
  'department',
);
assert.equal(
  buildWidgetRequestSignatureParams({
    config: requestConfig,
    dataSource: { params: sourceParams },
    extraParams,
  }).group_by,
  'department',
);

const tableExtraParams = buildWidgetExtraParams({
  namespaceId: 7,
  isTableLikeChart: true,
  tableQueryParams: {
    page: 3,
    page_size: 20,
    group_by: 'instance_type',
  },
  runtimeParams,
});
assert.deepEqual(tableExtraParams, {
  namespace_id: 7,
  page: 3,
  page_size: 20,
  group_by: 'department',
});
assert.deepEqual(
  buildWidgetRuntimeParams(control, 'user', sourceParams),
  {},
);
assert.deepEqual(
  buildWidgetRuntimeParams(undefined, 'department', sourceParams),
  {},
);
assert.deepEqual(
  buildWidgetRuntimeParams(control, undefined, sourceParams),
  {},
);
assert.deepEqual(
  buildWidgetRuntimeParams(
    { ...control, options: [{ label: 'invalid', value: '  ' }] },
    'department',
    sourceParams,
  ),
  {},
);
assert.deepEqual(
  buildWidgetRuntimeParams(
    {
      ...control,
      options: [
        { label: 'one', value: 'department' },
        { label: 'duplicate', value: 'department' },
      ],
    },
    'department',
    sourceParams,
  ),
  {},
);

const typedValueControl = {
  ...control,
  defaultValue: 1,
  options: [
    { label: '数字一', value: 1 },
    { label: '字符串一', value: '1' },
  ],
};
assert.equal(validateRuntimeParamControl(typedValueControl, sourceParams), null);
assert.equal(resolveRuntimeParamInitialValue(typedValueControl, sourceParams), 1);
assert.deepEqual(buildWidgetRuntimeParams(typedValueControl, 1, sourceParams), {
  group_by: 1,
});
assert.deepEqual(buildWidgetRuntimeParams(typedValueControl, '1', sourceParams), {
  group_by: '1',
});

const currentRequest = (signature: string) => ({
  requestEnabled: true,
  requestSignature: signature,
  hasRequestParams: true,
  hasRequestKey: true,
  filterSearchVersion: 0,
  namespaceSearchVersion: 0,
  reloadVersion: '0:0',
  tableQueryKey: '{}',
  hasEnabledFilterBindings: false,
  widgetUsesNamespace: false,
  isTableLikeChart: false,
});

let requestHistory = createWidgetRequestHistory(currentRequest('A'));
let requestDecision = decideWidgetRequest({
  history: requestHistory,
  current: currentRequest('A'),
  suppressInitialCacheFetch: true,
});
assert.equal(requestDecision.shouldFetch, false);
requestHistory = requestDecision.nextHistory;

requestDecision = decideWidgetRequest({
  history: requestHistory,
  current: currentRequest('B'),
  suppressInitialCacheFetch: false,
});
assert.equal(requestDecision.shouldFetch, true);
requestHistory = requestDecision.nextHistory;

requestDecision = decideWidgetRequest({
  history: requestHistory,
  current: currentRequest('A'),
  suppressInitialCacheFetch: false,
});
assert.equal(requestDecision.shouldFetch, true);

const secondInstanceHistory = createWidgetRequestHistory(currentRequest('A'));
const secondInstanceDecision = decideWidgetRequest({
  history: secondInstanceHistory,
  current: currentRequest('A'),
  suppressInitialCacheFetch: true,
});
assert.equal(secondInstanceDecision.shouldFetch, false);
assert.equal(secondInstanceHistory.hasRequested, false);
assert.equal(requestDecision.nextHistory.hasRequested, true);

assert.equal(
  shouldShowInitialWidgetLoading({
    loading: true,
    isTableLikeChart: false,
    hasRawPayload: false,
    hasSettledRequest: false,
  }),
  true,
);
assert.equal(
  shouldShowInitialWidgetLoading({
    loading: true,
    isTableLikeChart: false,
    hasRawPayload: false,
    hasSettledRequest: true,
  }),
  false,
);
assert.equal(hasActiveWidgetRuntimeParams('topN', runtimeParams), true);
assert.equal(
  hasActiveWidgetRuntimeParams(
    'topN',
    buildWidgetRuntimeParams(control, 'unknown', sourceParams),
  ),
  false,
);
assert.equal(hasActiveWidgetRuntimeParams('bar', runtimeParams), false);

const wrapperSource = readFileSync(
  new URL(
    '../src/app/ops-analysis/components/widgetDataRenderer.tsx',
    import.meta.url,
  ),
  'utf8',
);
assert.match(wrapperSource, /decideWidgetRequest\(/);
assert.match(wrapperSource, /suppressInitialCacheFetch/);
assert.match(wrapperSource, /hasSettledRequest/);
assert.match(wrapperSource, /hasActiveWidgetRuntimeParams\(chartType, runtimeParams\)/);
assert.match(wrapperSource, /shouldShowInitialWidgetLoading\(/);
assert.equal(
  (wrapperSource.match(/extraParams: requestExtraParams/g) || []).length,
  3,
);

const topNSource = readFileSync(
  new URL(
    '../src/app/ops-analysis/components/widgets/comTopN.tsx',
    import.meta.url,
  ),
  'utf8',
);
assert.match(topNSource, /resolveTopNContentState\(/);
assert.match(topNSource, /isTopNContentReady\(contentState\)/);
assert.match(topNSource, /showRuntimeParamControl \?/);
assert.match(topNSource, /<RuntimeParamSegmented/);
assert.match(topNSource, /className="min-h-0 flex-1">\{content\}/);
assert.match(topNSource, /topNValueField/);
assert.doesNotMatch(topNSource, /instance_count/);

const rendererSource = readFileSync(
  new URL(
    '../src/app/ops-analysis/components/widgetRenderer.tsx',
    import.meta.url,
  ),
  'utf8',
);
assert.match(rendererSource, /buildWidgetRuntimeInteractionProps\(/);
assert.match(rendererSource, /\{\.\.\.runtimeInteractionProps\}/);
assert.doesNotMatch(rendererSource, /runtimeParamValue=\{runtimeParamValue\}/);

const showcaseSource = readFileSync(
  new URL(
    '../src/app/ops-analysis/components/widgets/widgetShowcase.stories.tsx',
    import.meta.url,
  ),
  'utf8',
);
assert.match(showcaseSource, /TopNWithRuntimeDimension/);
assert.match(showcaseSource, /topNValueField: 'total_cost'/);
assert.match(showcaseSource, /onRuntimeParamChange=\{setRuntimeParamValue\}/);
const previewDefinition = showcaseSource.indexOf(
  'const TopNRuntimeDimensionPreview',
);
const demoDefinition = showcaseSource.indexOf(
  'const TopNWithRuntimeDimensionDemo',
);
assert.ok(previewDefinition >= 0);
assert.ok(demoDefinition > previewDefinition);
assert.match(
  showcaseSource.slice(previewDefinition, demoDefinition),
  /React\.useState/,
);
assert.doesNotMatch(
  showcaseSource.slice(demoDefinition, showcaseSource.indexOf('const Showcase')),
  /React\.useState/,
);
assert.equal(
  (
    showcaseSource
      .slice(demoDefinition, showcaseSource.indexOf('const Showcase'))
      .match(/<TopNRuntimeDimensionPreview/g) || []
  ).length,
  2,
);

console.log('ops analysis TopN runtime parameter tests passed');
