import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const projectRoot = new URL('../', import.meta.url);

async function readProjectFile(path) {
  return readFile(new URL(path, projectRoot), 'utf8');
}

test('智能应用列表和搜索结果直接进入应用对话', async () => {
  const workbench = await readProjectFile('src/app/workbench/page.tsx');
  const search = await readProjectFile('src/app/search/page.tsx');
  const header = await readProjectFile('src/app/conversation/components/conversation-header.tsx');

  assert.match(workbench, /buildConversationHref\(\{ botId: item\.bot, nodeId: item\.node_id \}\)/);
  assert.match(search, /buildConversationHref\(\{ botId: item\.bot, nodeId: item\.node_id \}\)/);
  assert.doesNotMatch(header, /workbench\/detail/);
});

test('会话路由保留应用入口节点并正确编码', async () => {
  const source = await readProjectFile('src/utils/conversationRoute.ts');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const routeModule = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

  assert.equal(
    routeModule.buildConversationHref({
      botId: 7,
      sessionId: 'session/1',
      nodeId: 'mobile node',
    }),
    '/conversation?bot_id=7&session_id=session%2F1&node_id=mobile+node',
  );

  const applications = [{ node_id: 'mobile-a' }, { node_id: 'mobile-b' }];
  assert.equal(routeModule.selectConversationApplication(applications, 'mobile-b'), applications[1]);
  assert.equal(routeModule.selectConversationApplication(applications), undefined);
  assert.equal(routeModule.selectConversationApplication([applications[0]]), applications[0]);
});

test('会话缓存按账号、团队和应用入口隔离，登出只清理会话键', async () => {
  const source = await readProjectFile('src/utils/conversationCache.ts');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const cacheModule = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

  const aliceScope = cacheModule.buildSessionsCacheScope({
    accountId: 'domain:alice',
    teamId: 1,
    botId: 7,
    nodeId: 'mobile-a',
  });
  const bobScope = cacheModule.buildSessionsCacheScope({
    accountId: 'domain:bob',
    teamId: 1,
    botId: 7,
    nodeId: 'mobile-a',
  });
  assert.notEqual(aliceScope, bobScope);
  assert.match(aliceScope, /account=domain%3Aalice/);
  assert.equal(cacheModule.buildSessionsCacheScope({ accountId: 'domain:alice', botId: 7 }), 'unresolved');

  const values = new Map([
    [`bk_lite_sessions_cache:${aliceScope}`, '[]'],
    [`bk_lite_sidebar_scroll_position:${aliceScope}`, '12'],
    ['theme', 'dark'],
  ]);
  const storage = {
    get length() { return values.size; },
    key(index) { return [...values.keys()][index] ?? null; },
    removeItem(key) { values.delete(key); },
  };

  cacheModule.clearConversationSessionCache(storage);
  assert.deepEqual([...values.entries()], [['theme', 'dark']]);
});

test('全局会话清理会终止流并清空 LRU，取消信号传到 Tauri 底层', async () => {
  const manager = await readProjectFile('src/context/conversation.tsx');
  const botApi = await readProjectFile('src/api/bot.ts');
  const tauriProxy = await readProjectFile('src/utils/tauriApiProxy.ts');

  assert.match(manager, /clearAll\(\): void \{[\s\S]*controller\.abort\(\)[\s\S]*this\.sessions\.clear\(\)[\s\S]*this\.accessOrder = \[\]/);
  assert.match(manager, /new AbortController\(\)/);
  assert.match(manager, /aiChatStream\([\s\S]*\{ signal \}\)/);
  assert.match(botApi, /apiStream<AIChatEvent>\(endpoint, data, options\)/);
  assert.match(tauriProxy, /signal\?\.addEventListener\('abort', handleAbort/);
  assert.match(tauriProxy, /invoke\('cancel_stream'/);
});

test('会话页不猜测缺失的 Bot 或多入口节点', async () => {
  const page = await readProjectFile('src/app/conversation/page.tsx');
  const detail = await readProjectFile('src/app/workbench/detail/page.tsx');
  const search = await readProjectFile('src/app/search/page.tsx');

  assert.doesNotMatch(page, /get\('bot_id'\) \|\| ['"]32['"]/);
  assert.match(page, /selectConversationApplication\(applications, requestedNodeId\)/);
  assert.match(page, /buildSessionsCacheScope\(\{/);
  assert.match(page, /accountId: userInfo/);
  assert.match(page, /teamId: getCurrentTeamCookie\(\)/);
  assert.match(detail, /selectConversationApplication\([\s\S]*requestedNodeId,/);
  assert.match(detail, /nodeId: botData\.node_id/);
  assert.match(detail, /node_id: botData\.node_id/);
  assert.doesNotMatch(search, /router\.push\(`\/conversation\?bot_id=/);
});

test('会话、工作台和搜索加载失败时保留明确重试入口', async () => {
  const conversation = await readProjectFile('src/app/conversation/page.tsx');
  const workbench = await readProjectFile('src/app/workbench/page.tsx');
  const search = await readProjectFile('src/app/search/page.tsx');

  assert.match(conversation, /messagesLoadFailed/);
  assert.match(conversation, /setMessagesReloadVersion/);
  assert.match(conversation, /!messagesLoadFailed && \(/);
  assert.match(workbench, /loadFailed[\s\S]*fetchApplications\(activeTab\)/);
  assert.match(search, /loadFailed[\s\S]*setConversationReloadVersion/);
});

test('翻译函数在重渲染之间保持稳定，避免会话详情重复请求', async () => {
  const translation = await readProjectFile('src/utils/i18n.ts');
  const conversation = await readProjectFile('src/app/conversation/page.tsx');

  assert.match(translation, /import \{ useCallback \} from 'react';/);
  assert.match(translation, /const t = useCallback\([\s\S]*?\}, \[intl\]\);/);
  assert.match(conversation, /\}, \[botId, requestedNodeId, t\]\);/);
});

test('搜索应用卡和返回操作可通过语义化按钮访问', async () => {
  const search = await readProjectFile('src/app/search/page.tsx');

  assert.match(search, /<button\s+type="button"\s+key=\{item\.id\}/);
  assert.match(search, /aria-label=\{t\('common\.back'\)\}/);
  assert.match(search, /min-h-11 min-w-11/);
  assert.match(search, /backgroundColor: 'var\(--color-success\)'/);
});

test('智能应用、对话和我的页面共用一级标题样式', async () => {
  const profile = await readProjectFile('src/app/profile/page.tsx');
  const pageHeader = await readProjectFile('src/components/mobile-page-header/index.tsx');
  const pageHeaderStyles = await readProjectFile('src/components/mobile-page-header/index.module.css');
  const conversationHeader = await readProjectFile('src/app/conversation/components/conversation-header.tsx');
  const safeHeader = await readProjectFile('src/components/mobile-safe-header/index.tsx');
  const safeHeaderStyles = await readProjectFile('src/components/mobile-safe-header/index.module.css');

  assert.match(profile, /<MobilePageHeader\s+title=\{t\('navigation\.profile'\)\}\s*\/>/);
  assert.doesNotMatch(profile, /text-2xl[^\n]*navigation\.profile/);
  assert.match(pageHeader, /import MobileSafeHeader/);
  assert.match(conversationHeader, /import MobileSafeHeader/);
  assert.match(pageHeader, /<MobileSafeHeader/);
  assert.match(conversationHeader, /<MobileSafeHeader/);
  assert.match(safeHeader, /styles\.content/);
  assert.match(safeHeaderStyles, /padding-top:\s*var\(--safe-area-inset-top\)/);
  assert.match(safeHeaderStyles, /min-height:\s*var\(--mobile-header-height\)/);
  assert.match(pageHeader, /searchType\?: SearchType/);
  assert.match(pageHeader, /\{searchType && \(/);
  assert.match(pageHeader, /styles\.leading[\s\S]*styles\.titleGroup[\s\S]*styles\.actions/);
  assert.match(pageHeaderStyles, /grid-template-columns:\s*minmax\(0, 1fr\) auto minmax\(0, 1fr\)/);
  assert.match(pageHeaderStyles, /\.titleGroup\s*\{[^}]*justify-self:\s*center;/s);
});

test('主页面壳层在 iOS 安全区内固定占满且不产生根滚动', async () => {
  const globals = await readProjectFile('src/styles/globals.css');
  const shell = await readProjectFile('src/components/mobile-tab-shell/index.module.css');

  assert.match(globals, /html,\s*body\s*\{[^}]*overflow:\s*hidden;/s);
  assert.match(shell, /\.shell\s*\{[^}]*position:\s*fixed;[^}]*inset:\s*0;/s);
  assert.doesNotMatch(shell, /\.shell\s*\{[^}]*height:\s*100%;/s);
  assert.match(shell, /padding-right:\s*var\(--safe-area-inset-right\)/);
  assert.match(shell, /padding-left:\s*var\(--safe-area-inset-left\)/);
});

test('页面保留用户缩放能力且不注册全局缩放拦截', async () => {
  const layout = await readProjectFile('src/app/layout.tsx');
  const providers = await readProjectFile('src/app/app-providers.tsx');

  assert.doesNotMatch(layout, /maximumScale/);
  assert.doesNotMatch(layout, /userScalable/);
  assert.doesNotMatch(providers, /preventZoom|preventDoubleTapZoom|preventGestureZoom/);
  assert.doesNotMatch(providers, /document\.addEventListener\((?:'|")(?:touchstart|touchend|gesturestart)/);
});

test('主页面头部与底栏背景连续覆盖 iOS 安全区', async () => {
  const layout = await readProjectFile('src/app/layout.tsx');
  const header = await readProjectFile('src/components/mobile-safe-header/index.module.css');
  const shell = await readProjectFile('src/components/mobile-tab-shell/index.module.css');
  const globals = await readProjectFile('src/styles/globals.css');
  const variables = await readProjectFile('src/styles/variables.css');

  assert.match(layout, /export const viewport:\s*Viewport\s*=\s*\{[\s\S]*viewportFit:\s*'cover'/);
  assert.doesNotMatch(layout, /<meta\s+name="viewport"/);
  assert.doesNotMatch(globals, /body\s*\{[^}]*padding-(?:top|bottom):\s*var\(--safe-area-inset-/s);
  assert.match(header, /padding-top:\s*var\(--safe-area-inset-top\)/);
  assert.match(header, /background:\s*var\(--color-page-header-bg\)/);
  assert.match(shell, /padding-bottom:\s*max\(4px, var\(--safe-area-inset-bottom\)\)/);
  assert.match(shell, /\.bottomNav\s*\{[^}]*background:\s*var\(--color-bottom-nav-bg\)/s);
  assert.equal((variables.match(/--mobile-header-height:\s*56px/g) || []).length, 2);
  assert.equal((variables.match(/--color-app-chrome-bg:\s*var\(--color-background-body\)/g) || []).length, 2);
  assert.equal((variables.match(/--color-page-header-bg:\s*var\(--color-app-chrome-bg\)/g) || []).length, 2);
  assert.equal((variables.match(/--color-bottom-nav-bg:\s*var\(--color-app-chrome-bg\)/g) || []).length, 2);
  assert.equal((variables.match(/--color-page-header-bg:/g) || []).length, 2);
  assert.equal((variables.match(/--color-bottom-nav-bg:/g) || []).length, 2);
});

test('iOS 关闭 WKWebView 原生自动 inset，安全区只由 CSS 管理', async () => {
  const cargo = await readProjectFile('src-tauri/Cargo.toml');
  const rustEntry = await readProjectFile('src-tauri/src/lib.rs');

  assert.match(
    cargo,
    /\[target\.'cfg\(target_os = "ios"\)'\.dependencies\][\s\S]*tauri-plugin-ios-webview-insets\s*=\s*"=0\.1\.0"/,
  );
  assert.match(rustEntry, /#\[cfg\(target_os = "ios"\)\][\s\S]*\.plugin\(tauri_plugin_ios_webview_insets::init\(\)\)/);
});

test('二级页面共用可回退到安全父页的返回语义', async () => {
  const providers = await readProjectFile('src/app/app-providers.tsx');
  const navigation = await readProjectFile('src/navigation/mobile-back.tsx');
  const pageHeader = await readProjectFile('src/components/mobile-page-header/index.tsx');
  const conversations = await readProjectFile('src/app/conversations/page.tsx');
  const search = await readProjectFile('src/app/search/page.tsx');
  const appDetail = await readProjectFile('src/app/workbench/detail/page.tsx');
  const account = await readProjectFile('src/app/profile/accountDetails/page.tsx');
  const conversationDetail = await readProjectFile('src/app/conversation/page.tsx');

  assert.match(providers, /<MobileNavigationProvider>/);
  assert.match(navigation, /routeStackRef/);
  assert.match(navigation, /router\.back\(\)/);
  assert.match(navigation, /router\.replace\(fallbackHref\)/);
  assert.match(navigation, /onBeforeBack\?\.\(\)/);
  assert.match(pageHeader, /useMobileBack\(\{ fallbackHref: backHref \|\| '\/workbench' \}\)/);
  assert.match(conversations, /backHref="\/workbench"/);
  assert.match(search, /useMobileBack\(\{ fallbackHref \}\)/);
  assert.match(appDetail, /fallbackHref: '\/workbench'/);
  assert.match(appDetail, /onBeforeBack: dismissAvatar/);
  assert.match(account, /useMobileBack\(\{ fallbackHref: '\/profile' \}\)/);

  for (const page of [search, appDetail, account]) {
    assert.doesNotMatch(page, /router\.back\(\)/);
  }
  assert.doesNotMatch(conversationDetail, /useMobileBack/);
});

test('iOS 容器按路由启停 WKWebView 原生边缘返回手势', async () => {
  const cargo = await readProjectFile('src-tauri/Cargo.toml');
  const rustEntry = await readProjectFile('src-tauri/src/lib.rs');
  const navigation = await readProjectFile('src/navigation/mobile-back.tsx');

  assert.match(
    cargo,
    /objc2\s*=\s*"=0\.6\.3"/,
  );
  assert.match(rustEntry, /#\[cfg\(target_os = "ios"\)\][\s\S]*get_webview_window\("main"\)/);
  assert.match(rustEntry, /setAllowsBackForwardNavigationGestures:\s*enabled/);
  assert.match(rustEntry, /set_back_forward_navigation_gestures/);
  assert.match(rustEntry, /apply_back_forward_navigation_gestures\(&main_webview, false\)/);

  const gestureRoutes = navigation.match(
    /NATIVE_BACK_GESTURE_ENABLED_ROUTES\s*=\s*new Set\(\[([\s\S]*?)\]\)/,
  )?.[1];
  assert.ok(gestureRoutes);
  for (const route of ['/conversations', '/search', '/workbench/detail', '/profile/accountDetails']) {
    assert.ok(gestureRoutes.includes(`'${route}'`));
  }
  for (const route of ['/workbench', '/profile', '/conversation']) {
    assert.equal(gestureRoutes.includes(`'${route}'`), false);
  }

  assert.match(navigation, /import\('@tauri-apps\/api\/core'\)/);
  assert.match(navigation, /invoke\('set_back_forward_navigation_gestures', \{ enabled \}\)/);
});

test('搜索与二级详情页统一使用 iOS 安全区头部', async () => {
  const search = await readProjectFile('src/app/search/page.tsx');
  const account = await readProjectFile('src/app/profile/accountDetails/page.tsx');
  const appDetail = await readProjectFile('src/app/workbench/detail/page.tsx');

  for (const page of [search, account, appDetail]) {
    assert.match(page, /import MobileSafeHeader from '@\/components\/mobile-safe-header';/);
    assert.match(page, /<MobileSafeHeader/);
  }

  assert.doesNotMatch(search, /\{\/\* 顶部搜索栏 \*\/\}[\s\S]*?<div className="bg-\[var\(--color-bg\)\] border-b/);
});

test('一级页面标题统一使用稍小的排版 token', async () => {
  const pageHeaderStyles = await readProjectFile('src/components/mobile-page-header/index.module.css');
  const variables = await readProjectFile('src/styles/variables.css');

  assert.match(pageHeaderStyles, /font-size:\s*var\(--mobile-page-title-font-size\)/);
  assert.equal((variables.match(/--mobile-page-title-font-size:\s*17px/g) || []).length, 2);
});

test('外层历史对话列表保留真实最近活跃时间', async () => {
  const conversations = await readProjectFile('src/app/conversations/page.tsx');
  const time = await readProjectFile('src/app/conversations/session-time.ts');

  assert.match(conversations, /session\.updated_at \|\| session\.created_at/);
  assert.match(conversations, /formatSessionActivity/);
  assert.match(time, /Intl\.DateTimeFormat/);
});

test('Mobile 会话列表使用独立分页接口', async () => {
  const api = await readProjectFile('src/api/bot.ts');

  assert.match(api, /interface MobileSessionPage\s*\{[\s\S]*count:\s*number;[\s\S]*items:\s*SessionItem\[\]/);
  assert.match(api, /page\?:\s*number/);
  assert.match(api, /page_size\?:\s*number/);
  assert.match(api, /chat_application\/mobile_sessions\//);
  assert.doesNotMatch(api, /entry_type:\s*'mobile'/);
});

test('Mobile 会话分页追加会去重并按总数判断是否还有下一页', async () => {
  const source = await readProjectFile('src/utils/sessionPagination.ts');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const pagination = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
  const firstPage = [
    { session_id: 'session-2', title: '二' },
    { session_id: 'session-1', title: '一' },
  ];
  const nextPage = [
    { session_id: 'session-1', title: '重复的一' },
    { session_id: 'session-0', title: '零' },
  ];

  assert.deepEqual(
    pagination.mergeSessionItems(firstPage, nextPage).map((item) => item.session_id),
    ['session-2', 'session-1', 'session-0'],
  );
  assert.equal(pagination.hasMoreSessions(firstPage, 3), true);
  assert.equal(pagination.hasMoreSessions(firstPage, 2), false);
  assert.equal(pagination.shouldShowSessionPagination(2, 2), false);
  assert.equal(pagination.shouldShowSessionPagination(21, 20), true);
  assert.equal(pagination.shouldShowSessionPagination(null, 19), false);
  assert.equal(pagination.shouldShowSessionPagination(null, 20), true);
});

test('会话页、侧栏和搜索按页加载 Mobile 会话', async () => {
  const conversations = await readProjectFile('src/app/conversations/page.tsx');
  const sidebar = await readProjectFile('src/app/conversation/components/conversation-sidebar.tsx');
  const search = await readProjectFile('src/app/search/page.tsx');

  for (const source of [conversations, sidebar, search]) {
    assert.match(source, /getMobileSessions/);
    assert.match(source, /page_size:\s*MOBILE_SESSION_PAGE_SIZE/);
    assert.match(source, /response\.data\?\.items/);
    assert.match(source, /<InfiniteScroll/);
    assert.match(source, /mergeSessionItems/);
  }
});

test('外层历史对话用真实应用身份区分入口', async () => {
  const conversations = await readProjectFile('src/app/conversations/page.tsx');
  const styles = await readProjectFile('src/app/conversations/page.module.css');
  const types = await readProjectFile('src/types/conversation.ts');

  assert.match(types, /app_id\?: number \| null/);
  assert.match(types, /app_name\?: string/);
  assert.match(types, /app_tags\?: string\[\]/);
  assert.match(conversations, /getAvatar\(session\.app_id\)/);
  assert.match(conversations, /session\.app_name/);
  assert.match(conversations, /session\.app_tags/);
  assert.match(conversations, /getAppTagLabel/);
  assert.doesNotMatch(conversations, /RightOutline/);
  assert.doesNotMatch(styles, /\.sessionArrow/);
});

test('对话抽屉按当前应用加载真实会话并支持真实标题搜索', async () => {
  const sidebar = await readProjectFile('src/app/conversation/components/conversation-sidebar.tsx');
  const sessionsCache = await readProjectFile('src/app/conversation/hooks/useSessionsCache.ts');
  const search = await readProjectFile('src/app/search/page.tsx');

  assert.match(sidebar, /getMobileSessions\(\{\s*bot_id: Number\(currentBotId\),\s*node_id: currentNodeId,[\s\S]*page_size: MOBILE_SESSION_PAGE_SIZE/);
  assert.match(sidebar, /session\.title/);
  assert.match(sidebar, /session\.updated_at \|\| session\.created_at/);
  assert.match(sidebar, /formatSessionActivity/);
  assert.match(sidebar, /<time[^>]*dateTime=\{activityTime\}/);
  assert.match(sessionsCache, /SESSIONS_CACHE_SCHEMA_VERSION = 2/);
  assert.match(sessionsCache, /version: SESSIONS_CACHE_SCHEMA_VERSION/);
  assert.doesNotMatch(search, /mockChatData/);
  assert.match(search, /getMobileSessions\([\s\S]*page_size: MOBILE_SESSION_PAGE_SIZE[\s\S]*signal: controller\.signal/);
});

test('对话抽屉一次打开只自动加载一次且返回应用入口位于搜索之前', async () => {
  const sidebar = await readProjectFile('src/app/conversation/components/conversation-sidebar.tsx');

  assert.match(sidebar, /requestGenerationRef/);
  assert.match(sidebar, /requestAbortRef/);
  assert.match(sidebar, /getMobileSessions\([\s\S]*signal: abortController\.signal/);
  assert.match(sidebar, /requestGeneration !== requestGenerationRef\.current/);

  const appsEntryIndex = sidebar.indexOf("router.push('/workbench')");
  const searchIndex = sidebar.indexOf('<SearchBar');
  assert.ok(appsEntryIndex >= 0 && appsEntryIndex < searchIndex);
  assert.doesNotMatch(sidebar, /t\('chat\.currentApp'\)/);
});

test('历史消息内容兼容服务端返回的字符串、数组、对象和数字', async () => {
  const source = await readProjectFile('src/app/conversation/utils/historyContent.ts');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const historyContentModule = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

  assert.equal(historyContentModule.toHistoryContentText('hello'), 'hello');
  assert.equal(historyContentModule.toHistoryContentText(1), '1');
  assert.equal(historyContentModule.toHistoryContentText([{ type: 'message', message: 'hello' }]), '[{"type":"message","message":"hello"}]');
  assert.equal(historyContentModule.toHistoryContentText({ message: 'hello' }), '{"message":"hello"}');
  assert.equal(historyContentModule.toHistoryContentText(null), '');
});

test('移动端接入会话删除接口并保留二次确认', async () => {
  const api = await readProjectFile('src/api/bot.ts');
  const deletionHook = await readProjectFile('src/app/conversation/hooks/useSessionDeletion.ts');
  const sidebar = await readProjectFile('src/app/conversation/components/conversation-sidebar.tsx');
  const conversations = await readProjectFile('src/app/conversations/page.tsx');

  assert.match(api, /delete_session_history/);
  assert.match(deletionHook, /ActionSheet\.show/);
  assert.match(deletionHook, /Dialog\.confirm/);
  assert.match(deletionHook, /deleteSessionHistory\(nodeId, session\.session_id\)/);
  assert.match(deletionHook, /conversationManager\.clearSession\(session\.session_id\)/);
  assert.match(deletionHook, /onDeleted\(session\)/);
  assert.match(sidebar, /useSessionDeletion/);
  assert.match(conversations, /<SwipeAction/);
  assert.match(conversations, /rightActions=\{session\.node_id/);
  assert.match(conversations, /useSessionDeletion/);
  assert.match(conversations, /handleSessionDeleted[\s\S]*await loadSessions\(\)/);
  assert.match(sidebar, /handleSessionDeleted[\s\S]*await fetchSessions\(\)/);
  assert.doesNotMatch(sidebar, /deleteSessionHistory|Dialog\.confirm|ActionSheet\.show/);
  assert.doesNotMatch(conversations, /deleteSessionHistory|Dialog\.confirm|ActionSheet\.show/);
  assert.match(conversations, /aria-label=\{t\('chat\.conversationActions'\)\}/);
});

test('新增对话交互文案保持中英文键一致', async () => {
  const zh = JSON.parse(await readProjectFile('src/locales/zh.json'));
  const en = JSON.parse(await readProjectFile('src/locales/en.json'));
  const keys = [
    'currentApp',
    'conversationHistory',
    'openConversationHistory',
    'closeConversationHistory',
    'newConversation',
    'deleteConversation',
    'deleteConversationConfirm',
    'deleteConversationSuccess',
    'deleteConversationFailed',
    'deleteRunningConversation',
  ];

  for (const key of keys) {
    assert.equal(typeof zh.chat[key], 'string');
    assert.equal(typeof en.chat[key], 'string');
  }
});

test('会话页使用可视视口固定壳层而不是让键盘顶起整页', async () => {
  const layout = await readProjectFile('src/app/layout.tsx');
  const page = await readProjectFile('src/app/conversation/page.tsx');
  const header = await readProjectFile('src/app/conversation/components/conversation-header.tsx');
  const safeHeaderStyles = await readProjectFile('src/components/mobile-safe-header/index.module.css');
  const viewportHook = await readProjectFile('src/app/conversation/hooks/useVisualViewport.ts');
  const customInput = await readProjectFile('src/app/conversation/components/custom-input.tsx');
  const globals = await readProjectFile('src/styles/globals.css');
  const androidManifestPatch = await readProjectFile('scripts/patch-android-manifest.mjs');
  const androidBuildShell = await readProjectFile('scripts/android-build.sh');
  const androidBuildBatch = await readProjectFile('scripts/android-build.bat');

  assert.match(layout, /interactiveWidget:\s*'resizes-content'/);
  assert.match(viewportHook, /window\.visualViewport/);
  assert.match(viewportHook, /addEventListener\('resize'/);
  assert.match(viewportHook, /addEventListener\('scroll'/);
  assert.match(viewportHook, /offsetTop/);
  assert.match(viewportHook, /isKeyboardOpen/);
  assert.match(page, /useVisualViewport/);
  assert.match(page, /fixed left-0 top-0/);
  assert.match(page, /top: visualViewport\.offsetTop/);
  assert.match(page, /height: visualViewport\.height/);
  assert.doesNotMatch(page, /visualViewportHeight.*safe-area-inset/s);
  assert.doesNotMatch(page, /calc\(100dvh - var\(--safe-area-inset-top\)/);
  assert.match(page, /visualViewport\.isKeyboardOpen/);
  assert.match(page, /'max\(8px, var\(--safe-area-inset-bottom\)\)'/);
  assert.doesNotMatch(page, /bg-\[var\(--color-background-body\)\][^\n]*pb-4/);
  assert.match(header, /<MobileSafeHeader/);
  assert.match(safeHeaderStyles, /safe-area-inset-top/);
  assert.match(customInput, /ios-focus-stable/);
  assert.match(globals, /ios-input-focus-stable/);
  assert.match(globals, /\.ios-focus-stable textarea:focus/);
  assert.match(page, /min-h-0/);
  assert.match(page, /scrollbar-hide/);
  assert.doesNotMatch(page, /className="custom-scrollbar"/);
  assert.match(androidManifestPatch, /android:windowSoftInputMode="adjustResize"/);
  assert.match(androidBuildShell, /node scripts\/patch-android-manifest\.mjs/);
  assert.match(androidBuildBatch, /node scripts\\patch-android-manifest\.mjs/);
});

test('会话页使用连续画布并只抬升输入控件', async () => {
  const page = await readProjectFile('src/app/conversation/page.tsx');
  const header = await readProjectFile('src/app/conversation/components/conversation-header.tsx');
  const safeHeaderStyles = await readProjectFile('src/components/mobile-safe-header/index.module.css');
  const customInput = await readProjectFile('src/app/conversation/components/custom-input.tsx');
  const variables = await readProjectFile('src/styles/variables.css');

  assert.match(page, /fixed left-0 top-0[^\n]*bg-\[var\(--color-background-body\)\]/);
  assert.match(header, /<MobileSafeHeader/);
  assert.match(safeHeaderStyles, /background:\s*var\(--color-page-header-bg\)/);
  assert.match(customInput, /<div className="pt-2 mr-2 relative bg-transparent">/);
  assert.match(customInput, /ios-focus-stable[^\n]*border border-\[var\(--color-border-2\)\]/);
  assert.match(customInput, /boxShadow: 'var\(--shadow-composer\)'/);
  assert.doesNotMatch(customInput, /rounded-2xl pt-4 mr-2 relative bg-\[var\(--color-bg\)\]/);
  assert.match(variables, /--shadow-composer: 0 1px 3px rgba\(16, 24, 40, 0\.08\);/);
  assert.match(variables, /--shadow-composer: 0 1px 3px rgba\(0, 0, 0, 0\.28\);/);
});

test('移动端根壳层与 iOS 上下安全区共用连续画布背景', async () => {
  const tabShell = await readProjectFile('src/components/mobile-tab-shell/index.module.css');
  const globals = await readProjectFile('src/styles/globals.css');

  assert.match(tabShell, /\.shell\s*\{[^}]*background:\s*var\(--color-background-body\)/s);
  assert.match(globals, /html,\s*body\s*\{[^}]*background(?:-color)?:\s*var\(--color-background-body\)/s);
});

test('底部导航使用 iOS 式纯色选中态而不给图标添加背景框', async () => {
  const tabShell = await readProjectFile('src/components/mobile-tab-shell/index.module.css');

  assert.doesNotMatch(tabShell, /\.navItemActive \.navIcon\s*\{[^}]*background:/s);
  assert.doesNotMatch(tabShell, /\.navItem:active \.navIcon\s*\{[^}]*background:/s);
  assert.match(tabShell, /\.navItem:active\s*\{[^}]*opacity:\s*0\.65/s);
  assert.match(tabShell, /\.navIcon\s*\{[^}]*font-size:\s*23px/s);
});

test('会话侧栏使用 transform 跟手推移主页面', async () => {
  const shell = await readProjectFile('src/app/conversation/components/conversation-drawer-shell.tsx');
  const sidebar = await readProjectFile('src/app/conversation/components/conversation-sidebar.tsx');
  const styles = await readProjectFile('src/app/conversation/components/conversation-drawer-shell.module.css');

  assert.doesNotMatch(shell, /(?:^|\s)-?translate-x-(?:0|full)(?:\s|$)/m);
  assert.match(shell, /transform: `translate3d\(\$\{offset\}px, 0, 0\)`/);
  assert.match(shell, /Math\.abs\(deltaX\) > Math\.abs\(deltaY\) \* 1\.15/);
  assert.match(shell, /shouldOpenConversationDrawer/);
  assert.match(shell, /querySelector<HTMLElement>\('aside'\)/);
  assert.doesNotMatch(shell, /querySelector<HTMLElement>\('button:not/);
  assert.match(sidebar, /tabIndex=\{-1\}/);
  assert.match(sidebar, /focus:outline-none/);
  assert.match(styles, /touch-action:\s*pan-y/);
  assert.match(styles, /prefers-reduced-motion:\s*reduce/);
});

test('Android Manifest 软键盘模式补丁可重复执行', async () => {
  const { applyAdjustResize } = await import(new URL('scripts/patch-android-manifest.mjs', projectRoot));
  const source = `<activity\n    android:name=".MainActivity"\n    android:exported="true">`;
  const patched = applyAdjustResize(source);

  assert.match(patched, /android:windowSoftInputMode="adjustResize"/);
  assert.equal(applyAdjustResize(patched), patched);
});

test('对话抽屉使用明确返回入口并限制在动态视口内', async () => {
  const sidebar = await readProjectFile('src/app/conversation/components/conversation-sidebar.tsx');
  const shellStyles = await readProjectFile('src/app/conversation/components/conversation-drawer-shell.module.css');

  assert.match(sidebar, /LeftOutline/);
  assert.match(sidebar, /t\('chat\.backToAppList'\)/);
  assert.doesNotMatch(sidebar, /CloseOutline/);
  assert.match(sidebar, /truncate text-base font-medium[^\n]*backToAppList/);
  assert.match(sidebar, /text-\[17px\] leading-6/);
  assert.match(sidebar, /min-h-0 flex-1 overflow-y-auto/);
  assert.match(sidebar, /placeholder=\{t\('common\.search'\)\}/);
  assert.match(sidebar, /flex h-full max-h-full w-full/);
  assert.match(sidebar, /h-full max-h-full/);
  assert.doesNotMatch(sidebar, /h-\[100dvh\]/);
  assert.match(sidebar, /overflow-hidden/);
  assert.doesNotMatch(sidebar, /t\('chat\.conversationHistory'\)/);
  assert.match(shellStyles, /position:\s*absolute/);
  assert.match(shellStyles, /inset-block:\s*0/);
});

test('会话侧栏在距离或速度达标时打开，快速左划时关闭', async () => {
  const source = await readProjectFile('src/app/conversation/utils/drawerGesture.ts');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const gesture = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

  assert.equal(gesture.shouldOpenConversationDrawer({ offset: 120, drawerWidth: 300, velocityX: 0 }), true);
  assert.equal(gesture.shouldOpenConversationDrawer({ offset: 80, drawerWidth: 300, velocityX: 0 }), false);
  assert.equal(gesture.shouldOpenConversationDrawer({ offset: 40, drawerWidth: 300, velocityX: 0.5 }), true);
  assert.equal(gesture.shouldOpenConversationDrawer({ offset: 260, drawerWidth: 300, velocityX: -0.5 }), false);
});

test('可安全重试的移动列表复用下拉刷新并保留旧内容', async () => {
  const pullToRefresh = await readProjectFile('src/components/mobile-pull-to-refresh/index.tsx');
  const pullToRefreshStyles = await readProjectFile('src/components/mobile-pull-to-refresh/index.module.css');
  const workbench = await readProjectFile('src/app/workbench/page.tsx');
  const conversations = await readProjectFile('src/app/conversations/page.tsx');
  const sidebar = await readProjectFile('src/app/conversation/components/conversation-sidebar.tsx');

  assert.match(pullToRefresh, /import \{ PullToRefresh, Toast \} from 'antd-mobile'/);
  assert.match(pullToRefresh, /status === 'complete' && refreshFailed/);
  assert.match(pullToRefresh, /Toast\.show\(\{ content: t\('refresh\.failed'\)/);
  assert.match(pullToRefresh, /className=\{styles\.root\}/);
  assert.match(pullToRefreshStyles, /min-height:\s*100%/);
  assert.match(pullToRefreshStyles, /\.adm-pull-to-refresh-content/);
  assert.match(pullToRefreshStyles, /flex:\s*1 0 auto/);
  assert.match(workbench, /MobilePullToRefresh[\s\S]*preserveContent: true/);
  assert.match(conversations, /MobilePullToRefresh[\s\S]*preserveContent: true/);
  assert.match(sidebar, /MobilePullToRefresh[\s\S]*preserveContent: true/);
  assert.match(workbench, /if \(!preserveContent\) \{\s*setLoading\(true\)/);
  assert.match(conversations, /if \(!preserveContent\) \{\s*setLoading\(true\)/);
});

test('会话组件文件统一使用小写 kebab-case', async () => {
  const componentsRoot = new URL('src/app/conversation/components/', projectRoot);
  const componentFiles = await readdir(componentsRoot);
  const customComponentFiles = await readdir(new URL('custom-components/', componentsRoot));
  const tsxFiles = [...componentFiles, ...customComponentFiles].filter((file) => file.endsWith('.tsx'));

  for (const file of tsxFiles) {
    assert.match(file, /^[a-z0-9]+(?:-[a-z0-9]+)*\.tsx$/);
  }
});
