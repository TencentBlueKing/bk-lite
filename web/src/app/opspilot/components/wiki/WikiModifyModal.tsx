'use client';

import React, { useEffect, useState } from 'react';
import { Form, Input, Modal, Select } from 'antd';
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

const fillTemplate = (tpl: PurposeSchemaTemplate | undefined, intro: string) => ({
  purpose_md: (tpl?.purpose_md || '').replace(/\{\{description\}\}/g, intro || ''),
  schema_md: tpl?.schema_md || '',
});

const WikiModifyModal: React.FC<WikiModifyModalProps> = ({ visible, onCancel, onConfirm, initialValues }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { groups } = useGroups();
  const { fetchTemplates, fetchKnowledgeBase } = useWikiApi();
  const [templates, setTemplates] = useState<PurposeSchemaTemplate[]>([]);
  const [confirmLoading, setConfirmLoading] = useState(false);

  useEffect(() => {
    if (!visible) return;
    fetchTemplates()
      .then((tpls) => {
        setTemplates(tpls);
        // 新建:默认套用「通用知识库」固定内容
        if (!initialValues) {
          const def = tpls.find((x) => x.key === 'general') || tpls[0];
          form.setFieldsValue({ template_key: def?.key, ...fillTemplate(def, '') });
        }
      })
      .catch(() => undefined);
    if (initialValues?.id) {
      form.resetFields();
      // 卡片菜单只透传了部分字段,编辑时拉取完整知识库回写(含用途/结构)
      fetchKnowledgeBase(initialValues.id)
        .then((full) => {
          form.setFieldsValue({
            name: full.name,
            introduction: full.introduction,
            team: full.team,
            template_key: full.template_key || 'general',
            purpose_md: full.purpose_md,
            schema_md: full.schema_md,
          });
        })
        .catch(() => undefined);
    } else {
      form.resetFields();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, initialValues]);

  // 选择模板 → 直接填入该模板固定的用途/结构(用户可再编辑)
  const onTemplateChange = (key: string) => {
    const tpl = templates.find((x) => x.key === key);
    form.setFieldsValue(fillTemplate(tpl, form.getFieldValue('introduction') || ''));
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
      width={560}
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
          <Select onChange={onTemplateChange} options={templates.map((tp) => ({ value: tp.key, label: tp.name }))} />
        </Form.Item>
        <Form.Item label={t('wiki.purpose')} name="purpose_md">
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item label={t('wiki.schema')} name="schema_md">
          <Input.TextArea rows={3} />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default WikiModifyModal;
