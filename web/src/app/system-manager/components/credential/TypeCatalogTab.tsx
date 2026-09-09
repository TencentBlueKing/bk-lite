'use client';

import React, { useEffect, useState } from 'react';
import { Button, Form, Input, message, Popconfirm, Space, Tag, Tooltip } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import ContentDrawer from '@/components/content-drawer';
import SearchActionBar from '@/components/search-action-bar';
import { renderFormFeedbackFooter } from '@/components/form-feedback-footer';
import PermissionWrapper from '@/components/permission';
import { useTranslation } from '@/utils/i18n';
import type { CredentialFieldSchema, CredentialTypeItem } from '@/components/credential-picker/types';
import { CredentialFieldsBlock } from '@/components/credential-picker';
import { useCredentialApi } from '@/app/system-manager/api/credential';
import CategoryCheckboxGroup from './CategoryCheckboxGroup';
import TypeFieldsDesigner from './TypeFieldsDesigner';
import type { ColumnItem } from '@/types';
import { HandledRequestError } from '@/utils/request';

const TYPE_DESIGNER_WIDTH = 860;
const BUILTIN_MARK_CLASS =
  'inline-flex h-[18px] shrink-0 items-center rounded px-1.5 text-xs font-medium leading-none text-[var(--color-text-3)] bg-[var(--color-fill-2)]';

const CATEGORY_TAG_COLOR: Record<string, string> = {
  host: 'blue',
  network: 'cyan',
  storage: 'gold',
  database: 'purple',
  middleware: 'geekblue',
  cloud: 'orange',
  other: 'default',
};

const BuiltinMark: React.FC<{ label: string }> = ({ label }) => (
  <span className={BUILTIN_MARK_CLASS}>{label}</span>
);

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
    setSaving(true);
    try {
      const created = await createCredentialType({
        key: values.key,
        name: values.name,
        categories: values.categories || [],
        fields: [],
      });
      message.success(t('common.saveSuccess'));
      setDraft(created);
      fillDesigner(created);
      setFields(created.fields || []);
      previewForm.resetFields();
      setDesignerReadOnly(false);
      setMetaOpen(false);
      setDesignerOpen(true);
      await load();
    } catch (error) {
      if (!(error instanceof HandledRequestError)) {
        message.error(t('common.saveFailed'));
      }
    } finally {
      setSaving(false);
    }
  };

  const handleSaveType = async () => {
    const values = await designerForm.validateFields();
    if (!values.key || !values.name) {
      return;
    }
    setSaving(true);
    try {
      await updateCredentialType(values.key, {
        name: values.name,
        categories: values.categories,
        fields,
      });
      message.success(t('common.saveSuccess'));
      setDesignerOpen(false);
      await load();
    } catch (error) {
      if (!(error instanceof HandledRequestError)) {
        message.error(t('common.saveFailed'));
      }
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnItem[] = [
    {
      title: t('system.credential.typeName'),
      dataIndex: 'name',
      key: 'name',
      render: (_, record: CredentialTypeItem) => (
        <span className="inline-flex items-center gap-1.5">
          <span>{record.name}</span>
          {record.is_builtin ? <BuiltinMark label={t('system.credential.builtin')} /> : null}
        </span>
      ),
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
                <Tag
                  bordered={false}
                  color={CATEGORY_TAG_COLOR[id] || 'default'}
                  className="m-0 rounded px-2 py-0.5 font-medium"
                >
                  <span className="opacity-80">{categoryLabel(id)}</span>
                </Tag>
              </span>
            </Tooltip>
          ))}
        </div>
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
      width: 120,
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
    <div className="flex h-full min-h-0 flex-col">
      <SearchActionBar
        searchProps={{
          placeholder: t('system.credential.typeSearchPlaceholder'),
          enterButton: false,
          onSearch: (value) => {
            setSearch(value);
            void load(1, pagination.pageSize, value);
          },
        }}
        actions={(
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              {t('system.credential.addType')}
            </Button>
          </PermissionWrapper>
        )}
      />
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
        confirmLoading={saving}
        onOk={() => void handleMetaOk()}
        onCancel={() => {
          if (!saving) {
            setMetaOpen(false);
          }
        }}
      >
        <Form form={metaForm} layout="vertical">
          <Form.Item name="name" label={t('system.credential.typeName')} rules={[{ required: true, whitespace: true }]}>
            <Input placeholder={t('common.inputTip')} />
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
            <Input placeholder={t('common.inputTip')} />
          </Form.Item>
          <Form.Item
            name="categories"
            label={t('system.credential.categoryBelong')}
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
              -{draftName || '—'}
            </span>
            {draft?.is_builtin ? <BuiltinMark label={t('system.credential.builtin')} /> : null}
          </div>
        )}
        open={designerOpen}
        width={TYPE_DESIGNER_WIDTH}
        destroyOnClose
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
          <div className="shrink-0 px-6 pt-5 pb-5">
            <Form form={designerForm} layout="vertical" disabled={designerReadOnly} className="flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-x-6">
                <Form.Item
                  name="name"
                  label={t('system.credential.typeName')}
                  rules={[{ required: true, whitespace: true }]}
                  className="!mb-0"
                >
                  <Input placeholder={t('common.inputTip')} disabled={Boolean(draft?.is_builtin)} />
                </Form.Item>
                <Form.Item
                  name="key"
                  label={t('system.credential.typeKeyShort')}
                  className="!mb-0"
                >
                  <Input disabled className="font-mono" />
                </Form.Item>
              </div>
              <Form.Item
                name="categories"
                label={t('system.credential.categoryBelong')}
                rules={[{ required: true }]}
                className="!mb-0"
              >
                <CategoryCheckboxGroup layout="inline" disabled={fieldsLocked} />
              </Form.Item>
            </Form>
          </div>
          <div className="flex min-h-0 w-full flex-1 gap-4 border-t border-[var(--color-border-2)] bg-[var(--color-bg)] px-6 py-4">
            <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
              <TypeFieldsDesigner value={fields} typeName={draftName} onChange={setFields} readOnly={fieldsLocked} />
            </div>
            <div className="flex min-h-0 w-[300px] shrink-0 flex-col overflow-hidden">
              <div className="mb-3 flex h-8 shrink-0 items-center">
                <h3 className="text-sm font-medium leading-5 text-[var(--color-text-1)]">
                  {t('system.credential.preview')}
                </h3>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto rounded-lg bg-[var(--color-fill-1)] px-4 py-4">
                {fields.length === 0 ? (
                  <div className="flex h-full min-h-[88px] items-center justify-center px-2 text-center">
                    <p className="mb-0 text-sm leading-6 text-[var(--color-text-3)]">{t('system.credential.previewEmpty')}</p>
                  </div>
                ) : (
                  <Form
                    form={previewForm}
                    layout="vertical"
                    className="w-full [&_.ant-form-item]:!mb-4 [&_.ant-form-item:last-child]:!mb-0"
                  >
                    <CredentialFieldsBlock fields={fields} form={previewForm} />
                  </Form>
                )}
              </div>
            </div>
          </div>
        </div>
      </ContentDrawer>
    </div>
  );
};

export default TypeCatalogTab;
