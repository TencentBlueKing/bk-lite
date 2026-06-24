'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Descriptions, Drawer, Form, Input, List, Modal, Popconfirm, Select, Space, Tag, Upload, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { UploadFile } from 'antd/es/upload/interface';
import { LoadingOutlined, UploadOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { Material, MaterialInfo, MaterialType } from '@/app/opspilot/types/wiki';

// 资料状态机:pending(待解析) → parsing(解析中) → done(已解析) → building(构建中) → built(已构建);失败 failed
const STATUS_META: Record<string, { color: string; key: string }> = {
  pending: { color: 'default', key: 'wiki.statusPending' },
  parsing: { color: 'processing', key: 'wiki.statusParsing' },
  done: { color: 'green', key: 'wiki.statusDone' },
  building: { color: 'processing', key: 'wiki.statusBuilding' },
  built: { color: 'green', key: 'wiki.statusBuilt' },
  failed: { color: 'red', key: 'wiki.statusFailed' },
  updated: { color: 'gold', key: 'wiki.statusUpdated' },
  invalid: { color: 'red', key: 'wiki.statusInvalid' },
};
const IN_PROGRESS = ['parsing', 'building'];

const MaterialTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchMaterials, fetchMaterialInfo, createMaterial, createMaterialFile, deleteMaterial, ingestMaterial, buildMaterial } =
    useWikiApi();
  const [form] = Form.useForm();
  const [data, setData] = useState<Material[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [type, setType] = useState<MaterialType>('text');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [detail, setDetail] = useState<MaterialInfo | null>(null);

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

  // 解析/构建为 Celery 异步:有资料处于「解析中/构建中」时每 3s 轮询刷新状态,全部完成后自动停止
  useEffect(() => {
    if (!data.some((m) => IN_PROGRESS.includes(m.status || ''))) return;
    const timer = setInterval(() => load(), 3000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const openCreate = () => {
    form.resetFields();
    setType('file');
    setFileList([]);
    form.setFieldsValue({ material_type: 'file' });
    setOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (values.material_type === 'file') {
        const f = fileList[0]?.originFileObj as File | undefined;
        if (!f) {
          message.error(t('wiki.materialFile'));
          return;
        }
        await createMaterialFile(kbId, values.name, f);
      } else {
        await createMaterial({ ...values, knowledge_base: kbId });
      }
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

  const openDetail = async (id: number) => setDetail(await fetchMaterialInfo(id));

  const handleBuild = async (id: number) => {
    await buildMaterial(id, true); // async=true:走 Celery,资料置「构建中」,由轮询反映结果
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
      render: (s: string) => {
        const meta = STATUS_META[s];
        return (
          <Tag color={meta?.color || 'default'} icon={IN_PROGRESS.includes(s) ? <LoadingOutlined spin /> : undefined}>
            {meta ? t(meta.key) : s}
          </Tag>
        );
      },
    },
    { title: 'AI', dataIndex: 'ai_summary', key: 'ai_summary', ellipsis: true },
    {
      title: '',
      key: 'action',
      width: 280,
      render: (_: unknown, record) => {
        const busy = IN_PROGRESS.includes(record.status || '');
        const canBuild = ['done', 'built'].includes(record.status || '');
        return (
          <Space>
            <Button type="link" size="small" onClick={() => openDetail(record.id)}>
              {t('wiki.detail')}
            </Button>
            <Button type="link" size="small" disabled={busy} onClick={() => handleIngest(record.id)}>
              {record.material_type === 'web' ? t('wiki.refreshSnapshot') : t('wiki.ingest')}
            </Button>
            <Button
              type="link"
              size="small"
              disabled={busy || !canBuild}
              title={!canBuild ? t('wiki.buildNeedParse') : undefined}
              onClick={() => handleBuild(record.id)}
            >
              {t('wiki.build')}
            </Button>
            <Popconfirm title={t('wiki.deleteConfirm')} onConfirm={() => handleDelete(record.id)}>
              <Button type="link" size="small" danger disabled={busy}>
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <div className="flex justify-end mb-3">
        <Button type="primary" onClick={openCreate}>
          {t('wiki.addMaterial')}
        </Button>
      </div>
      {/* scroll x:undefined 关闭 CustomTable 默认按列宽合计强制的横向滚动,列宽自适应容器,消除底部多余横向滚动条 */}
      <CustomTable<Material>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={data}
        pagination={false}
        scroll={{ x: undefined }}
      />

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
          <Form.Item label={t('wiki.materialType')} name="material_type" initialValue="file">
            <Select
              onChange={(v: MaterialType) => setType(v)}
              options={[
                { value: 'file', label: t('wiki.materialFile') },
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
          {type === 'file' && (
            <Form.Item label={t('wiki.materialFile')} required>
              <Upload.Dragger
                maxCount={1}
                fileList={fileList}
                beforeUpload={() => false}
                onChange={({ fileList: fl }) => {
                  const last = fl.slice(-1);
                  setFileList(last);
                  const fname = last[0]?.name;
                  if (fname && !form.getFieldValue('name')) form.setFieldsValue({ name: fname });
                }}
                accept=".pdf,.docx,.pptx,.xlsx,.xls,.csv,.txt,.md,.png,.jpg,.jpeg"
              >
                <p className="ant-upload-drag-icon">
                  <UploadOutlined />
                </p>
                <p className="ant-upload-text">{t('wiki.uploadHint')}</p>
                <p className="ant-upload-hint text-xs text-gray-400">pdf / docx / pptx / xlsx / csv / txt / md / 图片</p>
              </Upload.Dragger>
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* 资料详情(spec 4.2):原文/文件、AI 解读、版本、贡献的知识页面 */}
      <Drawer
        title={`${t('wiki.detail')}: ${detail?.material?.name ?? ''}`}
        open={!!detail}
        width={600}
        onClose={() => setDetail(null)}
      >
        {detail && (
          <>
            <Descriptions column={1} bordered size="small" className="mb-4">
              <Descriptions.Item label={t('wiki.materialType')}>{detail.material.material_type}</Descriptions.Item>
              <Descriptions.Item label={t('wiki.original')}>
                {detail.file_url ? (
                  <a href={detail.file_url} target="_blank" rel="noreferrer">
                    {t('wiki.openFile')}
                  </a>
                ) : (
                  <span className="break-all">{detail.original || '--'}</span>
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('wiki.aiSummary')}>
                <span className="whitespace-pre-wrap text-xs">{detail.ai_summary || '--'}</span>
              </Descriptions.Item>
            </Descriptions>
            <div className="mb-2 font-medium">{t('wiki.versions')}</div>
            <List
              size="small"
              className="mb-4"
              dataSource={detail.versions}
              renderItem={(v) => (
                <List.Item>
                  <span>#{v.id}</span>
                  <span className="text-xs text-gray-400">{v.created_at}</span>
                </List.Item>
              )}
            />
            <div className="mb-2 font-medium">{t('wiki.contributedPages')}</div>
            <List
              size="small"
              dataSource={detail.contributed_pages}
              renderItem={(p) => (
                <List.Item>
                  <span className="truncate mr-2">{p.title}</span>
                  <Tag>{p.page_type}</Tag>
                </List.Item>
              )}
            />
          </>
        )}
      </Drawer>
    </div>
  );
};

export default MaterialTab;
