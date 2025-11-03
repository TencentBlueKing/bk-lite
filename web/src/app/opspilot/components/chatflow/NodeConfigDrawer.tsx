'use client';

import React, { useState } from 'react';
import { Drawer, Form, Button, message } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { Node } from '@xyflow/react';
import type { UploadFile as AntdUploadFile } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import dayjs from 'dayjs';
import { useNodeConfigData } from './hooks/useNodeConfigData';
import { useKeyValueRows } from './hooks/useKeyValueRows';
import { NodeConfigForm } from './NodeConfigForm';

interface UploadFile extends AntdUploadFile {
  content?: string;
}

interface ChatflowNodeData {
  label: string;
  type: string;
  config?: any;
}

interface ChatflowNode extends Omit<Node, 'data'> {
  data: ChatflowNodeData;
}

interface NodeConfigDrawerProps {
  visible: boolean;
  node: ChatflowNode | null;
  nodes?: ChatflowNode[];
  onClose: () => void;
  onSave: (nodeId: string, config: any) => void;
  onDelete: (nodeId: string) => void;
}

const NodeConfigDrawer: React.FC<NodeConfigDrawerProps> = ({
  visible,
  node,
  nodes = [],
  onClose,
  onSave,
  onDelete
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const searchParams = useSearchParams();
  const botId = searchParams?.get('id') || '1';

  // 状态管理
  const [frequency, setFrequency] = useState('daily');
  const [uploadedFiles, setUploadedFiles] = useState<UploadFile[]>([]);
  const [notificationType, setNotificationType] = useState<'email' | 'enterprise_wechat_bot'>('email');

  // 使用自定义 Hooks
  const {
    skills,
    loadingSkills,
    loadSkills,
    notificationChannels,
    loadingChannels,
    loadChannels,
    allUsers,
    loadingUsers,
    loadUsers,
  } = useNodeConfigData();

  const paramRows = useKeyValueRows([{ key: '', value: '' }]);
  const headerRows = useKeyValueRows([{ key: '', value: '' }]);

  // 初始化表单数据
  React.useEffect(() => {
    if (node && node.data.config && visible) {
      const config = node.data.config || {};
      const formValues: any = { name: node.data.label, ...config };

      // 处理时间字段
      if (node.data.type === 'celery' && config.time) {
        try {
          if (typeof config.time === 'string') {
            const timeStr = config.time.includes(':') ? config.time : `${config.time}:00`;
            const today = new Date().toISOString().split('T')[0];
            formValues.time = dayjs(`${today} ${timeStr}`, 'YYYY-MM-DD HH:mm');
          } else {
            formValues.time = dayjs(config.time);
          }
        } catch (error) {
          console.warn('时间格式转换失败:', error);
          formValues.time = undefined;
        }
      }

      form.setFieldsValue(formValues);
      setFrequency(config.frequency || 'daily');

      // 初始化参数和头部
      const needsParamsAndHeaders = ['http', 'restful', 'openai'];
      if (needsParamsAndHeaders.includes(node.data.type)) {
        paramRows.resetRows(config.params?.length ? config.params : [{ key: '', value: '' }]);
        headerRows.resetRows(config.headers?.length ? config.headers : [{ key: '', value: '' }]);
      }

      // 初始化上传文件
      if (node.data.type === 'agents') {
        if (config.uploadedFiles?.length) {
          const files = config.uploadedFiles.map((file: any, index: number) => ({
            uid: file.uid || `file-${index}`,
            name: file.name,
            status: 'done' as const,
            content: file.content,
            response: { fileId: file.uid || `file-${index}`, fileName: file.name, content: file.content }
          }));
          setUploadedFiles(files);
        }
        loadSkills();
      }

      // 加载通知渠道和用户
      if (node.data.type === 'notification') {
        const type = (config.notificationType || 'email') as 'email' | 'enterprise_wechat_bot';
        setNotificationType(type);
        loadChannels(type);
        loadUsers();
      }
    } else {
      form.resetFields();
      paramRows.resetRows([]);
      headerRows.resetRows([]);
      setFrequency('daily');
      setUploadedFiles([]);
    }
  }, [node, visible]);

  const handleSave = () => {
    if (!node) return;

    form.validateFields().then((values) => {
      const configData = {
        ...values,
        params: paramRows.rows.filter(row => row.key && row.value),
        headers: headerRows.rows.filter(row => row.key && row.value)
      };

      if (node.data.type === 'agents') {
        configData.uploadedFiles = uploadedFiles.map(file => ({
          name: file.name,
          content: file.response?.content || file.content || ''
        }));
      }

      if (node.data.type === 'notification') {
        configData.notificationChannels = notificationChannels;
      }

      if (node.data.type === 'celery' && configData.time?.format) {
        configData.time = configData.time.format('HH:mm');
      }

      onSave(node.id, configData);
      message.success(t('chatflow.messages.nodeConfigured'));
    }).catch((errorInfo) => {
      console.log('Validation failed:', errorInfo);
    });
  };

  const handleDelete = () => {
    if (!node) return;
    onDelete(node.id);
    onClose();
  };

  const handleFrequencyChange = (value: string) => {
    setFrequency(value);
    form.setFieldsValue({ time: undefined, weekday: undefined, day: undefined });
  };

  return (
    <Drawer
      title={String(node?.data.label || '')}
      open={visible}
      onClose={onClose}
      width={480}
      placement="right"
      footer={
        <div className="flex justify-end gap-2">
          <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
            {t('chatflow.nodeConfig.deleteNode')}
          </Button>
          <Button onClick={onClose}>{t('chatflow.nodeConfig.cancel')}</Button>
          <Button type="primary" onClick={handleSave}>{t('chatflow.nodeConfig.confirm')}</Button>
        </div>
      }
    >
      <Form form={form} layout="vertical">
        {node && (
          <NodeConfigForm
            node={node}
            nodes={nodes}
            botId={botId}
            frequency={frequency}
            onFrequencyChange={handleFrequencyChange}
            paramRows={paramRows}
            headerRows={headerRows}
            uploadedFiles={uploadedFiles}
            setUploadedFiles={setUploadedFiles}
            skills={skills}
            loadingSkills={loadingSkills}
            notificationChannels={notificationChannels}
            loadingChannels={loadingChannels}
            notificationType={notificationType}
            setNotificationType={setNotificationType}
            loadChannels={loadChannels}
            allUsers={allUsers}
            loadingUsers={loadingUsers}
            form={form}
          />
        )}
      </Form>
    </Drawer>
  );
};

export default NodeConfigDrawer;
