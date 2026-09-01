import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const projectRoot = new URL('../', import.meta.url);
const readProjectFile = (path) => readFile(new URL(path, projectRoot), 'utf8');
async function loadModel(path) {
  const source = await readProjectFile(path);
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}#${Math.random()}`);
}

async function loadMonitorAdapter(apiGet) {
  const source = await readProjectFile('src/features/monitor/adapter.ts');
  const sourceFile = ts.createSourceFile('adapter.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const declarations = sourceFile.statements.filter((statement) => {
    if (ts.isFunctionDeclaration(statement)) {
      return ['record', 'text', 'number', 'texts', 'unwrap', 'mapMonitorInstance', 'getMonitorInstance'].includes(statement.name?.text);
    }
    if (ts.isVariableStatement(statement)) {
      return statement.declarationList.declarations.some((declaration) => (
        ts.isIdentifier(declaration.name)
        && ['LEGACY_INSTANCE_LOOKUP_PAGE_SIZE', 'LEGACY_INSTANCE_LOOKUP_MAX_PAGES'].includes(declaration.name.text)
      ));
    }
    return false;
  });
  const moduleSource = `
    const apiGet = (...args) => globalThis.__monitorAdapterApiGet(...args);
    ${declarations.map((statement) => statement.getText(sourceFile)).join('\n')}
    export { getMonitorInstance };
  `;
  globalThis.__monitorAdapterApiGet = apiGet;
  const compiled = ts.transpileModule(moduleSource, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}#${Math.random()}`);
}

async function loadRecentViewsPanel(fixture) {
  const source = await readProjectFile('src/features/monitor/recent-views-panel.tsx');
  const sourceFile = ts.createSourceFile('recent-views-panel.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const declarations = sourceFile.statements.filter((statement) => (
    ts.isFunctionDeclaration(statement)
    && ['entryKey', 'MonitorRecentViewsPanel'].includes(statement.name?.text)
  ));
  const moduleSource = `
    const h = (type, props, ...children) => ({ type, props: { ...(props || {}), children } });
    const Fragment = 'fragment';
    const useEffect = () => undefined;
    const useRef = (current) => ({ current });
    const Link = 'a';
    const MobilePullToRefresh = 'mobile-pull-to-refresh';
    const MobileResult = 'mobile-result';
    const MobileSkeleton = 'mobile-skeleton';
    const MonitorObjectIcon = 'monitor-object-icon';
    const formatRecentViewTime = () => '';
    const instanceSummaryEntries = () => [];
    const resolveMonitorReportingStatus = () => '';
    const useRecentViews = () => globalThis.__recentViewsPanelFixture.recentViews;
    const useAuth = () => globalThis.__recentViewsPanelFixture.auth;
    const formatAccountDateTime = () => '';
    const readMobileViewSnapshot = () => null;
    const restoreMobileViewScroll = () => undefined;
    const writeMobileViewSnapshot = () => undefined;
    const useTranslation = () => ({ t: (key) => key });
    const styles = new Proxy({}, { get: (_, key) => String(key) });
    const RECENT_VIEW_SUMMARY_LIMIT = 3;
    ${declarations.map((statement) => statement.getText(sourceFile)).join('\n')}
  `;
  globalThis.__recentViewsPanelFixture = fixture;
  const compiled = ts.transpileModule(moduleSource, {
    compilerOptions: {
      jsx: ts.JsxEmit.React,
      jsxFactory: 'h',
      jsxFragmentFactory: 'Fragment',
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}#${Math.random()}`);
}

function findRenderedNode(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (predicate(node)) return node;
  return (node.props?.children || []).flat(Infinity)
    .map((child) => findRenderedNode(child, predicate))
    .find(Boolean) || null;
}

test('监控单位标签与 Web findUnitNameById 优先级一致', async () => {
  const { resolveMonitorUnitLabel } = await loadModel('src/features/monitor/unit-label.ts');
  const unitList = [
    { unit_id: 'percent', display_unit: '%' },
    { unit_id: 'bytes', display_unit: 'B' },
    { unit_id: 'short', display_unit: 'short' },
  ];
  assert.equal(resolveMonitorUnitLabel('percent', undefined, unitList), '%');
  assert.equal(resolveMonitorUnitLabel('percent', 'pct', unitList), 'pct');
  assert.equal(resolveMonitorUnitLabel('unknown-unit', undefined, unitList), 'unknown-unit');
  assert.equal(resolveMonitorUnitLabel('short', undefined, unitList), '');
  assert.equal(resolveMonitorUnitLabel('bytes', 'none', unitList), '');
  assert.equal(resolveMonitorUnitLabel('percent', undefined, []), 'percent');

  const card = await readProjectFile('src/features/monitor/metric-card.tsx');
  const sheet = await readProjectFile('src/features/monitor/metric-chart-sheet.tsx');
  assert.match(card, /resolveMonitorUnitLabel\(metric\.unit,\s*displayUnit,\s*unitList\)/);
  assert.match(sheet, /resolveMonitorUnitLabel\(metric\.unit,\s*displayUnits\[metric\.id\],\s*unitList\)/);
});

test('列表未满一页时不展示「没有更多了」分页条', async () => {
  const { shouldShowListPagination } = await loadModel('src/utils/listPagination.ts');
  assert.equal(shouldShowListPagination(3, 3, 20), false);
  assert.equal(shouldShowListPagination(20, 20, 20), false);
  assert.equal(shouldShowListPagination(21, 20, 20), true);
  assert.equal(shouldShowListPagination(null, 19, 20), false);
  assert.equal(shouldShowListPagination(null, 20, 20), true);
});

test('监控对象树过滤不可见对象并保持服务端顺序', async () => {
  const { groupMonitorObjects, monitorRequestErrorKind, orderedMonitorObjects, sortMonitorInstances } = await loadModel('src/features/monitor/model.ts');
  const typeA = { id: 'db', name: 'db', displayName: 'DB', order: 1 };
  const typeB = { id: 'host-resource', name: 'host', displayName: 'Host', order: 2 };
  const object = (id, order, type, visible = true) => ({ id, order, visible, type });
  const groups = groupMonitorObjects([object(2, 2, typeB), object(1, 1, typeB), object(3, 3, typeB, false)]);
  assert.deepEqual(groups[0].objects.map((item) => item.id), [1, 2]);
  assert.deepEqual(
    orderedMonitorObjects([object(20, 2, typeB), object(10, 1, typeA), object(11, 2, typeA)]).map((item) => item.id),
    [10, 11, 20],
  );
  assert.deepEqual(
    sortMonitorInstances([
      { id: 'a', status: 'normal', lastReportedAt: 20 },
      { id: 'b', status: 'unavailable', lastReportedAt: 10 },
      { id: 'c', status: 'unavailable', lastReportedAt: 30 },
    ]).map((item) => item.id),
    ['c', 'b', 'a'],
  );
  assert.equal(monitorRequestErrorKind(new Error('API Error: 403')), 'forbidden');
  assert.equal(monitorRequestErrorKind(new Error('API Error: 404')), 'missing');
});

test('监控分类保留服务端字符串 ID 并优先展示 Web 的 display_type', async () => {
  const adapter = await readProjectFile('src/features/monitor/adapter.ts');
  assert.match(adapter, /id:\s*text\(type\.id \|\| item\.type\)/);
  assert.match(adapter, /displayName:\s*text\(item\.display_type \|\| type\.name \|\| item\.type\)/);
  assert.doesNotMatch(adapter, /type:\s*\{\s*id:\s*number\(type\.id\)/);
});

test('监控指标查询严格转义实例值并只替换 Web labels 占位符', async () => {
  const { buildMetricQuery } = await loadModel('src/features/monitor/model.ts');
  const result = buildMetricQuery({ query: 'up{__$labels__}', instanceIdKeys: ['host'], id: 1 }, ['a.b"c']);
  assert.equal(result, 'up{host=~"a\\\\.b\\"c"}');

  const adapter = await readProjectFile('src/features/monitor/adapter.ts');
  assert.match(adapter, /query:\s*text\(item\.query\)/);
  assert.doesNotMatch(adapter, /item\.view_query\s*\|\|\s*item\.query/);
});

test('监控详情兼容 Server 指标目录的分页响应', async () => {
  const { monitorCatalogItems } = await loadModel('src/features/monitor/model.ts');
  const items = [{ id: 1 }, { id: 2 }];
  assert.deepEqual(monitorCatalogItems(items), items);
  assert.deepEqual(monitorCatalogItems({ count: 2, items }), items);
  assert.deepEqual(monitorCatalogItems({ count: 0, items: [] }), []);
  assert.deepEqual(monitorCatalogItems({ count: 2, results: items }), []);

  const adapter = await readProjectFile('src/features/monitor/adapter.ts');
  assert.match(adapter, /monitorCatalogItems\(unwrap<unknown>\(groupRaw\)\)/);
  assert.match(adapter, /monitorCatalogItems\(unwrap<unknown>\(metricRaw\)\)/);
});

test('监控曲线丢弃非有限值，缺口由 gaps 断线并保留连续段', async () => {
  const {
    chartDataToMetricSeries,
    metricSeriesPoints,
    metricSeriesToChartData,
  } = await loadModel('src/features/monitor/model.ts');
  const {
    attachGapIntervals,
    getChartDataWithGapBreaks,
    getRenderedGapIntervals,
  } = await loadModel('src/features/monitor/gap-intervals.ts');
  const {
    buildSeriesPath,
    buildSeriesSinglePoint,
    metricAxisTimeOptions,
  } = await loadModel('src/features/monitor/metric-chart-utils.ts');

  // 与 Web renderChart 一致：API null 不进入序列。
  const series = metricSeriesPoints({
    unit: 'percent',
    startMs: 0,
    endMs: 4_000,
    gaps: [],
    series: [{
      metric: { instance_id: 'host-1' },
      values: [[1, '1'], [2, null], [3, '3'], [4, '4']],
    }],
  });
  assert.deepEqual(series[0].points, [[1, 1], [3, 3], [4, 4]]);

  const gaps = [{
    start: 1.5,
    end: 2.5,
    duration: 1,
    series: [{ metric: { instance_id: 'host-1' }, missing_points: 1 }],
  }];
  const chartData = attachGapIntervals(metricSeriesToChartData(series), gaps);
  const broken = getChartDataWithGapBreaks(chartData, gaps, [0, 4]);
  const prepared = chartDataToMetricSeries(broken, series);
  assert.ok(prepared[0].points.some((point) => point[1] === null), '缺口中点应注入 null 断线');
  assert.ok(prepared[0].points.filter((point) => point[1] !== null).length >= 3);

  const rendered = getRenderedGapIntervals(chartData, gaps, [0, 4]);
  assert.equal(rendered.length, 1);
  assert.ok(rendered[0].start >= 0 && rendered[0].end <= 4);

  // 卡片 sparkline：只连有效点，单点打圆；详情主图不走孤立点打点。
  const path = buildSeriesPath(series[0].points);
  assert.equal((path.match(/M /g) || []).length, 1);
  assert.equal((path.match(/L /g) || []).length, 2);
  assert.deepEqual(buildSeriesSinglePoint([[1, 19]]), { cx: 50, cy: 18 });
  assert.equal(buildSeriesSinglePoint(series[0].points), null);

  // 常量序列应对齐 Web mini-trend：垂直居中，不贴底。
  const flatPath = buildSeriesPath([[1, 0], [2, 0], [3, 0]]);
  const flatYs = [...flatPath.matchAll(/[\d.]+ ([\d.]+)/g)].map((match) => Number(match[1]));
  assert.ok(flatYs.length >= 2);
  assert.ok(flatYs.every((y) => y > 10 && y < 24), `flat sparkline should be vertically centered, got y=${flatYs.join(',')}`);

  // 完整时间窗下，靠后的数据应落在右侧（与 Web 7 天小图观感一致）。
  const windowed = buildSeriesPath(
    [[8, 10], [9, 20], [10, 15]],
    100,
    34,
    6,
    4,
    { startMs: 0, endMs: 10_000 },
  );
  const windowXs = [...windowed.matchAll(/([\d.]+) [\d.]+/g)].map((match) => Number(match[1]));
  assert.ok(windowXs[0] >= 70, `late data should sit on the right, got x=${windowXs.join(',')}`);

  // 7 天窗 → MM-DD HH:mm；1 小时窗 → HH:mm:ss
  assert.deepEqual(metricAxisTimeOptions(7 * 24 * 60 * 60 * 1000), {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
  assert.deepEqual(metricAxisTimeOptions(60 * 60 * 1000), {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
});

test('监控 Y 轴 nice 刻度与 Web lineChart 对齐', async () => {
  const {
    buildMetricNiceAxis,
    buildMetricYAxisDomain,
    formatMetricAxisNumber,
    getMetricNiceStep,
  } = await loadModel('src/features/monitor/metric-chart-utils.ts');
  assert.equal(getMetricNiceStep(3), 5);
  assert.equal(getMetricNiceStep(0.7), 1);
  assert.deepEqual(buildMetricYAxisDomain([0]), [0, 1]);
  const padded = buildMetricYAxisDomain([20, 30]);
  assert.ok(padded[0] <= 20);
  assert.ok(padded[0] >= 0);
  assert.ok(padded[1] >= 30);
  const nice = buildMetricNiceAxis(padded, 3);
  assert.equal(nice.ticks[0], nice.domain[0]);
  assert.equal(nice.ticks[nice.ticks.length - 1], nice.domain[1]);
  assert.ok(nice.interval > 0);
  assert.equal(formatMetricAxisNumber(20), '20');
  assert.equal(formatMetricAxisNumber(20.5), '20.5');
});

test('最终单位使用 query_range 响应，而不是指标定义的初始单位', async () => {
  const [card, sheet] = await Promise.all([
    readProjectFile('src/features/monitor/metric-card.tsx'),
    readProjectFile('src/features/monitor/metric-chart-sheet.tsx'),
  ]);
  assert.match(card, /setDisplayUnit\(result\.unit\)/);
  assert.match(card, /resolveMonitorUnitLabel\(metric\.unit,\s*displayUnit,\s*unitList\)/);
  assert.match(sheet, /onUnitChange\?\.\(result\.unit\)/);
  assert.match(sheet, /resolveMonitorUnitLabel\(metric\.unit,\s*displayUnits\[metric\.id\],\s*unitList\)/);
});

test('实例列表按元数据顺序展示全部指标列，空值保留为 null', async () => {
  const {
    buildDisplayMetricUnitIndex,
    displayFieldKey,
    formatMonitorTableMetricValue,
    instanceListSummaryEntries,
    instanceSummaryEntries,
    parseMonitorInstanceLookupHints,
    resolveEnumMetricLabel,
    resolveMonitorReportingStatus,
  } = await loadModel('src/features/monitor/model.ts');
  assert.equal(parseMonitorInstanceLookupHints("('mobile-demo-host-01',)").name, 'mobile-demo-host-01');
  assert.deepEqual(parseMonitorInstanceLookupHints("('mobile-demo-host-01',)").idValues, ['mobile-demo-host-01']);
  assert.equal(resolveMonitorReportingStatus('normal'), 'normal');
  assert.equal(resolveMonitorReportingStatus('unavailable'), 'unavailable');
  assert.equal(resolveMonitorReportingStatus('offline'), 'unavailable');
  assert.equal(resolveMonitorReportingStatus(''), '');
  assert.equal(displayFieldKey('Host', 'cpu_usage'), 'Host::cpu_usage');
  assert.equal(displayFieldKey('Host', 'node_info', 'ip'), 'field::Host::node_info::ip');
  assert.equal(formatMonitorTableMetricValue('32.926286000000005', '%', 'cpu_usage'), '32.93');
  assert.equal(formatMonitorTableMetricValue('12.0', 'counts', 'request_count'), '12');
  assert.equal(formatMonitorTableMetricValue('12.5', 'counts', 'cluster_node_count'), '12.5');
  assert.equal(formatMonitorTableMetricValue('unknown', '%', 'cpu_usage'), 'unknown');
  const object = {
    displayFields: [
      {
        key: 'metric:cpu',
        name: 'CPU使用率',
        type: 'metric',
        order: 0,
        metrics: [{ plugin: 'Host', metric: 'cpu_usage', field: '' }],
      },
      {
        key: 'metric:mem',
        name: '内存使用率',
        type: 'metric',
        order: 1,
        metrics: [{ plugin: 'Host', metric: 'mem_usage', field: '' }],
      },
      {
        key: 'metric:disk',
        name: '磁盘使用率',
        type: 'metric',
        order: 2,
        metrics: [{ plugin: 'Host', metric: 'disk_usage', field: '' }],
      },
      {
        key: 'metric:io',
        name: 'IO等待',
        type: 'metric',
        order: 3,
        metrics: [{ plugin: 'Host', metric: 'io_wait', field: '' }],
      },
    ],
  };
  const instance = {
    raw: {
      'Host::cpu_usage': { value: '12.5', unit: '%' },
      'Host::mem_usage': '',
      'Host::disk_usage': { value: '70', unit: '%' },
    },
    facts: {},
  };
  assert.deepEqual(instanceListSummaryEntries(object, instance), [
    { label: 'CPU使用率', value: '12.50%' },
    { label: '内存使用率', value: null },
    { label: '磁盘使用率', value: '70.00%' },
    { label: 'IO等待', value: null },
  ]);
  assert.deepEqual(instanceSummaryEntries(object, instance, 4), [
    { label: 'CPU使用率', value: '12.50%' },
    { label: '磁盘使用率', value: '70.00%' },
  ]);

  const enumObject = {
    displayFields: [{
      key: 'metric:probe',
      name: '探测结果',
      type: 'metric',
      order: 0,
      metrics: [{ plugin: 'Website', metric: 'probe_success', field: '' }],
    }],
  };
  const enumInstance = {
    raw: { 'Website::probe_success': { value: '1', unit: '' } },
    facts: {},
  };
  const enumUnits = buildDisplayMetricUnitIndex([{
    name: 'probe_success',
    pluginName: 'Website',
    unit: JSON.stringify([{ id: 0, name: '失败' }, { id: 1, name: '成功' }]),
  }]);
  assert.equal(resolveEnumMetricLabel(enumUnits.get('Website::probe_success'), '1'), '成功');
  assert.deepEqual(instanceListSummaryEntries(enumObject, enumInstance, 1, enumUnits), [
    { label: '探测结果', value: '成功' },
  ]);
  assert.deepEqual(instanceListSummaryEntries(enumObject, enumInstance, 1), [
    { label: '探测结果', value: '1.00' },
  ]);
});

test('实例列表会拉取 display_fields 指标 unit 以映射枚举摘要', async () => {
  const [adapter, panel] = await Promise.all([
    readProjectFile('src/features/monitor/adapter.ts'),
    readProjectFile('src/features/monitor/instances-panel.tsx'),
  ]);
  assert.match(adapter, /listDisplayFieldMetrics/);
  assert.match(adapter, /name_in:\s*names\.join\(','\)/);
  assert.match(panel, /listDisplayFieldMetrics\(monitorObject\.id/);
  assert.match(panel, /instanceListSummaryEntries\(monitorObject, instance, undefined, metricUnits\)/);
});

test('实例列表面板把摘要指标放进表格列并支持横向滚动', async () => {
  const [panel, styles, adapter] = await Promise.all([
    readProjectFile('src/features/monitor/instances-panel.tsx'),
    readProjectFile('src/features/monitor/monitor.module.css'),
    readProjectFile('src/features/monitor/adapter.ts'),
  ]);
  assert.match(panel, /instanceListSummaryEntries\(monitorObject, instance, undefined, metricUnits\)/);
  assert.match(panel, /summaryFields\.map/);
  assert.match(panel, /columnReportTime|columnReportingStatus/);
  assert.match(panel, /resolveMonitorReportingStatus/);
  assert.match(panel, /monitor\.reportingStatus\./);
  assert.match(panel, /statusTag/);
  assert.doesNotMatch(panel, /sortMonitorInstances/);
  // 运维阅读顺序：名称 → 上报状态 → 上报时间 → 全部 display_fields
  assert.match(
    panel,
    /columnName[\s\S]*columnReportingStatus[\s\S]*columnReportTime[\s\S]*summaryFields\.map/,
  );
  assert.doesNotMatch(panel, /slice\(0,\s*INSTANCE_LIST_SUMMARY_LIMIT\)|INSTANCE_LIST_SUMMARY_LIMIT/);
  assert.doesNotMatch(panel, /onTouchStart|onTouchEnd/);
  assert.match(panel, /data-instance-table-scroll/);
  assert.doesNotMatch(panel, /styles\.instanceMetrics/);
  assert.doesNotMatch(panel, /primaryField/);
  assert.match(styles, /\.instanceTableScroll\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(styles, /\.colSticky\s*\{[^}]*position:\s*sticky/s);
  assert.match(adapter, /add_metrics:\s*true/);
  assert.match(adapter, /metrics:\s*\(Array\.isArray\(meta\.metrics\)/);
  // 无数据时仍保留表头（含上报状态筛选），空态落在表体内。
  assert.match(panel, /instanceTableEmpty/);
  assert.match(panel, /instances\.length === 0[\s\S]*instanceTableEmpty[\s\S]*MobileResult/);
  assert.match(styles, /\.instanceTableEmpty\s*\{/);
});

test('最近查看的“昨天”按账号时区计算', async () => {
  const { formatRecentViewTime } = await loadModel('src/features/monitor/model.ts');
  const labels = { justNow: '刚刚', minutes: '{count}分钟前', hours: '{count}小时前', yesterday: '昨天' };
  assert.equal(formatRecentViewTime(
    '2026-08-10T15:30:00.000Z',
    { locale: 'zh-CN', timezone: 'America/Los_Angeles' },
    labels,
    Date.parse('2026-08-11T16:30:00.000Z'),
  ), '昨天');
});

test('最近查看默认 Tab 在前且详情成功后会记录浏览', async () => {
  const [page, detail, storage, panel, styles] = await Promise.all([
    readProjectFile('src/app/monitor/page.tsx'),
    readProjectFile('src/app/monitor/detail/page.tsx'),
    readProjectFile('src/features/monitor/recent-views-storage.ts'),
    readProjectFile('src/features/monitor/recent-views-panel.tsx'),
    readProjectFile('src/features/monitor/monitor.module.css'),
  ]);
  assert.match(page, /key="recent"[\s\S]*key="all"/);
  assert.match(page, /activeTab.*'recent'/);
  assert.match(page, /MonitorRecentViewsPanel/);
  assert.doesNotMatch(page, /recentPlaceholder/);
  assert.match(storage, /recordRecentView/);
  assert.match(storage, /bk_lite_mobile_monitor_recent_views|localStorage/);
  assert.match(detail, /recordRecentView/);
  assert.match(detail, /status !== 'ready'/);
  assert.match(detail, /!userInfo\?\.id/);
  assert.doesNotMatch(detail, /userInfo\?\.id \|\| 0/);
  assert.match(panel, /formatRecentViewTime/);
  assert.match(panel, /returnTab: 'recent'/);
  assert.match(panel, /instanceSummaryEntries/);
  assert.match(panel, /recentMetricsLine/);
  assert.match(panel, /recentMetricLabel/);
  assert.match(panel, /recentStatusText/);
  assert.match(panel, /recentMetaLine/);
  assert.match(panel, /recentViewedAt/);
  assert.doesNotMatch(panel, /monitor\.viewedAtLabel/);
  assert.match(panel, /monitor\.lastReportedLabel/);
  assert.match(panel, /size=\{26\}/);
  assert.match(styles, /\.recentRowIcon[\s\S]*?width:\s*26px/);
  assert.match(styles, /\.recentRow\s*\{[^}]*align-items:\s*start/s);
  assert.match(styles, /\.recentRow\s*\{[^}]*align-content:\s*center/s);
  assert.doesNotMatch(panel, /recentStatusInline/);
  assert.doesNotMatch(panel, /recentMetricValueEmpty/);
  assert.match(styles, /\.recentStatusText\[data-status='unavailable'\]\s*\{\s*color:\s*var\(--color-fail\)/);
  assert.match(styles, /\.recentStatusText\[data-status='normal'\]\s*\{\s*color:\s*var\(--color-success\)/);
  const { normalizeRecentViews, MAX_RECENT_VIEWS } = await loadModel('src/features/monitor/model.ts');
  assert.equal(MAX_RECENT_VIEWS, 20);
  const config = normalizeRecentViews({ items: Array.from({ length: 25 }, (_, index) => ({
    object_id: 1,
    instance_id: `host-${index}`,
    viewed_at: new Date(index * 1000).toISOString(),
  })) });
  assert.equal(config.items.length, 20);
});

test('监控请求始终带 objectId 且指标按视口懒加载', async () => {
  const [panel, adapter, card] = await Promise.all([
    readProjectFile('src/features/monitor/instances-panel.tsx'),
    readProjectFile('src/features/monitor/adapter.ts'),
    readProjectFile('src/features/monitor/metric-card.tsx'),
  ]);
  assert.match(adapter, /monitor_instance\/\$\{objectId\}\/list/);
  assert.match(adapter, /add_metrics:\s*true/);
  assert.match(adapter, /effective_plugins/);
  assert.match(adapter, /metrics_instance\/query_by_metric_range/);
  assert.match(adapter, /monitor_object_id:\s*monitorObjectId/);
  assert.match(adapter, /metric_id:\s*metricId/);
  assert.match(adapter, /instance_ids:\s*\[instanceId\]/);
  assert.doesNotMatch(adapter, /metrics_instance\/query_range/);
  assert.match(card, /IntersectionObserver/);
  assert.doesNotMatch(panel, /localStorage/);
});

test('监控与资产根页由限高滚动容器承载下拉刷新内容', async () => {
  const [panel, monitorStyles, assets, assetPanel, assetStyles] = await Promise.all([
    readProjectFile('src/features/monitor/instances-panel.tsx'),
    readProjectFile('src/features/monitor/monitor.module.css'),
    readProjectFile('src/app/assets/page.tsx'),
    readProjectFile('src/features/assets/all-assets-panel.tsx'),
    readProjectFile('src/features/assets/assets.module.css'),
  ]);
  assert.match(panel, /<div[\s\S]*className=\{styles\.scroll\}[\s\S]*?<MobilePullToRefresh/);
  assert.doesNotMatch(panel, /<MobilePullToRefresh[^>]*><div className=\{styles\.scroll\}>/);
  assert.match(assets, /<div[\s\S]*className=\{styles\.scroll\}[\s\S]*?<MobilePullToRefresh/);
  assert.match(assetPanel, /<div[\s\S]*className=\{styles\.scroll\}[\s\S]*?<MobilePullToRefresh/);
  assert.doesNotMatch(assets, /<MobilePullToRefresh[^>]*><div className=\{styles\.scroll\}>/);
  assert.doesNotMatch(assetPanel, /<MobilePullToRefresh[^>]*><div className=\{styles\.scroll\}>/);
  for (const styles of [monitorStyles, assetStyles]) {
    assert.match(styles, /\.scroll\s*\{[^}]*flex:\s*1[^}]*min-height:\s*0[^}]*overflow-y:\s*auto/s);
    assert.match(styles, /\.refreshContent\s*\{[^}]*min-height:\s*100%/s);
  }
});

test('关注配置与 Web 同结构、倒序且最多保留 100 条', async () => {
  const { addFollowedAsset, assetRequestErrorKind, normalizeFollowedConfig, serializeFollowedConfig } = await loadModel('src/features/assets/model.ts');
  const config = normalizeFollowedConfig({ items: [
    { model_id: 'host', inst_id: 1, followed_at: '2026-01-01T00:00:00Z' },
    { model_id: 'host', inst_id: 'bbbbbbbb-bbbb-4ccc-8ddd-eeeeeeeeeeee', followed_at: '2026-01-15T00:00:00Z' },
    { model_id: 'host', inst_uuid: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', followed_at: '2026-02-01T00:00:00Z' },
  ] });
  assert.deepEqual(config.items.map((item) => item.instanceId), [
    'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
    'bbbbbbbb-bbbb-4ccc-8ddd-eeeeeeeeeeee',
  ]);
  let many = { items: [] };
  for (let index = 0; index < 105; index += 1) many = addFollowedAsset(many, 'host', index, new Date(index * 1000).toISOString());
  assert.equal(many.items.length, 100);
  assert.deepEqual(Object.keys(serializeFollowedConfig(config).items[0]), ['model_id', 'inst_uuid', 'followed_at']);
  assert.equal(assetRequestErrorKind(new Error('API Error: 403')), 'forbidden');
  assert.equal(assetRequestErrorKind(new Error('API Error: 404')), 'missing');
  assert.equal(assetRequestErrorKind(new Error('API Error: 400 - 请使用 inst_uuid 定位实例')), 'missing');
});

test('资产列表把 search 响应的 inst_uuid 当主键，不因缺少 _id 被滤空', async () => {
  const { keepMappedAssetInstance, mapAssetInstance } = await loadModel('src/features/assets/model.ts');
  const insts = Array.from({ length: 5 }, (_, index) => ({
    inst_name: `MOBILE-UX-DEMO-ASSET-0${index + 1}`,
    inst_uuid: `aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeee0${index + 1}`,
    model_id: 'mobile_ux_demo_asset',
    organization_display: '默认组织',
  }));
  const items = insts.map((item) => mapAssetInstance(item, 'mobile_ux_demo_asset')).filter(keepMappedAssetInstance);
  assert.equal(items.length, 5);
  assert.equal(items[0].id, 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeee01');
  assert.equal(items[0].name, 'MOBILE-UX-DEMO-ASSET-01');
  assert.equal(items[0].organizationName, '默认组织');
  assert.equal(keepMappedAssetInstance(mapAssetInstance({ inst_name: 'ghost' }, 'host')), false);
  assert.equal(keepMappedAssetInstance(mapAssetInstance({ _id: 12, inst_name: 'legacy' }, 'host')), false);
});

test('资产复用 Web CMDB 接口、两阶段搜索和元数据字段详情', async () => {
  const [adapter, detail, search] = await Promise.all([
    readProjectFile('src/features/assets/adapter.ts'), readProjectFile('src/app/assets/detail/page.tsx'), readProjectFile('src/app/assets/search/page.tsx'),
  ]);
  assert.match(adapter, /cmdb_followed_assets|FOLLOWED_ASSETS_CONFIG_KEY/);
  assert.match(adapter, /fulltext_search\/stats/);
  assert.match(adapter, /fulltext_search\/by_model/);
  assert.match(adapter, /field_groups\/full_info/);
  assert.match(adapter, /mapAssetInstance/);
  assert.match(adapter, /field: 'inst_uuid', type: 'str\[\]'/);
  assert.match(adapter, /encodeURIComponent\(String\(instanceId\)\)/);
  assert.doesNotMatch(adapter, /item\._id as string/);
  assert.doesNotMatch(adapter, /field: 'id', type: 'id\[\]'/);
  // 模型内筛选须用 str*（contains）；裸 type "str" 会被 CMDB format_search_params 静默跳过
  assert.match(adapter, /field:\s*'inst_name',\s*type:\s*'str\*',\s*value:\s*keyword/);
  assert.doesNotMatch(adapter, /field:\s*'inst_name',\s*type:\s*'str',\s*value:\s*keyword/);
  assert.match(detail, /group\.fields\.map/);
  assert.match(detail, /getFollowedConfig\(\)[\s\S]*updateFollowedConfig/);
  // 详情字段须读 `${field.id}_display`，否则组织/用户等会落到原始 ID
  assert.match(detail, /assetValueText\([\s\S]*asset\.values\[`\$\{field\.id\}_display`\]/);
  assert.match(search, /canAccess\('assets', 'Search'\)/);
  assert.doesNotMatch(`${adapter}\n${detail}\n${search}`, /assetSearchHistory|mock|fixture/i);
});

test('资产详情字段展示优先 *_display，不把组织/用户原始 ID 当文案', async () => {
  const { assetValueText } = await loadModel('src/features/assets/model.ts');
  const time = (value) => `T:${value}`;
  const org = { id: 'organization', name: '组织', type: 'organization', option: null, order: 1 };
  assert.equal(assetValueText(org, [1], 'Yes', 'No', time, '默认组织'), '默认组织');
  assert.equal(assetValueText(org, [1], 'Yes', 'No', time), '--');
  assert.equal(assetValueText(org, [1], 'Yes', 'No', time, ''), '--');

  const user = { id: 'owner', name: '负责人', type: 'user', option: null, order: 2 };
  assert.equal(assetValueText(user, [9], 'Yes', 'No', time, '管理员(admin)'), '管理员(admin)');
  assert.equal(assetValueText(user, [9], 'Yes', 'No', time), '--');

  const status = {
    id: 'status',
    name: '状态',
    type: 'enum',
    option: [{ id: '1', name: '运行中' }, { id: 2, name: '已停止' }],
    order: 3,
  };
  assert.equal(assetValueText(status, '1', 'Yes', 'No', time, '运行中'), '运行中');
  assert.equal(assetValueText(status, 2, 'Yes', 'No', time), '已停止');
  assert.equal(assetValueText(status, ['1', '2'], 'Yes', 'No', time), '运行中, 已停止');

  const pwd = { id: 'password', name: '密码', type: 'pwd', option: null, order: 4 };
  assert.equal(assetValueText(pwd, 'secret', 'Yes', 'No', time), '***');
  assert.equal(assetValueText(pwd, '', 'Yes', 'No', time), '--');

  const tag = { id: 'tags', name: '标签', type: 'tag', option: null, order: 5 };
  assert.equal(assetValueText(tag, ['env:prod'], 'Yes', 'No', time, 'env:prod'), 'env:prod');
  assert.equal(assetValueText(tag, [{ value: 'app:web' }], 'Yes', 'No', time), 'app:web');

  const file = { id: 'doc', name: '附件', type: 'attachment', option: null, order: 6 };
  assert.equal(assetValueText(file, [{ file_id: 'f1', file_name: 'report.pdf' }], 'Yes', 'No', time, 'wrong display'), 'report.pdf');

  assert.equal(assetValueText({ id: 'online', name: '在线', type: 'bool', option: null, order: 7 }, true, 'Yes', 'No', time), 'Yes');
  assert.equal(assetValueText({ id: 'online', name: '在线', type: 'bool', option: null, order: 7 }, 'false', 'Yes', 'No', time), 'No');
  assert.equal(assetValueText({ id: 'ts', name: '时间', type: 'time', option: null, order: 8 }, '2026-01-01', 'Yes', 'No', time), 'T:2026-01-01');
});

test('资产表格、附件和图片保留结构化数据并复用 Web 文件直链接口', async () => {
  const {
    parseAssetFiles,
    parseAssetTableColumns,
    parseAssetTableRows,
  } = await loadModel('src/features/assets/model.ts');
  assert.deepEqual(parseAssetTableColumns([
    { column_id: 'port', column_name: '端口', column_type: 'number', order: 2 },
    { column_id: 'name', column_name: '名称', column_type: 'str', order: 1 },
  ]).map((item) => item.id), ['name', 'port']);
  assert.deepEqual(parseAssetTableRows('[{"name":"ssh","port":22}]'), [{ name: 'ssh', port: 22 }]);
  assert.deepEqual(parseAssetFiles('[{"file_id":"f1","file_name":"a.png","file_size":12}]'), [
    { fileId: 'f1', fileName: 'a.png', fileSize: 12, mimeType: '' },
  ]);

  const [adapter, detail, structured, styles] = await Promise.all([
    readProjectFile('src/features/assets/adapter.ts'),
    readProjectFile('src/app/assets/detail/page.tsx'),
    readProjectFile('src/features/assets/asset-structured-field.tsx'),
    readProjectFile('src/features/assets/assets.module.css'),
  ]);
  assert.match(adapter, /download_file\/\$\{encodeURIComponent\(fileId\)\}/);
  assert.match(adapter, /download:\s*1/);
  assert.match(detail, /AssetStructuredField/);
  assert.match(structured, /parseAssetTableRows|parseAssetFiles/);
  assert.match(structured, /getAssetFileUrl/);
  assert.match(styles, /\.structuredTableScroll\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(styles, /\.assetImagePreview\s*\{/);
});

test('资产列表卡片复用真实数据，不以模型首字母伪装图标', async () => {
  const [component, home, panel, search] = await Promise.all([
    readProjectFile('src/features/assets/asset-list-card.tsx'),
    readProjectFile('src/app/assets/page.tsx'),
    readProjectFile('src/features/assets/all-assets-panel.tsx'),
    readProjectFile('src/app/assets/search/page.tsx'),
  ]);
  for (const page of [home, panel, search]) assert.match(page, /AssetListCard/);
  assert.match(component, /asset\.organizationName/);
  assert.match(component, /asset\.values\.ip_addr/);
  assert.match(component, /showModel/);
  assert.match(component, /styles\.assetRow/);
  assert.match(component, /assetLead|AppstoreOutline/);
  assert.match(component, /getStableTypeStyle|assetMetaSwatch/);
  assert.match(component, /resolveAssetModelIconUrl|modelIcon/);
  assert.doesNotMatch(component, /charAt\(0\)|MobileListCard|raised|assetTag/);
});

test('资产根页使用顶栏假搜索框入口并继续进入既有精确搜索页', async () => {
  const [home, search, styles, header] = await Promise.all([
    readProjectFile('src/app/assets/page.tsx'),
    readProjectFile('src/app/assets/search/page.tsx'),
    readProjectFile('src/features/assets/assets.module.css'),
    readProjectFile('src/components/mobile-page-header/index.tsx'),
  ]);

  assert.match(home, /searchEntry=\{searchAllowed \? \{[\s\S]*href:\s*'\/assets\/search'/);
  assert.match(home, /placeholder:\s*t\('assets\.search'\)/);
  assert.doesNotMatch(home, /SearchOutline/);
  assert.doesNotMatch(home, /searchLauncher|searchField/);
  assert.doesNotMatch(home, /searchLauncherHint/);
  assert.match(header, /searchEntry/);
  assert.match(header, /styles\.searchEntry/);
  assert.match(search, /<Switch[\s\S]*checked=\{exact\}/);
  assert.doesNotMatch(styles, /\.searchLauncher\s*\{/);
  assert.doesNotMatch(styles, /\.searchField\s*\{/);
});

test('监控实例名称搜索走 list 接口而非特殊 search', async () => {
  const adapter = await readProjectFile('src/features/monitor/adapter.ts');
  assert.match(adapter, /listMonitorInstances\([\s\S]*monitor_instance\/\$\{objectId\}\/list\//);
  assert.doesNotMatch(adapter, /monitor_instance\/\$\{objectId\}\/search\//);
  assert.match(adapter, /name: keyword\.trim\(\)/);
});

test('监控全部实例支持上报状态表头筛选并写入 vm_params[status]', async () => {
  const [adapter, panel, zh, en] = await Promise.all([
    readProjectFile('src/features/monitor/adapter.ts'),
    readProjectFile('src/features/monitor/instances-panel.tsx'),
    readProjectFile('src/locales/zh.json'),
    readProjectFile('src/locales/en.json'),
  ]);
  const { normalizeReportingStatusFilters } = await loadModel('src/features/monitor/model.ts');

  assert.deepEqual(normalizeReportingStatusFilters(['normal']), ['normal']);
  assert.deepEqual(normalizeReportingStatusFilters(['unavailable']), ['unavailable']);
  assert.deepEqual(normalizeReportingStatusFilters(['normal', 'unavailable']), []);
  assert.deepEqual(normalizeReportingStatusFilters([]), []);
  assert.deepEqual(normalizeReportingStatusFilters(['bogus', 'normal']), ['normal']);

  assert.match(adapter, /vm_params\[status\]/);
  assert.match(adapter, /normalizeReportingStatusFilters/);
  assert.match(panel, /FilterOutline/);
  assert.match(panel, /filterReportingStatus/);
  assert.match(panel, /statusFilters/);
  assert.match(panel, /openStatusFilter|applyStatusFilter/);
  assert.match(panel, /status:\s*statusFilters/);
  assert.match(panel, /setStatusFilters\(\[\]\)/);
  assert.match(zh, /"filterReportingStatus"/);
  assert.match(en, /"filterReportingStatus"/);
  assert.match(zh, /"resetFilter"/);
  assert.match(en, /"resetFilter"/);
});

test('监控根页「全部实例」直接展示实例面板，旧 instances 路由回跳根页', async () => {
  const [page, panel, instancesPage, detailPage] = await Promise.all([
    readProjectFile('src/app/monitor/page.tsx'),
    readProjectFile('src/features/monitor/instances-panel.tsx'),
    readProjectFile('src/app/monitor/instances/page.tsx'),
    readProjectFile('src/app/monitor/detail/page.tsx'),
  ]);

  assert.match(page, /MonitorInstancesPanel/);
  assert.match(page, /MonitorRecentViewsPanel/);
  assert.match(page, /monitor\.tabs\.all/);
  assert.match(page, /monitor\.tabs\.recent/);
  assert.match(page, /activeTab === 'recent'/);
  assert.doesNotMatch(page, /objectTree|setExpanded|href=\{`\/monitor\/instances/);
  assert.match(panel, /listMonitorObjects/);
  assert.match(panel, /listMonitorInstances/);
  assert.match(panel, /orderedMonitorObjects|objectChip/);
  assert.match(panel, /objectChipCount/);
  assert.match(panel, /<Popup/);
  assert.match(panel, /instanceRow/);
  assert.match(panel, /MonitorObjectIcon|objectIcon/);
  assert.match(panel, /objectIcon:/);
  assert.match(panel, /shouldShowListPagination|MONITOR_PAGE_SIZE/);
  assert.match(panel, /router\.replace\(`\/monitor\?\$\{nextParams\.toString\(\)\}`\)/);
  assert.match(panel, /MobileSearchBar|<SearchBar/);
  assert.match(panel, /<MobilePullToRefresh/);
  assert.match(instancesPage, /router\.replace/);
  assert.match(instancesPage, /\/monitor\?/);
  assert.match(detailPage, /returnTab === 'recent'/);
  assert.match(detailPage, /recordRecentView/);
  assert.match(detailPage, /<MobilePageHeader[\s\S]*backHref=\{backHref\}/);
  assert.match(detailPage, /MonitorObjectIcon/);
  assert.match(detailPage, /objectIcon/);
  assert.match(detailPage, /DetailMetricsSkeleton|detailMetricsLoading/);
  assert.doesNotMatch(detailPage, /detailTabs|MobileSegmentTabs|activeTab === 'about'/);
  assert.doesNotMatch(panel, /facts:/);
  assert.match(detailPage, /groupToggle|expandedGroups/);
  assert.match(detailPage, /pluginSwitch|selectPluginTitle/);
  assert.match(detailPage, /<Popup/);
  assert.match(detailPage, /heroCard|heroFactLabel/);
  assert.match(detailPage, /toolCard|rangeSeg/);
  assert.match(detailPage, /showPluginPicker/);
  assert.match(detailPage, /initialExpandedGroupIds/);
  assert.match(detailPage, /groupCard|metricStack/);
  assert.match(detailPage, /MetricChartSheet|metricSheetIndex/);
  assert.match(await readProjectFile('src/features/monitor/metric-card.tsx'), /onOpen/);
  assert.match(await readProjectFile('src/features/monitor/metric-chart-sheet.tsx'), /MetricSheetEcharts|metricSheetChartWrap/);
  assert.match(await readProjectFile('src/features/monitor/metric-chart-utils.ts'), /formatMetricDisplay|formatMetricValue\(value, unit\)/);
  assert.match(await readProjectFile('src/features/monitor/metric-sheet-echarts.tsx'), /echarts-setup|tooltip|axisPointer/);
  assert.match(await readProjectFile('src/features/monitor/metric-sheet-echarts.tsx'), /buildMetricNiceAxis|formatMetricAxisNumber|showSymbol:\s*false/);
  assert.match(await readProjectFile('src/features/monitor/metric-sheet-echarts.tsx'), /min:\s*startMs|max:\s*endMs|getRenderedGapIntervals|GAP_FILL_COLOR|markArea/);
  assert.match(await readProjectFile('src/features/monitor/metric-chart-utils.ts'), /export function buildMetricNiceAxis|export function formatMetricAxisNumber|export function metricAxisTimeOptions|export function buildSeriesSinglePoint/);
  assert.match(await readProjectFile('src/features/monitor/echarts-setup.ts'), /LineChart|CanvasRenderer|AxisPointerComponent|MarkAreaComponent|MarkLineComponent/);
  assert.match(await readProjectFile('src/features/monitor/metric-chart-utils.ts'), /export function pickPointByRatio/);
  assert.match(await readProjectFile('src/features/monitor/gap-intervals.ts'), /getChartDataWithGapBreaks|getRenderedGapIntervals|attachGapIntervals/);
  assert.match(await readProjectFile('src/features/monitor/adapter.ts'), /gaps:|startMs:|endMs:|detect_gaps:\s*true/);
  assert.match(await readProjectFile('src/features/monitor/metric-chart-sheet.tsx'), /setGaps\(result\.gaps\)|startMs=\{windowMs\.startMs\}/);
  assert.match(await readProjectFile('src/features/monitor/metric-card.tsx'), /buildSeriesSinglePoint|chartPoint/);
  assert.doesNotMatch(await readProjectFile('src/features/monitor/metric-sheet-echarts.tsx'), /metricPointSymbolSize/);
  assert.match(await readProjectFile('package.json'), /"echarts"/);
  const monitorStyles = await readProjectFile('src/features/monitor/monitor.module.css');
  assert.match(monitorStyles, /\.metricSheetChart\s*\{[^}]*min-height:\s*180px/s);
  assert.match(monitorStyles, /\.heroCard\s*\{/);
  assert.match(monitorStyles, /\.toolCard\s*\{/);
  assert.match(monitorStyles, /\.metricGrid\s*\{[^}]*grid-template-columns:\s*repeat\(2/s);
  assert.match(detailPage, /getMonitorInstance\(/);
  assert.match(detailPage, /setInstanceStatus\(/);
  assert.match(detailPage, /setLastReportedAt\(/);
});

test('监控详情头部通过现有 list 接口回源状态与上报时间', async () => {
  const adapter = await readProjectFile('src/features/monitor/adapter.ts');
  const fn = adapter.slice(
    adapter.indexOf('export async function getMonitorInstance'),
    adapter.indexOf('export async function listEffectivePlugins'),
  );
  assert.match(fn, /monitor_instance\/\$\{objectId\}\/list\//);
  assert.match(fn, /instance_id:\s*instanceId/);
  assert.match(fn, /add_metrics:\s*hints\.addMetrics\s*\?\?\s*false/);
  assert.match(fn, /item\.id === instanceId/);
  assert.doesNotMatch(fn, /name:\s*keyword/);
  assert.doesNotMatch(fn, /parseMonitorInstanceLookupHints/);
});

test('旧 Server 忽略 instance_id 时不会把分页第一条误认成最近访问实例', async () => {
  const calls = [];
  const signal = new AbortController().signal;
  const { getMonitorInstance } = await loadMonitorAdapter(async (url, params, options) => {
    calls.push({ url, params, options });
    if (!params.instance_id) {
      return {
        count: 2,
        results: [
          { instance_id: "('other',)", instance_name: '其他实例', instance_id_values: ['other'] },
          { instance_id: "('target',)", instance_name: '已重命名实例', instance_id_values: ['target'] },
        ],
      };
    }
    return {
      count: 2,
      results: [{
        instance_id: "('other',)",
        instance_name: '其他实例',
        instance_id_values: ['other'],
      }],
    };
  });

  try {
    const result = await getMonitorInstance(7, "('target',)", { addMetrics: true }, signal);
    assert.equal(result?.name, '已重命名实例');
    assert.deepEqual(calls[0].params, {
      page: 1,
      page_size: 1,
      instance_id: "('target',)",
      add_metrics: true,
    });
    assert.deepEqual(calls[1].params, {
      page: 1,
      page_size: 100,
      add_metrics: true,
    });
    assert.ok(calls.every((call) => call.options.signal === signal));
  } finally {
    delete globalThis.__monitorAdapterApiGet;
  }
});

test('旧 Server 精确回退有分页上界，重复页不会无限请求', async () => {
  let calls = 0;
  const { getMonitorInstance } = await loadMonitorAdapter(async () => {
    calls += 1;
    return {
      count: 100_000,
      results: [{ instance_id: "('other',)", instance_name: '其他实例' }],
    };
  });

  try {
    await assert.rejects(
      getMonitorInstance(7, "('target',)"),
      /repeated a pagination page/,
    );
    assert.equal(calls, 3);
  } finally {
    delete globalThis.__monitorAdapterApiGet;
  }
});

test('最近访问能区分真实空、完整恢复、部分失败与全部不可用', async () => {
  const {
    mergeRecentViewResolutionEntries,
    monitorRecentViewsResolutionStatus,
  } = await loadModel('src/features/monitor/model.ts');
  const entry = { item: {}, object: {}, instance: {} };

  assert.equal(monitorRecentViewsResolutionStatus({
    entries: [], requestedCount: 0, failedCount: 0, failedItems: [],
  }), 'empty');
  assert.equal(monitorRecentViewsResolutionStatus({
    entries: [entry], requestedCount: 1, failedCount: 0, failedItems: [],
  }), 'ready');
  assert.equal(monitorRecentViewsResolutionStatus({
    entries: [entry], requestedCount: 3, failedCount: 1, failedItems: [{}],
  }), 'partial');
  assert.equal(monitorRecentViewsResolutionStatus({
    entries: [], requestedCount: 2, failedCount: 1, failedItems: [{}],
  }), 'unavailable');
  assert.equal(monitorRecentViewsResolutionStatus({
    entries: [], requestedCount: 2, failedCount: 1, failedItems: [{}],
  }, true), 'refresh-error');
  assert.equal(monitorRecentViewsResolutionStatus({
    entries: [], requestedCount: 1, failedCount: 0, failedItems: [],
  }), 'empty');
  assert.equal(monitorRecentViewsResolutionStatus({
    entries: [entry], requestedCount: 2, failedCount: 0, failedItems: [],
  }), 'ready');

  const resolved = (instanceId, viewedAt, name) => ({
    item: { objectId: 7, instanceId, viewedAt },
    object: { id: 7 },
    instance: { id: instanceId, name },
  });
  const merged = mergeRecentViewResolutionEntries([
    resolved("('failed',)", '2026-08-12T00:00:00Z', '保留旧内容'),
    resolved("('deleted',)", '2026-08-11T00:00:00Z', '不应复活'),
  ], {
    entries: [resolved("('ready',)", '2026-08-13T00:00:00Z', '新内容')],
    requestedCount: 3,
    failedCount: 1,
    failedItems: [{ objectId: 7, instanceId: "('failed',)", viewedAt: '2026-08-12T00:00:00Z' }],
  });
  assert.deepEqual(merged.map(({ instance }) => instance.name), ['新内容', '保留旧内容']);

});

test('最近访问部分失败和刷新失败的重试按钮保留已有内容', async () => {
  const calls = [];
  const fixture = {
    auth: { userInfo: { id: 1, locale: 'zh-CN', timezone: 'Asia/Shanghai' }, organizationScope: '1:1' },
    recentViews: {
      entries: [],
      status: 'partial',
      reload: (...args) => { calls.push(args); return Promise.resolve(); },
    },
  };
  const panelModule = await loadRecentViewsPanel(fixture);
  try {
    for (const [status, notice] of [
      ['partial', 'monitor.recentPartialRestore'],
      ['refresh-error', 'monitor.recentRefreshFailed'],
    ]) {
      fixture.recentViews.status = status;
      const rendered = panelModule.default();
      const retry = findRenderedNode(rendered, (node) => node.type === 'button');
      assert.ok(retry, `${status} 应渲染重试按钮`);
      assert.equal(retry.props.children.flat(Infinity).join(''), 'common.retry');
      assert.ok(findRenderedNode(rendered, (node) => node.type === 'span'
        && node.props.children.flat(Infinity).join('') === notice));
      retry.props.onClick();
    }
    fixture.recentViews.status = 'unavailable';
    const unavailable = findRenderedNode(
      panelModule.default(),
      (node) => node.type === 'mobile-result',
    );
    assert.equal(unavailable.props.title, 'monitor.recentRestoreFailed');
    assert.equal(unavailable.props.actionLabel, 'common.retry');
    unavailable.props.onAction();
    await Promise.resolve();
    assert.deepEqual(calls, [[undefined, true], [undefined, true], []]);
  } finally {
    delete globalThis.__recentViewsPanelFixture;
  }
});

test('精确实例查询兼容重命名和复合 ID，删除或越权时安全为空', async () => {
  const responses = new Map([
    ["('renamed',)", [{ instance_id: "('renamed',)", instance_name: '重命名后的名称' }]],
    ["('vc-a', 'host-1')", [{ instance_id: "('vc-a', 'host-1')", instance_name: '复合实例' }]],
    ["('deleted',)", []],
    ["('forbidden',)", []],
  ]);
  const { getMonitorInstance } = await loadMonitorAdapter(async (_url, params) => ({
    count: responses.get(params.instance_id)?.length || 0,
    results: responses.get(params.instance_id) || [],
  }));

  try {
    assert.equal((await getMonitorInstance(7, "('renamed',)"))?.name, '重命名后的名称');
    assert.equal((await getMonitorInstance(7, "('vc-a', 'host-1')"))?.id, "('vc-a', 'host-1')");
    assert.equal(await getMonitorInstance(7, "('deleted',)"), null);
    assert.equal(await getMonitorInstance(7, "('forbidden',)"), null);
  } finally {
    delete globalThis.__monitorAdapterApiGet;
  }
});

test('监控详情只在实例确认存在后记录最近查看，不可用场景统一反馈', async () => {
  const [detail, zh, en] = await Promise.all([
    readProjectFile('src/app/monitor/detail/page.tsx'),
    readProjectFile('src/locales/zh.json'),
    readProjectFile('src/locales/en.json'),
  ]);
  assert.match(detail, /instanceResolved/);
  assert.match(detail, /!instanceResolved[\s\S]*recordRecentView/);
  assert.match(detail, /t\('monitor\.detailUnavailable'\)/);
  assert.doesNotMatch(detail, /status === 'forbidden' \? t\('monitor\.detailForbidden'\)/);
  assert.match(zh, /"实例不可用、已删除或当前无权查看"/);
  assert.match(en, /"This instance is unavailable, deleted, or not accessible to you"/);
});

test('Mobile 搜索框高度走统一变量，业务页不再各自覆盖盒型', async () => {
  const [
    variables,
    searchBar,
    searchBarStyles,
    monitorStyles,
    assetsStyles,
    todoStyles,
    monitorPanel,
    assetsPanel,
    assetsSearch,
    todoSearch,
  ] = await Promise.all([
    readProjectFile('src/styles/variables.css'),
    readProjectFile('src/components/mobile-search-bar/index.tsx'),
    readProjectFile('src/components/mobile-search-bar/index.module.css'),
    readProjectFile('src/features/monitor/monitor.module.css'),
    readProjectFile('src/features/assets/assets.module.css'),
    readProjectFile('src/features/todo/todo.module.css'),
    readProjectFile('src/features/monitor/instances-panel.tsx'),
    readProjectFile('src/features/assets/all-assets-panel.tsx'),
    readProjectFile('src/app/assets/search/page.tsx'),
    readProjectFile('src/app/todo/search/page.tsx'),
  ]);

  assert.match(variables, /--mobile-search-bar-height:\s*34px/);
  assert.match(variables, /--mobile-search-bar-height-page:\s*34px/);
  assert.match(variables, /--mobile-search-bar-radius:\s*8px/);
  assert.match(searchBar, /size\s*=\s*'compact'/);
  assert.match(searchBar, /size === 'page'/);
  assert.match(searchBarStyles, /--mobile-search-bar-height/);
  assert.match(searchBarStyles, /--mobile-search-bar-height-page/);
  assert.match(searchBar, /mobile\/DESIGN\.md/);
  assert.match(monitorPanel, /MobileSearchBar/);
  assert.match(assetsPanel, /MobileSearchBar/);
  assert.match(assetsSearch, /size="page"/);
  assert.match(todoSearch, /size="page"/);
  // 远程搜索：草稿 input + onSearch 提交，不得输入防抖请求
  for (const [name, source] of [
    ['assetsPanel', assetsPanel],
    ['monitorPanel', monitorPanel],
    ['assetsSearch', assetsSearch],
    ['todoSearch', todoSearch],
  ]) {
    assert.match(source, /onSearch=\{/, `${name} 远程搜索应绑定 onSearch`);
  }
  assert.match(assetsPanel, /const \[input,\s*setInput\]/);
  assert.match(assetsPanel, /onSearch=\{submitSearch\}/);
  assert.match(assetsPanel, /onChange=\{setInput\}/);
  assert.doesNotMatch(assetsPanel, /setTimeout\(\(\)\s*=>\s*\{[\s\S]*loadInstances/, '资产列表不得输入防抖请求');
  assert.match(monitorPanel, /const \[input,\s*setInput\]/);
  assert.match(monitorPanel, /onSearch=\{submitSearch\}/);
  assert.match(monitorPanel, /onChange=\{setInput\}/);
  assert.doesNotMatch(monitorPanel, /setTimeout\(\(\)\s*=>\s*\{[\s\S]*loadInstances/, '监控列表不得输入防抖请求');
  assert.match(assetsSearch, /onSearch=\{submit\}/);
  assert.match(todoSearch, /onSearch=\{submit\}/);

  for (const [name, css] of [
    ['monitor', monitorStyles],
    ['assets', assetsStyles],
    ['todo', todoStyles],
  ]) {
    assert.doesNotMatch(
      css,
      /\.adm-search-bar-input-box/,
      `${name} 不应再直接覆盖 adm-search-bar-input-box 高度`,
    );
  }
});

test('资产全部采用分类落地再进入分类内模型工作台，不用列表区横滑切模型', async () => {
  const [page, panel, modelPage, styles, detail, variables] = await Promise.all([
    readProjectFile('src/app/assets/page.tsx'),
    readProjectFile('src/features/assets/all-assets-panel.tsx'),
    readProjectFile('src/app/assets/model/page.tsx'),
    readProjectFile('src/features/assets/assets.module.css'),
    readProjectFile('src/app/assets/detail/page.tsx'),
    readProjectFile('src/styles/variables.css'),
  ]);

  assert.match(page, /AllAssetsPanel/);
  assert.match(page, /assets\.tabs\.all/);
  assert.match(page, /classificationId/);
  assert.match(page, /classificationName/);
  assert.match(page, /lastAllQuery/);
  assert.match(page, /stashedAll/);
  assert.match(page, /onTabChange/);
  assert.match(page, /不清理分类 URL|避免闪落地页/);
  assert.match(page, /MobileSegmentTabs/);
  assert.match(page, /href:\s*'\/assets\/search'/);
  assert.doesNotMatch(page, /inAllWorkbench &&/);
  assert.match(page, /inAllWorkbench|allTabTitle|categoryPickerOpen/);
  assert.match(page, /onWorkbenchMetaChange|onCategoryPickerOpenChange/);
  assert.match(page, /DownOutline/);
  assert.match(page, /categorySwitchLabel|allTabLabel|workbenchLabelMeta/);
  assert.match(page, /workbenchLabelMeta/);
  // 切到「我关注的」时不再清空分类 query，避免切回时先渲染落地页
  assert.doesNotMatch(page, /if \(query\) router\.replace\('\/assets'\)/);
  assert.match(panel, /listAssetCatalog/);
  assert.match(panel, /listAssetInstances/);
  assert.match(panel, /browseByCategory|categoryRow/);
  assert.match(panel, /categoryRowCount|categoryModelCount/);
  assert.match(panel, /resolveAssetModelIconUrl/);
  assert.match(panel, /group\.models\.slice\(0,\s*3\)/);
  assert.match(panel, /categoryModelIcons|categoryModelIcon|categoryModelImage/);
  assert.doesNotMatch(panel, /categoryModelOverflow|remainingModelCount/);
  assert.match(panel, /backToLanding/);
  assert.doesNotMatch(panel, /categoryContext|categorySwitch/);
  assert.match(panel, /selectClassificationTitle|pickClassification/);
  assert.match(panel, /assets\.tabs\.all/);
  assert.match(panel, /categoryPickerOpen|onCategoryPickerOpenChange|onWorkbenchMetaChange/);
  assert.match(panel, /openClassification|modelsInClassification/);
  assert.match(panel, /neighborChip|classificationModels/);
  assert.match(panel, /neighborChipCount|model\.count/);
  assert.match(panel, /shouldShowListPagination|ASSET_PAGE_SIZE/);
  assert.match(panel, /aria-pressed/);
  assert.doesNotMatch(panel, /styles\.assetTableHead|assets\.columnName/);
  assert.doesNotMatch(page, /styles\.assetTableHead|assets\.columnName/);
  assert.match(panel, /classificationName/);
  assert.match(panel, /<Popup/);
  assert.doesNotMatch(panel, /categoryBack|LeftOutline/);
  assert.doesNotMatch(panel, /pickerFooter|viewAllCategories/);
  assert.match(panel, /router\.replace\(query \? `\/assets\?\$\{query\}` : '\/assets'\)/);
  assert.match(panel, /modelCaches/);
  assert.match(panel, /preserveContent/);
  assert.doesNotMatch(panel, /onTouchStart|shiftObject|changedTouches/);
  assert.match(modelPage, /router\.replace/);
  assert.match(modelPage, /classificationId/);
  assert.match(detail, /classificationId/);
  assert.match(styles, /\.categoryRow\s*\{/);
  assert.match(styles, /\.categoryRowCount\s*\{/);
  assert.match(styles, /\.categoryList\s*\{[^}]*display:\s*grid[^}]*gap:\s*8px/s);
  assert.match(styles, /\.categoryRow\s*\{[^}]*min-height:\s*68px[^}]*grid-template-columns:\s*58px minmax\(0, 1fr\) auto 16px[^}]*gap:\s*10px[^}]*padding:\s*10px 12px[^}]*border-radius:\s*12px/s);
  assert.match(styles, /\.categoryModelIcon\s*\{[^}]*width:\s*34px[^}]*height:\s*34px[^}]*border:\s*2px solid var\(--color-bg\)[^}]*border-radius:\s*9px/s);
  assert.match(styles, /\.categoryModelIcon:nth-child\(2\)\s*\{\s*left:\s*10px/);
  assert.match(styles, /\.categoryModelIcon:nth-child\(3\)\s*\{\s*left:\s*20px/);
  assert.match(styles, /\.categoryModelImage\s*\{[^}]*width:\s*30px[^}]*height:\s*30px/s);
  assert.match(styles, /\.categoryRowName\s*\{[^}]*font-size:\s*var\(--font-size-compact-title\)/s);
  assert.match(styles, /\.categoryRowCountEmpty\s*\{/);
  assert.equal((variables.match(/--font-size-compact-title:\s*14px/g) || []).length, 2);
  assert.match(styles, /\.allTabTitle\s*\{/);
  assert.match(styles, /\.allTabTitleChevron\s*\{/);
  assert.match(styles, /\.landingBody\s*\{/);
  assert.match(styles, /\.modelRail\s*\{/);
  assert.match(styles, /\.neighborChip\s*\{[^}]*border-bottom:\s*2px\s+solid\s+transparent/s);
  assert.match(styles, /\.neighborChipActive\s*\{[^}]*border-bottom-color:\s*var\(--color-primary\)/s);
  assert.match(styles, /\.neighborChipCount\s*\{/);
  assert.match(styles, /\.assetRow\s*\{[^}]*min-height:\s*var\(--mobile-table-row-min-height\)/s);
  assert.match(styles, /\.assetName\s*\{[^}]*font-size:\s*var\(--font-size-body\)/s);
  assert.match(styles, /\.assetLead\s*\{[^}]*width:\s*32px[^}]*height:\s*32px/s);
  assert.match(styles, /\.assetLeadImage\s*\{[^}]*width:\s*30px[^}]*height:\s*30px/s);
  assert.match(styles, /\.assetMetaSwatch\s*\{/);
  assert.match(styles, /\.assetLead\s*\{[^}]*background:\s*var\(--color-bg\)[^}]*border:\s*1px solid var\(--color-border-1\)[^}]*box-shadow:\s*var\(--shadow-composer\)/s);
  assert.doesNotMatch(styles, /\.assetTag\s*\{/);
  assert.match(styles, /\.assetMetaIp\s*\{[^}]*font-family:\s*ui-monospace/s);
  // 等宽 IP 与中文混排按基线对齐，色点保持居中
  assert.match(styles, /\.assetMetaRow\s*\{[^}]*align-items:\s*baseline/s);
  assert.match(styles, /\.assetMetaSwatch\s*\{[^}]*align-self:\s*center/s);
  assert.doesNotMatch(styles, /\.assetCard\s*\{[^}]*min-height:\s*78px/s);
});

test('资产模型默认选中与同分类邻居规则可复用', async () => {
  const {
    classificationIdForModel,
    modelsInClassification,
    neighborAssetModels,
    orderedAssetModels,
    resolveDefaultAssetModel,
  } = await loadModel('src/features/assets/model.ts');
  const classifications = [
    { id: 'infra', name: 'infra', order: 1, visible: true },
    { id: 'db', name: 'db', order: 2, visible: true },
  ];
  const models = [
    { id: 'sw', name: 'SW', classificationId: 'infra', icon: '', order: 2, visible: true, count: 10 },
    { id: 'host', name: 'Host', classificationId: 'infra', icon: '', order: 1, visible: true, count: 0 },
    { id: 'mysql', name: 'MySQL', classificationId: 'db', icon: '', order: 1, visible: true, count: 5 },
  ];
  assert.deepEqual(orderedAssetModels(classifications, models).map((item) => item.id), ['host', 'sw', 'mysql']);
  assert.equal(resolveDefaultAssetModel(orderedAssetModels(classifications, models), 'missing')?.id, 'sw');
  assert.equal(resolveDefaultAssetModel(orderedAssetModels(classifications, models), 'mysql')?.id, 'mysql');
  assert.deepEqual(
    neighborAssetModels(models, 'host').map((item) => item.id),
    ['host', 'sw'],
  );
  assert.deepEqual(modelsInClassification(models, 'infra').map((item) => item.id), ['host', 'sw']);
  assert.equal(classificationIdForModel(models, 'mysql'), 'db');
  assert.equal(classificationIdForModel(models, 'missing'), '');
});

async function loadAssetModelIcon() {
  const catalogJson = await readProjectFile('src/features/assets/model-icon-catalog.json');
  const source = (await readProjectFile('src/features/assets/model-icon.ts')).replace(
    /import catalog from '@\/features\/assets\/model-icon-catalog(?:\.json)?';\s*/,
    `const catalog = ${catalogJson};\n`,
  );
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
      resolveJsonModule: true,
      esModuleInterop: true,
    },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}#${Math.random()}`);
}

test('监控对象图标与 Web 同源路径解析，非法值回退默认图标', async () => {
  const { resolveMonitorObjectIconUrl, monitorObjectIconFallbackUrl } = await loadModel(
    'src/features/monitor/object-icon.ts',
  );
  assert.equal(resolveMonitorObjectIconUrl('cc-host_主机'), '/assets/icons/cc-host_主机.svg');
  assert.equal(resolveMonitorObjectIconUrl('mm-mysql_Mysql'), '/assets/icons/mm-mysql_Mysql.svg');
  assert.equal(resolveMonitorObjectIconUrl(''), '/assets/icons/cc-default_默认.svg');
  assert.equal(resolveMonitorObjectIconUrl('../etc/passwd'), '/assets/icons/cc-default_默认.svg');
  assert.equal(resolveMonitorObjectIconUrl('a/b'), '/assets/icons/cc-default_默认.svg');
  assert.equal(monitorObjectIconFallbackUrl(), '/assets/icons/cc-default_默认.svg');

  const [panel, detail, iconImage] = await Promise.all([
    readProjectFile('src/features/monitor/instances-panel.tsx'),
    readProjectFile('src/app/monitor/detail/page.tsx'),
    readProjectFile('src/features/monitor/object-icon-image.tsx'),
  ]);
  assert.match(panel, /MonitorObjectIcon/);
  assert.match(panel, /objectIcon:/);
  assert.match(detail, /MonitorObjectIcon/);
  assert.match(detail, /params\.get\('objectIcon'\)/);
  assert.match(iconImage, /cc-default_默认/);
  assert.match(iconImage, /\/assets\/icons\//);
});

test('资产模型 pill 颜色与 Web 首页同哈希，图标按需解析且不打包全量 SVG', async () => {
  const { getStableTypeStyle } = await loadModel('src/features/assets/type-style.ts');
  const { resolveAssetModelIconUrl } = await loadAssetModelIcon();
  const styleA = getStableTypeStyle('物理服务器');
  const styleB = getStableTypeStyle('物理服务器');
  const styleC = getStableTypeStyle('MySQL');
  assert.deepEqual(styleA, styleB);
  assert.notEqual(styleA.color, styleC.color);
  assert.match(styleA.color, /^#/);
  assert.equal(
    resolveAssetModelIconUrl('icons/cc-hard-server_硬件服务器'),
    '/assets/icons/cc-hard-server_硬件服务器.svg',
  );
  assert.equal(resolveAssetModelIconUrl('icon-cc-host'), '/assets/icons-realistic/cc-host_主机.svg');
  assert.equal(
    resolveAssetModelIconUrl('', 'physcial_server'),
    '/assets/icons-realistic/cc-hard-server_硬件服务器.svg',
  );
  assert.equal(resolveAssetModelIconUrl('../etc/passwd'), null);
  assert.doesNotMatch(await readProjectFile('src/features/assets/model-icon.ts'), /public\/assets\/icons/);
  assert.match(await readProjectFile('src/features/assets/model-icon-catalog.json'), /cc-hard-server_硬件服务器/);
});

test('资产详情关注操作与 Web 一致使用可访问的空心和实心星标', async () => {
  const [detail, styles] = await Promise.all([
    readProjectFile('src/app/assets/detail/page.tsx'),
    readProjectFile('src/features/assets/assets.module.css'),
  ]);

  assert.match(detail, /StarFill/);
  assert.match(detail, /StarOutline/);
  assert.match(detail, /aria-label=\{followLabel\}/);
  assert.match(detail, /followed\s*\?\s*<StarFill[^>]*\/>\s*:\s*<StarOutline/);
  assert.doesNotMatch(detail, /saving\s*\?\s*t\('common\.loading'\)/);
  assert.match(styles, /\.followButtonActive\s*\{[^}]*color:\s*var\(--color-warning\)/s);
});

test('资产列表卡片支持行内关注操作且不触发整卡跳转', async () => {
  const [component, home, panel, search, hook, styles] = await Promise.all([
    readProjectFile('src/features/assets/asset-list-card.tsx'),
    readProjectFile('src/app/assets/page.tsx'),
    readProjectFile('src/features/assets/all-assets-panel.tsx'),
    readProjectFile('src/app/assets/search/page.tsx'),
    readProjectFile('src/features/assets/use-followed-assets.ts'),
    readProjectFile('src/features/assets/assets.module.css'),
  ]);

  for (const page of [home, panel, search]) {
    assert.match(page, /useFollowedAssets/);
    assert.match(page, /onToggleFollow/);
    assert.match(page, /followStatus=\{follow\.status\}/);
  }
  // 与 Web 关注面板一致：取消关注只就地翻星，行保留到刷新后重新解析
  assert.match(home, /followed=\{follow\.isFollowed\(asset\.modelId, asset\.id\)/);
  assert.doesNotMatch(home, /nowFollowed === false|setFollowed\(\(current\) => current\.filter/);
  // 进入「我关注的」时同步刷新星标配置，他在「全部」/详情页的关注变更不会显示成未关注
  assert.match(home, /activeTab !== 'followed'\)[\s\S]*?follow\.reload\(\)/);
  assert.match(home, /isMobileViewStale\(cacheScope, 'assets-root'\)/);
  assert.match(hook, /invalidateMobileViewSnapshot\(cacheScope, 'assets-root'\)/);
  assert.match(component, /StarFill/);
  assert.match(component, /StarOutline/);
  assert.match(component, /aria-label=\{followLabel\}/);
  assert.match(component, /<div className=\{styles\.assetRow\}>[\s\S]*<Link className=\{styles\.assetRowLink\}/);
  assert.doesNotMatch(component, /<Link className=\{styles\.assetRow\}[\s\S]*<button/);
  assert.doesNotMatch(component, /event\.preventDefault\(\)|event\.stopPropagation\(\)/);
  assert.match(component, /disabled=\{followPending \|\| followStatus !== 'ready'\}/);
  // IP 并入名称下方 meta 行（模型 · 组织 · IP），行尾只留星标
  assert.match(component, /styles\.assetMetaIp/);
  assert.doesNotMatch(component, /styles\.assetIp[}>\s]/);
  assert.match(styles, /\.cardFollow\s*\{/);
  assert.match(hook, /getFollowedConfig\(\)[\s\S]*updateFollowedConfig/);
  assert.match(hook, /addFollowedAsset/);
  assert.match(hook, /removeFollowedAsset/);
  assert.match(hook, /assets-root/);
  assert.match(hook, /assets\.followFailed/);
});

test('资产详情头部使用模型元数据真实图标并按需回退', async () => {
  const [detail, adapter, styles] = await Promise.all([
    readProjectFile('src/app/assets/detail/page.tsx'),
    readProjectFile('src/features/assets/adapter.ts'),
    readProjectFile('src/features/assets/assets.module.css'),
  ]);

  assert.match(adapter, /export async function getAssetModel/);
  assert.match(adapter, /icon:\s*text\(found\.icn\)/);
  assert.match(detail, /getAssetModel\(actualModelId/);
  assert.match(detail, /resolveAssetModelIconUrl\(modelIcon, resolvedModelId\)/);
  assert.match(detail, /heroIconImage/);
  assert.match(detail, /onError=\{\(\) => setIconFailed\(true\)\}/);
  assert.match(styles, /\.heroIcon\s*\{[^}]*width:\s*36px[^}]*height:\s*36px[^}]*background:\s*var\(--color-bg\)[^}]*border:\s*1px solid var\(--color-border-1\)[^}]*box-shadow:\s*var\(--shadow-composer\)/s);
  assert.match(styles, /\.heroIconImage\s*\{[^}]*width:\s*32px[^}]*height:\s*32px[^}]*object-fit:\s*contain/s);
});

test('详情返回时按账号与团队恢复列表数据与滚动位置；独立搜索页不缓存结果', async () => {
  const [cache, assets, assetPanel, assetSearch, monitor, monitorPanel, todo, todoSearch, auth, detail, followHook] = await Promise.all([
    loadModel('src/navigation/mobile-view-cache.ts'),
    readProjectFile('src/app/assets/page.tsx'),
    readProjectFile('src/features/assets/all-assets-panel.tsx'),
    readProjectFile('src/app/assets/search/page.tsx'),
    readProjectFile('src/app/monitor/page.tsx'),
    readProjectFile('src/features/monitor/instances-panel.tsx'),
    readProjectFile('src/app/todo/page.tsx'),
    readProjectFile('src/app/todo/search/page.tsx'),
    readProjectFile('src/context/auth.tsx'),
    readProjectFile('src/app/assets/detail/page.tsx'),
    readProjectFile('src/features/assets/use-followed-assets.ts'),
  ]);

  cache.writeMobileViewSnapshot('user-1:team-a', 'assets', { tab: 'all' }, 128);
  assert.deepEqual(cache.readMobileViewSnapshot('user-1:team-a', 'assets'), {
    data: { tab: 'all' },
    scrollTop: 128,
  });
  assert.equal(cache.readMobileViewSnapshot('user-1:team-b', 'assets'), null);
  cache.invalidateMobileViewSnapshot('user-1:team-a', 'assets');
  assert.equal(cache.isMobileViewStale('user-1:team-a', 'assets'), true);
  cache.clearMobileViewStale('user-1:team-a', 'assets');
  assert.equal(cache.isMobileViewStale('user-1:team-a', 'assets'), false);
  cache.clearMobileViewCache();
  assert.equal(cache.readMobileViewSnapshot('user-1:team-a', 'assets'), null);

  assert.match(monitor, /readMobileViewSnapshot/);
  assert.match(monitor, /writeMobileViewSnapshot/);
  for (const page of [assets, assetPanel, monitorPanel, todo]) {
    assert.match(page, /readMobileViewSnapshot/);
    assert.match(page, /writeMobileViewSnapshot/);
    assert.match(page, /restoreMobileViewScroll/);
    assert.match(page, /scrollRef/);
  }
  // 独立搜索页不写视图快照
  for (const page of [assetSearch, todoSearch]) {
    assert.doesNotMatch(page, /readMobileViewSnapshot|writeMobileViewSnapshot|restoreMobileViewScroll/);
  }
  assert.match(assets, /isMobileViewStale\(cacheScope, 'assets-root'\)/);
  assert.match(assets, /clearMobileViewStale\(cacheScope, 'assets-root'\)/);
  assert.match(followHook, /invalidateMobileViewSnapshot\(cacheScope, 'assets-root'\)/);
  assert.match(detail, /invalidateMobileViewSnapshot\(cacheScope, 'assets-root'\)/);
  assert.match(detail, /backHref = backParams\.toString\(\) \? `\/assets\?\$\{backParams\.toString\(\)\}` : '\/assets'/);
  assert.match(todo, /useAlertFeed\(initialSnapshot\.current\?\.data\.feed\)/);
  assert.match(auth, /clearMobileViewCache\(\)/);
});
