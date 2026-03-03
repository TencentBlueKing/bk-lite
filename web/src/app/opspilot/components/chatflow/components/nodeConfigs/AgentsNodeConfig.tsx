import React from 'react';
import { Form, Input, Select, Button, Upload } from 'antd';
import { InboxOutlined, PlusOutlined } from '@ant-design/icons';
import Link from 'next/link';
import type { AgentsNodeConfigProps } from './types';

const { Option } = Select;
const { TextArea } = Input;

export const AgentsNodeConfig: React.FC<AgentsNodeConfigProps> = ({
  t,
  skills,
  loadingSkills,
  uploadProps,
  form,
}) => {
  return (
    <>
      <div className="relative">
        <Form.Item
          name="agent"
          label={t('chatflow.nodeConfig.selectAgent')}
          rules={[{ required: true }]}
        >
          <Select
            placeholder={t('chatflow.nodeConfig.pleaseSelectAgent')}
            loading={loadingSkills}
            showSearch
            onChange={(agentId) => {
              const selectedAgent = skills.find((s) => s.id === agentId);
              if (selectedAgent) form.setFieldsValue({ agentName: selectedAgent.name });
            }}
            filterOption={(input, option) => option?.label?.toString().toLowerCase().includes(input.toLowerCase()) ?? false}
          >
            {skills.map((s) => <Option key={s.id} value={s.id} label={s.name}>{s.name}</Option>)}
          </Select>
        </Form.Item>
        <Link href="/opspilot/skill" target="_blank" className="absolute right-0 top-0">
          <Button type="link" size="small" icon={<PlusOutlined />} className="text-blue-500 hover:text-blue-600 text-xs">
            {t('chatflow.nodeConfig.addAgent')}
          </Button>
        </Link>
      </div>
      <Form.Item name="agentName" className="hidden"><Input /></Form.Item>
      <Form.Item name="prompt" label={t('chatflow.nodeConfig.promptAppend')} tooltip={t('chatflow.nodeConfig.promptAppendTooltip')}>
        <TextArea rows={4} placeholder={t('chatflow.nodeConfig.promptPlaceholder')} />
      </Form.Item>
      <Form.Item label={t('chatflow.nodeConfig.uploadKnowledge')} tooltip={t('chatflow.nodeConfig.uploadKnowledgeTooltip')}>
        <Upload.Dragger {...uploadProps}>
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">{t('chatflow.nodeConfig.uploadHint')}</p>
          <p className="ant-upload-hint">{t('chatflow.nodeConfig.uploadDescription')}</p>
        </Upload.Dragger>
      </Form.Item>
    </>
  );
};
