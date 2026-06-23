'use client';

import React, { useEffect, useState } from 'react';
import { Button, Form, Input, Modal, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useGroups from '@/app/opspilot/hooks/useGroups';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { PurposeSchemaTemplate, WikiKnowledgeBase } from '@/app/opspilot/types/wiki';

interface WikiModifyModalProps {
  visible: boolean;
  onCancel: () => void;
  onConfirm: (values: Record<string, unknown>) => void;
  initialValues?: WikiKnowledgeBase | null;
}

const WikiModifyModal: React.FC<WikiModifyModalProps> = ({ visible, onCancel, onConfirm, initialValues }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { groups } = useGroups();
  const { fetchTemplates, generatePurposeSchema } = useWikiApi();
  const [templates, setTemplates] = useState<PurposeSchemaTemplate[]>([]);
  const [generating, setGenerating] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);

  useEffect(() => {
    if (!visible) return;
    fetchTemplates()
      .then(setTemplates)
      .catch(() => undefined);
    if (initialValues) {
      form.setFieldsValue({
        name: initialValues.name,
        introduction: initialValues.introduction,
        team: initialValues.team,
        template_key: initialValues.template_key || 'general',
        purpose_md: initialValues.purpose_md,
        schema_md: initialValues.schema_md,
      });
    } else {
      form.resetFields();
      form.setFieldsValue({ template_key: 'general' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, initialValues]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const r = await generatePurposeSchema({
        template_key: form.getFieldValue('template_key'),
        description: form.getFieldValue('introduction'),
      });
      form.setFieldsValue({ purpose_md: r.purpose_md, schema_md: r.schema_md });
    } finally {
      setGenerating(false);
    }
  };

  const handleOk = async () => {
    const values = await form.validateFields();
    setConfirmLoading(true);
    try {
      await onConfirm(values);
    } finally {
      setConfirmLoading(false);
    }
  };

  return (
    <Modal
      title={initialValues ? t('wiki.edit') : t('wiki.create')}
      open={visible}
      onOk={handleOk}
      confirmLoading={confirmLoading}
      onCancel={onCancel}
      width={720}
      destroyOnClose
    >
      <Form form={form} layout="vertical">
        <Form.Item label={t('wiki.name')} name="name" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item label={t('common.organization')} name="team" rules={[{ required: true }]}>
          <Select
            mode="multiple"
            options={(groups || []).map((g: { id: string | number; name: string }) => ({ value: g.id, label: g.name }))}
          />
        </Form.Item>
        <Form.Item label={t('wiki.introduction')} name="introduction">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Form.Item label={t('wiki.template')} name="template_key">
          <Select options={templates.map((tp) => ({ value: tp.key, label: tp.name }))} />
        </Form.Item>
        <div className="text-right mb-2">
          <Button onClick={handleGenerate} loading={generating}>
            {t('wiki.generateByAI')}
          </Button>
        </div>
        <Form.Item label={t('wiki.purpose')} name="purpose_md">
          <Input.TextArea rows={4} />
        </Form.Item>
        <Form.Item label={t('wiki.schema')} name="schema_md">
          <Input.TextArea rows={5} />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default WikiModifyModal;
