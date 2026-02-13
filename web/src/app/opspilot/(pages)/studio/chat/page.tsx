'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useStudioApi } from '@/app/opspilot/api/studio';
import { List, Button, Dropdown, Skeleton, Popconfirm } from 'antd';
import CustomChatSSE from '@/app/opspilot/components/custom-chat-sse';
import { processHistoryMessageContent } from '@/app/opspilot/components/custom-chat-sse/historyMessageProcessor';
import Icon from '@/components/icon';
import type { MenuProps } from 'antd';

const StudioChatPage: React.FC = () => {
  const [selectedItem, setSelectedItem] = useState<string>('k8s');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [chatKey, setChatKey] = useState(0);

  const [agentList, setAgentList] = useState<any[]>([]);
  const [currentAgent, setCurrentAgent] = useState<any | null>(null);
  const [agentLoading, setAgentLoading] = useState(true);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [functionList, setFunctionList] = useState<any[]>([]);
  const [functionLoading, setFunctionLoading] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);

  const chatLoadingTimerRef = useRef<NodeJS.Timeout | null>(null);

  const { fetchApplication, fetchWebChatSessions, fetchSessionMessages, fetchSkillGuide, deleteSessionHistory } = useStudioApi();

  useEffect(() => {
    return () => {
      if (chatLoadingTimerRef.current) clearTimeout(chatLoadingTimerRef.current);
    };
  }, []);

  useEffect(() => {
    async function fetchAgents() {
      setAgentLoading(true);
      try {
        const data = await fetchApplication({ app_type: 'web_chat' });
        const agents = (data || []).map((item: any) => ({
          id: item.id,
          name: item.app_name,
          icon: item.app_icon || item.node_config?.appIcon || 'duihuazhinengti',
          description: item.app_description || item.node_config?.appDescription || '',
          bot_id: item.bot,
          node_id: item.node_id
        }));
        setAgentList(agents);
        if (agents.length > 0) setCurrentAgent(agents[0]);
      } catch {
        setAgentList([]);
        setCurrentAgent(null);
      } finally {
        setAgentLoading(false);
      }
    }
    fetchAgents();
  }, []);

  // 监听 agent 变化，获取历史会话和引导语
  useEffect(() => {
    async function fetchSessionsAndGuide() {
      if (!currentAgent?.bot_id) {
        setFunctionList([]);
        setGuide('');
        setSessionId(null);
        setSelectedItem('');
        setInitialMessages([]);
        return;
      }
      setFunctionLoading(true);
      // 切换 agent 时重置状态
      setSessionId(null);
      setSelectedItem('');
      setInitialMessages([]);
      
      try {
        const sessions = await fetchWebChatSessions(currentAgent.bot_id, currentAgent.node_id);
        setFunctionList(
          (sessions || []).map((item: any) => ({
            id: item.session_id,
            title: item.title,
            icon: 'jiqiren3',
          }))
        );
        if (currentAgent?.bot_id && currentAgent?.node_id) {
          const guideRes = await fetchSkillGuide(currentAgent.bot_id, currentAgent.node_id);
          setGuide(guideRes?.guide || '');
        } else {
          setGuide('');
        }
      } catch {
        setFunctionList([]);
        setGuide('');
      } finally {
        setFunctionLoading(false);
      }
    }
    fetchSessionsAndGuide();
  }, [currentAgent]);

  // 监听 functionList 变化，自动选中第一个历史会话并展示其消息
  useEffect(() => {
    if (functionList.length > 0) {
      // 如果当前已经有选中的会话，不要重新加载（避免打断正在进行的对话）
      if (sessionId && functionList.find(item => item.id === sessionId)) {
        return;
      }
      setSelectedItem(functionList[0].id);
      handleSelectSession(functionList[0].id);
    } else if (currentAgent?.bot_id) {
      // 如果没有历史对话但有当前应用，创建一个新会话以便用户开始对话
      const newId = `session_${Date.now()}`;
      setSessionId(newId);
      setSelectedItem(newId);
      setInitialMessages([]);
      setChatKey(k => k + 1);
    }
  }, [functionList]);

  const agentMenuItems: MenuProps['items'] = agentList.map(agent => ({
    key: agent.id,
    label: (
      <div className="flex items-center gap-2 py-1">
        <Icon type={agent.icon} className="text-xl" />
        <span>{agent.name}</span>
      </div>
    ),
    onClick: () => setCurrentAgent(agent),
  }));

  const [initialMessages, setInitialMessages] = useState<any[]>([]);
  const [guide, setGuide] = useState<string>('');

  const handleSelectSession = async (id: string) => {
    setChatLoading(true);
    setSelectedItem(id);
    setSessionId(id);
    try {
      const data = await fetchSessionMessages(id);
      const messages = (data || []).map((item: any) => ({
        id: String(item.id),
        role: item.conversation_role === 'user' ? 'user' : 'bot',
        content: processHistoryMessageContent(item.conversation_content, item.conversation_role),
        createAt: item.conversation_time,
      }));
      setInitialMessages(messages);
    } catch {
      setInitialMessages([]);
    } finally {
      if (chatLoadingTimerRef.current) clearTimeout(chatLoadingTimerRef.current);
      chatLoadingTimerRef.current = setTimeout(() => {
        setChatLoading(false);
      }, 400);
    }
  };

  const handleNewChat = () => {
    setChatLoading(true);
    setChatKey(k => k + 1);
    const newId = `session_${Date.now()}`;
    setFunctionList(list => [
      {
        id: newId,
        title: `新会话 ${new Date().toLocaleString('zh-CN', { hour12: false })}`,
        icon: 'jiqiren3',
      },
      ...list
    ]);
    setSessionId(newId);
    setSelectedItem(newId);
    setInitialMessages([]);
    if (chatLoadingTimerRef.current) clearTimeout(chatLoadingTimerRef.current);
    chatLoadingTimerRef.current = setTimeout(() => {
      setChatLoading(false);
    }, 400);
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!currentAgent?.node_id) return;
    
    try {
      await deleteSessionHistory(currentAgent.node_id, sessionId);
      // 从列表中移除
      setFunctionList(list => list.filter(item => item.id !== sessionId));
      // 如果删除的是当前选中的会话，清空选择
      if (selectedItem === sessionId) {
        setSelectedItem('');
        setSessionId(null);
        setInitialMessages([]);
        setChatKey(k => k + 1);
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  const handleSendMessage = async (message: string) => {
    try {
      const bot_id = currentAgent?.bot_id;
      const node_id = currentAgent?.node_id;
      const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
      const url = `${baseUrl}/api/proxy/opspilot/bot_mgmt/execute_chat_flow/${bot_id}/${node_id}/`;
      const payload = {
        message: message,
        session_id: sessionId,
      };
      
      // 如果是临时会话（以 session_ 开头），在首次发送消息后添加到历史列表
      if (sessionId && sessionId.startsWith('session_') && !functionList.find(item => item.id === sessionId)) {
        setFunctionList(list => [
          {
            id: sessionId,
            title: `新会话 ${new Date().toLocaleString('zh-CN', { hour12: false })}`,
            icon: 'jiqiren3',
          },
          ...list
        ]);
      }
      
      return {
        url,
        payload
      };
    } catch (error) {
      console.error('Failed to send message:', error);
      return null;
    }
  };

  // initialMessages 变化时，重置 chatKey 以强制刷新 CustomChatSSE
  useEffect(() => {
    setChatKey(k => k + 1);
  }, [initialMessages]);

  return (
    <div className="absolute left-0 right-0 bottom-0 flex overflow-hidden" style={{ top: '56px', height: 'calc(100vh - 56px)' }}>
      {!sidebarCollapsed && (
        <div className="w-64 flex-shrink-0 border-r border-gray-200 bg-white flex flex-col">
          {/* 顶部智能体选择器和收缩按钮 */}
          <div className="px-4 pt-4 pb-3 border-b border-gray-200 flex-shrink-0">
            <div className="flex items-center justify-between mb-3">
              <Dropdown menu={{ items: agentMenuItems }} trigger={['click']} placement="bottomLeft">
                <div className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 rounded px-2 py-1 flex-1">
                  {agentLoading ? (
                    <Skeleton.Avatar active size="large" shape="circle" />
                  ) : (
                    <Icon 
                      type={currentAgent?.icon || 'jiqiren3'} 
                      className="text-3xl text-blue-500 flex-shrink-0"
                    />
                  )}
                  <span className="text-sm font-medium text-gray-900 truncate flex-1">
                    {agentLoading ? <Skeleton.Input active size="small" style={{ width: 80 }} /> : (currentAgent?.name || '')}
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
            <Button 
              type="primary" 
              className="w-full" 
              icon={<Icon type="tianjia" />}
              onClick={handleNewChat}
            >
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
                    onClick={() => handleSelectSession(item.id)}
                    style={{ border: 'none' }}
                  >
                    <div className="flex items-center justify-between w-full gap-2">
                      <div className={`text-sm px-2 font-normal flex-1 truncate ${selectedItem === item.id ? 'text-blue-600' : 'text-gray-900'}`}>
                        {item.title}
                      </div>
                      <Popconfirm
                        title="删除会话"
                        description="确定要删除这个会话吗？删除后无法恢复。"
                        onConfirm={(e) => handleDeleteSession(e!, item.id)}
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

      {/* 收缩状态的侧边栏 */}
      {sidebarCollapsed && (
        <div className="w-12 flex-shrink-0 border-r border-gray-200 bg-white flex flex-col items-center py-4 gap-3">
          <div 
            className="text-xl cursor-pointer hover:text-blue-500 transition-colors"
            onClick={() => setSidebarCollapsed(false)}
          >
            <Icon type="xiangyoushousuo" />
          </div>
          <div className="h-px w-8 bg-gray-200" />
          <div 
            className="cursor-pointer"
            onClick={() => setSidebarCollapsed(false)}
          >
            <Icon 
              type={currentAgent.icon} 
              className="text-3xl text-blue-500"
            />
          </div>
          <div className="text-xl cursor-pointer hover:text-blue-500 transition-colors">
            <Icon type="quanping1" />
          </div>
        </div>
      )}

      {/* 右侧对话区域 */}
      <div className="flex-1 bg-gray-50 min-w-0 h-full">
        {chatLoading ? (
          <div className="w-full h-full flex flex-col pt-8">
            <div className="flex gap-4 items-end mb-6 w-full px-8">
              <div className="rounded-full bg-blue-100 w-12 h-12 flex items-center justify-center">
                <Icon type="jiqiren3" className="text-2xl text-blue-500" />
              </div>
              <div className="flex-1">
                <div className="h-4 bg-gray-200 rounded w-2/3 mb-2 animate-pulse" />
                <div className="h-4 bg-gray-200 rounded w-1/2 animate-pulse" />
              </div>
            </div>
            <div className="flex gap-4 items-end justify-end mb-6 w-full px-8">
              <div className="flex-1 text-right">
                <div className="h-4 bg-gray-200 rounded w-1/2 mb-2 animate-pulse inline-block" />
                <div className="h-4 bg-gray-200 rounded w-2/3 animate-pulse inline-block" />
              </div>
              <div className="rounded-full bg-gray-100 w-12 h-12 flex items-center justify-center">
                <Icon type="yonghu" className="text-2xl text-gray-500" />
              </div>
            </div>
            <div className="flex gap-4 items-end mb-6 w-full px-8">
              <div className="rounded-full bg-blue-100 w-12 h-12 flex items-center justify-center">
                <Icon type="jiqiren3" className="text-2xl text-blue-500" />
              </div>
              <div className="flex-1">
                <div className="h-4 bg-gray-200 rounded w-1/2 mb-2 animate-pulse" />
                <div className="h-4 bg-gray-200 rounded w-1/3 animate-pulse" />
              </div>
            </div>
          </div>
        ) : (
          <CustomChatSSE
            key={chatKey}
            handleSendMessage={handleSendMessage}
            guide={guide}
            useAGUIProtocol={true}
            showHeader={false}
            requirePermission={false}
            initialMessages={initialMessages}
          />
        )}
      </div>
    </div>
  );
};

export default StudioChatPage;
