'use client';

import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Button, Dropdown, List, Popconfirm, Skeleton, Tag } from 'antd';
import type { MenuProps } from 'antd';
import CustomChatSSE from '@/app/opspilot/components/custom-chat-sse';
import { processHistoryMessageWithExtras } from '@/app/opspilot/components/custom-chat-sse/historyMessageProcessor';
import { parseLlmContextUsage, type LlmContextUsage } from '@/app/opspilot/components/custom-chat-sse/llmContextUsage';
import Icon from '@/components/icon';
import { useSkillApi } from '@/app/opspilot/api/skill';
import { readWebChatEntry } from '@/app/opspilot/(pages)/skill/chat/entry';

interface WebChatChannel {
  id: number;
  name: string;
  skill_name?: string;
  app_name?: string;
  app_description?: string;
  introduction?: string;
  icon?: string;
  enable_conversation_history?: boolean;
};

interface SkillChatSession {
  id: string;
  title: string;
  icon: string;
  channel_type?: string;
  persisted?: boolean;
};

interface MountedChatSession {
  id: string;
  initialMessages: any[];
  initialContextUsage: LlmContextUsage | null;
}

const CHANNEL_TYPE_TAG: Record<string, { color: string; label: string }> = {
  platform: { color: 'cyan', label: '平台' },
  web_chat: { color: 'blue', label: 'Web' },
  embedded_chat: { color: 'purple', label: '嵌入式' },
  enterprise_wechat: { color: 'green', label: '企微' },
  enterprise_wechat_aibot: { color: 'green', label: '企微机器人' },
  dingtalk: { color: 'orange', label: '钉钉' },
  feishu: { color: 'blue', label: '飞书' },
  wechat_official: { color: 'green', label: '公众号' },
};

const newSessionTitle = () => `新会话 ${new Date().toLocaleString('zh-CN', { hour12: false })}`;

/** 与平台悬浮壳一致：渠道名；撞名或与智能体名不同时展示「渠道名（智能体名）」 */
const mapWebChatChannels = (data: any[]): WebChatChannel[] => {
  const prepared = (Array.isArray(data) ? data : []).map((item) => {
    const channelName =
      String(item?.name || item?.app_name || '').trim() ||
      String(item?.skill_name || '').trim() ||
      `渠道 ${item?.id ?? ''}`;
    const skillName = String(item?.skill_name || '').trim() || undefined;
    return { item, channelName, skillName };
  });

  const channelNameCounts = new Map<string, number>();
  for (const row of prepared) {
    channelNameCounts.set(row.channelName, (channelNameCounts.get(row.channelName) || 0) + 1);
  }

  return prepared.map(({ item, channelName, skillName }) => {
    const collision = (channelNameCounts.get(channelName) || 0) > 1;
    const name =
      skillName && (collision || skillName !== channelName)
        ? `${channelName}（${skillName}）`
        : channelName;
    return {
      id: item.id,
      name,
      skill_name: skillName,
      app_name: item.name || item.app_name,
      app_description: item.introduction || item.app_description || '',
      introduction: item.introduction || '',
      icon: 'duihuazhinengti',
      enable_conversation_history: item.enable_conversation_history !== false,
    };
  });
};

const SkillWebChatPage: React.FC = () => {
  const searchParams = useSearchParams();
  const entryToken = searchParams?.get('entry') || '';
  const { fetchWebChatSkillChannels, fetchSkillConversations, fetchSkillSessionMessages, deleteSkillSession } = useSkillApi();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [agentLoading, setAgentLoading] = useState(true);
  const [agentList, setAgentList] = useState<WebChatChannel[]>([]);
  const [currentAgent, setCurrentAgent] = useState<WebChatChannel | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState('');
  const [functionList, setFunctionList] = useState<SkillChatSession[]>([]);
  const [functionLoading, setFunctionLoading] = useState(false);
  const [mountedChats, setMountedChats] = useState<MountedChatSession[]>([]);
  const [openingSessionId, setOpeningSessionId] = useState('');

  useEffect(() => {
    async function loadChannels() {
      setAgentLoading(true);
      try {
        const data = await fetchWebChatSkillChannels();
        const agents = mapWebChatChannels(data);
        setAgentList(agents);
        const requestedChannelId = readWebChatEntry(entryToken);
        const preferred = requestedChannelId
          ? agents.find((agent) => String(agent.id) === requestedChannelId)
          : undefined;
        // 带了入口凭证却对不上时，不回退到列表第一项。
        setCurrentAgent(entryToken ? preferred || null : preferred || agents[0] || null);
      } catch {
        setAgentList([]);
        setCurrentAgent(null);
      } finally {
        setAgentLoading(false);
      }
    }
    loadChannels();
  }, [entryToken]);

  useEffect(() => {
    async function loadSessions() {
      if (!currentAgent?.id) {
        setFunctionList([]);
        setSessionId(null);
        setSelectedItem('');
        setMountedChats([]);
        return;
      }
      setFunctionLoading(true);
      setSessionId(null);
      setSelectedItem('');
      setMountedChats([]);
      try {
        const sessions = await fetchSkillConversations(currentAgent.id);
        setFunctionList(
          (sessions || [])
            .filter((item: any) => (item.channel_type || 'web_chat') === 'web_chat')
            .map((item: any) => ({
              id: item.session_id,
              title: item.title || '新会话',
              icon: 'jiqiren3',
              channel_type: 'web_chat',
              persisted: true,
            }))
        );
      } catch {
        setFunctionList([]);
      } finally {
        setFunctionLoading(false);
      }
    }
    loadSessions();
  }, [currentAgent?.id]);

  useEffect(() => {
    if (functionList.length > 0) {
      if (sessionId && functionList.find((item) => item.id === sessionId)) {
        return;
      }
      setSelectedItem(functionList[0].id);
      handleSelectSession(functionList[0]);
      return;
    }
    if (currentAgent?.id) {
      const newId = `session_${Date.now()}`;
      setSessionId(newId);
      setSelectedItem(newId);
      setMountedChats([{ id: newId, initialMessages: [], initialContextUsage: null }]);
    }
  }, [functionList]);

  const agentMenuItems: MenuProps['items'] = agentList.map((agent) => ({
    key: String(agent.id),
    label: (
      <div className="flex items-center gap-2 py-1">
        <Icon type={agent.icon || 'duihuazhinengti'} className="text-xl" />
        <span>{agent.name}</span>
      </div>
    ),
    onClick: () => setCurrentAgent(agent),
  }));

  const mountChat = (session: MountedChatSession) => {
    setMountedChats((current) => (current.some((item) => item.id === session.id) ? current : [...current, session]));
  };

  const handleSelectSession = async (item: SkillChatSession | string) => {
    const session = typeof item === 'string' ? functionList.find((row) => row.id === item) : item;
    const id = session?.id || (typeof item === 'string' ? item : '');
    setSelectedItem(id);
    setSessionId(id);
    if (mountedChats.some((chat) => chat.id === id)) {
      return;
    }
    if (!session?.persisted) {
      mountChat({ id, initialMessages: [], initialContextUsage: null });
      return;
    }
    setOpeningSessionId(id);
    try {
      const payload = await fetchSkillSessionMessages(id);
      const messages = (payload.messages || []).map((row: any) => {
        const role = row.conversation_role === 'user' ? 'user' : 'bot';
        const processed = processHistoryMessageWithExtras(row.conversation_content, role);
        return {
          id: String(row.id),
          role,
          content: processed.content,
          createAt: row.conversation_time,
          thinking: processed.thinking,
          isThinking: false,
          browserStepsHistory: processed.browserStepsHistory ?? null,
          agentStepProgress: processed.agentStepProgress,
          plannedExecutionSteps: processed.plannedExecutionSteps,
          wikiCitations: processed.wikiCitations,
          toolCalls: processed.toolCalls,
          isStreamingTools: false,
          configDiffReports: processed.configDiffReports,
          configAnalysisReports: processed.configAnalysisReports,
          userChoiceRequests: processed.userChoiceRequests,
          approvalRequests: processed.approvalRequests,
          repairCommands: processed.repairCommands,
          reportFileDownloads: processed.reportFileDownloads,
        };
      });
      mountChat({
        id,
        initialMessages: messages,
        initialContextUsage: parseLlmContextUsage(payload.llm_context_usage),
      });
    } catch {
      mountChat({ id, initialMessages: [], initialContextUsage: null });
    } finally {
      setOpeningSessionId((current) => (current === id ? '' : current));
    }
  };

  const handleNewChat = () => {
    const newId = `session_${Date.now()}`;
    setFunctionList((list) => [
      {
        id: newId,
        title: newSessionTitle(),
        icon: 'jiqiren3',
        channel_type: 'web_chat',
        persisted: false,
      },
      ...list,
    ]);
    setSessionId(newId);
    setSelectedItem(newId);
    mountChat({ id: newId, initialMessages: [], initialContextUsage: null });
  };

  const handleDeleteSession = async (sessionIdToDelete: string) => {
    const target = functionList.find((item) => item.id === sessionIdToDelete);
    try {
      if (target?.persisted) {
        await deleteSkillSession(sessionIdToDelete);
      }
      setFunctionList((list) => list.filter((item) => item.id !== sessionIdToDelete));
      setMountedChats((current) => current.filter((chat) => chat.id !== sessionIdToDelete));
      if (selectedItem === sessionIdToDelete) {
        setSelectedItem('');
        setSessionId(null);
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  const handleSendMessage = (panelSessionId: string) => async (message: string) => {
    if (!currentAgent?.id) return null;
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
    const url = `${baseUrl}/api/proxy/opspilot/skill_channel/${currentAgent.id}/chat/`;
    const preview = message.replace(/\n/g, ' ').slice(0, 50);
    setFunctionList((list) => {
      if (list.find((item) => item.id === panelSessionId)) {
        return list.map((item) =>
          item.id === panelSessionId && (!item.persisted || item.title.startsWith('新会话'))
            ? { ...item, title: preview || item.title, persisted: true, channel_type: item.channel_type || 'web_chat' }
            : item.id === panelSessionId
              ? { ...item, persisted: true }
              : item
        );
      }
      return [
        {
          id: panelSessionId,
          title: preview || newSessionTitle(),
          icon: 'jiqiren3',
          channel_type: 'web_chat',
          persisted: true,
        },
        ...list,
      ];
    });
    return {
      url,
      payload: { message, session_id: panelSessionId },
      interruptRequest: {
        enabled: true,
        url: '/api/proxy/opspilot/bot_mgmt/interrupt_chat_flow_execution/',
        reason: 'user_manual',
      },
    };
  };

  const renderChannelTag = (channelType?: string) => {
    const meta = CHANNEL_TYPE_TAG[channelType || 'web_chat'] || { color: 'blue', label: 'Web' };
    return <Tag color={meta.color}>{meta.label}</Tag>;
  };

  return (
    <div className="absolute inset-0 flex overflow-hidden">
      {!sidebarCollapsed && (
        <div className="w-64 flex-shrink-0 border-r border-[var(--color-border-1)] bg-[var(--color-bg)] flex flex-col">
          <div className="px-4 pt-4 pb-3 border-b border-[var(--color-border-1)] flex-shrink-0">
            <div className="flex items-center justify-between mb-3">
              <Dropdown menu={{ items: agentMenuItems }} trigger={['click']} placement="bottomLeft">
                <div className="flex items-center gap-2 cursor-pointer hover:bg-[var(--color-fill-2)] rounded px-2 py-1 flex-1">
                  {agentLoading ? (
                    <Skeleton.Avatar active size="large" shape="circle" />
                  ) : (
                    <Icon type={currentAgent?.icon || 'jiqiren3'} className="text-3xl text-[var(--color-primary)] flex-shrink-0" />
                  )}
                  <span className="text-sm font-medium text-[var(--color-text-1)] truncate flex-1">
                    {agentLoading ? <Skeleton.Input active size="small" style={{ width: 80 }} /> : currentAgent?.name || '暂无可用渠道'}
                  </span>
                  <Icon type="xiala" className="text-[var(--color-text-4)] text-xs flex-shrink-0" />
                </div>
              </Dropdown>
              <div
                className="w-8 h-8 rounded-full bg-[var(--color-bg)] border border-[var(--color-border-1)] shadow-sm hover:shadow-md cursor-pointer hover:text-[var(--color-primary)] transition-all ml-2 flex-shrink-0 flex items-center justify-center"
                onClick={() => setSidebarCollapsed(true)}
              >
                <Icon type="xiangzuoshousuo" className="text-base" />
              </div>
            </div>
            <Button type="primary" className="w-full" icon={<Icon type="tianjia" />} onClick={handleNewChat} disabled={!currentAgent}>
              开启新对话
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto min-h-0">
            <div className="p-2">
              <div className="text-xs text-[var(--color-text-3)] px-3 py-2">历史对话</div>
              <List
                dataSource={functionList}
                loading={functionLoading}
                className="bg-transparent [&_.ant-list-item]:border-none"
                renderItem={(item) => (
                  <List.Item
                    className={`cursor-pointer py-3 px-4 mx-2 mb-1 rounded transition-colors border-0 group ${
                      selectedItem === item.id
                        ? '!bg-[var(--color-primary-bg-active)] hover:!bg-[var(--color-primary-bg-active)]'
                        : '!bg-transparent hover:!bg-[var(--color-fill-2)]'
                    }`}
                    onClick={() => handleSelectSession(item)}
                    style={{ border: 'none' }}
                  >
                    <div className="flex items-center justify-between w-full gap-2">
                      <div className={`text-sm px-2 font-normal flex-1 truncate ${selectedItem === item.id ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-1)]'}`}>
                        <span className="mr-2">{renderChannelTag(item.channel_type)}</span>
                        {item.title}
                      </div>
                      <Popconfirm
                        title="删除会话"
                        description="确定要删除这个会话吗？删除后无法恢复。"
                        onConfirm={() => handleDeleteSession(item.id)}
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                      >
                        <div
                          className="invisible group-hover:visible flex-shrink-0 p-1 rounded cursor-pointer transition-all hover:bg-[var(--color-fail)]/10"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Icon type="shanchu" className="text-[var(--color-text-4)] hover:text-[var(--color-fail)] text-base" />
                        </div>
                      </Popconfirm>
                    </div>
                  </List.Item>
                )}
              />
            </div>
          </div>
        </div>
      )}

      {sidebarCollapsed && (
        <div className="w-12 flex-shrink-0 border-r border-[var(--color-border-1)] bg-[var(--color-bg)] flex flex-col items-center py-4 gap-3">
          <div className="text-xl cursor-pointer text-[var(--color-text-2)] hover:text-[var(--color-primary)] transition-colors" onClick={() => setSidebarCollapsed(false)}>
            <Icon type="xiangyoushousuo" />
          </div>
        </div>
      )}

      <div className="flex-1 bg-[var(--color-bg)] min-w-0 h-full relative">
        {!currentAgent && !agentLoading ? (
          <div className="w-full h-full flex items-center justify-center text-[var(--color-text-3)]">当前组织暂无已启用的 Web 对话渠道</div>
        ) : (
          mountedChats.map((chat) => (
            <div key={chat.id} className={chat.id === selectedItem ? 'h-full' : 'hidden'}>
              <CustomChatSSE
                handleSendMessage={handleSendMessage(chat.id)}
                guide={currentAgent?.app_description || ''}
                useAGUIProtocol={true}
                showHeader={false}
                requirePermission={false}
                initialMessages={chat.initialMessages}
                initialContextUsage={chat.initialContextUsage}
                removePendingBotMessageOnCancel={true}
                conversationHistoryEnabled={currentAgent?.enable_conversation_history !== false}
              />
            </div>
          ))
        )}
        {openingSessionId === selectedItem ? (
          <div className="absolute inset-0 flex items-center justify-center bg-[var(--color-bg)] text-[var(--color-text-4)]">加载中...</div>
        ) : null}
      </div>
    </div>
  );
};

export default SkillWebChatPage;
