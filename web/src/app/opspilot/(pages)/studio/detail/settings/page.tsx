'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Form, Button, Dropdown, Menu, Tag, message, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { DownOutlined } from '@ant-design/icons';
import useGroups from '@/app/opspilot/hooks/useGroups';
import { useSearchParams } from 'next/navigation';
import type { ChatflowExecutionState } from '@/app/opspilot/components/chatflow/types';
import PermissionWrapper from '@/components/permission';
import styles from '@/app/opspilot/styles/common.module.scss';
import Icon from '@/components/icon';
import { useStudioApi } from '@/app/opspilot/api/studio';
import ChatflowSettings from '@/app/opspilot/components/studio/chatflowSettings';
import { useUnsavedChanges } from '@/app/opspilot/hooks/useUnsavedChanges';
import { useStudio } from '@/app/opspilot/context/studioContext';

const actionButtonClassName = 'inline-flex h-7 items-center rounded-md px-2.5 text-[11px] font-medium leading-none';
const actionTagClassName = 'mb-0 mr-0 inline-flex h-7 items-center rounded-md px-2 text-[11px] font-medium leading-none';

const StudioSettingsPage: React.FC = () => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { groups } = useGroups();
  const [pageLoading, setPageLoading] = useState(true);
  const [saveLoading, setSaveLoading] = useState(false);
  const [botPermissions, setBotPermissions] = useState<string[]>([]);
  const [online, setOnline] = useState(false);
  const [workflowData, setWorkflowData] = useState<{ nodes: any[], edges: any[] }>({ nodes: [], edges: [] });
  const [initialExecutionId, setInitialExecutionId] = useState<string | null>(null);
  const [chatflowExecutionState, setChatflowExecutionState] = useState<ChatflowExecutionState>({
    summary: { status: 'idle' },
    previewOpen: false,
    latestExecutionId: '',
    openPreview: () => {},
    closePreview: () => {},
  });

  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [originalWorkflowData, setOriginalWorkflowData] = useState<{ nodes: any[], edges: any[] }>({ nodes: [], edges: [] });

  const searchParams = useSearchParams();
  const botId = searchParams ? searchParams.get('id') : null;
  const { fetchInitialData, saveBotConfig, toggleOnlineStatus } = useStudioApi();
  const { refreshBotInfo } = useStudio();

  useEffect(() => {
    if (!botId) return;

    const fetchData = async () => {
      try {
        const [,,,botData] = await fetchInitialData(botId);

        setInitialExecutionId(botData.execution_id || null);

        if (botData.workflow_data && typeof botData.workflow_data === 'object') {
          const { nodes = [], edges = [] } = botData.workflow_data;
          if (Array.isArray(nodes) && Array.isArray(edges)) {
            setWorkflowData({ nodes, edges });
          }
        }

        form.setFieldsValue({
          name: botData.name,
          introduction: botData.introduction,
          group: botData.team,
        });

        setOnline(botData.online);
        setBotPermissions(botData.permissions || []);
      } catch {
        message.error(t('common.fetchFailed'));
      } finally {
        setPageLoading(false);
      }
    };

    fetchData();
  }, [botId]);

  // Initialize original workflow data when page loads
  useEffect(() => {
    if (!pageLoading) {
      setOriginalWorkflowData({
        nodes: [...workflowData.nodes],
        edges: [...workflowData.edges]
      });
      setHasUnsavedChanges(false);
    }
  }, [pageLoading]);

  const toggleOnline = async () => {
    try {
      await toggleOnlineStatus(botId);
      setOnline(prevOnline => !prevOnline);
      message.success(t('common.saveSuccess'));
    } catch {
      message.error(t('common.saveFailed'));
    }
  };

  const theme = typeof window !== 'undefined' && localStorage.getItem('theme');
  const overlayBgClass = theme === 'dark' ? 'bg-gray-950' : 'bg-white';

  // Move chatflow related functions to top level
  const handleClearCanvas = () => {
    const emptyWorkflowData = { nodes: [], edges: [] };
    setWorkflowData(emptyWorkflowData);

    // Check if clearing makes data different from original
    const originalDataStr = JSON.stringify(originalWorkflowData);
    const emptyDataStr = JSON.stringify(emptyWorkflowData);
    const isChanged = originalDataStr !== emptyDataStr;
    setHasUnsavedChanges(isChanged);

    message.success('Canvas cleared');
  };

  const handleSaveWorkflow = useCallback((newWorkflowData: { nodes: any[], edges: any[] }) => {
    // Update workflow data
    setWorkflowData(prev => {
      const prevDataStr = JSON.stringify(prev);
      const newDataStr = JSON.stringify(newWorkflowData);

      if (prevDataStr !== newDataStr) {
        // Check if data has changed from original
        const originalDataStr = JSON.stringify(originalWorkflowData);
        const isChanged = newDataStr !== originalDataStr;
        setHasUnsavedChanges(isChanged);

        return { nodes: [...newWorkflowData.nodes], edges: [...newWorkflowData.edges] };
      }

      return prev;
    });
  }, [originalWorkflowData]);

  const handleChatflowSave = async (isPublish = false) => {
    setSaveLoading(true);
    try {
      const values = await form.validateFields();

      const payload = {
        name: values.name,
        introduction: values.introduction,
        team: values.group,
        workflow_data: workflowData,
        is_publish: isPublish
      };

      await saveBotConfig(botId, payload);

      // Reset unsaved changes status after successful save
      setOriginalWorkflowData({
        nodes: [...workflowData.nodes],
        edges: [...workflowData.edges]
      });
      setHasUnsavedChanges(false);
      refreshBotInfo();

      message.success(t(isPublish ? 'common.publishSuccess' : 'common.saveSuccess'));

      if (isPublish) {
        setOnline(true);
      }
    } catch (error) {
      console.error('Save failed', error);
      message.error(t('common.saveFailed'));
    } finally {
      setSaveLoading(false);
    }
  };

  // Setup unsaved changes warning
  useUnsavedChanges({
    hasUnsavedChanges: hasUnsavedChanges,
    onSave: async () => {
      await handleChatflowSave(false);
    },
    message: t('chatflow.unsavedWorkflowChanges')
  });

  // Move chatflowMenu to top level
  const chatflowMenu = (
    <Menu style={{ width: 300 }}>
      <Menu.Item key="info" disabled style={{ whiteSpace: 'normal', opacity: 1, cursor: 'default' }}>
        <div className="text-sm">{t('studio.settings.publishTip')} {t('studio.settings.selectedParams')}</div>
      </Menu.Item>
      <Menu.Divider />
      <Menu.Item key="save_publish">
        <PermissionWrapper
          className='w-full'
          requiredPermissions={['Save&Publish']}
          instPermissions={botPermissions}>
          <Button type="primary" size="small" style={{ width: '100%' }} onClick={() => handleChatflowSave(true)}>
            {t('common.save')} & {t('common.publish')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key="save_only">
        <PermissionWrapper
          className='w-full'
          requiredPermissions={['Edit']}
          instPermissions={botPermissions}>
          <Button size="small" style={{ width: '100%' }} onClick={() => handleChatflowSave(false)}>
            {t('common.saveOnly')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
      {online && (
        <Menu.Item key="offline" onClick={toggleOnline}>
          <div className="flex justify-end items-center">
            <span className="mr-1.25 text-gray-500">{t('studio.off')}</span>
            <Icon type="offline" />
          </div>
        </Menu.Item>
      )}
    </Menu>
  );

  const renderChatflowExecutionAction = () => {
    const { summary, previewOpen, latestExecutionId, openPreview } = chatflowExecutionState;
    if (summary.status === 'idle') {
      return null;
    }

    const label = summary.status === 'running'
      ? t('chatflow.preview.running')
      : summary.status === 'failed'
        ? t('chatflow.preview.failed')
        : summary.status === 'interrupted'
          ? t('chatflow.preview.interrupted', '已中断')
          : summary.status === 'interrupt_requested'
            ? t('chatflow.preview.interruptRequested', '中断中')
            : t('chatflow.preview.success');

    const statusColor = summary.status === 'running'
      ? 'processing'
      : summary.status === 'failed'
        ? 'error'
        : summary.status === 'interrupted'
          ? 'default'
          : summary.status === 'interrupt_requested'
            ? 'orange'
            : 'success';

    const logButton = (
      <Button
        size="small"
        type={previewOpen ? 'primary' : 'default'}
        className={actionButtonClassName}
        onClick={openPreview}
      >
        {t('chatflow.preview.logTitle')}
      </Button>
    );

    const statusTag = (
      <Tag color={statusColor} className={actionTagClassName}>
        {label}
      </Tag>
    );

    if (summary.status === 'failed' && summary.reason) {
      return (
        <div className="flex items-center gap-2">
          {logButton}
          <span title={summary.reason}>{statusTag}</span>
        </div>
      );
    }

    if (latestExecutionId) {
      return (
        <div className="flex items-center gap-2">
          <span title={latestExecutionId}>{logButton}</span>
          <span title={latestExecutionId}>{statusTag}</span>
        </div>
      );
    }

    return (
      <div className="flex items-center gap-2">
        {logButton}
        {statusTag}
      </div>
    );
  };

  // Render chatflow interface
  return (
    <div className="relative flex w-full h-full">
      {(pageLoading || saveLoading) && (
        <div
          className={`absolute inset-0 flex justify-center items-center min-h-125 ${overlayBgClass} bg-opacity-50 z-50`}>
          <Spin size="large" />
        </div>
      )}
      {!pageLoading && (
        <div className="w-full flex flex-col h-full">
          <div className="absolute top-0 right-0 z-10 flex items-center gap-2">
            {renderChatflowExecutionAction()}
            <Tag
              color={online ? 'green' : ''}
              className={`${styles.statusTag} ${actionTagClassName} ${online ? styles.online : styles.offline}`}
            >
              {online ? t('studio.on') : t('studio.off')}
            </Tag>
            <Dropdown overlay={chatflowMenu} trigger={['click']}>
              <Button icon={<DownOutlined />} size="small" type="primary" className={actionButtonClassName}>
                {t('common.settings')}
              </Button>
            </Dropdown>
          </div>

          <ChatflowSettings
            form={form}
            groups={groups}
            onClear={handleClearCanvas}
            onSaveWorkflow={handleSaveWorkflow}
            workflowData={workflowData}
            initialExecutionId={initialExecutionId}
            onExecutionStateChange={setChatflowExecutionState}
          />
        </div>
      )}
    </div>
  );
};

export default StudioSettingsPage;
