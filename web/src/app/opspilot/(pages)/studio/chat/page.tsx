'use client';

import React, { useState, useEffect } from 'react';
import { useStudioApi } from '@/app/opspilot/api/studio';
import { List, Button, Dropdown, Skeleton } from 'antd';
import CustomChatSSE from '@/app/opspilot/components/custom-chat-sse';
import Icon from '@/components/icon';
import type { MenuProps } from 'antd';

const StudioChatPage: React.FC = () => {
  const [selectedItem, setSelectedItem] = useState<string>('k8s');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  // 聊天区重置用 key
  const [chatKey, setChatKey] = useState(0);

  const [agentList, setAgentList] = useState<any[]>([]);
  const [currentAgent, setCurrentAgent] = useState<any | null>(null);
  const [agentLoading, setAgentLoading] = useState(true);

  // 新增：记录当前会话 sessionId
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [functionList, setFunctionList] = useState<any[]>([]);
  const [functionLoading, setFunctionLoading] = useState(false);

  const { fetchApplication, fetchWebChatSessions, fetchSessionMessages } = useStudioApi();

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

  // 监听 agent 变化，获取历史会话
  useEffect(() => {
    async function fetchSessions() {
      if (!currentAgent?.bot_id) {
        setFunctionList([]);
        return;
      }
      setFunctionLoading(true);
      try {
        const sessions = await fetchWebChatSessions(currentAgent.bot_id);
        // sessions: [{ session_id, title }]
        setFunctionList(
          (sessions || []).map((item: any) => ({
            id: item.session_id,
            title: item.title,
            icon: 'jiqiren3', // 可根据需要调整
          }))
        );
      } catch {
        setFunctionList([]);
      } finally {
        setFunctionLoading(false);
      }
    }
    fetchSessions();
  }, [currentAgent]);

  // 监听 functionList 变化，自动选中第一个历史会话并展示其消息
  useEffect(() => {
    if (functionList.length > 0) {
      setSelectedItem(functionList[0].id);
      handleSelectSession(functionList[0].id);
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

  // 点击历史会话，获取消息列表
  const handleSelectSession = async (id: string) => {
    setSelectedItem(id);
    try {
      const data = await fetchSessionMessages(id);
      const messages = (data || []).map((item: any) => ({
        id: String(item.id),
        role: item.conversation_role === 'user' ? 'user' : 'bot',
        content: item.conversation_content,
        createAt: item.conversation_time,
      }));
      setInitialMessages(messages);
    } catch {
      setInitialMessages([]);
    }
  };

  const handleNewChat = () => {
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
  };

  const handleSendMessage = async (message: string) => {
    try {
      const bot_id = currentAgent?.bot_id;
      const node_id = currentAgent?.node_id;
      const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
      const url = `${baseUrl}/api/proxy/opspilot/bot_mgmt/execute_chat_flow/${bot_id}/${node_id}/`;
      const payload = {
        user_message: message,
        session_id: sessionId,
      };
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
                className="text-xl cursor-pointer hover:text-blue-500 transition-colors ml-2 flex-shrink-0"
                onClick={() => setSidebarCollapsed(true)}
              >
                <Icon type="xiangzuoshousuo" />
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
                    className={`cursor-pointer py-3 px-4 mx-2 mb-1 rounded hover:bg-gray-100 transition-colors border-0 ${
                      selectedItem === item.id ? 'bg-blue-50 hover:bg-blue-50' : ''
                    }`}
                    onClick={() => handleSelectSession(item.id)}
                    style={{ border: 'none' }}
                  >
                    <div className={`text-sm px-2 font-normal ${selectedItem === item.id ? 'text-blue-600' : 'text-gray-900'}`}>
                      {item.title}
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
        <CustomChatSSE
          key={chatKey}
          handleSendMessage={handleSendMessage}
          guide={''}
          useAGUIProtocol={true}
          showHeader={false}
          requirePermission={false}
          initialMessages={initialMessages}
        />
      </div>
    </div>
  );
};

export default StudioChatPage;
