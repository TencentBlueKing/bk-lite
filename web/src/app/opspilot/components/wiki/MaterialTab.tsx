'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { Material, MaterialType } from '@/app/opspilot/types/wiki';

const STATUS_COLOR: Record<string, string> = {
  done: 'green',
  pending: 'default',
  building: 'blue',
  failed: 'red',
  updated: 'gold',
  invalid: 'red',
};

const MaterialTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchMaterials, createMaterial, deleteMaterial, ingestMaterial, buildMaterial } = useWikiApi();
  const [form] = Form.useForm();
  const [data, setData] = useState<Material[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [type, setType] = useState<MaterialType>('text');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchMaterials(kbId));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const openCreate = () => {
    form.resetFields();
    setType('text');
    form.setFieldsValue({ material_type: 'text' });
    setOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      await createMaterial({ ...values, knowledge_base: kbId });
      message.success(t('wiki.saveSuccess'));
      setOpen(false);
      load();
    } finally {
      setSaving(false);
    }
  };

  const handleIngest = async (id: number) => {
    await ingestMaterial(id);
    message.success(t('wiki.saveSuccess'));
    load();
  };

  const handleBuild = async (id: number) => {
    await buildMaterial(id);
    message.success(t('wiki.saveSuccess'));
    load();
  };

  const handleDelete = async (id: number) => {
    await deleteMaterial(id);
    message.success(t('wiki.deleteSuccess'));
    load();
  };

  const columns: ColumnsType<Material> = [
    { title: t('wiki.name'), dataIndex: 'name', key: 'name' },
    { title: t('wiki.materialType'), dataIndex: 'material_type', key: 'material_type', width: 100 },
    {
      title: t('wiki.status'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    { title: 'AI', dataIndex: 'ai_summary', key: 'ai_summary', ellipsis: true },
    {
      title: '',
      key: 'action',
      width: 220,
      render: (_: unknown, record) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleIngest(record.id)}>
            {t('wiki.ingest')}
          </Button>
          <Button type="link" size="small" onClick={() => handleBuild(record.id)}>
            {t('wiki.build')}
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
    <div>
      <div className="flex justify-end mb-3">
        <Button type="primary" onClick={openCreate}>
          {t('wiki.addMaterial')}
        </Button>
      </div>
      <Table<Material> rowKey="id" loading={loading} columns={columns} dataSource={data} />

      <Modal
        title={t('wiki.addMaterial')}
        open={open}
        onOk={handleSave}
        confirmLoading={saving}
        onCancel={() => setOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item label={t('wiki.name')} name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label={t('wiki.materialType')} name="material_type" initialValue="text">
            <Select
              onChange={(v: MaterialType) => setType(v)}
              options={[
                { value: 'text', label: t('wiki.materialText') },
                { value: 'web', label: t('wiki.materialWeb') },
              ]}
            />
          </Form.Item>
          {type === 'text' && (
            <Form.Item label={t('wiki.materialText')} name="text_content" rules={[{ required: true }]}>
              <Input.TextArea rows={6} />
            </Form.Item>
          )}
          {type === 'web' && (
            <Form.Item label="URL" name="url" rules={[{ required: true }]}>
              <Input placeholder="https://..." />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default MaterialTab;
