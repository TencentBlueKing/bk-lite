import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import { buildInteractionPoints, cardListLinkPoints, topNLinkPoints } from '@/app/ops-analysis/utils/interactionPoints';
import { buildTopNItems } from '@/app/ops-analysis/utils/topNData';
import { parseCardListItems, DEFAULT_CARD_LIST_MAX_ITEMS } from '@/app/ops-analysis/utils/cardList';
import {
  interactionActionColumnTitle,
  interactionActionLinkText,
  interactionKindForChartType,
  isAllowedInteractionUrl,
  isFirstActionColumn,
  listInteractionVariables,
  listPresentDataVariables,
  listTableFieldVariables,
  listUnmatchedInteractionTokens,
  migrateActionsToInteraction,
  normalizeInteractionLink,
  prepareInteractionNavigation,
  readChartClickPoint,
  readWidgetInteraction,
  applicationTopologyLinkPoint,
  interactionCapability,
  resolveInteractionUrl,
  sceneLinkPoint,
  shouldNavigateInteraction,
  shouldRenderEventTimelineFieldLink,
  shouldRenderInteractionActionButton,
  shouldShowInteractionEntry,
  withInteractionActionColumn,
  type ChartLinkPoint,
} from '@/app/ops-analysis/utils/interactionLink';

const filter = (
  partial: Partial<UnifiedFilterDefinition> & Pick<UnifiedFilterDefinition, 'id' | 'key' | 'type'>,
): UnifiedFilterDefinition => ({
  name: partial.key,
  order: 0,
  enabled: true,
  ...partial,
});

const now = new Date('2026-10-15T00:00:00.000Z');

test('resolves filter ids, multi-select, empty values, and escaped dollars', () => {
  const definitions = [
    filter({ id: 'env', key: 'env', type: 'string', name: '环境' }),
    filter({ id: 'hosts', key: 'host', type: 'string', name: '主机' }),
  ];
  const url = resolveInteractionUrl(
    'https://example.com/item?env=$env$&host=$host$&plain=\\$keep',
    {
      definitions,
      values: { env: 'prod-id', hosts: ['a', '', 'b'] },
      now,
    },
  );

  assert.equal(
    url,
    'https://example.com/item?env=prod-id&host=a%2C%2Cb&plain=$keep',
  );
});

test('encodes each token and leaves the rest of the URL untouched', () => {
  const definitions = [filter({ id: 'q', key: 'q', type: 'string' })];
  const url = resolveInteractionUrl('https://example.com/a b?q=$q$', {
    definitions,
    values: { q: 'x y' },
    now,
  });

  assert.equal(url, 'https://example.com/a b?q=x%20y');
});

test('converts a relative time range at click time and exposes start and end', () => {
  const definitions = [
    filter({ id: 'time', key: 'time', type: 'timeRange', name: '时间' }),
  ];
  const input = {
    definitions,
    values: { time: { selectValue: 60 } },
    now,
  };

  assert.equal(
    resolveInteractionUrl('$time$', input),
    `${encodeURIComponent('2026-10-14T23:00:00.000Z,2026-10-15T00:00:00.000Z')}`,
  );
  assert.equal(
    resolveInteractionUrl('$time.start$', input),
    encodeURIComponent('2026-10-14T23:00:00.000Z'),
  );
  assert.equal(
    resolveInteractionUrl('$time.end$', input),
    encodeURIComponent('2026-10-15T00:00:00.000Z'),
  );
});

test('resolves clicked point fields without encoding the whole URL', () => {
  const point: ChartLinkPoint = {
    seriesName: 'cpu',
    time: '2026-10-15T00:00:00.000Z',
    numeric: 1.5,
    text: '1.5',
    raw: 1.5,
    fields: { host: 'web 01', region: 'a/b' },
  };
  const url = resolveInteractionUrl(
    '/ops?series=$__series.name$&at=$__value.time$&n=$__value.numeric$&host=$__data.fields.host$&text=$__value.text$&raw=$__value.raw$',
    { definitions: [], values: {}, point, now },
  );

  assert.equal(
    url,
    '/ops?series=cpu&at=2026-10-15T00%3A00%3A00.000Z&n=1.5&host=web%2001&text=1.5&raw=1.5',
  );
  assert.deepEqual(
    listUnmatchedInteractionTokens('$__value.text$ $__value.raw$', []),
    [],
  );
});

test('allows http, https, and site paths, and blocks other protocols', () => {
  assert.equal(isAllowedInteractionUrl('https://example.com/a?b=1'), true);
  assert.equal(isAllowedInteractionUrl('http://example.com'), true);
  assert.equal(isAllowedInteractionUrl('/cmdb/assetData?id=1'), true);
  assert.equal(isAllowedInteractionUrl('javascript:alert(1)'), false);
  assert.equal(isAllowedInteractionUrl('data:text/html,hi'), false);
  assert.equal(isAllowedInteractionUrl('vbscript:msg'), false);
  assert.equal(isAllowedInteractionUrl('//evil.example'), false);
  assert.equal(isAllowedInteractionUrl('///evil.example'), false);
  assert.equal(isAllowedInteractionUrl('javascript:alert(1)'), false);
  assert.equal(isAllowedInteractionUrl(' javascript:alert(1)'), false);
});

test('new tab plans noopener navigation and same tab keeps screen mode', () => {
  const external = prepareInteractionNavigation(
    'https://example.com/item',
    'newTab',
    '?screen=true',
  );
  assert.equal(external.ok, true);
  if (external.ok) {
    assert.equal(external.mode, 'newTab');
    assert.equal(external.href, 'https://example.com/item');
  }

  const internal = prepareInteractionNavigation('/cmdb/asset', 'sameTab', '?screen=true');
  assert.equal(internal.ok, true);
  if (internal.ok) {
    assert.equal(internal.mode, 'sameFrame');
    assert.equal(internal.href.includes('screen=true'), true);
  }

  assert.deepEqual(
    prepareInteractionNavigation('javascript:alert(1)', 'sameTab', ''),
    { ok: false, reason: 'blocked' },
  );
});

test('keeps only the first legacy action and turns mappings into a query', () => {
  const link = migrateActionsToInteraction([
    {
      columnKey: '__actions__',
      text: '查看',
      url: 'https://example.com/item',
      openMode: 'newTab',
      params: [
        { key: 'id', source: 'rowField', sourceKey: 'host_id' },
        { key: 'env', source: 'fixed', value: 'prod id' },
      ],
    },
    {
      columnKey: '__actions__',
      text: '第二条',
      url: 'https://example.com/other',
    },
  ]);

  assert.deepEqual(link, {
    kind: 'data',
    name: '查看',
    url: 'https://example.com/item?id=$__data.fields.host_id$&env=prod%20id',
    openMode: 'newTab',
  });
  assert.equal(
    readWidgetInteraction({
      chartType: 'table',
      actions: [
        {
          columnKey: '__actions__',
          text: '查看',
          url: '/cmdb',
          params: [{ key: 'id', source: 'rowField', sourceKey: 'id' }],
        },
      ],
    })?.url,
    '/cmdb?id=$__data.fields.id$',
  );
});

test('stored interaction wins and title-only widgets keep the link as a title link', () => {
  const stored = readWidgetInteraction({
    chartType: 'line',
    interaction: {
      kind: 'title',
      name: '详情',
      url: '/ops?env=$env$',
      openMode: 'sameTab',
    },
    actions: [{ columnKey: 'op', text: '旧', url: '/old' }],
  });
  assert.equal(stored?.kind, 'title');
  assert.equal(stored?.url, '/ops?env=$env$');
  for (const chartType of ['text', 'networkStatusTopology', 'relatedTopology', 'topologyMap']) {
    const kept = readWidgetInteraction({
      chartType,
      interaction: { kind: 'data', name: '点', url: '/x', openMode: 'sameTab' },
    });
    assert.equal(kept?.kind, 'title');
    assert.equal(kept?.url, '/x');
    assert.equal(interactionKindForChartType(chartType, 'data'), 'title');
  }
  assert.equal(interactionKindForChartType('line', 'data'), 'data');
  assert.equal(interactionKindForChartType('bar', 'title'), 'title');
  assert.equal(interactionKindForChartType('line', 'none'), 'none');
  assert.equal(interactionKindForChartType('text', 'none'), 'none');
  assert.equal(normalizeInteractionLink({
    kind: 'none',
    name: '详情',
    url: '/ops',
    openMode: 'newTab',
  }, 'line'), undefined);
});

test('empty legacy action urls are not turned into a query-only link', () => {
  assert.equal(migrateActionsToInteraction([
    {
      columnKey: 'op',
      text: '查看',
      url: '   ',
      params: [{ key: 'id', source: 'rowField', sourceKey: 'host' }],
    },
  ]), undefined);
  assert.equal(migrateActionsToInteraction([
    { columnKey: 'op', text: '查看', url: '' },
  ]), undefined);
  assert.equal(migrateActionsToInteraction([
    { columnKey: 'op', text: '查看', url: 'javascript:alert(1)' },
  ]), undefined);
});

test('edit shows the entry without navigation and share hides it', () => {
  assert.equal(shouldShowInteractionEntry('edit', true), true);
  assert.equal(shouldNavigateInteraction('edit'), false);
  assert.equal(shouldShowInteractionEntry('view', true), true);
  assert.equal(shouldNavigateInteraction('view'), true);
  assert.equal(shouldShowInteractionEntry('share', true), false);
  assert.equal(shouldShowInteractionEntry('view', false), false);
});

test('line points keep the original timestamp, row, and label without changing plotted values', () => {
  const chart = ChartDataTransformer.transformToLineBarData([
    { name: 1760486400, value: 3, host: 'web-01' },
    { name: 1760486460, value: 4, host: 'web-02' },
  ]);

  assert.deepEqual(chart.values, [3, 4]);
  assert.equal(chart.points?.[0]?.time, '2025-10-15T00:00:00.000Z');
  assert.equal(chart.points?.[0]?.numeric, 3);
  assert.equal(chart.points?.[0]?.fields?.host, 'web-01');
  assert.equal(chart.points?.[0]?.raw, 3);
  assert.equal(chart.categories[0]?.includes('10-15'), true);
});

test('tuple rows without a time axis keep the original category and list it as 分类', () => {
  const chart = ChartDataTransformer.transformToLineBarData([
    ['east', 3],
    ['west', 1],
  ]);
  const labels = {
    valueGroup: '数据点',
    fieldGroup: '数据字段',
    fieldLabel: (field: string) => field,
    series: '系列',
    category: '分类',
    time: '时间',
    numeric: '数值',
  };

  assert.deepEqual(chart.values, [3, 1]);
  assert.equal(chart.points?.[0]?.axisField, 'name');
  assert.equal(chart.points?.[0]?.fields?.name, 'east');
  assert.equal(chart.points?.[0]?.numeric, 3);
  assert.equal(chart.points?.[0]?.time, undefined);

  const variables = listPresentDataVariables('line', [['east', 3]], labels, chart.points);
  assert.deepEqual(
    variables.filter((item) => item.group === '数据点').map((item) => [item.label, item.token, item.example]),
    [
      ['分类', '$__data.fields.name$', 'east'],
      ['数值', '$__value.numeric$', '3'],
    ],
  );
  assert.equal(variables.some((item) => item.label === '时间'), false);

  const timed = ChartDataTransformer.transformToLineBarData([[1760486400, 3]]);
  assert.equal(timed.points?.[0]?.time, '2025-10-15T00:00:00.000Z');
  assert.equal(timed.points?.[0]?.axisField, undefined);
  assert.equal(timed.points?.[0]?.fields, undefined);
  assert.equal(
    listPresentDataVariables('line', [[1760486400, 3]], labels, timed.points)
      .some((item) => item.label === '分类'),
    false,
  );
});

test('a missing multi-series category keeps that category field', () => {
  const chart = ChartDataTransformer.transformToLineBarData({
    cpu: [{ name: 'a', value: 1 }],
    mem: [{ name: 'a', value: 2 }, { name: 'b', value: 3, host: 'web' }],
  });
  const cpu = chart.series?.find((series) => series.name === 'cpu');
  const missing = cpu?.points?.[chart.categories.indexOf('b')];

  assert.deepEqual(cpu?.data, [1, 0]);
  assert.equal(missing?.seriesName, 'cpu');
  assert.equal(missing?.axisField, 'name');
  assert.equal(missing?.fields?.name, 'b');
  assert.equal(missing?.numeric, undefined);
  assert.equal(missing?.fields?.host, undefined);
  assert.equal(missing?.fields?.value, undefined);

  const tuples = ChartDataTransformer.transformToLineBarData({
    cpu: [['east', 1]],
    mem: [['east', 2], ['west', 4]],
  });
  const westIndex = tuples.categories.indexOf('west');
  const west = tuples.series?.find((series) => series.name === 'cpu')?.points?.[westIndex];
  assert.equal(west?.fields?.name, 'west');
  assert.equal(west?.seriesName, 'cpu');
  assert.equal(west?.numeric, undefined);

  const timed = ChartDataTransformer.transformToLineBarData({
    cpu: [[1760486400, 1]],
    mem: [[1760486400, 2], [1760486460, 3]],
  });
  const gap = timed.series
    ?.find((series) => series.name === 'cpu')
    ?.points
    ?.find((point) => point.time === '2025-10-15T00:01:00.000Z');
  assert.equal(gap?.seriesName, 'cpu');
  assert.equal(gap?.numeric, undefined);
  assert.equal(gap?.fields, undefined);
});

test('dropdown lists only fields that exist for the chart and the rows', () => {
  const chart = ChartDataTransformer.transformToLineBarData({
    cpu: [{ name: 'a', value: 1 }],
  });
  const points = chart.series?.[0]?.points ?? [];
  const variables = listPresentDataVariables('line', { cpu: [] }, {
    valueGroup: '数据点',
    fieldGroup: '数据字段',
    fieldLabel: (field) => field,
    series: '系列',
    category: '分类',
    numeric: '数值',
  }, points);

  assert.deepEqual(
    variables.filter((item) => item.group === '数据点').map((item) => [item.label, item.token, item.example]),
    [
      ['系列', '$__series.name$', 'cpu'],
      ['分类', '$__data.fields.name$', 'a'],
      ['数值', '$__value.numeric$', '1'],
    ],
  );
  assert.deepEqual(
    variables.filter((item) => item.group === '数据字段').map((item) => item.token),
    ['$__data.fields.value$'],
  );
  assert.equal(variables.some((item) => item.token === '$__value.time$'), false);
  assert.equal(variables.some((item) => item.token === '$__value.text$'), false);
  assert.equal(variables.some((item) => item.token === '$__value.raw$'), false);

  const tableVariables = listTableFieldVariables(
    [{ host: 'web-01', cpu: 1 }],
    { fieldGroup: '字段', fieldLabel: (field) => field },
  );
  assert.deepEqual(
    tableVariables.map((item) => item.token),
    ['$__data.fields.cpu$', '$__data.fields.host$'],
  );

  const sceneLabels = {
    valueGroup: '值',
    fieldGroup: '字段',
    fieldLabel: (field: string) => field,
    cabinetGroup: '机柜',
    cabinetId: '机柜 ID',
    cabinetName: '机柜名称',
    cabinetLocation: '机柜位置',
    cabinetType: '机柜类型',
    cabinetState: '机柜状态',
    deviceGroup: '设备',
    deviceId: '设备 ID',
    deviceName: '设备名称',
    deviceModel: '模型 ID',
    deviceUStart: '起始 U 位',
    objectGroup: '对象',
    objectType: '对象类型',
    objectId: '对象 ID',
    objectName: '对象名称',
    objectModelId: '对象模型 ID',
  };
  const roomTokens = [
    '$__data.fields.object.type$',
    '$__data.fields.object.id$',
    '$__data.fields.object.name$',
    '$__data.fields.object.model_id$',
    '$__data.fields.cabinet.id$',
    '$__data.fields.cabinet.name$',
    '$__data.fields.cabinet.location$',
    '$__data.fields.cabinet.type$',
    '$__data.fields.cabinet.state$',
    '$__data.fields.device.id$',
    '$__data.fields.device.name$',
    '$__data.fields.device.model_id$',
    '$__data.fields.device.u_start$',
  ];
  const room = listPresentDataVariables('room3D', null, sceneLabels);
  assert.deepEqual(room.map((item) => item.token), roomTokens);
  assert.deepEqual(
    listPresentDataVariables('room3D', {
      racks: [{ rack_id: 'r1', rack_name: 'A', devices: [{ device_id: 'd1', device_name: 'srv' }] }],
    }, sceneLabels).map((item) => item.token),
    roomTokens,
  );
  assert.deepEqual(room.map((item) => [item.label, item.group, item.valueType]), [
    ['对象类型', '对象', 'text'],
    ['对象 ID', '对象', 'text'],
    ['对象名称', '对象', 'text'],
    ['对象模型 ID', '对象', 'text'],
    ['机柜 ID', '机柜', 'text'],
    ['机柜名称', '机柜', 'text'],
    ['机柜位置', '机柜', 'text'],
    ['机柜类型', '机柜', 'text'],
    ['机柜状态', '机柜', 'text'],
    ['设备 ID', '设备', 'text'],
    ['设备名称', '设备', 'text'],
    ['模型 ID', '设备', 'text'],
    ['起始 U 位', '设备', 'number'],
  ]);
  assert.equal(room.some((item) => item.example), false);
});

test('filter variable list adds start and end only for time filters', () => {
  const variables = listInteractionVariables({
    definitions: [
      filter({ id: 'env', key: 'env', type: 'string', name: '环境' }),
      filter({ id: 'time', key: 'time', type: 'timeRange', name: '时间' }),
    ],
    dataVariables: [],
    filterGroup: '筛选',
    timeStartLabel: (name) => `${name}开始`,
    timeEndLabel: (name) => `${name}结束`,
  });

  assert.deepEqual(variables.map((item) => item.token), [
    '$env$',
    '$time$',
    '$time.start$',
    '$time.end$',
  ]);
  assert.equal(variables[0]?.valueType, 'text');
  assert.equal(variables[1]?.valueType, 'timeRange');
  assert.equal(variables[2]?.valueType, 'timeRange');
  assert.equal(variables[3]?.valueType, 'timeRange');
});

test('chart clicks expose the fields that exist on each widget', () => {
  const single = buildInteractionPoints('single', { cpu: 12, host: 'web' }, {
    selectedFields: ['cpu'],
  });
  assert.equal(single[0]?.numeric, 12);
  assert.equal(single[0]?.fields?.host, 'web');

  const gauge = buildInteractionPoints('gauge', { value: 40 }, {
    selectedFields: ['value'],
  });
  assert.equal(gauge[0]?.numeric, 40);

  const topNRows = [
    { name: 'a', value: 3 },
    { name: '  ', value: 9 },
    { name: 'b', value: '0' },
  ];
  const topNConfig = { topNLabelField: 'name', topNValueField: 'value' };
  const topNItems = buildTopNItems(topNRows, 'name', 'value');
  const topN = buildInteractionPoints('topN', topNRows, topNConfig);
  assert.deepEqual(topNItems.map((item) => item.name), ['a', 'b']);
  assert.deepEqual(topN, topNLinkPoints(topNItems, 'value'));
  assert.equal(topN[0]?.seriesName, 'a');
  assert.equal(topN[0]?.numeric, 3);
  assert.equal(topN[0]?.raw, 3);
  assert.equal(topN[0]?.fields?.name, 'a');
  assert.equal(topN[1]?.numeric, 0);
  assert.equal(topN[1]?.raw, '0');

  const pie = buildInteractionPoints('pie', [
    { name: 'up', value: 2 },
  ], { dimensionField: 'name', valueField: 'value' });
  assert.equal(pie[0]?.seriesName, 'up');
  assert.equal(pie[0]?.numeric, 2);

  const radarPoint = readChartClickPoint({
    data: { __links: [{ seriesName: 'cpu', numeric: 1 }, { seriesName: 'mem', numeric: 2 }] },
    event: { target: { __dimIdx: 1 } },
  });
  assert.equal(radarPoint?.seriesName, 'mem');
  const radarArea = readChartClickPoint({
    data: { __links: [{ seriesName: 'cpu', numeric: 1 }, { seriesName: 'mem', numeric: 2 }, { seriesName: 'disk', numeric: 3 }, { seriesName: 'net', numeric: 4 }] },
    event: { offsetX: 40, offsetY: 100 },
    radar: { centerX: 100, centerY: 100, indicatorCount: 4 },
  });
  assert.equal(radarArea?.seriesName, 'mem');

  const tableColumns = withInteractionActionColumn(
    [{ key: 'host', columnType: 'data' }],
    { kind: 'data', name: '查看', url: '/host', openMode: 'sameTab' },
    'view',
    { key: '__interaction', columnType: 'actions' },
  );
  assert.equal(tableColumns.at(-1)?.key, '__interaction');
  assert.equal(isFirstActionColumn(tableColumns, 1), true);
  const replaced = withInteractionActionColumn(
    [
      { key: 'host', columnType: 'data' },
      { key: '__actions__', title: '查看', columnType: 'actions' },
    ],
    { kind: 'data', name: '查看', url: '/host', openMode: 'sameTab' },
    'view',
    { key: '__interaction', title: '操作', columnType: 'actions' },
  );
  assert.deepEqual(replaced.map((column) => column.key), ['host', '__interaction']);
  assert.deepEqual(withInteractionActionColumn(
    [
      { key: 'host', columnType: 'data' },
      { key: '__actions__', columnType: 'actions' },
    ],
    undefined,
    'view',
    { key: '__interaction', columnType: 'actions' },
  ).map((column) => column.key), ['host']);
  assert.equal(withInteractionActionColumn(
    tableColumns,
    { kind: 'data', name: '查看', url: '/host', openMode: 'sameTab' },
    'share',
    { key: 'extra', columnType: 'actions' },
  ).some((column) => column.key === 'extra'), false);

  const applicationLabels = {
    valueGroup: '值',
    fieldGroup: '字段',
    fieldLabel: (field: string) => field,
    systemGroup: '应用系统',
    systemId: '系统 ID',
    systemName: '系统名称',
    hostGroup: '主机',
    hostId: '主机 ID',
    hostName: '主机名称',
    hostIp: '主机 IP',
    hostOs: '操作系统',
    applicationGroup: '应用',
    applicationId: '应用 ID',
    applicationName: '应用名称',
    objectGroup: '对象',
    objectType: '对象类型',
    objectId: '对象 ID',
    objectName: '对象名称',
    objectModelId: '对象模型 ID',
  };
  const applicationTokens = [
    '$__data.fields.object.type$',
    '$__data.fields.object.id$',
    '$__data.fields.object.name$',
    '$__data.fields.object.model_id$',
    '$__data.fields.system.id$',
    '$__data.fields.system.name$',
    '$__data.fields.host.id$',
    '$__data.fields.host.name$',
    '$__data.fields.host.ip$',
    '$__data.fields.host.os$',
    '$__data.fields.application.id$',
    '$__data.fields.application.name$',
  ];
  const systems = listPresentDataVariables('application3D', null, applicationLabels);
  assert.deepEqual(systems.map((item) => item.token), applicationTokens);
  assert.deepEqual(
    listPresentDataVariables('application3D', {
      items: [{ id: 'sys-1', name: '门户' }],
    }, applicationLabels).map((item) => [item.label, item.token]),
    systems.map((item) => [item.label, item.token]),
  );

  assert.deepEqual(interactionCapability('applicationTopology'), {
    title: true,
    data: 'contextMenu',
  });
  const topologyTokens = [
    '$__data.fields.object.id$',
    '$__data.fields.object.name$',
    '$__data.fields.object.model_id$',
  ];
  const topology = listPresentDataVariables('applicationTopology', null, applicationLabels);
  assert.deepEqual(topology.map((item) => item.token), topologyTokens);
  const nodeId = '9f3c2a10-6b2e-4d11-9a77-0c1e8b44aa01';
  const topologyPoint = applicationTopologyLinkPoint({
    id: nodeId,
    name: '订单服务',
    modelId: 'application',
  });
  assert.equal(topologyPoint.fields?.['object.id'], nodeId);
  assert.equal(topologyPoint.fields?.['object.name'], '订单服务');
  assert.equal(topologyPoint.fields?.['object.model_id'], 'application');
  assert.equal(topologyPoint.fields?.['object.type'], undefined);
  assert.equal(
    resolveInteractionUrl(
      '/cmdb/assetData/detail/baseInfo?model_id=$__data.fields.object.model_id$&inst_uuid=$__data.fields.object.id$&inst_name=$__data.fields.object.name$',
      { definitions: [], values: {}, point: topologyPoint, now },
    ),
    `/cmdb/assetData/detail/baseInfo?model_id=application&inst_uuid=${nodeId}&inst_name=${encodeURIComponent('订单服务')}`,
  );
});

test('scene link points fill the right-clicked object and its related fields', () => {
  const devicePoint = sceneLinkPoint({
    cabinet: {
      rack_id: 'rack-1',
      rack_name: 'A01',
      location: 'A-1',
      rack_type_name: '网络柜',
      rack_type: 'network',
      rack_state_name: null,
      rack_state: '1',
    },
    device: {
      device_id: 'dev-1',
      device_name: 'srv',
      model_id: 'model-9',
      rack_u_start: 12,
      status: 'online',
    } as Parameters<typeof sceneLinkPoint>[0]['device'],
  });
  assert.equal(devicePoint.fields?.['object.type'], 'device');
  assert.equal(devicePoint.fields?.['object.id'], 'dev-1');
  assert.equal(devicePoint.fields?.['object.name'], 'srv');
  assert.equal(devicePoint.fields?.['cabinet.id'], 'rack-1');
  assert.equal(devicePoint.fields?.['cabinet.name'], 'A01');
  assert.equal(devicePoint.fields?.['cabinet.location'], 'A-1');
  assert.equal(devicePoint.fields?.['cabinet.type'], 'network');
  assert.equal(devicePoint.fields?.['cabinet.state'], '1');
  assert.equal(devicePoint.fields?.['device.model_id'], 'model-9');
  assert.equal(devicePoint.fields?.['object.model_id'], 'model-9');
  assert.equal(devicePoint.fields?.['device.u_start'], 12);
  assert.equal(devicePoint.fields?.['device.status'], undefined);
  assert.equal(
    resolveInteractionUrl(
      '/cmdb/assetData/detail/baseInfo?model_id=$__data.fields.object.model_id$&inst_uuid=$__data.fields.object.id$&inst_name=$__data.fields.object.name$',
      { definitions: [], values: {}, point: devicePoint },
    ),
    '/cmdb/assetData/detail/baseInfo?model_id=model-9&inst_uuid=dev-1&inst_name=srv',
  );

  const cabinetOnly = sceneLinkPoint({
    cabinet: {
      rack_id: 'rack-2',
      rack_name: 'B02',
      rack_type: 'server',
      rack_type_name: '服务器柜',
      rack_state: '1',
      rack_state_name: '启用',
    },
  });
  assert.equal(cabinetOnly.fields?.['object.type'], 'cabinet');
  assert.equal(cabinetOnly.fields?.['object.model_id'], 'rack');
  assert.equal(cabinetOnly.fields?.['cabinet.type'], 'server');
  assert.equal(cabinetOnly.fields?.['cabinet.state'], '1');
  assert.equal(cabinetOnly.fields?.['device.id'], undefined);
  assert.equal(
    resolveInteractionUrl('$__data.fields.device.model_id$', {
      definitions: [],
      values: {},
      point: cabinetOnly,
    }),
    '',
  );
  const displayNameOnly = sceneLinkPoint({
    cabinet: {
      rack_id: 'rack-3',
      rack_name: 'C03',
      rack_type_name: '网络柜',
      rack_state_name: '启用',
    },
  });
  assert.equal(displayNameOnly.fields?.['cabinet.type'], undefined);
  assert.equal(displayNameOnly.fields?.['cabinet.state'], undefined);
  assert.equal(displayNameOnly.fields?.['object.model_id'], 'rack');

  const zeroU = sceneLinkPoint({
    device: { device_id: 'dev-0', device_name: 'edge', rack_u_start: 0 },
  });
  assert.equal(zeroU.fields?.['device.u_start'], 0);
  assert.equal(zeroU.fields?.['object.type'], 'device');
  assert.equal(zeroU.fields?.['object.model_id'], undefined);

  const legacyNames = sceneLinkPoint({
    cabinet: { id: 'c-old', name: '旧机柜' },
    device: { id: 'd-old', name: '旧设备' },
  });
  assert.equal(legacyNames.fields?.['cabinet.id'], 'c-old');
  assert.equal(legacyNames.fields?.['device.name'], '旧设备');
  assert.equal(legacyNames.fields?.['object.type'], 'device');

  const hostPoint = sceneLinkPoint({
    host: { id: 'host-1', name: 'web-1', ip: '10.0.0.8', os: 'Linux' },
  });
  assert.deepEqual(hostPoint.fields, {
    'host.id': 'host-1',
    'host.name': 'web-1',
    'host.ip': '10.0.0.8',
    'host.os': 'Linux',
    'object.type': 'host',
    'object.id': 'host-1',
    'object.name': 'web-1',
    'object.model_id': 'host',
  });
  const customHost = sceneLinkPoint({
    host: { id: 'host-2', name: 'vm-1', modelId: 'vmware_vm' },
  });
  assert.equal(customHost.fields?.['object.model_id'], 'vmware_vm');

  const applicationPoint = sceneLinkPoint({
    application: { id: 'app-1', name: '门户' },
  });
  assert.equal(applicationPoint.fields?.['application.id'], 'app-1');
  assert.equal(applicationPoint.fields?.['application.name'], '门户');
  assert.equal(applicationPoint.fields?.['object.type'], 'application');
  assert.equal(applicationPoint.fields?.['object.model_id'], 'application');
  assert.equal(applicationPoint.fields?.['system.id'], undefined);
  assert.equal(
    sceneLinkPoint({ application: { id: 'app-2', name: '订单', model_id: 'custom_app' } }).fields?.['object.model_id'],
    'custom_app',
  );

  const systemPoint = sceneLinkPoint({
    system: { id: 'sys-1', name: '门户系统' },
  });
  assert.equal(systemPoint.fields?.['system.id'], 'sys-1');
  assert.equal(systemPoint.fields?.['system.name'], '门户系统');
  assert.equal(systemPoint.fields?.['object.type'], 'system');
  assert.equal(systemPoint.fields?.['object.id'], 'sys-1');
  assert.equal(systemPoint.fields?.['object.model_id'], 'system');
  assert.equal(
    sceneLinkPoint({ system: { id: 'sys-2', name: '计费', modelId: 'biz_system' } }).fields?.['object.model_id'],
    'biz_system',
  );
});

test('table action column title stays fixed while the cell uses the interaction name', () => {
  const copy = (key: string, fallback?: string) => fallback ?? key;
  assert.equal(interactionActionColumnTitle(copy), '操作');
  assert.equal(interactionActionLinkText('查看', copy), '查看');
  assert.equal(interactionActionLinkText('  ', copy), '打开链接');
  assert.equal(interactionActionLinkText('', copy), '打开链接');
  assert.equal(interactionActionLinkText(undefined, copy), '打开链接');
});

test('event table and event timeline expose the clicked row fields', () => {
  const labels = {
    valueGroup: '值',
    fieldGroup: '字段',
    fieldLabel: (field: string) => field,
  };
  const rows = [{ id: 'evt-1', title: 'CPU', severity: 'critical' }];
  const eventTable = listPresentDataVariables(
    'eventTable',
    rows,
    labels,
    buildInteractionPoints('eventTable', rows),
  );
  assert.deepEqual(eventTable.map((item) => item.token), [
    '$__data.fields.id$',
    '$__data.fields.severity$',
    '$__data.fields.title$',
  ]);

  const events = [{
    time: '2026-08-01 10:15:00',
    title: 'CPU usage reached 95%',
    host: 'web-01',
    link: '/monitor/view/detail?id=1',
  }];
  const timelinePoints = buildInteractionPoints('eventTimeline', events);
  assert.equal(timelinePoints[0]?.text, 'CPU usage reached 95%');
  assert.equal(Date.parse(timelinePoints[0]?.time || ''), Date.parse('2026-08-01 10:15:00'));
  assert.equal(timelinePoints[0]?.fields?.host, 'web-01');
  const timeline = listPresentDataVariables('eventTimeline', events, {
    ...labels,
    time: '时间',
  }, timelinePoints);
  assert.equal(timeline.some((item) => item.label === '时间' && item.token === '$__value.time$'), true);
  assert.equal(timeline.some((item) => item.token === '$__value.text$'), false);
  assert.equal(timeline.some((item) => item.token === '$__value.raw$'), false);
  assert.equal(timeline.some((item) => item.token === '$__data.fields.host$'), true);
  assert.equal(timeline.some((item) => item.token === '$__data.fields.title$'), true);
  assert.equal(
    resolveInteractionUrl('$__value.text$', { definitions: [], values: {}, point: timelinePoints[0] }),
    encodeURIComponent('CPU usage reached 95%'),
  );

  const dataLink = {
    kind: 'data' as const,
    name: '查看',
    url: '/ops/event?title=$__value.text$',
    openMode: 'sameTab' as const,
  };
  assert.equal(shouldRenderEventTimelineFieldLink(dataLink, '/monitor/view/detail?id=1'), false);
  assert.equal(shouldRenderEventTimelineFieldLink(undefined, '/monitor/view/detail?id=1'), true);
  assert.equal(shouldRenderInteractionActionButton(dataLink, 'view', true), true);
  assert.equal(shouldRenderInteractionActionButton(dataLink, 'edit', true), true);
  assert.equal(shouldRenderInteractionActionButton(dataLink, 'share', true), false);
  assert.equal(shouldShowInteractionEntry('share', true), false);
  assert.equal(shouldNavigateInteraction('edit'), false);
});

test('dropdown lists chart data points and omits text, raw, and unknown fields', () => {
  const labels = {
    valueGroup: '数据点',
    fieldGroup: '数据字段',
    fieldLabel: (field: string) => field,
    category: '分类',
    series: '系列',
    name: '名称',
    indicator: '指标',
    numeric: '数值',
    time: '时间',
  };
  assert.deepEqual(
    listPresentDataVariables('pie', null, labels).map((item) => [item.label, item.token]),
    [['分类', '$__series.name$'], ['数值', '$__value.numeric$']],
  );
  assert.deepEqual(
    listPresentDataVariables('line', null, labels).map((item) => item.token),
    ['$__series.name$', '$__value.numeric$'],
  );
  assert.deepEqual(
    listPresentDataVariables('bar', null, labels).map((item) => item.token),
    ['$__series.name$', '$__value.numeric$'],
  );
  for (const chartType of ['gauge', 'single']) {
    assert.deepEqual(
      listPresentDataVariables(chartType, null, labels).map((item) => [item.label, item.token]),
      [['数值', '$__value.numeric$']],
    );
  }
  assert.deepEqual(listPresentDataVariables('table', null, labels), []);
  assert.deepEqual(listPresentDataVariables('topN', null, labels), []);
  assert.equal(
    listPresentDataVariables('line', null, labels).some((item) => item.example || item.token.includes('__data.fields') || item.token.includes('__value.time')),
    false,
  );

  const timed = buildInteractionPoints('line', [
    { name: 1760486400, value: 3, host: 'web-01' },
  ]);
  const timedMenu = listPresentDataVariables('line', [{ name: 1760486400 }], labels, timed);
  assert.deepEqual(
    timedMenu.filter((item) => item.group === '数据点').map((item) => item.label),
    ['时间', '数值'],
  );
  assert.equal(timedMenu.some((item) => item.label === '分类'), false);
  assert.equal(timedMenu.some((item) => item.token === '$__data.fields.host$'), true);

  const gauge = listPresentDataVariables('gauge', { cpu: 12, host: 'web' }, labels, buildInteractionPoints('gauge', { cpu: 12, host: 'web' }, {
    selectedFields: ['cpu'],
  }));
  assert.deepEqual(
    gauge.filter((item) => item.group === '数据点').map((item) => item.token),
    ['$__value.numeric$'],
  );
  assert.equal(gauge.some((item) => item.token === '$__series.name$'), false);
  assert.equal(gauge.some((item) => item.token === '$__data.fields.host$'), true);

  const radar = listPresentDataVariables('radar', [{ cpu: 1 }], labels, [
    { seriesName: 'cpu', numeric: 1, fields: { cpu: 1 } },
  ]);
  assert.deepEqual(radar.map((item) => [item.label, item.token]), [
    ['指标', '$__series.name$'],
    ['数值', '$__value.numeric$'],
  ]);

  const cards = listPresentDataVariables('cardList', [{ title: '主机' }], labels, [
    { seriesName: '主机', fields: { title: '主机' } },
  ]);
  assert.deepEqual(cards.map((item) => [item.label, item.token, item.example]), [
    ['名称', '$__series.name$', '主机'],
    ['title', '$__data.fields.title$', '主机'],
  ]);

  const graph = listPresentDataVariables('nodeGraph', [], labels, [
    { seriesName: 'a → b', numeric: 2, text: 'a → b', raw: 2, fields: { source: 'a', target: 'b' } },
  ]);
  assert.deepEqual(
    graph.filter((item) => item.group === '数据点').map((item) => item.label),
    ['名称', '数值'],
  );
  assert.equal(graph.some((item) => item.token === '$__value.text$' || item.token === '$__value.raw$'), false);
  assert.equal(graph.some((item) => item.token === '$__data.fields.source$'), true);
});

test('card list click points follow the same filtered and truncated cards', () => {
  const rows = [
    { title: '   ', host: 'skip' },
    ...Array.from({ length: DEFAULT_CARD_LIST_MAX_ITEMS + 1 }, (_, index) => ({
      title: `R${index}`,
      host: `h${index}`,
    })),
  ];
  const parsed = parseCardListItems(rows, { titleField: 'title' });
  const points = cardListLinkPoints(parsed.items);
  assert.equal(points.length, DEFAULT_CARD_LIST_MAX_ITEMS);
  assert.equal(points[0]?.seriesName, parsed.items[0]?.primary);
  assert.equal(points[0]?.fields?.host, 'h0');
  assert.equal(points[99]?.fields?.host, 'h99');
  assert.equal(points.some((point) => point.fields?.host === 'skip'), false);
  assert.equal(points.some((point) => point.fields?.host === 'h100'), false);
});

test('multi value field rows come from the same extracted items', () => {
  const points = buildInteractionPoints('multiValue', {
    data: { items: [{ label: 'cpu', value: '12', host: 'web-01' }] },
  }, {});
  assert.equal(points[0]?.seriesName, 'cpu');
  assert.equal(points[0]?.numeric, 12);
  assert.equal(points[0]?.fields?.host, 'web-01');
});

test('node graph edge clicks carry the parallel index and service port', () => {
  const ip = buildInteractionPoints('nodeGraph', [
    { src: '10.0.0.1', dst: '10.0.0.2', value: 7 },
    { src: '10.0.0.2', dst: '10.0.0.1', value: 2 },
  ], {
    nodeGraphIdentityMode: 'ip',
    nodeGraphSourceField: 'src',
    nodeGraphTargetField: 'dst',
    nodeGraphValueField: 'value',
  });
  const ipEdges = ip.filter((point) => point.fields?.source);
  assert.deepEqual(
    ipEdges.map((edge) => edge.fields?.parallelIndex),
    [0, 1],
  );

  const service = buildInteractionPoints('nodeGraph', [
    { src: '10.0.0.1', dst: '10.0.0.9', dst_port: 443, value: 7 },
    { src: '10.0.0.1', dst: '10.0.0.9', dst_port: 80, value: 2 },
  ], {
    nodeGraphIdentityMode: 'service',
    nodeGraphSourceField: 'src',
    nodeGraphTargetField: 'dst',
    nodeGraphTargetPortField: 'dst_port',
    nodeGraphValueField: 'value',
  });
  const serviceEdges = service.filter((point) => point.fields?.source);
  assert.equal(serviceEdges.find((edge) => edge.fields?.target === '10.0.0.9:443')?.fields?.port, '443');
  assert.equal(serviceEdges.find((edge) => edge.fields?.target === '10.0.0.9:80')?.fields?.port, '80');
});

test('interaction dropdown group names exist in Chinese and English', () => {
  const zh = JSON.parse(readFileSync(new URL('../../locales/zh.json', import.meta.url), 'utf8')).dashboard;
  const en = JSON.parse(readFileSync(new URL('../../locales/en.json', import.meta.url), 'utf8')).dashboard;
  assert.equal(zh.interactionGroupFilter, '画布筛选');
  assert.equal(zh.interactionGroupValue, '数据点');
  assert.equal(zh.interactionGroupField, '数据字段');
  assert.equal(en.interactionGroupFilter, 'Canvas filters');
  assert.equal(en.interactionGroupValue, 'Data points');
  assert.equal(en.interactionGroupField, 'Data fields');
  assert.equal(zh.interactionGroupCabinet, '机柜');
  assert.equal(en.interactionGroupCabinet, 'Cabinet');
  assert.equal(zh.interactionGroupDevice, '设备');
  assert.equal(en.interactionGroupDevice, 'Device');
  assert.equal(zh.interactionGroupSystem, '应用系统');
  assert.equal(en.interactionGroupSystem, 'Application system');
  assert.equal(zh.interactionGroupHost, '主机');
  assert.equal(en.interactionGroupHost, 'Host');
  assert.equal(zh.interactionGroupApplication, '应用');
  assert.equal(en.interactionGroupApplication, 'Application');
  assert.equal(zh.interactionGroupObject, '对象');
  assert.equal(en.interactionGroupObject, 'Object');
  assert.equal(zh.interactionCabinetLocation, '机柜位置');
  assert.equal(en.interactionCabinetLocation, 'Cabinet location');
  assert.equal(zh.interactionCabinetType, '机柜类型');
  assert.equal(en.interactionCabinetType, 'Cabinet type');
  assert.equal(zh.interactionCabinetState, '机柜状态');
  assert.equal(en.interactionCabinetState, 'Cabinet status');
  assert.equal(zh.interactionModelId, '模型 ID');
  assert.equal(en.interactionModelId, 'Model ID');
  assert.equal(zh.interactionObjectModelId, '对象模型 ID');
  assert.equal(en.interactionObjectModelId, 'Object Model ID');
  assert.equal(zh.interactionDeviceModel, undefined);
  assert.equal(en.interactionDeviceModel, undefined);
  assert.equal(zh.interactionDeviceUStart, '起始 U 位');
  assert.equal(en.interactionDeviceUStart, 'Start U');
  assert.equal(zh.interactionDeviceStatus, undefined);
  assert.equal(en.interactionDeviceStatus, undefined);
  assert.equal(zh.interactionHostIp, '主机 IP');
  assert.equal(en.interactionHostIp, 'Host IP');
  assert.equal(zh.interactionHostOs, '操作系统');
  assert.equal(en.interactionHostOs, 'Operating system');
  assert.equal(zh.interactionApplicationId, '应用 ID');
  assert.equal(en.interactionApplicationId, 'Application ID');
  assert.equal(zh.interactionApplicationName, '应用名称');
  assert.equal(en.interactionApplicationName, 'Application name');
  assert.equal(zh.interactionObjectType, '对象类型');
  assert.equal(en.interactionObjectType, 'Object type');
  assert.equal(zh.interactionObjectId, '对象 ID');
  assert.equal(en.interactionObjectId, 'Object ID');
  assert.equal(zh.interactionObjectName, '对象名称');
  assert.equal(en.interactionObjectName, 'Object name');
  assert.equal(zh.interactionPointCategory, '分类');
  assert.equal(en.interactionPointCategory, 'Category');
  assert.equal(zh.interactionSeriesName, '系列');
  assert.equal(en.interactionSeriesName, 'Series');
  assert.equal(zh.interactionPointName, '名称');
  assert.equal(en.interactionPointName, 'Name');
  assert.equal(zh.interactionPointIndicator, '指标');
  assert.equal(en.interactionPointIndicator, 'Indicator');
  assert.equal(zh.interactionValueText, undefined);
  assert.equal(en.interactionValueText, undefined);
  assert.equal(zh.interactionValueRaw, undefined);
  assert.equal(en.interactionValueRaw, undefined);
  assert.equal(zh.interactionLinkType, '链接类型');
  assert.equal(en.interactionLinkType, 'Link type');
  assert.equal(zh.interactionNone, '无');
  assert.equal(en.interactionNone, 'None');
  assert.equal(zh.interactionNoneTip, '无：不设置跳转');
  assert.equal(en.interactionNoneTip, 'None: no navigation is set');
  assert.equal(zh.interactionNoneHint, '未设置交互，组件不可点击跳转');
  assert.equal(en.interactionNoneHint, 'No interaction is set. The widget cannot be opened by clicking.');
  assert.equal(zh.interactionActionColumn, '操作');
  assert.equal(en.interactionActionColumn, 'Actions');
  assert.equal(zh.interactionChartTooltipHint, '{name} ↗ 点击打开');
  assert.equal(en.interactionChartTooltipHint, '{name} ↗ Click to open');
  assert.equal(zh.interactionHoverHint, '点击打开：{name}');
  assert.equal(en.interactionHoverHint, 'Click to open: {name}');
  assert.equal(zh.interactionContextHint, undefined);
  assert.equal(en.interactionContextHint, undefined);
  assert.equal(zh.interactionOpen, '打开链接');
  assert.equal(en.interactionOpen, 'Open link');
  assert.equal(zh.interactionUrlRequired, '请输入 URL');
  assert.equal(en.interactionUrlRequired, 'Enter a URL');
  for (const key of [
    'filterTokenOption',
    'filterTokenTypeString',
    'filterTokenTypeNumber',
    'filterTokenTypeTimeRange',
    'filterTokenTypeDateRange',
    'operationColumn',
    'operationColumnTitle',
  ]) {
    assert.equal(zh[key], undefined);
    assert.equal(en[key], undefined);
  }
  assert.equal(zh.interactionLinkTypeTitleTip, '标题链接：标题行最右侧显示 > 图标');
  assert.equal(en.interactionLinkTypeTitleTip, 'Title link: a > icon appears at the far right of the title row');
  assert.equal(zh.interactionLinkTypeDataTip, '数据链接：点击数据点、柱、扇区或数字打开');
  assert.equal(en.interactionLinkTypeDataTip, 'Data link: click a point, bar, sector, or number to open');
  assert.equal(zh.interactionTitleOnlyTip, '该组件仅支持标题链接，点击标题行最右侧 > 打开');
  assert.equal(en.interactionTitleOnlyTip, 'This widget only supports a title link. Click the > at the far right of the title row to open.');
  assert.equal(zh.interactionTextTitleTip, '标题链接：文本行最右侧显示 > 图标');
  assert.equal(en.interactionTextTitleTip, 'Title link: a > icon appears at the far right of the text row');
  assert.equal(zh.interactionUrlPlaceholder, '输入 URL，键入 $ 插入变量');
  assert.equal(en.interactionUrlPlaceholder, 'Enter a URL, type $ to insert a variable');
  for (const key of [
    'interactionSection',
    'interactionTitleHint',
    'interactionDataTableHint',
    'interactionDataMenuHint',
    'interactionDataClickHint',
    'interactionDataTimelineHint',
    'interactionDataUnsupported',
    'interactionTokenHint',
  ]) {
    assert.equal(zh[key], undefined);
    assert.equal(en[key], undefined);
  }
});
