'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Dropdown, List, Popconfirm, Skeleton, Tag } from 'antd';
import type { MenuProps } from 'antd';
import CustomChatSSE from '@/app/opspilot/components/custom-chat-sse';
import { processHistoryMessageWithExtras } from '@/app/opspilot/components/custom-chat-sse/historyMessageProcessor';
import { parseLlmContextUsage, type LlmContextUsage } from '@/app/opspilot/components/custom-chat-sse/llmContextUsage';
import Icon from '@/components/icon';
import { useSkillApi } from '@/app/opspilot/api/skill';

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

const CHANNEL_TYPE_TAG: Record<string, { color: string; label: string }> = {
  platform: { color: 'cyan', label: '平台' },
  web_chat: { color: 'blue', label: 'Web' },
  embedded_chat: { color: 'purple', label: '嵌入式' },
  enterprise_wechat: { color: 'green', label: '企微' },
  enterprise_wechat_aibot: { color: 'green', label: '企微机器人' },
  dingtalk: { color: 'orange', label: '钉钉' },
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
  const { fetchWebChatSkillChannels, fetchSkillConversations, fetchSkillSessionMessages, deleteSkillSession } = useSkillApi();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [agentLoading, setAgentLoading] = useState(true);
  const [agentList, setAgentList] = useState<WebChatChannel[]>([]);
  const [currentAgent, setCurrentAgent] = useState<WebChatChannel | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState('');
  const [functionList, setFunctionList] = useState<SkillChatSession[]>([]);
  const [functionLoading, setFunctionLoading] = useState(false);
  const [chatKey, setChatKey] = useState(0);
  const [chatLoading, setChatLoading] = useState(false);
  const [initialMessages, setInitialMessages] = useState<any[]>([]);
  const [initialContextUsage, setInitialContextUsage] = useState<LlmContextUsage | null>(null);
  const chatLoadingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (chatLoadingTimerRef.current) clearTimeout(chatLoadingTimerRef.current);
    };
  }, []);

  useEffect(() => {
    async function loadChannels() {
      setAgentLoading(true);
      try {
        const data = await fetchWebChatSkillChannels();
        const agents = mapWebChatChannels(data);
        setAgentList(agents);
        setCurrentAgent(agents[0] || null);
      } catch {
        setAgentList([]);
        setCurrentAgent(null);
      } finally {
        setAgentLoading(false);
      }
    }
    loadChannels();
  }, []);

  useEffect(() => {
    async function loadSessions() {
      if (!currentAgent?.id) {
        setFunctionList([]);
        setSessionId(null);
        setSelectedItem('');
        setInitialMessages([]);
        setInitialContextUsage(null);
        return;
      }
      setFunctionLoading(true);
      setSessionId(null);
      setSelectedItem('');
      setInitialMessages([]);
      setInitialContextUsage(null);
      try {
        const sessions = await fetchSkillConversations(currentAgent.id);
        setFunctionList(
          (sessions || []).map((item: any) => ({
            id: item.session_id,
            title: item.title || '新会话',
            icon: 'jiqiren3',
            channel_type: item.channel_type || 'web_chat',
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
      setInitialMessages([]);
      setInitialContextUsage(null);
      setChatKey((k) => k + 1);
    }
  }, [functionList]);

  useEffect(() => {
    setChatKey((k) => k + 1);
  }, [initialMessages]);

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

  const handleSelectSession = async (item: SkillChatSession | string) => {
    const session = typeof item === 'string' ? functionList.find((row) => row.id === item) : item;
    const id = session?.id || (typeof item === 'string' ? item : '');
    setChatLoading(true);
    setSelectedItem(id);
    setSessionId(id);
    if (!session?.persisted) {
      setInitialMessages([]);
      setInitialContextUsage(null);
      if (chatLoadingTimerRef.current) clearTimeout(chatLoadingTimerRef.current);
      chatLoadingTimerRef.current = setTimeout(() => setChatLoading(false), 300);
      return;
    }
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
      setInitialMessages(messages);
      setInitialContextUsage(parseLlmContextUsage(payload.llm_context_usage));
    } catch {
      setInitialMessages([]);
      setInitialContextUsage(null);
    } finally {
      if (chatLoadingTimerRef.current) clearTimeout(chatLoadingTimerRef.current);
      chatLoadingTimerRef.current = setTimeout(() => setChatLoading(false), 400);
    }
  };

  const handleNewChat = () => {
    setChatLoading(true);
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
    setInitialMessages([]);
    setInitialContextUsage(null);
    if (chatLoadingTimerRef.current) clearTimeout(chatLoadingTimerRef.current);
    chatLoadingTimerRef.current = setTimeout(() => setChatLoading(false), 300);
  };

  const handleDeleteSession = async (sessionIdToDelete: string) => {
    const target = functionList.find((item) => item.id === sessionIdToDelete);
    try {
      if (target?.persisted) {
        await deleteSkillSession(sessionIdToDelete);
      }
      setFunctionList((list) => list.filter((item) => item.id !== sessionIdToDelete));
      if (selectedItem === sessionIdToDelete) {
        setSelectedItem('');
        setSessionId(null);
        setInitialMessages([]);
        setInitialContextUsage(null);
        setChatKey((k) => k + 1);
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  const handleSendMessage = async (message: string) => {
    if (!currentAgent?.id) return null;
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
    const url = `${baseUrl}/api/proxy/opspilot/skill_channel/${currentAgent.id}/chat/`;
    if (sessionId) {
      const preview = message.replace(/\n/g, ' ').slice(0, 50);
      setFunctionList((list) => {
        if (list.find((item) => item.id === sessionId)) {
          return list.map((item) =>
            item.id === sessionId && (!item.persisted || item.title.startsWith('新会话'))
              ? { ...item, title: preview || item.title, persisted: true, channel_type: item.channel_type || 'web_chat' }
              : item.id === sessionId
                ? { ...item, persisted: true }
                : item
          );
        }
        return [
          {
            id: sessionId,
            title: preview || newSessionTitle(),
            icon: 'jiqiren3',
            channel_type: 'web_chat',
            persisted: true,
          },
          ...list,
        ];
      });
    }
    return {
      url,
      payload: { message, session_id: sessionId },
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
    <div className="absolute left-0 right-0 bottom-0 flex overflow-hidden" style={{ top: '56px', height: 'calc(100vh - 56px)' }}>
      {!sidebarCollapsed && (
        <div className="w-64 flex-shrink-0 border-r border-gray-200 bg-white flex flex-col">
          <div className="px-4 pt-4 pb-3 border-b border-gray-200 flex-shrink-0">
            <div className="flex items-center justify-between mb-3">
              <Dropdown menu={{ items: agentMenuItems }} trigger={['click']} placement="bottomLeft">
                <div className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 rounded px-2 py-1 flex-1">
                  {agentLoading ? (
                    <Skeleton.Avatar active size="large" shape="circle" />
                  ) : (
                    <Icon type={currentAgent?.icon || 'jiqiren3'} className="text-3xl text-blue-500 flex-shrink-0" />
                  )}
                  <span className="text-sm font-medium text-gray-900 truncate flex-1">
                    {agentLoading ? <Skeleton.Input active size="small" style={{ width: 80 }} /> : currentAgent?.name || '暂无可用渠道'}
                  </span>
                  <Icon type="xiala" className="text-gray-400 text-xs flex-shrink-0" />
                </div>
              </Dropdown>
              <div
                className="w-8 h-8 rounded-full bg-white shadow-md hover:shadow-lg cursor-pointer hover:text-blue-500 transition-all ml-2 flex-shrink-0 flex items-center justify-center"
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
              <div className="text-xs text-gray-500 px-3 py-2">历史对话</div>
              <List
                dataSource={functionList}
                loading={functionLoading}
                renderItem={(item) => (
                  <List.Item
                    className={`cursor-pointer py-3 px-4 mx-2 mb-1 rounded hover:bg-gray-100 transition-colors border-0 group ${
                      selectedItem === item.id ? 'bg-blue-50 hover:bg-blue-50' : ''
                    }`}
                    onClick={() => handleSelectSession(item)}
                    style={{ border: 'none' }}
                  >
                    <div className="flex items-center justify-between w-full gap-2">
                      <div className={`text-sm px-2 font-normal flex-1 truncate ${selectedItem === item.id ? 'text-blue-600' : 'text-gray-900'}`}>
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
                          className="invisible group-hover:visible flex-shrink-0 p-1 hover:bg-red-50 rounded cursor-pointer transition-all"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Icon type="shanchu" className="text-gray-400 hover:text-red-500 text-base" />
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
        <div className="w-12 flex-shrink-0 border-r border-gray-200 bg-white flex flex-col items-center py-4 gap-3">
          <div className="text-xl cursor-pointer hover:text-blue-500 transition-colors" onClick={() => setSidebarCollapsed(false)}>
            <Icon type="xiangyoushousuo" />
          </div>
        </div>
      )}

      <div className="flex-1 bg-gray-50 min-w-0 h-full">
        {!currentAgent && !agentLoading ? (
          <div className="w-full h-full flex items-center justify-center text-gray-500">当前组织暂无已启用的 Web 对话渠道</div>
        ) : chatLoading ? (
          <div className="w-full h-full flex items-center justify-center text-gray-400">加载中...</div>
        ) : (
          <CustomChatSSE
            key={chatKey}
            handleSendMessage={handleSendMessage}
            guide={currentAgent?.app_description || ''}
            useAGUIProtocol={true}
            showHeader={false}
            requirePermission={false}
            initialMessages={initialMessages}
            initialContextUsage={initialContextUsage}
            removePendingBotMessageOnCancel={true}
            conversationHistoryEnabled={currentAgent?.enable_conversation_history !== false}
          />
        )}
      </div>
    </div>
  );
};

export default SkillWebChatPage;
