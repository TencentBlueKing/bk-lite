'use client';

import React, { useEffect, useState } from 'react';
import { Button, Form, Input, message, Popconfirm, Space, Tag, Tooltip } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import ContentDrawer from '@/components/content-drawer';
import { renderFormFeedbackFooter } from '@/components/form-feedback-footer';
import PermissionWrapper from '@/components/permission';
import { useTranslation } from '@/utils/i18n';
import type { CredentialFieldSchema, CredentialTypeItem } from '@/components/credential-picker/types';
import { CredentialFieldsBlock } from '@/components/credential-picker';
import { useCredentialApi } from '@/app/system-manager/api/credential';
import CategoryCheckboxGroup from './CategoryCheckboxGroup';
import TypeFieldsDesigner from './TypeFieldsDesigner';
import type { ColumnItem } from '@/types';

const TYPE_DESIGNER_WIDTH = 920;
const TYPE_PREVIEW_WIDTH = 340;

const TypeCatalogTab: React.FC = () => {
  const { t } = useTranslation();
  const {
    getCredentialTypes,
    createCredentialType,
    updateCredentialType,
    deleteCredentialType,
  } = useCredentialApi();
  const [metaForm] = Form.useForm();
  const [designerForm] = Form.useForm();
  const [previewForm] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<CredentialTypeItem[]>([]);
  const [search, setSearch] = useState('');
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [metaOpen, setMetaOpen] = useState(false);
  const [designerOpen, setDesignerOpen] = useState(false);
  const [designerReadOnly, setDesignerReadOnly] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState<Partial<CredentialTypeItem> | null>(null);
  const [fields, setFields] = useState<CredentialFieldSchema[]>([]);

  const categoryLabel = (id: string) => t(`system.credential.categories.${id}`, id);
  const draftName = Form.useWatch('name', designerForm) || draft?.name || '';
  const draftKey = Form.useWatch('key', designerForm) || draft?.key || '';
  const fieldsLocked = designerReadOnly || Boolean(draft?.is_builtin);

  const fillDesigner = (record: Partial<CredentialTypeItem>) => {
    designerForm.setFieldsValue({
      name: record.name,
      key: record.key,
      categories: record.categories?.length ? record.categories : ['other'],
    });
  };

  const load = async (page = pagination.current, pageSize = pagination.pageSize, keyword = search) => {
    setLoading(true);
    try {
      const data = await getCredentialTypes({ search: keyword, page, page_size: pageSize });
      setItems(data.items);
      setPagination({ current: page, pageSize, total: data.count });
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const openCreate = () => {
    metaForm.resetFields();
    metaForm.setFieldsValue({ categories: ['other'] });
    setDraft(null);
    setMetaOpen(true);
  };

  const openDesigner = (record: CredentialTypeItem, readOnly: boolean) => {
    setDraft(record);
    setFields(record.fields || []);
    previewForm.resetFields();
    fillDesigner(record);
    setDesignerReadOnly(readOnly);
    setDesignerOpen(true);
  };

  const handleMetaOk = async () => {
    const values = await metaForm.validateFields();
    const nextDraft = { key: values.key, name: values.name, categories: values.categories, is_builtin: false };
    setDraft(nextDraft);
    fillDesigner(nextDraft);
    setFields([]);
    previewForm.resetFields();
    setDesignerReadOnly(false);
    setMetaOpen(false);
    setDesignerOpen(true);
  };

  const handleSaveType = async () => {
    const values = await designerForm.validateFields();
    if (!values.key || !values.name) {
      return;
    }
    setSaving(true);
    try {
      const exists = items.some((item) => item.key === values.key);
      if (exists) {
        await updateCredentialType(values.key, {
          name: values.name,
          categories: values.categories,
          fields,
        });
      } else {
        await createCredentialType({
          key: values.key,
          name: values.name,
          categories: values.categories || [],
          fields,
        });
      }
      message.success(t('common.saveSuccess'));
      setDesignerOpen(false);
      await load();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnItem[] = [
    {
      title: t('system.credential.typeName'),
      dataIndex: 'name',
      key: 'name',
      render: (_, record: CredentialTypeItem) => <span>{record.name}</span>,
    },
    {
      title: t('system.credential.typeKey'),
      dataIndex: 'key',
      key: 'key',
      render: (key: string) => (
        <span className="text-[var(--color-text-3)]">{key}</span>
      ),
    },
    {
      title: t('system.credential.category'),
      dataIndex: 'categories',
      key: 'categories',
      render: (categories: string[]) => (
        <div className="flex flex-wrap gap-1">
          {(categories || []).map((id) => (
            <Tooltip key={id} title={id}>
              <span>
                <Tag bordered={false} className="m-0 rounded bg-[var(--color-fill-2)] px-2 py-0.5 font-medium text-[var(--color-text-2)]">
                  {categoryLabel(id)}
                </Tag>
              </span>
            </Tooltip>
          ))}
        </div>
      ),
    },
    {
      title: t('system.credential.source'),
      dataIndex: 'is_builtin',
      key: 'source',
      render: (isBuiltin: boolean) => (
        <Tag color={isBuiltin ? 'blue' : 'orange'}>
          {isBuiltin ? t('system.credential.builtin') : t('system.credential.custom')}
        </Tag>
      ),
    },
    {
      title: t('system.credential.credentialCount'),
      dataIndex: 'credential_count',
      key: 'credential_count',
      render: (count: number) => count ?? 0,
    },
    {
      title: t('common.actions'),
      key: 'actions',
      dataIndex: 'actions',
      render: (_, record: CredentialTypeItem) => (
        <Space>
          {record.is_builtin ? (
            <Button type="link" size="small" onClick={() => openDesigner(record, true)}>
              {t('common.detail')}
            </Button>
          ) : (
            <>
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button type="link" size="small" onClick={() => openDesigner(record, false)}>
                  {t('common.edit')}
                </Button>
              </PermissionWrapper>
              {(record.credential_count || 0) === 0 ? (
                <PermissionWrapper requiredPermissions={['Delete']}>
                  <Popconfirm title={t('common.delConfirm')} onConfirm={() => void deleteCredentialType(record.key).then(() => load())}>
                    <Button type="link" size="small" danger>
                      {t('common.delete')}
                    </Button>
                  </Popconfirm>
                </PermissionWrapper>
              ) : null}
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex justify-end gap-2">
        <Input.Search
          allowClear
          className="w-60"
          placeholder={t('common.search')}
          onSearch={(value) => {
            setSearch(value);
            void load(1, pagination.pageSize, value);
          }}
        />
        <PermissionWrapper requiredPermissions={['Add']}>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('system.credential.addType')}
          </Button>
        </PermissionWrapper>
        <Button type="text" icon={<ReloadOutlined />} onClick={() => void load()} />
      </div>
      <div className="min-h-0 flex-1">
        <CustomTable
          rowKey="key"
          loading={loading}
          columns={columns}
          dataSource={items}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            onChange: (page, pageSize) => void load(page, pageSize),
          }}
        />
      </div>
      <OperateModal
        title={t('system.credential.addType')}
        open={metaOpen}
        okText={t('system.credential.saveAndDesignFields')}
        onOk={() => void handleMetaOk()}
        onCancel={() => setMetaOpen(false)}
      >
        <Form form={metaForm} layout="vertical">
          <Form.Item name="name" label={t('system.credential.typeName')} rules={[{ required: true, whitespace: true }]}>
            <Input placeholder={t('system.credential.typeNamePlaceholder')} />
          </Form.Item>
          <Form.Item
            name="key"
            label={t('system.credential.typeKey')}
            extra={t('system.credential.typeKeyHint')}
            rules={[
              { required: true },
              { pattern: /^[a-z][a-z0-9_]*$/, message: t('system.credential.typeKeyHint') },
            ]}
          >
            <Input placeholder={t('system.credential.typeKeyPlaceholder')} />
          </Form.Item>
          <Form.Item
            name="categories"
            label={t('system.credential.categoryBelong')}
            extra={t('system.credential.categoryHint')}
            rules={[{ required: true }]}
          >
            <CategoryCheckboxGroup />
          </Form.Item>
        </Form>
      </OperateModal>
      <ContentDrawer
        title={(
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold text-[var(--color-text-1)]">
              {designerReadOnly
                ? t('system.credential.viewTypePrefix')
                : t('system.credential.editTypePrefix')}
              {' · '}
              {draftName || '—'}
            </span>
            {draftKey ? (
              <Tag bordered={false} className="!m-0 font-mono text-[var(--color-text-2)]">
                {draftKey}
              </Tag>
            ) : null}
            <Tag color={draft?.is_builtin ? 'blue' : 'orange'} className="!m-0">
              {draft?.is_builtin ? t('system.credential.builtin') : t('system.credential.custom')}
            </Tag>
          </div>
        )}
        open={designerOpen}
        width={TYPE_DESIGNER_WIDTH}
        footer={designerReadOnly ? null : (
          <div className="flex justify-end">
            {renderFormFeedbackFooter({
              confirmLoading: saving,
              confirmText: t('system.credential.saveType'),
              cancelText: t('common.cancel'),
              primaryFirst: false,
              onCancel: () => setDesignerOpen(false),
              onConfirm: () => void handleSaveType(),
            })}
          </div>
        )}
        styles={{
          body: {
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            padding: 0,
            overflow: 'hidden',
          },
        }}
        onClose={() => setDesignerOpen(false)}
      >
        <div className="flex h-full min-h-0 flex-col">
          <div className="shrink-0 border-b border-[var(--color-fill-2)] bg-[var(--color-bg-container)] px-5 py-4">
            <Form form={designerForm} layout="vertical" disabled={designerReadOnly} className="flex flex-col gap-3.5">
              <Form.Item
                name="name"
                label={<span className="text-xs font-medium text-[var(--color-text-3)]">{t('system.credential.typeName')}</span>}
                rules={[{ required: true, whitespace: true }]}
                className="!mb-0"
              >
                <Input placeholder={t('system.credential.typeNamePlaceholder')} disabled={Boolean(draft?.is_builtin)} />
              </Form.Item>
              <Form.Item
                name="key"
                label={<span className="text-xs font-medium text-[var(--color-text-3)]">{t('system.credential.typeKeyShort')}</span>}
                className="!mb-0"
              >
                <Input disabled className="font-mono" />
              </Form.Item>
              <Form.Item
                name="categories"
                label={<span className="text-xs font-medium text-[var(--color-text-3)]">{t('system.credential.categoryBelong')}</span>}
                extra={fieldsLocked ? null : (
                  <span className="mt-1 block text-xs text-[var(--color-text-3)]">{t('system.credential.categoryHint')}</span>
                )}
                rules={[{ required: true }]}
                className="!mb-0"
              >
                <CategoryCheckboxGroup layout="boxed" disabled={fieldsLocked} />
              </Form.Item>
            </Form>
          </div>
          <div className="flex w-full min-h-0 flex-1 max-[900px]:flex-col">
            <div className="min-h-0 min-w-0 flex-1 overflow-y-auto px-5 py-4 pb-6">
              <TypeFieldsDesigner value={fields} typeName={draftName} onChange={setFields} readOnly={fieldsLocked} />
            </div>
            <div
              className="overflow-y-auto border-l border-[var(--color-fill-2)] bg-[var(--color-fill-1)] px-5 py-4 pb-6 max-[900px]:w-full max-[900px]:border-l-0 max-[900px]:border-t"
              style={{ width: TYPE_PREVIEW_WIDTH, flex: `0 0 ${TYPE_PREVIEW_WIDTH}px` }}
            >
              <div className="mb-3">
                <h3 className="text-[13px] font-semibold text-[var(--color-text-1)]">
                  {t('system.credential.preview')}
                </h3>
              </div>
              <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                <Form form={previewForm} layout="vertical" className="w-full">
                  {fields.length === 0 ? (
                    <span className="text-xs text-[var(--color-text-3)]">{t('system.credential.previewEmpty')}</span>
                  ) : (
                    <CredentialFieldsBlock fields={fields} form={previewForm} />
                  )}
                </Form>
              </div>
            </div>
          </div>
        </div>
      </ContentDrawer>
    </div>
  );
};

export default TypeCatalogTab;
