import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import type { ParamItem } from '../src/app/ops-analysis/types/dataSource';
import {
  buildComponentSwitchRuntimeParams,
  clearComponentParamSwitch,
  findComponentSwitchParams,
  getComponentSwitchCandidates,
  isComponentSwitchCandidate,
  reconcileComponentParamValue,
  reconcileComponentSwitchResult,
  resolveComponentSwitchRuntime,
  validateComponentParamSwitch,
  validateComponentSwitchDetails,
} from '../src/app/ops-analysis/utils/componentParamSwitch';
import {
  buildParamInputOptionsResultKey,
  createParamInputOptionsLoader,
  createParamInputOptionsNotifier,
} from '../src/app/ops-analysis/utils/paramInputOptionsLoader';
import { buildWidgetExtraParams, buildWidgetRequestSignatureParams } from '../src/app/ops-analysis/utils/widgetDataTransform';
import { buildWidgetSubmitConfig } from '../src/app/ops-analysis/components/widgetConfig/utils/submitConfig';
import { isTopNContentReady, resolveTopNContentState } from '../src/app/ops-analysis/utils/topNContentState';

const options = [
  { label: '数字一', value: 1 },
  { label: '字符一', value: '1' },
];
const switchParam: ParamItem = {
  name: 'group_by', alias_name: '排行维度', type: 'string', value: 'missing',
  filterType: 'params',
  inputConfig: {
    control: 'select',
    componentSwitch: true,
    optionsSource: { type: 'static', staticItems: options },
  },
};
const ordinaryParam: ParamItem = {
  name: 'keyword', alias_name: '关键字', type: 'string', value: '',
  filterType: 'params', inputConfig: { control: 'input' },
};

assert.deepEqual(getComponentSwitchCandidates([switchParam, ordinaryParam]), [switchParam]);
assert.deepEqual(findComponentSwitchParams([switchParam, ordinaryParam]), [switchParam]);
assert.equal(validateComponentParamSwitch([switchParam, ordinaryParam]), null);
assert.equal(validateComponentParamSwitch([switchParam, { ...switchParam, name: 'other' }]), 'multipleComponentSwitchParams');
assert.equal(reconcileComponentParamValue('1', options), '1');
assert.equal(reconcileComponentParamValue(1, options), 1);
assert.equal(reconcileComponentParamValue('missing', options), 1);
assert.equal(reconcileComponentParamValue('saved', []), 'saved');
assert.deepEqual(reconcileComponentSwitchResult(null, options), { value: 1, changed: true });
assert.deepEqual(reconcileComponentSwitchResult(undefined, options), { value: 1, changed: true });
assert.deepEqual(reconcileComponentSwitchResult(true, []), { value: true, changed: false });
assert.deepEqual(reconcileComponentSwitchResult([1, 2], []), { value: [1, 2], changed: false });
assert.deepEqual(reconcileComponentSwitchResult('1', options), { value: '1', changed: false });
assert.deepEqual(reconcileComponentSwitchResult(1, options), { value: 1, changed: false });
assert.deepEqual(buildComponentSwitchRuntimeParams(switchParam, '1', options), { group_by: '1' });
assert.deepEqual(buildComponentSwitchRuntimeParams(switchParam, 'missing', options), {});
assert.deepEqual(buildComponentSwitchRuntimeParams({ ...switchParam, name: ' ' }, '1', options), {});
assert.equal((clearComponentParamSwitch(switchParam).inputConfig as { componentSwitch?: boolean }).componentSwitch, undefined);
assert.equal(clearComponentParamSwitch(switchParam).inputConfig?.control, 'select');
assert.equal(isComponentSwitchCandidate(switchParam), true);
assert.equal(isComponentSwitchCandidate({ ...switchParam, filterType: 'fixed' }), false);
assert.equal(isComponentSwitchCandidate({ ...switchParam, type: 'number' }), false);
assert.equal(isComponentSwitchCandidate({ ...switchParam, inputConfig: { control: 'input' } }), false);
assert.equal(isComponentSwitchCandidate({ ...switchParam, inputConfig: { ...switchParam.inputConfig!, componentSwitch: false } as ParamItem['inputConfig'] }), false);
assert.deepEqual(validateComponentSwitchDetails([switchParam]), { valid: true, params: [switchParam] });
assert.deepEqual(validateComponentSwitchDetails([switchParam, { ...switchParam, name: 'region' }]), {
  valid: false,
  params: [switchParam, { ...switchParam, name: 'region' }],
});
const invalidInputConfig = { control: 'input', componentSwitch: true } as unknown as ParamItem['inputConfig'];
assert.equal((clearComponentParamSwitch({ ...switchParam, inputConfig: invalidInputConfig }).inputConfig as { componentSwitch?: boolean }).componentSwitch, undefined);

const resolvedRuntime = resolveComponentSwitchRuntime('topN', switchParam, options, 'missing');
assert.deepEqual(resolvedRuntime, { value: 1, params: { group_by: 1 } });
assert.deepEqual(resolveComponentSwitchRuntime('bar', switchParam, options, '1'), { value: undefined, params: {} });
const runtimeExtraParams = buildWidgetExtraParams({ isTableLikeChart: false, tableQueryParams: {}, runtimeParams: resolvedRuntime.params });
assert.equal(buildWidgetRequestSignatureParams({
  config: { dataSourceParams: [switchParam] },
  dataSource: { params: [switchParam] } as any,
  extraParams: runtimeExtraParams,
}).group_by, 1);

const submitResult = buildWidgetSubmitConfig({
  values: { name: 'TopN', chartType: 'topN', dataSourceParams: [switchParam, { ...switchParam, name: 'region' }] },
  chartType: 'topN', showChartThemeMode: false, showTableFilterFields: false,
  selectedFields: [], thresholdColors: [], filterBindings: {}, displayColumns: [], filterFields: [], actions: [],
});
assert.equal(submitResult.error, 'multipleComponentSwitchParams');

assert.equal(resolveTopNContentState({ loading: true, hasRows: true }), 'loading');
assert.equal(resolveTopNContentState({ loading: false, errorMessage: 'failed', hasRows: true }), 'error');
assert.equal(resolveTopNContentState({ loading: false, hasRows: false }), 'empty');
assert.equal(resolveTopNContentState({ loading: false, hasRows: true }), 'ready');
assert.equal(isTopNContentReady('empty'), true);
assert.equal(isTopNContentReady('ready'), true);
assert.equal(isTopNContentReady('loading'), false);

const notifier = createParamInputOptionsNotifier();
const resultKey = buildParamInputOptionsResultKey('config', options);
let notifications = 0;
assert.equal(notifier.notify(resultKey, options), false);
assert.equal(notifier.notify(resultKey, options, () => { notifications += 1; }), true);
assert.equal(notifier.notify(resultKey, options, () => { notifications += 1; }), false);
assert.equal(notifications, 1);

const testAsyncLoading = async () => {
const staticLoader = createParamInputOptionsLoader({
  getDataSourceList: async () => [],
  getSourceDataByApiId: async () => [],
});
const staticResult = staticLoader.load(switchParam.inputConfig);
assert.equal(staticResult.sync, true);
assert.deepEqual(await staticResult.promise, { status: 'success', options });

type Resolver = (value: unknown) => void;
const resolvers: Resolver[] = [];
let requests = 0;
const dynamicLoader = createParamInputOptionsLoader({
  getDataSourceList: async () => [],
  getSourceDataByApiId: async () => {
    requests += 1;
    return new Promise((resolve) => resolvers.push(resolve));
  },
});
const dynamicConfig = {
  control: 'select' as const,
  optionsSource: { type: 'dynamic' as const, sourceId: 7, valueField: 'id', labelField: 'name' },
};
const first = dynamicLoader.load(dynamicConfig);
const duplicate = dynamicLoader.load({ ...dynamicConfig, optionsSource: { ...dynamicConfig.optionsSource } });
assert.equal(first.promise, duplicate.promise);
await Promise.resolve();
assert.equal(requests, 1);
const second = dynamicLoader.load({ ...dynamicConfig, optionsSource: { ...dynamicConfig.optionsSource, sourceId: 8 } });
await Promise.resolve();
assert.equal(requests, 2);
resolvers[0]({ items: [{ id: 1, name: 'stale' }] });
assert.equal(await first.promise, null);
resolvers[1]({ items: [{ id: 2, name: 'latest' }] });
assert.deepEqual(await second.promise, { status: 'success', options: [{ value: 2, label: 'latest' }] });

const sourceListResolvers: Resolver[] = [];
let secondStageRequests = 0;
const sourceRefLoader = createParamInputOptionsLoader({
  getDataSourceList: async () => new Promise((resolve) => sourceListResolvers.push(resolve)),
  getSourceDataByApiId: async () => {
    secondStageRequests += 1;
    return { items: [{ id: 1, name: 'option' }] };
  },
});
const sourceRefConfig = {
  control: 'select' as const,
  optionsSource: {
    type: 'dynamic' as const,
    sourceRef: { type: 'rest_api' as const, value: '/options/a' },
    valueField: 'id', labelField: 'name',
  },
};
const staleSourceRef = sourceRefLoader.load(sourceRefConfig);
await Promise.resolve();
const latestSourceRef = sourceRefLoader.load({
  ...sourceRefConfig,
  optionsSource: { ...sourceRefConfig.optionsSource, sourceRef: { type: 'rest_api' as const, value: '/options/b' } },
});
await Promise.resolve();
sourceListResolvers[0]([{ id: 1, rest_api: '/options/a' }]);
assert.equal(await staleSourceRef.promise, null);
assert.equal(secondStageRequests, 0);
sourceListResolvers[1]([{ id: 2, rest_api: '/options/b' }]);
assert.deepEqual(await latestSourceRef.promise, { status: 'success', options: [{ value: 1, label: 'option' }] });
assert.equal(secondStageRequests, 1);

const emptyLoader = createParamInputOptionsLoader({
  getDataSourceList: async () => [],
  getSourceDataByApiId: async () => ({ items: [] }),
});
assert.deepEqual(await emptyLoader.load(dynamicConfig).promise, { status: 'error', options: [] });
const failingLoader = createParamInputOptionsLoader({
  getDataSourceList: async () => [],
  getSourceDataByApiId: async () => { throw new Error('load failed'); },
});
assert.deepEqual(await failingLoader.load(dynamicConfig).promise, { status: 'error', options: [] });
};

const hookSource = readFileSync(new URL('../src/app/ops-analysis/hooks/useParamInputOptions.ts', import.meta.url), 'utf8');
assert.match(hookSource, /useRef/);
assert.match(hookSource, /getParamInputConfigKey/);
assert.match(hookSource, /loaderRef\.current!?\.load/);
assert.match(hookSource, /resultKey/);
assert.doesNotMatch(hookSource, /useEffect\([\s\S]*?\[[^\]]*getDataSourceList/);
assert.doesNotMatch(hookSource, /useEffect\([\s\S]*?\[[^\]]*getSourceDataByApiId/);

const editorSource = readFileSync(new URL('../src/app/ops-analysis/components/paramInputConfigEditor.tsx', import.meta.url), 'utf8');
const widgetConfigSource = readFileSync(new URL('../src/app/ops-analysis/components/widgetConfig.tsx', import.meta.url), 'utf8');
const rendererSource = readFileSync(new URL('../src/app/ops-analysis/components/widgetDataRenderer.tsx', import.meta.url), 'utf8');
const widgetRendererSource = readFileSync(new URL('../src/app/ops-analysis/components/widgetRenderer.tsx', import.meta.url), 'utf8');
const topNSource = readFileSync(new URL('../src/app/ops-analysis/components/widgets/comTopN.tsx', import.meta.url), 'utf8');
const controlSource = readFileSync(new URL('../src/app/ops-analysis/components/componentParamSwitchControl.tsx', import.meta.url), 'utf8');
const paramInputControlSource = readFileSync(new URL('../src/app/ops-analysis/components/paramInputControl.tsx', import.meta.url), 'utf8');
const dashboardSource = readFileSync(new URL('../src/app/ops-analysis/(pages)/view/dashBoard/index.tsx', import.meta.url), 'utf8');
const topologySource = readFileSync(new URL('../src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts', import.meta.url), 'utf8');
assert.match(editorSource, /componentSwitchEnabled/);
assert.match(editorSource, /componentSwitchOccupied/);
assert.match(widgetConfigSource, /resolvedParamOptionsRef/);
assert.match(widgetConfigSource, /clearComponentParamSwitch/);
assert.doesNotMatch(widgetConfigSource, /runtimeParamControl/);
assert.match(rendererSource, /useParamInputOptions\(componentSwitchParam\?\.inputConfig\)/);
assert.match(rendererSource, /getTypedValueKey\(savedComponentSwitchValue\)/);
assert.match(rendererSource, /resolveComponentSwitchRuntime/);
assert.match(rendererSource, /requestExtraParams/);
assert.match(rendererSource, /headerRuntimeSlot \? null : componentSwitchControl/);
assert.match(widgetRendererSource, /componentSwitchControl/);
assert.match(topNSource, /\{componentSwitchControl\}/);
assert.match(controlSource, /inputConfig/);
assert.match(controlSource, /<Segmented/);
assert.match(controlSource, /<Select/);
assert.match(controlSource, /block=\{block\}/);
assert.match(paramInputControlSource, /createParamInputOptionsNotifier/);
assert.doesNotMatch(paramInputControlSource, /\[[^\]]*onOptionsResolved[^\]]*\]/);
assert.doesNotMatch(dashboardSource, /runtimeParamControl/);
assert.doesNotMatch(topologySource, /runtimeParamControl/);

const zhLocale = JSON.parse(readFileSync(new URL('../src/app/ops-analysis/locales/zh.json', import.meta.url), 'utf8'));
const enLocale = JSON.parse(readFileSync(new URL('../src/app/ops-analysis/locales/en.json', import.meta.url), 'utf8'));
assert.match(zhLocale.dashboard.componentSwitchOccupied, /\{label\}/);
assert.match(enLocale.dashboard.componentSwitchOccupied, /\{label\}/);

const scanFiles = (directory: URL): string[] =>
  readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const child = new URL(entry.name, directory);
    const path = fileURLToPath(child);
    return statSync(path).isDirectory() ? scanFiles(new URL(`${entry.name}/`, directory)) : [path];
  });
const productionFiles = scanFiles(new URL('../src/app/ops-analysis/', import.meta.url));
const legacyPattern = /RuntimeParamControl|runtimeParamControl|runtimeParamSegmented|filterType\s*[:=]\s*['"]widget['"]/;
assert.deepEqual(productionFiles.filter((path) => legacyPattern.test(readFileSync(path, 'utf8'))), []);
assert.doesNotMatch(rendererSource, /runtimeParamControl/);

testAsyncLoading().then(() => {
  console.log('ops analysis component parameter switch tests passed');
});
