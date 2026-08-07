import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const projectRoot = new URL('../', import.meta.url);

async function readProjectFile(path) {
  return readFile(new URL(path, projectRoot), 'utf8');
}

async function loadModel() {
  const source = await readProjectFile('src/features/todo/model.ts');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}#${Math.random()}`);
}

test('三个待办视图使用互斥的服务端筛选，第一个等级才是高优先级', async () => {
  const { buildPresetQuery, selectHighestLevel } = await loadModel();
  const highest = selectHighestLevel([
    { levelId: 2, displayName: 'low' },
    { levelId: 0, displayName: 'critical' },
    { levelId: 1, displayName: 'warning' },
  ]);

  assert.equal(highest.levelId, 0);
  assert.deepEqual(buildPresetQuery('mine', 1, highest.levelId), {
    page: 1, page_size: 20, activate: 'true', my_alert: 'true',
  });
  assert.deepEqual(buildPresetQuery('open', 1, highest.levelId), {
    page: 1, page_size: 20, activate: 'true',
  });
  assert.deepEqual(buildPresetQuery('high', 1, highest.levelId), {
    page: 1, page_size: 20, activate: 'true', level: '0',
  });
  assert.equal(buildPresetQuery('high', 1, null), null);
});

test('搜索只提交用户选择的一个服务端字段', async () => {
  const { buildSearchQuery } = await loadModel();
  assert.deepEqual(buildSearchQuery('title', ' disk ', 2), {
    page: 2, page_size: 20, title: 'disk',
  });
  assert.deepEqual(buildSearchQuery('alert_id', 'A-1', 1), {
    page: 1, page_size: 20, alert_id: 'A-1',
  });
  assert.equal(buildSearchQuery('content', '  ', 1), null);
});

test('轻处置动作同时受 Edit 权限、状态和当前处理人约束', async () => {
  const { availableAlertActions, primaryAlertAction, formatAlertCount } = await loadModel();
  assert.deepEqual(availableAlertActions({ status: 'unassigned', operators: [] }, 'roger', true), ['assign']);
  assert.deepEqual(availableAlertActions({ status: 'pending', operators: ['roger'] }, 'roger', true), ['acknowledge']);
  assert.deepEqual(availableAlertActions({ status: 'pending', operators: ['alice'] }, 'roger', true), []);
  assert.deepEqual(availableAlertActions({ status: 'processing', operators: ['roger'] }, 'roger', true), ['reassign', 'close']);
  assert.deepEqual(availableAlertActions({ status: 'processing', operators: ['roger'] }, 'roger', false), []);
  assert.equal(primaryAlertAction(['reassign', 'close']), 'close');
  assert.equal(primaryAlertAction(['assign']), 'assign');
  assert.equal(formatAlertCount(0), '');
  assert.equal(formatAlertCount(12), '12');
  assert.equal(formatAlertCount(120), '99+');
});

test('告警详情请求错误按 403/404/其它分流', async () => {
  const { alertRequestErrorKind, isPermissionDenied } = await loadModel();
  assert.equal(alertRequestErrorKind(new Error('API Error: 403 - forbidden')), 'forbidden');
  assert.equal(alertRequestErrorKind(new Error('API Error: 404 - missing')), 'missing');
  assert.equal(alertRequestErrorKind(new Error('API Error: 500 - boom')), 'error');
  assert.equal(alertRequestErrorKind('nope'), 'error');
  assert.equal(isPermissionDenied(new Error('API Error: 403')), true);
  assert.equal(isPermissionDenied(new Error('API Error: 404')), false);
});

test('分页追加按告警主键去重并保留服务端新值', async () => {
  const { mergePage } = await loadModel();
  assert.deepEqual(
    mergePage([{ id: 1, title: 'old' }], [{ id: 1, title: 'new' }, { id: 2, title: 'two' }], (item) => item.id),
    [{ id: 1, title: 'new' }, { id: 2, title: 'two' }],
  );
});

test('待办 adapter 只复用现有 Web/Server 接口和权限，不声明新端点', async () => {
  const adapter = await readProjectFile('src/features/todo/adapter.ts');
  assert.match(adapter, /\/alerts\/api\/alerts\//);
  assert.match(adapter, /\/alerts\/api\/level\//);
  assert.match(adapter, /\/alerts\/api\/log\//);
  assert.match(adapter, /\/core\/api\/user_group\/user_list\//);
  assert.match(adapter, /operator\/\$\{action\}/);
  assert.doesNotMatch(adapter, /mobile[_/-](level|timeline)/i);
});

test('待办页面覆盖列表、搜索、详情三区段和轻处置且不跨模块跳转', async () => {
  const [listPage, listStyles, segmentTabsStyles, searchPage, detailPage, feed, zh, en] = await Promise.all([
    readProjectFile('src/app/todo/page.tsx'),
    readProjectFile('src/features/todo/todo.module.css'),
    readProjectFile('src/components/mobile-segment-tabs/index.module.css'),
    readProjectFile('src/app/todo/search/page.tsx'),
    readProjectFile('src/app/todo/alerts/detail/page.tsx'),
    readProjectFile('src/features/todo/use-alert-feed.ts'),
    readProjectFile('src/locales/zh.json'),
    readProjectFile('src/locales/en.json'),
  ]);

  assert.match(listPage, /MobileSegmentTabs/);
  assert.match(listPage, /Tabs\.Tab[\s\S]*key="mine"[\s\S]*key="high"[\s\S]*key="open"/);
  assert.match(listPage, /formatAlertCount|tabBadge/);
  assert.match(listPage, /MobilePullToRefresh/);
  assert.match(listPage, /MobilePullToRefresh disabled=\{loading \|\| highUnavailable\}/);
  assert.match(listPage, /MobileSkeleton[\s\S]*variant="list"/);
  assert.match(listPage, /InfiniteScroll/);
  assert.match(listPage, /shouldShowListPagination/);
  assert.match(listPage, /TODO_PAGE_SIZE/);
  assert.match(listPage, /isMobileViewStale/);
  assert.match(listPage, /controller\.revalidate/);
  assert.match(listPage, /clearMobileViewStale/);
  assert.match(feed, /const revalidate = useCallback/);
  assert.doesNotMatch(listStyles, /\.tabs\s+:global\(\.adm-tabs-tab-active\)::after/);
  assert.doesNotMatch(segmentTabsStyles, /\.tabs\s+:global\(\.adm-tabs-tab-active\)::after/);
  // 下划线隐藏已收口到共享 MobileSegmentTabs，不再散落在待办业务样式。
  assert.match(segmentTabsStyles, /\.tabs\s+:global\(\.adm-tabs-tab-line\)\s*\{\s*display:\s*none/);
  assert.match(listStyles, /\.statusPill/);
  assert.match(listStyles, /\.tabBadge/);
  assert.match(searchPage, /'title'[\s\S]*'content'[\s\S]*'alert_id'/);
  assert.doesNotMatch(searchPage, /readMobileViewSnapshot|writeMobileViewSnapshot|assets-search|todo-search/);
  assert.match(detailPage, /key="summary"[\s\S]*key="events"[\s\S]*key="changes"/);
  assert.match(detailPage, /availableAlertActions/);
  assert.match(detailPage, /primaryAlertAction/);
  assert.match(detailPage, /detailFacts/);
  assert.match(detailPage, /Dialog\.confirm/);
  assert.match(detailPage, /changeStatus\('forbidden'\)|setChangeStatus\(isPermissionDenied/);
  assert.match(detailPage, /invalidateMobileViewSnapshots\(cacheScope, \['todo-root'\]\)/);
  assert.doesNotMatch(detailPage, /todo-search/);
  assert.match(detailPage, /onBeforeBack=\{dismissPicker\}/);
  assert.match(detailPage, /alertRequestErrorKind/);
  assert.match(detailPage, /todo\.detailForbidden/);
  assert.match(detailPage, /todo\.detailMissing/);
  assert.match(detailPage, /todo\.backToTodo/);
  assert.doesNotMatch(`${listPage}\n${searchPage}\n${detailPage}`, /router\.(push|replace)\(`?\/(monitor|assets|workbench)/);
  assert.deepEqual(Object.keys(JSON.parse(zh).todo.actions), Object.keys(JSON.parse(en).todo.actions));
  assert.equal(JSON.parse(zh).todo.detailForbidden, '没有查看此告警的权限');
  assert.equal(JSON.parse(en).todo.detailMissing, 'This alert does not exist or was deleted');
});

test('轻处置后标记列表缓存失效，返回时可先展示再静默刷新', async () => {
  const source = await readProjectFile('src/navigation/mobile-view-cache.ts');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const cache = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}#${Math.random()}`);

  cache.clearMobileViewCache();
  cache.writeMobileViewSnapshot('u1:t1', 'todo-root', { items: [1] }, 40);
  assert.equal(cache.isMobileViewStale('u1:t1', 'todo-root'), false);

  cache.invalidateMobileViewSnapshots('u1:t1', ['todo-root']);
  assert.equal(cache.isMobileViewStale('u1:t1', 'todo-root'), true);
  assert.deepEqual(cache.readMobileViewSnapshot('u1:t1', 'todo-root'), {
    data: { items: [1] },
    scrollTop: 40,
  });

  cache.clearMobileViewStale('u1:t1', 'todo-root');
  assert.equal(cache.isMobileViewStale('u1:t1', 'todo-root'), false);

  cache.clearMobileViewCache();
  assert.equal(cache.isMobileViewStale('u1:t1', 'todo-root'), false);
});

test('关注告警列表使用紧凑色柱与语义字号层级', async () => {
  const styles = await readProjectFile('src/features/todo/todo.module.css');

  assert.match(styles, /\.severityMark\s*\{[^}]*height:\s*28px/s);
  assert.match(styles, /\.levelName\s*\{[^}]*font-size:\s*var\(--font-size-secondary\)/s);
  assert.match(styles, /\.statusText,\s*\.cardDuration\s*\{[^}]*font-size:\s*var\(--font-size-secondary\)/s);
  assert.match(styles, /\.alertTitle\s*\{[^}]*font-size:\s*var\(--font-size-subtitle\)/s);
  assert.match(styles, /\.alertCard\s*\{[^}]*min-height:\s*92px/s);
});
