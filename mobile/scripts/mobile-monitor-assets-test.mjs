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
});

test('实例列表按元数据顺序展示前三条摘要，空值保留为 null', async () => {
  const {
    INSTANCE_LIST_SUMMARY_LIMIT,
    displayFieldKey,
    instanceListSummaryEntries,
    instanceSummaryEntries,
  } = await loadModel('src/features/monitor/model.ts');
  assert.equal(INSTANCE_LIST_SUMMARY_LIMIT, 3);
  assert.equal(displayFieldKey('Host', 'cpu_usage'), 'Host::cpu_usage');
  assert.equal(displayFieldKey('Host', 'node_info', 'ip'), 'field::Host::node_info::ip');
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
    { label: 'CPU使用率', value: '12.5%' },
    { label: '内存使用率', value: null },
    { label: '磁盘使用率', value: '70%' },
  ]);
  assert.deepEqual(instanceSummaryEntries(object, instance, 4), [
    { label: 'CPU使用率', value: '12.5%' },
    { label: '磁盘使用率', value: '70%' },
  ]);
});

test('实例列表面板把摘要指标放进表格列并支持横向滚动', async () => {
  const [panel, styles, adapter] = await Promise.all([
    readProjectFile('src/features/monitor/instances-panel.tsx'),
    readProjectFile('src/features/monitor/monitor.module.css'),
    readProjectFile('src/features/monitor/adapter.ts'),
  ]);
  assert.match(panel, /instanceListSummaryEntries\(monitorObject, instance\)/);
  assert.match(panel, /summaryFields\.map/);
  assert.match(panel, /INSTANCE_LIST_SUMMARY_LIMIT/);
  assert.match(panel, /data-instance-table-scroll/);
  assert.doesNotMatch(panel, /styles\.instanceMetrics/);
  assert.doesNotMatch(panel, /primaryField/);
  assert.match(styles, /\.instanceTableScroll\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(styles, /\.colSticky\s*\{[^}]*position:\s*sticky/s);
  assert.match(adapter, /add_metrics:\s*true/);
  assert.match(adapter, /metrics:\s*\(Array\.isArray\(meta\.metrics\)/);
});

test('最近查看保持纯占位，监控请求始终带 objectId 且指标按视口懒加载', async () => {
  const [page, panel, adapter, card] = await Promise.all([
    readProjectFile('src/app/monitor/page.tsx'),
    readProjectFile('src/features/monitor/instances-panel.tsx'),
    readProjectFile('src/features/monitor/adapter.ts'),
    readProjectFile('src/features/monitor/metric-card.tsx'),
  ]);
  assert.match(page, /recentPlaceholder/);
  assert.doesNotMatch(`${page}\n${panel}\n${adapter}`, /last_viewed_at|MonitorRecentInstanceView|recent[_-](view|instance)|localStorage/);
  assert.match(adapter, /monitor_instance\/\$\{objectId\}\/list/);
  assert.match(adapter, /add_metrics:\s*true/);
  assert.match(adapter, /effective_plugins/);
  assert.match(adapter, /metrics_instance\/query_range/);
  assert.match(card, /IntersectionObserver/);
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
    { model_id: 'host', inst_id: 2, followed_at: '2026-02-01T00:00:00Z' },
  ] });
  assert.deepEqual(config.items.map((item) => item.instanceId), [2, 1]);
  let many = { items: [] };
  for (let index = 0; index < 105; index += 1) many = addFollowedAsset(many, 'host', index, new Date(index * 1000).toISOString());
  assert.equal(many.items.length, 100);
  assert.deepEqual(Object.keys(serializeFollowedConfig(config).items[0]), ['model_id', 'inst_id', 'followed_at']);
  assert.equal(assetRequestErrorKind(new Error('API Error: 403')), 'forbidden');
  assert.equal(assetRequestErrorKind(new Error('API Error: 404')), 'missing');
});

test('资产复用 Web CMDB 接口、两阶段搜索和元数据字段详情', async () => {
  const [adapter, detail, search] = await Promise.all([
    readProjectFile('src/features/assets/adapter.ts'), readProjectFile('src/app/assets/detail/page.tsx'), readProjectFile('src/app/assets/search/page.tsx'),
  ]);
  assert.match(adapter, /cmdb_followed_assets|FOLLOWED_ASSETS_CONFIG_KEY/);
  assert.match(adapter, /fulltext_search\/stats/);
  assert.match(adapter, /fulltext_search\/by_model/);
  assert.match(adapter, /field_groups\/full_info/);
  assert.match(adapter, /organizationName:\s*text\(item\.organization_display\)/);
  assert.match(detail, /group\.fields\.map/);
  assert.match(detail, /getFollowedConfig\(\)[\s\S]*updateFollowedConfig/);
  assert.match(search, /canAccess\('assets', 'Search'\)/);
  assert.doesNotMatch(`${adapter}\n${detail}\n${search}`, /assetSearchHistory|mock|fixture/i);
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

test('资产根页使用头部轻量搜索入口并继续进入既有精确搜索页', async () => {
  const [home, search, styles] = await Promise.all([
    readProjectFile('src/app/assets/page.tsx'),
    readProjectFile('src/app/assets/search/page.tsx'),
    readProjectFile('src/features/assets/assets.module.css'),
  ]);

  assert.match(home, /MobilePageHeader[\s\S]*searchLauncher[\s\S]*(?:<Tabs|<MobileSegmentTabs)/);
  assert.match(home, /href="\/assets\/search"/);
  assert.match(home, /searchPlaceholder/);
  assert.doesNotMatch(home, /searchLauncherHint/);
  assert.match(search, /<Switch[\s\S]*checked=\{exact\}/);
  assert.match(styles, /\.searchLauncher\s*\{[^}]*min-height:\s*40px/s);
  assert.match(styles, /\.searchField\s*\{[^}]*height:\s*34px/s);
  assert.doesNotMatch(styles, /\.searchLauncher\s*\{[^}]*min-height:\s*76px/s);
});

test('监控根页「全部实例」直接展示实例面板，旧 instances 路由回跳根页', async () => {
  const [page, panel, instancesPage, detailPage] = await Promise.all([
    readProjectFile('src/app/monitor/page.tsx'),
    readProjectFile('src/features/monitor/instances-panel.tsx'),
    readProjectFile('src/app/monitor/instances/page.tsx'),
    readProjectFile('src/app/monitor/detail/page.tsx'),
  ]);

  assert.match(page, /MonitorInstancesPanel/);
  assert.match(page, /monitor\.tabs\.all/);
  assert.doesNotMatch(page, /objectTree|setExpanded|href=\{`\/monitor\/instances/);
  assert.match(panel, /listMonitorObjects/);
  assert.match(panel, /listMonitorInstances/);
  assert.match(panel, /orderedMonitorObjects|shiftObject|objectChip/);
  assert.match(panel, /modeLoadedIssue|loaded_issue/);
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
  assert.match(detailPage, /const backHref = objectId[\s\S]*`\/monitor\?\$\{backParams\.toString\(\)\}`[\s\S]*:\s*'\/monitor'/);
  assert.match(detailPage, /<MobilePageHeader[\s\S]*backHref=\{backHref\}/);
  assert.match(detailPage, /MonitorObjectIcon/);
  assert.match(detailPage, /objectIcon/);
  assert.match(detailPage, /detailTabs\.about|activeTab === 'about'/);
  assert.match(detailPage, /groupToggle|expandedGroups/);
  assert.match(detailPage, /pluginSwitch|selectPluginTitle/);
  assert.match(detailPage, /<Popup/);
  assert.match(detailPage, /plugins\.length > 0/);
  assert.match(detailPage, /getMonitorInstance\(/);
  assert.match(detailPage, /setInstanceStatus\(/);
  assert.match(detailPage, /setLastReportedAt\(/);
});

test('监控详情头部通过现有 list 接口回源状态与上报时间', async () => {
  const adapter = await readProjectFile('src/features/monitor/adapter.ts');
  assert.match(adapter, /export async function getMonitorInstance/);
  assert.match(adapter, /monitor_instance\/\$\{objectId\}\/list\//);
  assert.match(adapter, /add_metrics:\s*false/);
  assert.match(adapter, /item\.id === instanceId/);
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

  assert.match(variables, /--mobile-search-bar-height:\s*30px/);
  assert.match(variables, /--mobile-search-bar-height-page:\s*36px/);
  assert.match(variables, /--mobile-search-bar-radius:\s*8px/);
  assert.match(searchBar, /size\s*=\s*'compact'/);
  assert.match(searchBar, /size === 'page'/);
  assert.match(searchBarStyles, /--mobile-search-bar-height/);
  assert.match(searchBarStyles, /--mobile-search-bar-height-page/);
  assert.match(monitorPanel, /MobileSearchBar/);
  assert.match(assetsPanel, /MobileSearchBar/);
  assert.match(assetsSearch, /size="page"/);
  assert.match(todoSearch, /size="page"/);

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
  const [page, panel, modelPage, styles, detail] = await Promise.all([
    readProjectFile('src/app/assets/page.tsx'),
    readProjectFile('src/features/assets/all-assets-panel.tsx'),
    readProjectFile('src/app/assets/model/page.tsx'),
    readProjectFile('src/features/assets/assets.module.css'),
    readProjectFile('src/app/assets/detail/page.tsx'),
  ]);

  assert.match(page, /AllAssetsPanel/);
  assert.match(page, /assets\.tabs\.all/);
  assert.match(page, /classificationId/);
  assert.match(page, /classificationName/);
  assert.match(page, /lastAllQuery/);
  assert.match(page, /onTabChange|router\.replace\('\/assets'\)/);
  assert.match(page, /MobileSegmentTabs/);
  assert.match(page, /searchLauncher/);
  assert.doesNotMatch(page, /inAllWorkbench &&/);
  assert.match(page, /inAllWorkbench|allTabTitle|categoryPickerOpen/);
  assert.match(page, /onWorkbenchMetaChange|onCategoryPickerOpenChange/);
  assert.match(page, /DownOutline/);
  assert.match(page, /categorySwitchLabel|allTabLabel/);
  assert.match(panel, /listAssetCatalog/);
  assert.match(panel, /listAssetInstances/);
  assert.match(panel, /browseByCategory|categoryRow/);
  assert.match(panel, /categoryRowCount|categoryModelCount/);
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
  assert.match(styles, /\.allTabTitle\s*\{/);
  assert.match(styles, /\.allTabTitleChevron\s*\{/);
  assert.match(styles, /\.landingBody\s*\{/);
  assert.doesNotMatch(styles, /\.categoryCard\s*\{[^}]*border-radius:\s*12px/s);
  assert.match(styles, /\.modelRail\s*\{/);
  assert.match(styles, /\.neighborChip\s*\{[^}]*border-radius:\s*999px/s);
  assert.match(styles, /\.neighborChipCount\s*\{/);
  assert.match(styles, /\.assetRow\s*\{[^}]*min-height:\s*56px/s);
  assert.match(styles, /\.assetName\s*\{[^}]*font-size:\s*13px/s);
  assert.match(styles, /\.assetLead\s*\{[^}]*width:\s*28px/s);
  assert.match(styles, /\.assetMetaSwatch\s*\{/);
  assert.match(styles, /\.assetLead\s*\{[^}]*border:\s*1px solid var\(--color-primary-border\)/s);
  assert.doesNotMatch(styles, /\.assetTag\s*\{/);
  assert.match(styles, /\.assetIp\s*\{[^}]*color:\s*var\(--color-text-2\)/s);
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
  const catalog = await readProjectFile('src/features/assets/model-icon-catalog.ts');
  const source = (await readProjectFile('src/features/assets/model-icon.ts')).replace(
    /import \{ MODEL_ICON_CATALOG \} from '@\/features\/assets\/model-icon-catalog';\s*/,
    '',
  );
  const output = ts.transpileModule(`${catalog}\n${source}`, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
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
  assert.match(await readProjectFile('src/features/assets/model-icon-catalog.ts'), /cc-hard-server_硬件服务器/);
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

test('详情返回时按账号与团队恢复列表数据、搜索条件和滚动位置', async () => {
  const [cache, assets, assetPanel, assetSearch, monitor, monitorPanel, todo, todoSearch, auth, detail] = await Promise.all([
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
  for (const page of [assets, assetPanel, assetSearch, monitorPanel, todo, todoSearch]) {
    assert.match(page, /readMobileViewSnapshot/);
    assert.match(page, /writeMobileViewSnapshot/);
    assert.match(page, /restoreMobileViewScroll/);
    assert.match(page, /scrollRef/);
  }
  assert.match(detail, /backHref = backParams\.toString\(\) \? `\/assets\?\$\{backParams\.toString\(\)\}` : '\/assets'/);
  assert.match(todo, /useAlertFeed\(initialSnapshot\.current\?\.data\.feed\)/);
  assert.match(auth, /clearMobileViewCache\(\)/);
});
