'use client';

import React from 'react';
import { Form, Input } from 'antd';
import type { UploadProps } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { message } from 'antd';
import {
  CeleryNodeConfig,
  HttpNodeConfig,
  AgentsNodeConfig,
  ApiInfoNodeConfig,
  WebChatNodeConfig,
  MobileNodeConfig,
  ConditionNodeConfig,
  IntentClassificationNodeConfig,
  NotificationNodeConfig,
  EnterpriseWechatNodeConfig,
  DingtalkNodeConfig,
  WechatOfficialNodeConfig,
} from './components/nodeConfigs';

export const NodeConfigForm: React.FC<any> = ({
  node,
  nodes,
  botId,
  frequency,
  onFrequencyChange,
  paramRows,
  headerRows,
  uploadedFiles,
  setUploadedFiles,
  skills,
  loadingSkills,
  notificationChannels,
  loadingChannels,
  notificationType,
  setNotificationType,
  loadChannels,
  allUsers,
  loadingUsers,
  form,
}) => {
  const { t } = useTranslation();
  const nodeType = node.data.type;

  const copyApiUrl = async () => {
    const currentOrigin = typeof window !== 'undefined' ? window.location.origin : '';
    const apiUrl = `${currentOrigin}/api/v1/opspilot/bot_mgmt/execute_chat_flow/${botId}/${node.id}`;
    try {
      await navigator.clipboard.writeText(apiUrl);
      message.success(t('chatflow.nodeConfig.apiLinkCopied'));
    } catch {
      const textArea = document.createElement('textarea');
      textArea.value = apiUrl;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      message.success(t('chatflow.nodeConfig.apiLinkCopied'));
    }
  };

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    accept: '.md',
    fileList: uploadedFiles,
    beforeUpload: (file) => {
      if (!file.name.toLowerCase().endsWith('.md')) {
        message.error(t('chatflow.nodeConfig.onlyMdFilesSupported'));
        return false;
      }
      if (file.size / 1024 / 1024 >= 10) {
        message.error(t('chatflow.nodeConfig.fileSizeLimit'));
        return false;
      }
      return true;
    },
    onChange: (info) => setUploadedFiles([...info.fileList]),
    onRemove: (file) => {
      setUploadedFiles(uploadedFiles.filter((item: any) => item.uid !== file.uid));
      message.success(t('chatflow.nodeConfig.fileDeleted'));
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      try {
        const fileContent = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (e) => resolve(e.target?.result as string);
          reader.onerror = reject;
          reader.readAsText(file as File);
        });
        const fileUid = `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const fileWithContent = {
          uid: fileUid,
          name: (file as File).name,
          content: fileContent,
          status: 'done' as const,
          response: { fileId: fileUid, fileName: (file as File).name, content: fileContent }
        };
        onSuccess && onSuccess(fileWithContent.response);
      } catch (error) {
        console.error('File read error:', error);
        onError && onError(new Error(t('chatflow.nodeConfig.fileReadError')));
      }
    }
  };

  return (
    <>
      {/* Common fields */}
      <Form.Item name="name" label={t('chatflow.nodeConfig.nodeName')} rules={[{ required: true }]}>
        <Input placeholder={t('chatflow.nodeConfig.pleaseEnterNodeName')} />
      </Form.Item>
      <Form.Item name="inputParams" label={t('chatflow.nodeConfig.inputParams')} rules={[{ required: true }]}>
        <Input placeholder={t('chatflow.nodeConfig.pleaseEnterInputParams')} />
      </Form.Item>
      <Form.Item name="outputParams" label={t('chatflow.nodeConfig.outputParams')} rules={[{ required: true }]}>
        <Input placeholder={t('chatflow.nodeConfig.pleaseEnterOutputParams')} />
      </Form.Item>

      {/* Node type specific configs */}
      {nodeType === 'celery' && (
        <CeleryNodeConfig t={t} frequency={frequency} onFrequencyChange={onFrequencyChange} />
      )}

      {nodeType === 'http' && (
        <HttpNodeConfig t={t} paramRows={paramRows} headerRows={headerRows} />
      )}

      {nodeType === 'agents' && (
        <AgentsNodeConfig
          t={t}
          skills={skills}
          loadingSkills={loadingSkills}
          uploadedFiles={uploadedFiles}
          setUploadedFiles={setUploadedFiles}
          uploadProps={uploadProps}
          form={form}
        />
      )}

      {['restful', 'openai', 'agui', 'embedded_chat'].includes(nodeType) && (
        <ApiInfoNodeConfig t={t} nodeType={nodeType} botId={botId} nodeId={node.id} copyApiUrl={copyApiUrl} />
      )}

      {nodeType === 'web_chat' && <WebChatNodeConfig t={t} form={form} />}

      {nodeType === 'mobile' && <MobileNodeConfig t={t} />}

      {nodeType === 'condition' && <ConditionNodeConfig t={t} nodes={nodes} />}

      {nodeType === 'intent_classification' && (
        <IntentClassificationNodeConfig t={t} skills={skills} loadingSkills={loadingSkills} />
      )}

      {nodeType === 'notification' && (
        <NotificationNodeConfig
          t={t}
          notificationType={notificationType}
          setNotificationType={setNotificationType}
          notificationChannels={notificationChannels}
          loadingChannels={loadingChannels}
          loadChannels={loadChannels}
          allUsers={allUsers}
          loadingUsers={loadingUsers}
          form={form}
        />
      )}

      {nodeType === 'enterprise_wechat' && <EnterpriseWechatNodeConfig t={t} />}

      {nodeType === 'dingtalk' && <DingtalkNodeConfig t={t} />}

      {nodeType === 'wechat_official' && <WechatOfficialNodeConfig t={t} />}
    </>
  );
};
