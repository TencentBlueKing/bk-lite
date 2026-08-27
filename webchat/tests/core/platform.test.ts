import assert from 'node:assert/strict';
import test from 'node:test';

import {
  asRecordList,
  dockCollapsedStorageKey,
  fillUrlTemplate,
  formatSessionTime,
  isPersistedPlatformSession,
  isPlatformMode,
  lastSessionStorageKey,
  mapPlatformApplications,
  PLATFORM_DOCK_CHAT_WIDTH,
  PLATFORM_HISTORY_RAIL_DOCK,
  platformDockInsetWidth,
  shouldShowPlatformLauncher,
  mapPlatformMessages,
  mapPlatformSessions,
  readDockCollapsed,
  removePlatformSession,
  resolvePlatformSelection,
  sessionTitleFromUserContent,
  shouldFetchPlatformMessages,
  shouldRefreshPlatformSessions,
  unwrapPlatformPayload,
  writeDockCollapsed,
} from '../../packages/webchat-core/src/platform';
import { isSilentCustomEvent } from '../../packages/webchat-core/src/aguiHistoryText';
import { normalizeWebChatConfig } from '../../packages/webchat-core/src/config';

const platform = {
  applicationsUrl: 'https://host.test/skill_channel/platform/',
  sessionsUrl: 'https://host.test/conversations/?channel_id={channelId}',
  messagesUrl: 'https://host.test/messages/?session_id={sessionId}',
  chatUrlTemplate: 'https://host.test/skill_channel/{channelId}/chat/',
};

test('platform mode wins over top-level sseUrl when the contract is complete', () => {
  assert.equal(isPlatformMode({ platform, sseUrl: 'https://bot.test/chat' }), true);
  assert.equal(isPlatformMode({ sseUrl: 'https://bot.test/chat' }), false);
  assert.equal(
    isPlatformMode({
      platform: { ...platform, chatUrlTemplate: '' },
    }),
    false
  );
});

test('normalizeWebChatConfig keeps the named platform contract', () => {
  const normalized = normalizeWebChatConfig({
    sseUrl: 'https://legacy.test/chat',
    platform,
  });

  assert.equal(normalized.sseUrl, 'https://legacy.test/chat');
  assert.deepEqual(normalized.platform, platform);
});

test('fills host URL templates without baking console paths into webchat', () => {
  assert.equal(
    fillUrlTemplate(platform.chatUrlTemplate, { channelId: 12 }),
    'https://host.test/skill_channel/12/chat/'
  );
  assert.equal(
    fillUrlTemplate(platform.sessionsUrl, { channelId: 12 }),
    'https://host.test/conversations/?channel_id=12'
  );
  assert.equal(
    fillUrlTemplate(platform.messagesUrl, { sessionId: 'session_1' }),
    'https://host.test/messages/?session_id=session_1'
  );
});

test('unwraps gateway envelopes and paginated lists', () => {
  assert.deepEqual(
    unwrapPlatformPayload({ result: true, data: [{ id: 1 }] }),
    [{ id: 1 }]
  );
  assert.deepEqual(asRecordList({ results: [{ id: 1 }] }), [{ id: 1 }]);
  assert.deepEqual(asRecordList({ items: [{ id: 2 }] }), [{ id: 2 }]);
});

test('maps published platform skill channels and restores last selection', () => {
  const apps = mapPlatformApplications([
    {
      id: 2,
      skill_id: 20,
      app_name: '配置检查',
      skill_name: 'cfg-skill',
      channel_type: 'platform',
    },
    {
      id: 1,
      skill_id: 10,
      skill_name: 'K8s RCA',
      channel_type: 'platform',
    },
    {
      id: 3,
      skill_id: 30,
      name: '我来测试的',
      skill_name: '智能体A',
      channel_type: 'platform',
    },
    {
      id: 4,
      skill_id: 40,
      name: '我来测试的',
      skill_name: '智能体B',
      channel_type: 'platform',
    },
  ]);
  const sessions = mapPlatformSessions([
    { session_id: 's-new', title: '最新', created_at: '2026-08-18T00:00:00Z' },
    { session_id: 's-old', title: '更早' },
  ]);

  assert.deepEqual(apps[0], {
    id: '2',
    name: '配置检查（cfg-skill）',
    channelId: '2',
    skillId: '20',
    skillName: 'cfg-skill',
  });
  assert.deepEqual(apps[1], {
    id: '1',
    name: 'K8s RCA',
    channelId: '1',
    skillId: '10',
    skillName: 'K8s RCA',
  });
  assert.equal(apps[2].name, '我来测试的（智能体A）');
  assert.equal(apps[3].name, '我来测试的（智能体B）');
  assert.equal(sessions[0].updatedAt, '2026-08-18T00:00:00Z');
  assert.equal(sessions[1].updatedAt, undefined);
  assert.equal(lastSessionStorageKey('webchat:platform', 'alice', '7'), 'webchat:platform:alice:7');
  assert.deepEqual(
    resolvePlatformSelection(apps, sessions, { appId: '1', sessionId: 's-old' }),
    { app: apps[1], sessionId: 's-old' }
  );
  assert.deepEqual(
    resolvePlatformSelection(apps, sessions, { appId: 'missing', sessionId: 'gone' }),
    { app: apps[0], sessionId: 's-new' }
  );
  assert.deepEqual(
    resolvePlatformSelection([apps[0]], sessions, { appId: '1', sessionId: 's-old' }),
    { app: apps[0], sessionId: 's-new' }
  );
});

test('draft sessions do not refetch history; clicking the current session does not either', () => {
  const sessions = [{ id: 's-real' }];
  assert.equal(
    shouldFetchPlatformMessages({
      sessionId: 'session_1',
      loadedSessionId: null,
      sessions,
    }),
    false
  );
  assert.equal(
    shouldFetchPlatformMessages({
      sessionId: 's-real',
      loadedSessionId: 's-real',
      sessions,
    }),
    false
  );
  assert.equal(
    shouldFetchPlatformMessages({
      sessionId: 's-real',
      loadedSessionId: 'session_1',
      sessions,
    }),
    true
  );
  assert.equal(
    shouldFetchPlatformMessages({
      sessionId: 'session_1',
      loadedSessionId: 'session_1',
      sessions: [{ id: 'session_1' }],
    }),
    false
  );
});

test('session list refreshes after a finished run, not the connect handshake', () => {
  assert.equal(shouldRefreshPlatformSessions('connecting', 'connected'), false);
  assert.equal(shouldRefreshPlatformSessions('idle', 'connected'), false);
  assert.equal(shouldRefreshPlatformSessions('chatting', 'connected'), true);
  assert.equal(shouldRefreshPlatformSessions('error', 'idle'), true);
});

test('draft session title comes from the first user message', () => {
  assert.equal(sessionTitleFromUserContent('分析下CPU时间分布'), '分析下CPU时间分布');
  assert.equal(
    sessionTitleFromUserContent([{ type: 'message', message: '介绍下系统负载趋势' }]),
    '介绍下系统负载趋势'
  );
  assert.equal(sessionTitleFromUserContent('   '), '新会话');
});

test('maps history messages to readable text, including object payloads', () => {
  const messages = mapPlatformMessages([
    {
      id: 1,
      conversation_role: 'user',
      conversation_content: 'hello',
      conversation_time: '2026-01-01T00:00:00Z',
    },
    {
      id: 2,
      conversation_role: 'bot',
      conversation_content: { content: 'report body', extra: true },
    },
  ]);

  assert.equal(messages[0].sender, 'user');
  assert.equal(messages[0].content, 'hello');
  assert.equal(messages[1].sender, 'bot');
  assert.equal(messages[1].content, 'report body');
});

test('assembles stored AG-UI event dumps into readable assistant text', () => {
  const pythonish = mapPlatformMessages([
    {
      id: 3,
      conversation_role: 'bot',
      conversation_content:
        "{'messageId': 'msg_1', 'delta': '集群', 'type': 'TEXT_MESSAGE_CONTENT', 'timestamp': 1}{'messageId': 'msg_1', 'delta': '健康', 'type': 'TEXT_MESSAGE_CONTENT'}",
    },
  ]);
  assert.equal(pythonish[0].content, '集群健康');

  const jsonArray = mapPlatformMessages([
    {
      id: 4,
      conversation_role: 'bot',
      conversation_content: JSON.stringify([
        { type: 'TEXT_MESSAGE_START', messageId: 'm2', role: 'assistant' },
        { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm2', delta: 'Hello' },
        { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm2', delta: '!' },
      ]),
    },
  ]);
  assert.equal(jsonArray[0].content, 'Hello!');

  const eventObject = mapPlatformMessages([
    {
      id: 5,
      conversation_role: 'bot',
      conversation_content: { type: 'TEXT_MESSAGE_CONTENT', delta: 'PVC' },
    },
  ]);
  assert.equal(eventObject[0].content, 'PVC');
});

test('drops protocol-only AG-UI dumps and keeps assistant text from mixed dumps', () => {
  const protocolOnly = mapPlatformMessages([
    {
      id: 10,
      conversation_role: 'bot',
      conversation_content:
        "[{'type': 'RUN_STARTED', 'threadId': 't1'}, {'type': 'CUSTOM', 'name': 'agent_step_progress', 'value': {'index': 1}}]",
    },
  ]);
  assert.equal(protocolOnly.length, 0);

  const mixed = mapPlatformMessages([
    {
      id: 11,
      conversation_role: 'bot',
      conversation_content:
        "[{'type': 'RUN_STARTED'}, {'type': 'TEXT_MESSAGE_CONTENT', 'delta': '工作负载正常'}, {'type': 'CUSTOM', 'name': 'agent_step_progress', 'value': {'status': 'running'}}]",
    },
  ]);
  assert.equal(mixed[0].content, '工作负载正常');
});

test('history replay keeps THINKING text on metadata, not in the answer bubble', () => {
  const replayed = mapPlatformMessages([
    {
      id: 13,
      conversation_role: 'bot',
      conversation_content: JSON.stringify([
        { type: 'RUN_STARTED' },
        { type: 'THINKING', delta: 'Guang' },
        { type: 'THINKING', delta: 'zhou is the capital' },
        { type: 'TEXT_MESSAGE_CONTENT', delta: '广州是广东省省会' },
        { type: 'RUN_FINISHED' },
      ]),
    },
  ]);
  assert.equal(replayed[0].content, '广州是广东省省会');
  assert.equal(replayed[0].metadata?.thinking, 'Guangzhou is the capital');
  assert.equal(replayed[0].metadata?.isThinking, false);
});

test('planned execution CUSTOM events stay out of chat bubbles', () => {
  // 实时流（Chat.applyCustomEvent）与历史回放共用同一份静默清单
  assert.equal(isSilentCustomEvent('stream_keepalive'), true);
  assert.equal(isSilentCustomEvent('planned_execution_status'), true);
  assert.equal(isSilentCustomEvent('planned_execution_step'), true);
  assert.equal(isSilentCustomEvent('wiki_citations'), true);
  assert.equal(isSilentCustomEvent('approval_request'), false);
  assert.equal(isSilentCustomEvent('config_analysis_report'), false);

  const planned = mapPlatformMessages([
    {
      id: 12,
      conversation_role: 'bot',
      conversation_content: JSON.stringify([
        { type: 'RUN_STARTED' },
        { type: 'CUSTOM', name: 'planned_execution_status', value: { phase: 'planning' } },
        {
          type: 'CUSTOM',
          name: 'planned_execution_step',
          value: { phase: 'start', step_index: 1, total_steps: 1, objective: '查询当前时间', tools: ['get_current_time'] },
        },
        { type: 'TEXT_MESSAGE_CONTENT', delta: '现在是下午两点' },
        { type: 'RUN_FINISHED' },
      ]),
    },
  ]);
  assert.equal(planned[0].content, '现在是下午两点');
});

test('removes a history session and clears current when it was selected', () => {
  const sessions = [
    { id: 's-new', title: '最新' },
    { id: 's-old', title: '更早' },
  ];
  assert.equal(isPersistedPlatformSession('s-old', sessions), true);
  assert.equal(isPersistedPlatformSession('session_draft', sessions), false);
  assert.deepEqual(removePlatformSession(sessions, 's-old', 's-new'), {
    sessions: [{ id: 's-new', title: '最新' }],
    currentId: 's-new',
  });
  assert.deepEqual(removePlatformSession(sessions, 's-new', 's-new'), {
    sessions: [{ id: 's-old', title: '更早' }],
    currentId: null,
  });
});

test('formats session timestamps in Chinese relative units', () => {
  const now = Date.parse('2026-08-18T10:00:00Z');
  assert.equal(formatSessionTime('2026-08-18T09:59:40Z', now), '刚刚');
  assert.equal(formatSessionTime('2026-08-18T09:36:00Z', now), '24 分钟前');
  assert.equal(formatSessionTime('2026-08-18T07:00:00Z', now), '3 小时前');
  assert.equal(formatSessionTime('2026-08-17T09:00:00Z', now), '昨天');
  assert.equal(formatSessionTime(undefined, now), undefined);
});

test('dock collapsed helpers default to collapsed when storage is empty', () => {
  // PlatformChat uses in-memory collapsed state; helpers stay available for other hosts.
  const store = new Map<string, string>();
  const storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
  };
  const key = dockCollapsedStorageKey('webchat:platform', 'alice', '7');
  assert.equal(key, 'webchat:platform:collapsed:alice:7');
  assert.equal(readDockCollapsed(storage, key), true);
  writeDockCollapsed(storage, key, true);
  assert.equal(readDockCollapsed(storage, key), true);
  writeDockCollapsed(storage, key, false);
  assert.equal(readDockCollapsed(storage, key), false);
  assert.equal(readDockCollapsed({ getItem: () => null }, key), true);
});

test('hides the launcher when the published app list is empty and the host is not a manager', () => {
  assert.equal(shouldShowPlatformLauncher({ appCount: 2, canManageAgents: false }), true);
  assert.equal(shouldShowPlatformLauncher({ appCount: 0, canManageAgents: false }), false);
  assert.equal(shouldShowPlatformLauncher({ appCount: 0, canManageAgents: true }), true);
  assert.equal(shouldShowPlatformLauncher({ appCount: 0 }), true);
});

test('dock inset matches the open pane and drops to zero when collapsed or fullscreen', () => {
  assert.equal(
    platformDockInsetWidth({ visible: true }),
    PLATFORM_DOCK_CHAT_WIDTH,
  );
  assert.equal(
    platformDockInsetWidth({ visible: true, historyOpen: true }),
    PLATFORM_DOCK_CHAT_WIDTH + PLATFORM_HISTORY_RAIL_DOCK,
  );
  assert.equal(platformDockInsetWidth({ visible: false }), 0);
  assert.equal(platformDockInsetWidth({ visible: true, fullscreen: true }), 0);
  assert.equal(
    platformDockInsetWidth({ visible: true, fullscreen: true, historyOpen: true }),
    0,
  );
});
