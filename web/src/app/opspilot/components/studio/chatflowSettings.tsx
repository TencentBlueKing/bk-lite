'use client';

import React, { useState, useRef } from 'react';
import { Form, Input, Select, Collapse } from 'antd';
import { CaretRightOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import ChatflowEditor, { ChatflowEditorRef } from '@/app/opspilot/components/chatflow/ChatflowEditor';
import type { ChatflowExecutionState } from '@/app/opspilot/components/chatflow/types';
import Icon from '@/components/icon';

const { Option } = Select;
const { TextArea } = Input;
const { Panel } = Collapse;

const nodeCategories = [
  {
    key: 'triggers',
    labelKey: 'chatflow.triggers',
    items: [
      { type: 'celery', icon: 'a-icon-dingshichufa1x', labelKey: 'chatflow.celery' },
      { type: 'restful', icon: 'RESTfulAPI', labelKey: 'chatflow.restful' },
      { type: 'openai', icon: 'icon-test2', labelKey: 'chatflow.openai' },
      { type: 'agui', icon: 'huifu-copy', labelKey: 'chatflow.agui' },
    ]
  },
  {
    key: 'applications',
    labelKey: 'chatflow.applications',
    items: [
      { type: 'embedded_chat', icon: 'wendaduihua', labelKey: 'chatflow.embeddedChat' },
      { type: 'web_chat', icon: 'WebSphereMQ', labelKey: 'chatflow.webChat' },
      { type: 'mobile', icon: 'zhuji', labelKey: 'chatflow.mobile' },
      { type: 'enterprise_wechat', icon: 'qiwei2', labelKey: 'chatflow.enterpriseWechat' },
      { type: 'dingtalk', icon: 'dingding', labelKey: 'chatflow.dingtalk' },
      { type: 'wechat_official', icon: 'weixingongzhonghao', labelKey: 'chatflow.wechatOfficial' },
    ]
  },
  {
    key: 'agents',
    labelKey: 'chatflow.agents',
    items: [
      { type: 'agents', icon: 'zhinengti', labelKey: 'chatflow.agents' }
    ]
  },
  {
    key: 'logic',
    labelKey: 'chatflow.logicNodes',
    items: [
      { type: 'condition', icon: 'tiaojianfenzhi', labelKey: 'chatflow.condition' },
      { type: 'intent_classification', icon: 'question-circle-fill', labelKey: 'chatflow.intentClassification' }
    ]
  },
  {
    key: 'actions',
    labelKey: 'chatflow.actionNodes',
    items: [
      { type: 'http', icon: 'HTTP', labelKey: 'chatflow.http' },
      { type: 'notification', icon: 'alarm', labelKey: 'chatflow.notification' }
    ]
  }
];

// 节点库项目组件 - 增强版本
const NodeLibraryItem = ({ type, icon, label, onDragStart }: {
  type: string;
  icon: string;
  label: string;
  onDragStart: (event: React.DragEvent, nodeType: string) => void;
}) => {
  const handleDragStart = (event: React.DragEvent<HTMLDivElement>) => {
    event.dataTransfer.setData('application/reactflow', type);
    event.dataTransfer.effectAllowed = 'move';

    // 添加视觉反馈
    const target = event.currentTarget as HTMLDivElement;
    target.style.opacity = '0.5';

    // 调用父组件的处理函数
    onDragStart(event, type);
  };

  const handleDragEnd = (event: React.DragEvent<HTMLDivElement>) => {
    const target = event.currentTarget as HTMLDivElement;
    target.style.opacity = '1';
  };

  return (
    <div
      className="flex flex-1 items-center rounded border border-gray-200 p-2 text-(--color-text-2) cursor-grab transition-all duration-200 hover:border-blue-400 hover:bg-blue-50 hover:text-(--color-primary)"
      draggable
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <Icon type={icon} className="mr-2 text-sm text-blue-500 shrink-0" />
      <span className="text-xs truncate">{label}</span>
    </div>
  );
};

interface ChatflowSettingsProps {
  form: any;
  groups: any[];
  onClear?: () => void;
  onSaveWorkflow?: (workflowData: { nodes: any[], edges: any[] }) => void;
  workflowData?: { nodes: any[], edges: any[] } | null;
  initialExecutionId?: string | null;
  onExecutionStateChange?: (state: ChatflowExecutionState) => void;
}

const ChatflowSettings: React.FC<ChatflowSettingsProps> = ({
  form,
  groups,
  onClear,
  onSaveWorkflow,
  workflowData,
  initialExecutionId,
  onExecutionStateChange,
}) => {
  const { t } = useTranslation();
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [activeAccordionKeys, setActiveAccordionKeys] = useState<string[]>(['nodes']);
  const chatflowEditorRef = useRef<ChatflowEditorRef>(null);

  const onDragStart = (event: React.DragEvent, nodeType: string) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.effectAllowed = 'move';
  };

  const handleAccordionChange = (keys: string | string[]) => {
    setActiveAccordionKeys(Array.isArray(keys) ? keys : [keys]);
  };

  const handleWorkflowChange = (nodes: any[], edges: any[]) => {
    if (onSaveWorkflow) {
      onSaveWorkflow({ nodes, edges });
    }
  };

  // 处理清空画布的回调
  const handleClearClick = () => {
    // Clear the editor directly using ref
    if (chatflowEditorRef.current) {
      chatflowEditorRef.current.clearCanvas();
    }

    // Notify parent component to clear workflow data
    if (onClear) {
      onClear();
    }
  };

  return (
    <div className="w-full flex h-full">
      {/* Left Sidebar - Combined Information and Nodes */}
      <div className={`transition-all duration-300 ease-in-out border-r border-(--color-border-2) overflow-y-auto h-[calc(100vh-200px)] ${
        isSidebarCollapsed ? 'w-0 opacity-0' : 'w-80'
      }`}>
        <div>
          <Collapse
            size="small"
            ghost
            activeKey={activeAccordionKeys}
            onChange={handleAccordionChange}
            expandIcon={({ isActive }) => <CaretRightOutlined rotate={isActive ? 90 : 0} />}
            className="bg-transparent"
          >
            {/* Information Panel - 默认不展开 */}
            <Panel
              key="information"
              header={
                <div className="flex items-center">
                  <span className="text-sm font-medium">{t('studio.information')}</span>
                </div>
              }
            >
              <div className="pt-2">
                <Form form={form} labelCol={{ flex: '0 0 60px' }} wrapperCol={{ flex: '1' }}>
                  <Form.Item
                    label={t('common.name')}
                    name="name"
                    rules={[{ required: true, message: `${t('common.inputMsg')}${t('common.name')}` }]}
                  >
                    <Input />
                  </Form.Item>
                  <Form.Item
                    label={t('common.organization')}
                    name="group"
                    rules={[{ required: true, message: `${t('common.inputMsg')}${t('common.organization')}` }]}
                  >
                    <Select mode="multiple">
                      {groups.map((group) => (
                        <Option key={group.id} value={group.id}>
                          {group.name}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                  <Form.Item
                    label={t('studio.form.introduction')}
                    name="introduction"
                    rules={[{ required: true, message: `${t('common.inputMsg')}${t('studio.form.introduction')}` }]}
                  >
                    <TextArea rows={4} />
                  </Form.Item>
                </Form>
              </div>
            </Panel>

            {/* Nodes Panel - 默认展开 */}
            <Panel
              key="nodes"
              header={
                <div className="flex items-center">
                  <span className="text-sm font-medium">{t('chatflow.nodes')}</span>
                </div>
              }
            >
              <div>
                <Collapse
                  size="small"
                  ghost
                  defaultActiveKey={['triggers', 'applications', 'agents', 'logic', 'actions']}
                  expandIcon={({ isActive }) => <CaretRightOutlined rotate={isActive ? 90 : 0} />}
                >
                  {nodeCategories.map((category) => (
                    <Panel
                      key={category.key}
                      header={
                        <div className="flex items-center">
                          <span className="mt-0.75 text-xs">{t(category.labelKey)}</span>
                        </div>
                      }
                    >
                      <div className="grid grid-cols-2 gap-2">
                        {category.items.map((item) => (
                          <NodeLibraryItem
                            key={item.type}
                            type={item.type}
                            icon={item.icon}
                            label={t(item.labelKey)}
                            onDragStart={onDragStart}
                          />
                        ))}
                      </div>
                    </Panel>
                  ))}
                </Collapse>
              </div>
            </Panel>
          </Collapse>
        </div>
      </div>

      {/* Sidebar Toggle Button */}
      <div className="relative">
        <button
          onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          className="absolute top-1/2 z-10 flex h-6 w-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-gray-300 bg-(--color-bg) shadow-sm transition-colors hover:bg-gray-50"
          style={{ left: '0px' }}
          title={isSidebarCollapsed ? t('chatflow.expandSidebar') : t('chatflow.collapseSidebar')}
        >
          <Icon
            type={isSidebarCollapsed ? 'icon-test1' : 'icon-test'}
            className="text-gray-500 text-lg"
          />
        </button>
      </div>

      {/* Right Panel - Chatflow Canvas */}
      <div className={`flex-1 transition-all duration-300 ease-in-out ${
        isSidebarCollapsed ? 'pl-8' : 'pl-4'
      }`}>
        <div className="flex items-center mb-2 px-2">
          <h2 className="text-sm font-semibold text-(--color-text-1)">{t('chatflow.canvas')}</h2>
          <button
            onClick={handleClearClick}
            className="text-gray-500 hover:text-red-500 transition-colors p-1 rounded hover:bg-red-50 ml-2"
            title={t('chatflow.clear')}
          >
            <Icon type="shanchu" className="text-lg" />
          </button>
        </div>
        <div className="border rounded-md shadow-sm bg-white h-[calc(100vh-230px)] mx-2">
          <ChatflowEditor
            ref={chatflowEditorRef}
            onSave={handleWorkflowChange}
            initialData={workflowData}
            initialExecutionId={initialExecutionId}
            onExecutionStateChange={onExecutionStateChange}
          />
        </div>
      </div>
    </div>
  );
};

export default ChatflowSettings;
