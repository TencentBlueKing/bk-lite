'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Form, Input, Modal, Popconfirm, Select, Space, Spin, Table, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { PurposeSchemaTemplate, WikiKnowledgeBase } from '@/app/opspilot/types/wiki';

const WikiListPage: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const {
    fetchKnowledgeBases,
    createKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    fetchTemplates,
    generatePurposeSchema,
  } = useWikiApi();

  const [form] = Form.useForm();
  const [data, setData] = useState<WikiKnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<WikiKnowledgeBase | null>(null);
  const [templates, setTemplates] = useState<PurposeSchemaTemplate[]>([]);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchKnowledgeBases());
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
    fetchTemplates()
      .then(setTemplates)
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ template_key: 'general' });
    setModalOpen(true);
  };

  const openEdit = (record: WikiKnowledgeBase) => {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      introduction: record.introduction,
      template_key: record.template_key || 'general',
      purpose_md: record.purpose_md,
      schema_md: record.schema_md,
    });
    setModalOpen(true);
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const result = await generatePurposeSchema({
        template_key: form.getFieldValue('template_key'),
        description: form.getFieldValue('introduction'),
      });
      form.setFieldsValue({ purpose_md: result.purpose_md, schema_md: result.schema_md });
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updateKnowledgeBase(editing.id, values);
      } else {
        await createKnowledgeBase({ ...values, team: [] });
      }
      message.success(t('wiki.saveSuccess'));
      setModalOpen(false);
      load();
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    await deleteKnowledgeBase(id);
    message.success(t('wiki.deleteSuccess'));
    load();
  };

  const columns: ColumnsType<WikiKnowledgeBase> = [
    {
      title: t('wiki.name'),
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record) => (
        <a onClick={() => router.push(`/opspilot/wiki/detail?id=${record.id}`)}>{text}</a>
      ),
    },
    { title: t('wiki.introduction'), dataIndex: 'introduction', key: 'introduction', ellipsis: true },
    { title: t('wiki.status'), dataIndex: 'status', key: 'status', width: 120 },
    {
      title: '',
      key: 'action',
      width: 160,
      render: (_: unknown, record) => (
        <Space>
          <Button type="link" size="small" onClick={() => openEdit(record)}>
            {t('common.edit')}
          </Button>
          <Popconfirm title={t('wiki.deleteConfirm')} onConfirm={() => handleDelete(record.id)}>
            <Button type="link" size="small" danger>
              {t('common.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-lg font-semibold">{t('wiki.title')}</h2>
          <p className="text-sm text-gray-500">{t('wiki.description')}</p>
        </div>
        <Button type="primary" onClick={openCreate}>
          {t('wiki.create')}
        </Button>
      </div>
      <Spin spinning={loading}>
        <Table<WikiKnowledgeBase> rowKey="id" columns={columns} dataSource={data} locale={{ emptyText: t('wiki.empty') }} />
      </Spin>

      <Modal
        title={editing ? t('wiki.edit') : t('wiki.create')}
        open={modalOpen}
        onOk={handleSave}
        confirmLoading={saving}
        onCancel={() => setModalOpen(false)}
        width={720}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item label={t('wiki.name')} name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label={t('wiki.introduction')} name="introduction">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item label={t('wiki.template')} name="template_key">
            <Select
              options={templates.map((tpl) => ({ value: tpl.key, label: tpl.name }))}
              placeholder={t('wiki.template')}
            />
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
    </div>
  );
};

export default WikiListPage;
