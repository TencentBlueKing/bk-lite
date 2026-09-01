import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const projectRoot = new URL('../', import.meta.url);

async function readProjectFile(path) {
  return readFile(new URL(path, projectRoot), 'utf8');
}

async function loadTypeScriptModule(path) {
  const source = await readProjectFile(path);
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}#${Math.random()}`);
}

function permissionTree(name, operation = ['View']) {
  return [{ name: 'group', children: [{ name, operation }] }];
}

const staticMenus = [
  { name: 'Alarms', url: '/alarm/alarms' },
  { name: 'view_list', url: '/monitor/view' },
  { name: 'asset_info', url: '/cmdb/assetData' },
  { name: 'bot_list', url: '/opspilot/studio' },
];

function fullFacts() {
  return {
    licensedClients: ['alarm', 'monitor', 'cmdb', 'opspilot'],
    staticMenus,
    userMenusByClient: {
      alarm: permissionTree('Alarms', ['View', 'Edit']),
      monitor: permissionTree('view_list', ['View', 'Detail']),
      cmdb: permissionTree('asset_info', ['View']),
      opspilot: permissionTree('bot_list', ['View']),
    },
    customMenusByClient: {},
  };
}

test('五个模块按固定顺序解析，操作权限保留在同一接口', async () => {
  const { resolveAvailability } = await loadTypeScriptModule('src/platform/availability/model.ts');
  const resolved = resolveAvailability(fullFacts());

  assert.deepEqual(resolved.visibleModules, ['todo', 'monitor', 'assets', 'apps', 'profile']);
  assert.deepEqual(resolved.operations.todo, ['View', 'Edit']);
});

test('资产全局搜索能力只跟随 Web 独立 search 菜单权限', async () => {
  const { resolveAvailability } = await loadTypeScriptModule('src/platform/availability/model.ts');
  const facts = fullFacts();
  facts.staticMenus.push({ name: 'search', url: '/cmdb/assetSearch' });
  facts.userMenusByClient.cmdb = [{ name: 'group', children: [
    { name: 'asset_info', operation: ['View'] },
    { name: 'search', operation: ['View'] },
  ] }];
  assert.equal(resolveAvailability(facts).operations.assets.includes('Search'), true);
  facts.userMenusByClient.cmdb = permissionTree('asset_info', ['View']);
  assert.equal(resolveAvailability(facts).operations.assets.includes('Search'), false);
});

test('许可缺失、用户菜单缺失和自定义菜单移除都会关闭对应入口', async () => {
  const { resolveAvailability } = await loadTypeScriptModule('src/platform/availability/model.ts');
  const facts = fullFacts();
  facts.licensedClients = facts.licensedClients.filter((client) => client !== 'monitor');
  facts.userMenusByClient.opspilot = [];
  facts.customMenusByClient.cmdb = {
    isBuiltIn: false,
    menus: [{ name: 'search', url: '/cmdb/assetSearch' }],
  };

  assert.deepEqual(resolveAvailability(facts).visibleModules, ['todo', 'profile']);
});

test('安全落点优先记忆的有权 Tab，否则按固定业务顺序回退', async () => {
  const { resolveSafeModule, moduleForPath } = await loadTypeScriptModule('src/platform/availability/model.ts');

  assert.equal(resolveSafeModule(['monitor', 'apps', 'profile'], 'apps'), 'apps');
  assert.equal(resolveSafeModule(['monitor', 'apps', 'profile'], 'assets'), 'monitor');
  assert.equal(resolveSafeModule(['profile'], 'todo'), 'profile');
  assert.equal(moduleForPath('/assets/models/host'), 'assets');
  assert.equal(moduleForPath('/conversation'), 'apps');
});

test('账号时区决定时间与日期边界，非法时区回退 Web 默认值', async () => {
  const {
    formatAccountActivity,
    formatAccountDateTime,
  } = await loadTypeScriptModule('src/platform/preferences/dateTime.ts');
  const value = '2026-01-01T00:30:00Z';
  const timeOptions = { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };

  assert.equal(
    formatAccountDateTime(value, { locale: 'en', timezone: 'UTC' }, timeOptions),
    '00:30',
  );
  assert.equal(
    formatAccountDateTime(value, { locale: 'en', timezone: 'Asia/Shanghai' }, timeOptions),
    '08:30',
  );
  assert.equal(
    formatAccountDateTime(value, { locale: 'en', timezone: 'Invalid/Zone' }, timeOptions),
    '08:30',
  );

  const now = new Date('2026-01-01T08:00:00Z');
  assert.match(
    formatAccountActivity(value, { locale: 'en', timezone: 'America/Los_Angeles' }, 'Yesterday', now),
    /^Yesterday /,
  );
  assert.doesNotMatch(
    formatAccountActivity(value, { locale: 'en', timezone: 'Asia/Shanghai' }, 'Yesterday', now),
    /^Yesterday /,
  );
});

test('壳层复用 Web 菜单代理并保留会话手势和既有时区设置', async () => {
  const [
    providers,
    layout,
    tabShell,
    auth,
    navigation,
    accountDetails,
    nginx,
    nextConfig,
  ] = await Promise.all([
    readProjectFile('src/app/app-providers.tsx'),
    readProjectFile('src/app/layout.tsx'),
    readProjectFile('src/components/mobile-tab-shell/index.tsx'),
    readProjectFile('src/context/auth.tsx'),
    readProjectFile('src/navigation/mobile-back.tsx'),
    readProjectFile('src/app/profile/accountDetails/page.tsx'),
    readProjectFile('nginx.h5.conf'),
    readProjectFile('next.config.ts'),
  ]);

  assert.match(providers, /MobileAvailabilityProvider[\s\S]*MobileAccessGate/);
  assert.match(providers, /OrganizationScopeTree/);
  assert.match(layout, /MobilePolyfills/);
  assert.match(layout, /@\/polyfills['"]?/);
  assert.doesNotMatch(providers, /polyfills\/(react-dom|antd-mobile-render)/);
  assert.doesNotMatch(providers, /MobilePolyfills|@\/polyfills/);
  assert.match(tabShell, /visibleModules/);
  assert.match(tabShell, /MOBILE_MODULE_ORDER/);
  assert.match(auth, /router\.replace\('\/'\)/);
  assert.match(navigation, /pathname === '\/conversation'[\s\S]*return false/);
  assert.match(navigation, /ROOT_ROUTES\.has\(normalizedPathname\)/);
  assert.match(accountDetails, /timezone: currentTimezone/);
  assert.match(accountDetails, /updateStoredUserInfo\(\{ timezone: saveData\.timezone \}\)/);
  assert.match(nginx, /location = \/api\/menu[\s\S]*bklite-web:3000\/api\/menu/);
  assert.match(nextConfig, /source: '\/api\/menu'[\s\S]*\/api\/menu/);
});

test('一级 Tab 顶栏左上角挂载组织定位器，详情页不挂', async () => {
  const [
    header,
    headerStyles,
    switcher,
    switcherStyles,
    todo,
    monitor,
    assets,
    workbench,
    profile,
    profileStyles,
    alertDetail,
    monitorDetail,
    assetDetail,
  ] = await Promise.all([
    readProjectFile('src/components/mobile-page-header/index.tsx'),
    readProjectFile('src/components/mobile-page-header/index.module.css'),
    readProjectFile('src/components/organization-switcher/index.tsx'),
    readProjectFile('src/components/organization-switcher/index.module.css'),
    readProjectFile('src/app/todo/page.tsx'),
    readProjectFile('src/app/monitor/page.tsx'),
    readProjectFile('src/app/assets/page.tsx'),
    readProjectFile('src/app/workbench/page.tsx'),
    readProjectFile('src/app/profile/page.tsx'),
    readProjectFile('src/app/profile/page.module.css'),
    readProjectFile('src/app/todo/alerts/detail/page.tsx'),
    readProjectFile('src/app/monitor/detail/page.tsx'),
    readProjectFile('src/app/assets/detail/page.tsx'),
  ]);

  assert.match(header, /showOrganization/);
  assert.match(header, /leadingOrganization/);
  assert.match(header, /styles\.leading[\s\S]*OrganizationSwitcher/);
  assert.doesNotMatch(
    header.slice(header.indexOf('styles.actions'), header.length),
    /OrganizationSwitcher/,
  );
  assert.match(todo, /showOrganization/);
  assert.match(todo, /searchEntry/);
  assert.match(todo, /todo\.searchAlerts/);
  assert.match(monitor, /showOrganization/);
  assert.doesNotMatch(monitor, /searchEntry/);
  assert.match(assets, /showOrganization/);
  assert.match(assets, /searchEntry/);
  assert.match(workbench, /showOrganization/);
  assert.match(workbench, /searchEntry/);
  assert.match(workbench, /search\.searchApp/);
  assert.doesNotMatch(profile, /showOrganization/);
  assert.doesNotMatch(profile, /MobilePageHeader/);
  assert.doesNotMatch(profile, /searchEntry/);
  assert.match(profile, /MobileSafeHeader/);
  assert.match(profile, /OrganizationSwitcher variant="inline"/);
  assert.match(profile, /styles\.pageTitle/);
  assert.match(header, /searchEntry\?:/);
  assert.match(headerStyles, /\.searchEntry\s*\{/);
  assert.match(headerStyles, /\.headerContentTabRootWithSearch\s*\{/);
  assert.match(profile, /account\.organization/);
  assert.doesNotMatch(profile, /account\.role/);
  assert.match(profile, /styles\.identityFactRow/);
  assert.match(profile, /styles\.identityDomain/);
  assert.match(profile, /styles\.identityTitleRow/);
  assert.match(profile, /readCachedAccountOverview|accountOverviewCache/);
  assert.doesNotMatch(profile, /styles\.domain(?![A-Za-z])/);
  assert.match(profileStyles, /\.identity\s*\{[^}]*padding:\s*16px/s);
  assert.match(profileStyles, /\.identity\s*\{[^}]*border-radius:\s*12px/s);
  assert.match(profileStyles, /\.avatar\s*\{[^}]*width:\s*52px/s);
  assert.match(profileStyles, /\.identityCopy h2\s*\{[^}]*font-weight:\s*600/s);
  assert.match(profileStyles, /\.menuSection\s*\{[^}]*border:\s*0/s);
  assert.match(profileStyles, /\.menuSection\s*\{[^}]*border-radius:\s*12px/s);
  assert.match(profileStyles, /\.body\s*\{[^}]*padding:\s*8px 12px 20px/s);
  assert.match(profileStyles, /\.identityDomain\s*\{[^}]*border-radius:\s*7px/s);
  assert.match(profileStyles, /\.identityFactRow dd\s*\{[^}]*font-weight:\s*600/s);
  assert.match(profileStyles, /\.identityFacts\s*\{[^}]*gap:\s*7px/s);
  assert.doesNotMatch(profileStyles, /(?<![A-Za-z])\.domain\s*\{/);
  assert.doesNotMatch(profileStyles, /\.identity\s*\{[^}]*border-bottom:/s);
  assert.match(headerStyles, /\.searchEntry\s*\{[^}]*border-radius:\s*999px/s);
  assert.match(headerStyles, /\.searchEntry\s*\{[^}]*height:\s*30px/s);
  assert.match(headerStyles, /\.headerContentTabRootWithSearch \.actions\s*\{[^}]*grid-column:\s*3/s);
  assert.match(switcher, /variant === 'inline'/);
  assert.match(switcher, /trigger\.closest\('header'\)/);
  assert.match(switcher, /trigger\.getBoundingClientRect\(\)\.bottom/);
  assert.match(switcher, /commitAndClose/);
  assert.match(switcher, /draftTeamId/);
  assert.doesNotMatch(switcher, /setPanelTop\(safeTop\)/);
  assert.doesNotMatch(alertDetail, /showOrganization/);
  assert.doesNotMatch(monitorDetail, /showOrganization/);
  assert.doesNotMatch(assetDetail, /showOrganization/);

  const [todoSearch, assetSearch, conversations, accountCache, authSource, teamCookie] = await Promise.all([
    readProjectFile('src/app/todo/search/page.tsx'),
    readProjectFile('src/app/assets/search/page.tsx'),
    readProjectFile('src/app/conversations/page.tsx'),
    readProjectFile('src/utils/accountOverviewCache.ts'),
    readProjectFile('src/context/auth.tsx'),
    readProjectFile('src/utils/teamCookie.ts'),
  ]);
  assert.doesNotMatch(todoSearch, /showOrganization/);
  assert.doesNotMatch(assetSearch, /showOrganization/);
  assert.doesNotMatch(conversations, /showOrganization/);
  assert.match(accountCache, /clearCachedAccountOverview/);
  assert.match(authSource, /clearCachedAccountOverview/);
  assert.match(teamCookie, /max-age=\$\{maxAge\}/);
  assert.match(headerStyles, /\.leadingOrganization\s*\{/);
  assert.match(headerStyles, /\.headerContentTabRoot\s*\{/);
  assert.match(headerStyles, /\.titleGroupSrOnly\s*\{/);
  assert.match(switcher, /TeamOutline/);
  assert.match(switcherStyles, /\.triggerIcon\s*\{[^}]*color:\s*var\(--color-text-2\)/s);
  assert.doesNotMatch(switcherStyles, /\.triggerIcon\s*\{[^}]*background:/s);
  assert.match(switcherStyles, /\.triggerName\s*\{[^}]*text-overflow:\s*ellipsis[^}]*white-space:\s*nowrap/s);
  assert.doesNotMatch(switcherStyles, /-webkit-line-clamp/);
});

test('菜单权限不因普通窗口焦点切换而整组重载', async () => {
  const availabilityProvider = await readProjectFile('src/platform/availability/context.tsx');

  assert.doesNotMatch(availabilityProvider, /window\.addEventListener\(['"]focus['"]/);
  assert.match(availabilityProvider, /document\.addEventListener\(['"]visibilitychange['"]/);
  assert.match(availabilityProvider, /refreshPromiseRef/);
});

test('我的页可用性失败不展示 Banner，账号失败仅头像区局部刷新重试', async () => {
  const [profile, styles] = await Promise.all([
    readProjectFile('src/app/profile/page.tsx'),
    readProjectFile('src/app/profile/page.module.css'),
  ]);
  assert.doesNotMatch(profile, /availabilityBanner|availability\.loadFailed/);
  assert.match(profile, /MobilePullToRefresh/);
  assert.match(profile, /availabilityStatus === 'error'/);
  assert.match(profile, /refreshAvailability/);
  assert.match(profile, /identityError/);
  assert.match(profile, /account\.loadFailed/);
  assert.match(profile, /RedoOutline/);
  assert.match(profile, /identityRetry/);
  assert.match(styles, /\.identityRetry\s*\{[^}]*border:\s*0/s);
  assert.doesNotMatch(profile, /inlineNotice/);
  assert.doesNotMatch(styles, /\.availabilityBanner\s*\{/);
});

test('桌面鼠标下拉刷新先锁定纵向意图，再按阈值触发', async () => {
  const {
    DESKTOP_PULL_THRESHOLD,
    getDesktopPullIntent,
    getDesktopPullProgress,
  } = await loadTypeScriptModule('src/components/mobile-pull-to-refresh/desktop-pull.ts');

  assert.equal(getDesktopPullIntent(3, 5), 'pending');
  assert.equal(getDesktopPullIntent(24, 9), 'cancelled');
  assert.equal(getDesktopPullIntent(4, -12), 'cancelled');
  assert.equal(getDesktopPullIntent(5, 18), 'pulling');
  assert.equal(getDesktopPullProgress(DESKTOP_PULL_THRESHOLD - 1).canRelease, false);
  assert.equal(getDesktopPullProgress(DESKTOP_PULL_THRESHOLD).canRelease, true);
  assert.ok(getDesktopPullProgress(DESKTOP_PULL_THRESHOLD * 3).headOffset <= 64);
});

test('共享下拉刷新只接管鼠标指针，并保留 antd-mobile 真机实现', async () => {
  const pullToRefresh = await readProjectFile('src/components/mobile-pull-to-refresh/index.tsx');

  assert.match(pullToRefresh, /<PullToRefresh/);
  assert.match(pullToRefresh, /event\.pointerType !== 'mouse'/);
  assert.match(pullToRefresh, /isAtScrollStart/);
  assert.match(pullToRefresh, /setPointerCapture/);
  assert.match(pullToRefresh, /suppressClick/);
  assert.doesNotMatch(pullToRefresh, /TouchEvent|dispatchEvent/);
});
