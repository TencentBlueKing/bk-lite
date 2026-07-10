'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Descriptions, Drawer, Form, Input, InputNumber, List, Modal, Select, Space, Switch, Tag, Upload, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { UploadFile } from 'antd/es/upload/interface';
import { LoadingOutlined, UploadOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import MarkdownRenderer from '@/components/markdown';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { Material, MaterialDeleteImpact, MaterialInfo, MaterialType, MaterialUpdateImpact } from '@/app/opspilot/types/wiki';

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
const MATERIAL_TYPE_KEY: Record<MaterialType, string> = {
  file: 'wiki.materialFile',
  text: 'wiki.materialText',
  web: 'wiki.materialWeb',
};
const IN_PROGRESS = ['parsing', 'building'];
const SUPPORTED_FILE_EXTENSIONS = [
  '.pdf',
  '.docx',
  '.pptx',
  '.xlsx',
  '.xls',
  '.msg',
  '.html',
  '.htm',
  '.txt',
  '.md',
  '.markdown',
  '.csv',
  '.json',
  '.xml',
  '.jpg',
  '.jpeg',
  '.png',
  '.gif',
  '.bmp',
  '.tiff',
  '.tif',
  '.webp',
  '.zip',
  '.epub',
];
const FILE_ACCEPT = SUPPORTED_FILE_EXTENSIONS.join(',');
const SHOW_MATERIAL_REINDEX_ACTION = false;

const MaterialTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const {
    fetchKnowledgeBase,
    fetchMaterials,
    fetchMaterialInfo,
    fetchMaterialDeleteImpact,
    fetchMaterialUpdateImpact,
    createMaterial,
    updateMaterial,
    createMaterialFile,
    batchCreateMaterials,
    deleteMaterial,
    ingestMaterial,
    buildMaterial,
    proposeUpdate,
    reindexMaterial,
  } = useWikiApi();
  const [form] = Form.useForm();
  const [data, setData] = useState<Material[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingMaterial, setEditingMaterial] = useState<Material | null>(null);
  const [type, setType] = useState<MaterialType>('text');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [folderImport, setFolderImport] = useState(false);
  const [detail, setDetail] = useState<MaterialInfo | null>(null);
  const [hasVisionModel, setHasVisionModel] = useState(false);
  const [reindexingMaterialId, setReindexingMaterialId] = useState<number | null>(null);
  const [deleteImpactVisible, setDeleteImpactVisible] = useState(false);
  const [deleteImpactLoading, setDeleteImpactLoading] = useState(false);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Material | null>(null);
  const [deleteImpact, setDeleteImpact] = useState<MaterialDeleteImpact | null>(null);
  const [updateImpactVisible, setUpdateImpactVisible] = useState(false);
  const [updateImpactLoading, setUpdateImpactLoading] = useState(false);
  const [updateSubmitting, setUpdateSubmitting] = useState(false);
  const [updateTarget, setUpdateTarget] = useState<Material | null>(null);
  const [updateImpact, setUpdateImpact] = useState<MaterialUpdateImpact | null>(null);
  const isEditing = Boolean(editingMaterial);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchMaterials(kbId, { page, page_size: pageSize });
      setData(res.items);
      setTotal(res.count);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize]);

  useEffect(() => {
    fetchKnowledgeBase(kbId)
      .then((kb) => setHasVisionModel(Boolean(kb.vision_model)))
      .catch(() => setHasVisionModel(false));
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
    setEditingMaterial(null);
    setType('file');
    setFileList([]);
    setFolderImport(false);
    form.setFieldsValue({ material_type: 'file', ocr_enhance: false });
    setOpen(true);
  };

  const closeMaterialModal = () => {
    if (saving) return;
    setOpen(false);
    setEditingMaterial(null);
  };

  const openEdit = (record: Material) => {
    setEditingMaterial(record);
    setType(record.material_type);
    setFileList([]);
    setFolderImport(false);
    form.resetFields();
    form.setFieldsValue({
      name: record.name,
      material_type: record.material_type,
      text_content: record.text_content ?? '',
      url: record.url ?? '',
      sync_enabled: Boolean(record.sync_policy?.enabled),
      sync_interval_hours: record.sync_policy?.interval_hours ?? 24,
      ocr_enhance: Boolean(record.ocr_enhance),
    });
    setOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      let successMessage = t('wiki.saveSuccess');
      if (editingMaterial) {
        if (editingMaterial.material_type === 'file') {
          await updateMaterial(editingMaterial.id, { ocr_enhance: Boolean(values.ocr_enhance) });
        } else if (editingMaterial.material_type === 'web') {
          await updateMaterial(editingMaterial.id, {
            name: values.name,
            sync_policy: { enabled: !!values.sync_enabled, interval_hours: values.sync_interval_hours ?? 24 },
          });
        } else if (editingMaterial.material_type === 'text') {
          await updateMaterial(editingMaterial.id, {
            name: values.name,
            text_content: values.text_content ?? '',
          });
        }
      } else if (values.material_type === 'file') {
        const files = fileList
          .map((item) => item.originFileObj as File | undefined)
          .filter((file): file is File => Boolean(file));
        if (!files.length) {
          message.error(t('wiki.fileRequired'));
          return;
        }
        if (files.length === 1) {
          // 单文件走原 create 端点:与单文件上传行为保持完全一致(独立 name 字段)
          await createMaterialFile(
            kbId,
            values.name || files[0].name,
            files[0],
            Boolean(values.ocr_enhance)
          );
        } else {
          // 多文件走 batch_create 端点:单次请求,失败文件汇总到 errors
          const result = await batchCreateMaterials(kbId, files, Boolean(values.ocr_enhance));
          const failed = result?.errors ?? [];
          if (failed.length) {
            // 部分失败:展示汇总,允许用户从列表中删除失败项
            const preview = failed
              .slice(0, 3)
              .map((f) => `${f.name}: ${f.error}`)
              .join('；');
            const suffix = failed.length > 3 ? `…(共 ${failed.length} 项)` : `共 ${failed.length} 项`;
            message.warning(`${t('wiki.batchAddMaterialPartial')}: ${suffix}\n${preview}`);
          }
          successMessage = `${t('wiki.batchAddMaterialDone')}: ${result?.items?.length ?? 0}`;
        }
      } else {
        // 网页资料:按站点单独配置同步策略(替代原知识库级别的统一规则)
        const { sync_enabled, sync_interval_hours, ...rest } = values;
        delete rest.ocr_enhance;
        const payload: Partial<Material> = { ...rest, knowledge_base: kbId };
        if (values.material_type === 'web') {
          payload.sync_policy = { enabled: !!sync_enabled, interval_hours: sync_interval_hours ?? 24 };
        }
        await createMaterial(payload);
      }
      message.success(successMessage);
      setOpen(false);
      setEditingMaterial(null);
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

  const openDeleteImpact = async (record: Material) => {
    setDeleteTarget(record);
    setDeleteImpact(null);
    setDeleteImpactVisible(true);
    setDeleteImpactLoading(true);
    try {
      setDeleteImpact(await fetchMaterialDeleteImpact(record.id));
    } finally {
      setDeleteImpactLoading(false);
    }
  };

  const closeDeleteImpact = () => {
    if (deleteSubmitting) return;
    setDeleteImpactVisible(false);
    setDeleteTarget(null);
    setDeleteImpact(null);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleteSubmitting(true);
    try {
      await deleteMaterial(deleteTarget.id);
      message.success(t('wiki.deleteSuccess'));
      setDeleteImpactVisible(false);
      setDeleteTarget(null);
      setDeleteImpact(null);
      load();
    } finally {
      setDeleteSubmitting(false);
    }
  };

  const openUpdateImpact = async (record: Material) => {
    setUpdateTarget(record);
    setUpdateImpact(null);
    setUpdateImpactVisible(true);
    setUpdateImpactLoading(true);
    try {
      setUpdateImpact(await fetchMaterialUpdateImpact(record.id));
    } finally {
      setUpdateImpactLoading(false);
    }
  };

  const closeUpdateImpact = () => {
    if (updateSubmitting) return;
    setUpdateImpactVisible(false);
    setUpdateTarget(null);
    setUpdateImpact(null);
  };

  const handleProposeUpdate = async () => {
    if (!updateTarget) return;
    setUpdateSubmitting(true);
    try {
      await proposeUpdate(updateTarget.id);
      message.success(t('wiki.proposeUpdateDone'));
      setUpdateImpactVisible(false);
      setUpdateTarget(null);
      setUpdateImpact(null);
      load();
    } finally {
      setUpdateSubmitting(false);
    }
  };

  const handleReindexMaterial = async (id: number) => {
    setReindexingMaterialId(id);
    try {
      await reindexMaterial(id);
      message.success(t('wiki.reindexPageDone'));
      load();
    } finally {
      setReindexingMaterialId(null);
    }
  };

  const materialTypeLabel = (type: MaterialType) => t(MATERIAL_TYPE_KEY[type] || type);

  const renderImpactPages = (pages: MaterialDeleteImpact['affected_pages']) => (
    <List
      size="small"
      dataSource={pages}
      locale={{ emptyText: t('wiki.noAffectedPages') }}
      renderItem={(pageItem) => (
        <List.Item>
          <div className="min-w-0">
            <div className="truncate font-medium">{pageItem.title}</div>
            {pageItem.reason && (
              <div className="text-xs text-[var(--color-text-3)] mt-0.5">{pageItem.reason}</div>
            )}
            <Space size={[4, 4]} wrap className="mt-1">
              <Tag className="m-0">#{pageItem.id}</Tag>
              <Tag className="m-0">{pageItem.page_type}</Tag>
              <Tag className="m-0">{pageItem.status}</Tag>
            </Space>
          </div>
        </List.Item>
      )}
    />
  );

  const versionLabel = (version?: MaterialUpdateImpact['latest_version']) => {
    if (!version) return '--';
    const hash = version.content_hash ? version.content_hash.slice(0, 8) : '--';
    return `#${version.id} ${hash}`;
  };

  const columns: ColumnsType<Material> = [
    { title: t('wiki.name'), dataIndex: 'name', key: 'name' },
    { title: t('wiki.materialType'), dataIndex: 'material_type', key: 'material_type', width: 100, render: (type: MaterialType) => materialTypeLabel(type) },
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
    {
      // AI 解读列只做单行预览:自定义 render 绕过 CustomTable 的 EllipsisWithTooltip,
      // 并 showTitle:false 关闭原生提示——超长内容不再 hover 弹出全文撑出滚动条,完整内容见「详情」抽屉
      title: t('wiki.aiSummary'),
      dataIndex: 'ai_summary',
      key: 'ai_summary',
      width: 320,
      ellipsis: { showTitle: false },
      render: (s: string) => <span className="text-[var(--color-text-3)]">{s || '--'}</span>,
    },
    {
      title: t('common.actions'),
      key: 'action',
      width: 360,
      render: (_: unknown, record) => {
        const busy = IN_PROGRESS.includes(record.status || '');
        const canBuild = ['done', 'built'].includes(record.status || '');
        const canProposeUpdate = record.status === 'updated';
        return (
          <Space>
            <Button type="link" size="small" onClick={() => openDetail(record.id)}>
              {t('wiki.detail')}
            </Button>
            <Button type="link" size="small" disabled={busy} onClick={() => openEdit(record)}>
              {t('common.edit')}
            </Button>
            <Button type="link" size="small" disabled={busy} onClick={() => handleIngest(record.id)}>
              {t('wiki.ingest')}
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
            {SHOW_MATERIAL_REINDEX_ACTION && (
              <Button
                type="link"
                size="small"
                disabled={busy || (reindexingMaterialId !== null && reindexingMaterialId !== record.id)}
                loading={reindexingMaterialId === record.id}
                onClick={() => handleReindexMaterial(record.id)}
              >
                {t('wiki.reindexPage')}
              </Button>
            )}
            {canProposeUpdate && (
              <Button type="link" size="small" disabled={busy} onClick={() => openUpdateImpact(record)}>
                {t('wiki.proposeUpdate')}
              </Button>
            )}
            <Button type="link" size="small" danger disabled={busy} onClick={() => openDeleteImpact(record)}>
              {t('common.delete')}
            </Button>
          </Space>
        );
      },
    },
  ];

  return (
    <div className="h-full flex flex-col">
      <div className="flex justify-end mb-3 shrink-0">
        <Button type="primary" onClick={openCreate}>
          {t('wiki.addMaterial')}
        </Button>
      </div>
      {/* flex-1 容器给表格确定高度,使分页时 CustomTable 自动算出的 scroll.y 稳定;
          scroll x:undefined 关闭默认按列宽合计强制的横向滚动,列宽自适应容器 */}
      <div className="flex-1 min-h-0">
        <CustomTable<Material>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={data}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
          scroll={{ x: undefined }}
        />
      </div>

      <Modal
        title={t('wiki.deleteImpact')}
        open={deleteImpactVisible}
        onOk={handleDelete}
        okText={t('common.delete')}
        okButtonProps={{ danger: true, disabled: deleteImpactLoading || !deleteImpact }}
        confirmLoading={deleteSubmitting}
        onCancel={closeDeleteImpact}
        maskClosable={false}
        destroyOnHidden
        // 弹窗禁止触底:限制最大高度,主体内部滚动(前端规范:弹窗禁止触底)
        styles={{ body: { maxHeight: 'calc(100vh - 280px)', overflowY: 'auto', overflowX: 'hidden' } }}
      >
        {deleteImpactLoading ? (
          <div className="py-6 text-center text-[var(--color-text-3)]">
            <LoadingOutlined spin className="mr-2" />
            {t('wiki.deleteImpactLoading')}
          </div>
        ) : (
          deleteImpact && (
            <>
              <div className="mb-3 text-sm text-[var(--color-text-2)]">{t('wiki.deleteImpactTip')}</div>
              <Descriptions column={3} bordered size="small">
                <Descriptions.Item label={t('wiki.affectedPages')}>{deleteImpact.affected_count}</Descriptions.Item>
                <Descriptions.Item label={t('wiki.willLoseSource')}>
                  {deleteImpact.will_be_source_invalid_count}
                </Descriptions.Item>
                <Descriptions.Item label={t('wiki.sharedSourceProtected')}>
                  {deleteImpact.shared_source_protected_count}
                </Descriptions.Item>
              </Descriptions>
              <div className="mt-4 mb-2 font-medium">{t('wiki.willLoseSource')}</div>
              {renderImpactPages(deleteImpact.will_be_source_invalid)}
              <div className="mt-4 mb-2 font-medium">{t('wiki.sharedSourceProtected')}</div>
              {renderImpactPages(deleteImpact.shared_source_protected)}
            </>
          )
        )}
      </Modal>

      <Modal
        title={t('wiki.updateImpact')}
        open={updateImpactVisible}
        onOk={handleProposeUpdate}
        okText={t('wiki.proposeUpdate')}
        okButtonProps={{ disabled: updateImpactLoading || !updateImpact }}
        confirmLoading={updateSubmitting}
        onCancel={closeUpdateImpact}
        maskClosable={false}
        destroyOnHidden
      >
        {updateImpactLoading ? (
          <div className="py-6 text-center text-[var(--color-text-3)]">
            <LoadingOutlined spin className="mr-2" />
            {t('wiki.updateImpactLoading')}
          </div>
        ) : (
          updateImpact && (
            <>
              <div className="mb-3 text-sm text-[var(--color-text-2)]">{t('wiki.updateImpactTip')}</div>
              <Descriptions column={3} bordered size="small">
                <Descriptions.Item label={t('wiki.contentChanged')}>
                  {updateImpact.content_changed ? t('common.yes') : t('common.no')}
                </Descriptions.Item>
                <Descriptions.Item label={t('wiki.latestVersion')}>{versionLabel(updateImpact.latest_version)}</Descriptions.Item>
                <Descriptions.Item label={t('wiki.previousVersion')}>
                  {versionLabel(updateImpact.previous_version)}
                </Descriptions.Item>
                <Descriptions.Item label={t('wiki.affectedPages')}>{updateImpact.affected_count}</Descriptions.Item>
                <Descriptions.Item label={t('wiki.pendingReviewPages')}>
                  {updateImpact.pending_review_count}
                </Descriptions.Item>
              </Descriptions>
              <div className="mt-4 mb-2 font-medium">{t('wiki.pendingReviewPages')}</div>
              {renderImpactPages(updateImpact.pending_review_pages)}
            </>
          )
        )}
      </Modal>

      <Modal
        title={isEditing ? t('wiki.editMaterial') : t('wiki.addMaterial')}
        open={open}
        onOk={handleSave}
        confirmLoading={saving}
        onCancel={closeMaterialModal}
        maskClosable={false}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          {(type !== 'file' || isEditing) && (
            <Form.Item
              label={t('wiki.name')}
              name="name"
              rules={[{ required: true, message: `${t('common.inputMsg')}${t('wiki.name')}` }]}
            >
              <Input disabled={isEditing && type === 'file'} />
            </Form.Item>
          )}
          <Form.Item label={t('wiki.materialType')} name="material_type" initialValue="file">
            <Select
              disabled={isEditing}
              onChange={(v: MaterialType) => {
                setType(v);
                if (v !== 'file') setFolderImport(false);
              }}
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
            <>
              <Form.Item label="URL" name="url" rules={isEditing ? [] : [{ required: true }]}>
                <Input placeholder="https://..." disabled={isEditing} />
              </Form.Item>
              {/* 网页同步按站点单独配置 */}
              <Form.Item
                label={t('wiki.webSyncEnabled')}
                name="sync_enabled"
                valuePropName="checked"
                initialValue={true}
                tooltip={t('wiki.webSyncTip')}
              >
                <Switch />
              </Form.Item>
              <Form.Item label={t('wiki.webSyncInterval')} name="sync_interval_hours" initialValue={24}>
                <InputNumber min={1} max={720} addonAfter={t('wiki.hours')} />
              </Form.Item>
            </>
          )}
          {type === 'file' && !isEditing && (
            <>
              <Form.Item label={t('wiki.folderImport')} tooltip={t('wiki.folderImportTip')}>
                <Switch checked={folderImport} onChange={(checked) => setFolderImport(checked)} />
              </Form.Item>
              <Form.Item label={t('wiki.materialFile')} required>
                <Upload.Dragger
                  multiple
                  directory={folderImport}
                  fileList={fileList}
                  beforeUpload={() => false}
                  onChange={({ fileList: fl }) => {
                    setFileList(fl);
                    // 上传文件后自动用文件名作为名称,无需用户额外填写
                    const fname = fl.length === 1 ? fl[0]?.name : '';
                    if (fname && !form.getFieldValue('name')) form.setFieldsValue({ name: fname });
                    if (fl.length > 1) form.setFieldsValue({ name: '' });
                  }}
                  accept={FILE_ACCEPT}
                >
                  <p className="ant-upload-drag-icon">
                    <UploadOutlined />
                  </p>
                  <p className="ant-upload-text">{t('wiki.uploadHint')}</p>
                  <p className="ant-upload-hint text-xs text-gray-400">{t('wiki.supportedFileHint')}</p>
                  {fileList.length > 1 && (
                    <p className="ant-upload-hint text-xs text-gray-400">
                      {t('wiki.selectedFiles')}: {fileList.length}
                    </p>
                  )}
                </Upload.Dragger>
              </Form.Item>
            </>
          )}
          {/* 新增时可选择图片增强;编辑文件资料时只允许修改该开关 */}
          {(!isEditing || type === 'file') && (
            <Form.Item
              label={t('wiki.imageEnhance')}
              name="ocr_enhance"
              valuePropName="checked"
              initialValue={false}
              tooltip={hasVisionModel ? t('wiki.imageEnhanceTip') : t('wiki.imageEnhanceDisabledTip')}
            >
              <Switch disabled={!hasVisionModel} />
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* 资料详情(spec 4.2):原文/文件、AI 解读、版本、贡献的知识页面 */}
      <Drawer
        title={`${t('wiki.detail')}: ${detail?.material?.name ?? ''}`}
        open={!!detail}
        width="min(960px, calc(100vw - 48px))"
        onClose={() => setDetail(null)}
      >
        {detail && (
          <>
            <Descriptions
              column={1}
              bordered
              size="small"
              className="mb-4"
              labelStyle={{ width: 144, whiteSpace: 'nowrap' }}
              contentStyle={{ minWidth: 0 }}
            >
              <Descriptions.Item label={t('wiki.materialType')}>
                {materialTypeLabel(detail.material.material_type)}
              </Descriptions.Item>
              {detail.material.material_type === 'web' && (
                <Descriptions.Item label={t('wiki.webSyncEnabled')}>
                  {detail.material.sync_policy?.enabled
                    ? `${t('wiki.webSyncInterval')} ${detail.material.sync_policy?.interval_hours ?? 24} ${t('wiki.hours')}`
                    : '--'}
                </Descriptions.Item>
              )}
              {detail.material.material_type === 'file' && (
                <Descriptions.Item label={t('wiki.imageEnhance')}>
                  {detail.material.ocr_enhance ? t('common.yes') : t('common.no')}
                </Descriptions.Item>
              )}
              <Descriptions.Item label={t('wiki.original')}>
                {detail.file_url ? (
                  <a href={detail.file_url} target="_blank" rel="noreferrer">
                    {t('wiki.downloadFile')}
                  </a>
                ) : (
                  <span className="break-all">{detail.original || '--'}</span>
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('wiki.aiSummary')}>
                {detail.ai_summary ? (
                  <div className="max-w-full overflow-x-auto text-xs">
                    <MarkdownRenderer content={detail.ai_summary} />
                  </div>
                ) : (
                  '--'
                )}
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
