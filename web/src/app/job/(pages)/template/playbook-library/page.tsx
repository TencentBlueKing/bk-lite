'use client';

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Button,
  Tag,
  Modal,
  message,
  Form,
  Input,
  Upload,
  Tabs,
  Table,
  Empty,
  Alert,
} from 'antd';
import {
  CloudUploadOutlined,
  InboxOutlined,
  FolderOutlined,
  FileOutlined,
  DownloadOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import { Playbook, FileTreeNode } from '@/app/job/types';
import { ColumnItem } from '@/types';
import GroupTreeSelect from '@/components/group-tree-select';
import SearchCombination from '@/components/search-combination';
import { SearchFilters, FieldConfig } from '@/components/search-combination/types';
import { useRouter } from 'next/navigation';
import MarkdownRenderer from '@/components/markdown';

const { Dragger } = Upload;

const PlaybookLibraryPage = () => {
  const { t } = useTranslation();
  const { isLoading: isApiReady } = useApiClient();
  const router = useRouter();
  const {
    getPlaybookList,
    getPlaybookDetail,
    createPlaybook,
    updatePlaybook,
    deletePlaybook,
    upgradePlaybook,
    downloadPlaybook,
  } = useJobApi();

  const [form] = Form.useForm();
  const [uploadForm] = Form.useForm();
  const [upgradeForm] = Form.useForm();
  const [data, setData] = useState<Playbook[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchFilters, setSearchFilters] = useState<SearchFilters>({});
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  // Upload modal
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadConfirmLoading, setUploadConfirmLoading] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  // Edit modal
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingPlaybook, setEditingPlaybook] = useState<Playbook | null>(null);
  const [editConfirmLoading, setEditConfirmLoading] = useState(false);

  // View modal
  const [viewModalOpen, setViewModalOpen] = useState(false);
  const [viewingPlaybook, setViewingPlaybook] = useState<Playbook | null>(null);
  const [viewLoading, setViewLoading] = useState(false);

  // Upgrade modal
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [upgradeConfirmLoading, setUpgradeConfirmLoading] = useState(false);
  const [upgradeFile, setUpgradeFile] = useState<File | null>(null);
  const [upgradeTargetId, setUpgradeTargetId] = useState<number | null>(null);
  const [upgradeTargetPlaybook, setUpgradeTargetPlaybook] = useState<Playbook | null>(null);

  const fetchData = useCallback(
    async (fetchParams: { filters?: SearchFilters; current?: number; pageSize?: number } = {}) => {
      setLoading(true);
      try {
        const filters = fetchParams.filters ?? searchFilters;
        const queryParams: Record<string, unknown> = {
          page: fetchParams.current ?? pagination.current,
          page_size: fetchParams.pageSize ?? pagination.pageSize,
        };
        if (filters && Object.keys(filters).length > 0) {
          Object.entries(filters).forEach(([field, conditions]) => {
            conditions.forEach((condition) => {
              if (condition.lookup_expr === 'in' && Array.isArray(condition.value)) {
                queryParams[field] = (condition.value as string[]).join(',');
              } else {
                queryParams[field] = condition.value;
              }
            });
          });
        }
        const res = await getPlaybookList(queryParams as Record<string, unknown>);
        setData(res.items || []);
        setPagination((prev) => ({
          ...prev,
          total: res.count || 0,
        }));
      } finally {
        setLoading(false);
      }
    },
    [searchFilters, pagination.current, pagination.pageSize]
  );

  useEffect(() => {
    if (!isApiReady) {
      fetchData();
    }
  }, [isApiReady]);

  useEffect(() => {
    if (!isApiReady) {
      fetchData();
    }
  }, [pagination.current, pagination.pageSize]);

  const handleSearchChange = useCallback((filters: SearchFilters) => {
    setSearchFilters(filters);
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ filters, current: 1 });
  }, [fetchData]);

  const fieldConfigs: FieldConfig[] = useMemo(() => [
    {
      name: 'name',
      label: t('job.playbookName'),
      lookup_expr: 'icontains',
    },
    {
      name: 'version',
      label: t('job.version'),
      lookup_expr: 'icontains',
    },
    {
      name: 'team',
      label: t('job.organization'),
      lookup_expr: 'icontains',
    },
    {
      name: 'description',
      label: t('job.playbookDescription'),
      lookup_expr: 'icontains',
    },
  ], [t]);

  const handleTableChange = (pag: Record<string, number>) => {
    setPagination((prev) => ({ ...prev, ...pag }));
  };

  const formatTime = (timeStr: string) => {
    if (!timeStr) return '-';
    const d = new Date(timeStr);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const getNextVersion = (version: string) => {
    const match = version.match(/^v?(\d+)\.(\d+)\.(\d+)$/);
    if (!match) return 'v1.0.1';
    const [, major, minor, patch] = match;
    return `v${major}.${minor}.${Number(patch) + 1}`;
  };

  // Upload modal handlers
  const openUploadModal = () => {
    uploadForm.resetFields();
    setUploadFile(null);
    setUploadModalOpen(true);
  };

  const handleUploadSubmit = async () => {
    try {
      const values = await uploadForm.validateFields();
      if (!uploadFile) {
        message.warning(t('job.pleaseUploadFile'));
        return;
      }
      setUploadConfirmLoading(true);

      const formData = new FormData();
      formData.append('file', uploadFile);
      if (values.version) {
        formData.append('version', values.version);
      }
      if (values.team && values.team.length > 0) {
        values.team.forEach((id: number) => {
          formData.append('team', String(id));
        });
      }

      await createPlaybook(formData);
      message.success(t('job.uploadPlaybookSuccess'));
      setUploadModalOpen(false);
      fetchData();
    } catch {
      // validation or API error
    } finally {
      setUploadConfirmLoading(false);
    }
  };

  // Edit modal handlers
  const openEditModal = (record: Playbook) => {
    setEditingPlaybook(record);
    form.resetFields();
    form.setFieldsValue({
      name: record.name,
      description: record.description,
      team: record.team || [],
    });
    setEditModalOpen(true);
  };

  const handleEditSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (!editingPlaybook) return;
      setEditConfirmLoading(true);
      await updatePlaybook(editingPlaybook.id, {
        name: values.name,
        description: values.description || '',
        team: values.team || [],
      });
      message.success(t('job.editPlaybook'));
      setEditModalOpen(false);
      fetchData();
    } catch {
      // validation or API error
    } finally {
      setEditConfirmLoading(false);
    }
  };

  // View modal — fetch detail then open
  const openViewModal = async (record: Playbook) => {
    setViewLoading(true);
    setViewModalOpen(true);
    try {
      const detail = await getPlaybookDetail(record.id);
      setViewingPlaybook(detail);
    } catch {
      message.error('Failed to load playbook detail');
      setViewModalOpen(false);
    } finally {
      setViewLoading(false);
    }
  };

  // Download
  const handleDownload = async (record: Playbook) => {
    try {
      const blob = await downloadPlaybook(record.id);
      const url = window.URL.createObjectURL(new Blob([blob]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', record.file_name || `${record.name}.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      message.error(t('job.downloadFailed'));
    }
  };

  // Upgrade modal
  const openUpgradeModal = (id: number) => {
    setUpgradeTargetId(id);
    // Find the playbook from viewingPlaybook or data list
    const targetPlaybook = viewingPlaybook?.id === id
      ? viewingPlaybook
      : data.find(p => p.id === id) || null;
    setUpgradeTargetPlaybook(targetPlaybook);
    upgradeForm.resetFields();
    setUpgradeFile(null);
    setUpgradeModalOpen(true);
  };

  const handleUpgradeSubmit = async () => {
    try {
      if (!upgradeFile) {
        message.warning(t('job.pleaseUploadFile'));
        return;
      }
      if (!upgradeTargetId) return;
      setUpgradeConfirmLoading(true);

      const formData = new FormData();
      formData.append('file', upgradeFile);
      const values = await upgradeForm.validateFields();
      if (values.version) {
        formData.append('version', values.version);
      }

      const updated = await upgradePlaybook(upgradeTargetId, formData);
      message.success(t('job.upgradeSuccess'));
      setUpgradeModalOpen(false);
      // Update the viewing playbook if it's the same one
      if (viewingPlaybook && viewingPlaybook.id === upgradeTargetId) {
        setViewingPlaybook(updated);
      }
      fetchData();
    } catch {
      // error
    } finally {
      setUpgradeConfirmLoading(false);
    }
  };

  // Delete
  const handleDelete = (record: Playbook) => {
    Modal.confirm({
      title: t('job.deletePlaybook'),
      content: t('job.deletePlaybookConfirm'),
      okText: t('job.confirm'),
      cancelText: t('job.cancel'),
      centered: true,
      onOk: async () => {
        await deletePlaybook(record.id);
        message.success(t('job.deletePlaybook'));
        fetchData();
      },
    });
  };

  // File tree renderer
  const renderFileTree = (nodes: FileTreeNode[], depth = 0) => {
    return nodes.map((node, idx) => (
      <div key={`${depth}-${idx}-${node.name}`}>
        <div
          className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-[var(--color-bg-1)]"
          style={{ paddingLeft: `${depth * 20 + 8}px` }}
        >
          <div className="flex items-center gap-2">
            {node.type === 'directory' ? (
              <FolderOutlined style={{ color: '#faad14' }} />
            ) : (
              <FileOutlined style={{ color: 'var(--color-text-3)' }} />
            )}
            <span className="text-sm" style={{ color: 'var(--color-text-1)' }}>
              {node.name}
            </span>
          </div>
          {node.type === 'file' && (
            <a className="text-[var(--color-primary)] text-sm cursor-pointer">
              {t('job.preview')}
            </a>
          )}
        </div>
        {node.type === 'directory' && node.children && renderFileTree(node.children, depth + 1)}
      </div>
    ));
  };

  // View modal tabs
  const viewTabs = useMemo(() => {
    if (!viewingPlaybook) return [];
    return [
      {
        key: 'basicInfo',
        label: t('job.basicInfoTab'),
        children: (
          <div className="space-y-4 py-2">
            {[
              { label: t('job.playbookName'), value: viewingPlaybook.name },
              { label: t('job.playbookDescription'), value: viewingPlaybook.description || '-' },
              { label: t('job.currentVersion'), value: viewingPlaybook.version || '-' },
              { label: t('job.recentUpdateTime'), value: formatTime(viewingPlaybook.updated_at) },
              { label: t('job.uploader'), value: viewingPlaybook.created_by || '-' },
            ].map((item, idx) => (
              <div key={idx} className="flex">
                <span
                  className="w-32 shrink-0 text-sm"
                  style={{ color: 'var(--color-text-3)' }}
                >
                  {item.label}
                </span>
                <span className="text-sm" style={{ color: 'var(--color-text-1)' }}>
                  {item.value}
                </span>
              </div>
            ))}
          </div>
        ),
      },
      {
        key: 'params',
        label: t('job.paramsDescriptionTab'),
        children:
          viewingPlaybook.params && viewingPlaybook.params.length > 0 ? (
            <Table
              dataSource={viewingPlaybook.params}
              rowKey="name"
              pagination={false}
              size="small"
              columns={[
                {
                  title: t('job.parameterName'),
                  dataIndex: 'name',
                  key: 'name',
                  render: (text: string) => (
                    <span className="font-mono text-[var(--color-primary)]">{text}</span>
                  ),
                },
                {
                  title: t('job.defaultVal'),
                  dataIndex: 'default',
                  key: 'default',
                  render: (text: string) => text || '-',
                },
                {
                  title: t('job.paramDesc'),
                  dataIndex: 'description',
                  key: 'description',
                  render: (text: string) => text || '-',
                },
              ]}
            />
          ) : (
            <Empty description={t('job.noParams')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ),
      },
      {
        key: 'fileList',
        label: t('job.fileListTab'),
        children:
          viewingPlaybook.file_list && viewingPlaybook.file_list.length > 0 ? (
            <div
              className="rounded-md border p-2"
              style={{ borderColor: 'var(--color-border-1)' }}
            >
              {renderFileTree(viewingPlaybook.file_list)}
            </div>
          ) : (
            <Empty description={t('job.noFiles')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ),
      },
      {
        key: 'readme',
        label: t('job.readmeTab'),
        children: viewingPlaybook.readme ? (
          <MarkdownRenderer content={viewingPlaybook.readme} />
        ) : (
          <Empty description={t('job.noReadme')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ),
      },
    ];
  }, [viewingPlaybook, t]);

  const columns: ColumnItem[] = [
    {
      title: t('job.playbookName'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: t('job.version'),
      dataIndex: 'version',
      key: 'version',
      width: 100,
      render: (_: unknown, record: Playbook) => (
        <Tag color="blue">{record.version || 'v1.0.0'}</Tag>
      ),
    },
    {
      title: t('job.organization'),
      dataIndex: 'team_name',
      key: 'team_name',
      width: 120,
      render: (_: unknown, record: Playbook) => (
        <div className="flex flex-wrap gap-1">
          {(record.team_name && record.team_name.length > 0)
            ? record.team_name.map((name: string, idx: number) => (
              <Tag key={idx}>{name}</Tag>
            ))
            : '-'}
        </div>
      ),
    },
    {
      title: t('job.creator'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 120,
    },
    {
      title: t('job.updateTime'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (_: unknown, record: Playbook) => <span>{formatTime(record.updated_at)}</span>,
    },
    {
      title: t('job.playbookDescription'),
      dataIndex: 'description',
      key: 'description',
      width: 200,
      ellipsis: true,
    },
    {
      title: t('job.operation'),
      dataIndex: 'action',
      key: 'action',
      width: 200,
      render: (_: unknown, record: Playbook) => (
        <div className="flex items-center gap-3">
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => openViewModal(record)}
          >
            {t('job.viewScript')}
          </a>
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => openEditModal(record)}
          >
            {t('job.editRule')}
          </a>
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => router.push(`/job/execution/quick-exec?playbook_id=${record.id}`)}
          >
            {t('job.executeScript')}
          </a>
          <a
            className="text-red-500 cursor-pointer"
            onClick={() => handleDelete(record)}
          >
            {t('job.deletePlaybook')}
          </a>
        </div>
      ),
    },
  ];

  return (
    <div className="w-full h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div
        className="rounded-lg px-6 py-4 mb-4 flex-shrink-0"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <h2
          className="text-base font-medium m-0 mb-1"
          style={{ color: 'var(--color-text-1)' }}
        >
          {t('job.playbookLibrary')}
        </h2>
        <p className="text-sm m-0" style={{ color: 'var(--color-text-3)' }}>
          {t('job.playbookLibraryDesc')}
        </p>
      </div>

      {/* Table Section */}
      <div
        className="rounded-lg px-6 py-6 flex-1 min-h-0 flex flex-col"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        {/* Toolbar */}
        <div className="flex justify-between mb-4 flex-shrink-0">
          <SearchCombination
            fieldConfigs={fieldConfigs}
            onChange={handleSearchChange}
            fieldWidth={120}
            selectWidth={300}
          />
          <div className="flex gap-2">
            <Button
              type="primary"
              icon={<CloudUploadOutlined />}
              onClick={openUploadModal}
            >
              {t('job.uploadPlaybook')}
            </Button>
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 min-h-0">
          <CustomTable
            columns={columns}
            dataSource={data}
            loading={loading}
            rowKey="id"
            pagination={pagination}
            onChange={handleTableChange}
          />
        </div>
      </div>

      {/* Upload Modal */}
      <OperateModal
        title={t('job.uploadPlaybook')}
        open={uploadModalOpen}
        confirmLoading={uploadConfirmLoading}
        onCancel={() => setUploadModalOpen(false)}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => setUploadModalOpen(false)}>{t('job.cancel')}</Button>
            <Button type="primary" loading={uploadConfirmLoading} onClick={handleUploadSubmit}>
              {t('job.confirmUpload')}
            </Button>
          </div>
        }
        width={600}
      >
        <Form form={uploadForm} layout="vertical" colon={false}>
          <Form.Item label={t('job.uploadFile')}>
            <Dragger
              accept=".zip,.tar.gz,.tgz"
              maxCount={1}
              fileList={uploadFile ? [{ uid: '-1', name: uploadFile.name, status: 'done' as const }] : []}
              beforeUpload={(file) => {
                const isValid = file.name.endsWith('.zip') || file.name.endsWith('.tar.gz') || file.name.endsWith('.tgz');
                if (!isValid) {
                  message.error(t('job.onlyZipAllowed'));
                  return Upload.LIST_IGNORE;
                }
                setUploadFile(file);
                return false;
              }}
              onRemove={() => {
                setUploadFile(null);
              }}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">{t('job.dragUploadText')}</p>
              <p className="ant-upload-hint">{t('job.dragUploadHint')}</p>
            </Dragger>
          </Form.Item>

          <Form.Item
            name="version"
            label={t('job.versionOptional')}
          >
            <Input placeholder={t('job.versionPlaceholder')} />
          </Form.Item>

          <Form.Item
            name="team"
            label={t('job.organization')}
            rules={[{ required: true, message: t('job.organizationPlaceholder') }]}
          >
            <GroupTreeSelect multiple placeholder={t('job.organizationPlaceholder')} />
          </Form.Item>
        </Form>
      </OperateModal>

      {/* Edit Modal */}
      <OperateModal
        title={t('job.editPlaybook')}
        open={editModalOpen}
        confirmLoading={editConfirmLoading}
        onCancel={() => setEditModalOpen(false)}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => setEditModalOpen(false)}>{t('job.cancel')}</Button>
            <Button type="primary" loading={editConfirmLoading} onClick={handleEditSubmit}>
              {t('job.save')}
            </Button>
          </div>
        }
        width={600}
      >
        <Form form={form} layout="vertical" colon={false}>
          <Form.Item
            name="name"
            label={t('job.playbookName')}
            rules={[{ required: true, message: t('job.playbookNamePlaceholder') }]}
          >
            <Input placeholder={t('job.playbookNamePlaceholder')} />
          </Form.Item>

          <Form.Item
            name="team"
            label={t('job.organization')}
          >
            <GroupTreeSelect multiple placeholder={t('job.organizationPlaceholder')} />
          </Form.Item>

          <Form.Item
            name="description"
            label={t('job.playbookDescription')}
          >
            <Input.TextArea
              rows={3}
              placeholder={t('job.playbookDescriptionPlaceholder')}
            />
          </Form.Item>
        </Form>
      </OperateModal>

      {/* View Modal */}
      <Modal
        open={viewModalOpen}
        onCancel={() => {
          setViewModalOpen(false);
          setViewingPlaybook(null);
        }}
        width={800}
        styles={{
          body: {
            height: 500,
            display: 'flex',
            flexDirection: 'column',
          },
        }}
        footer={
          <Button onClick={() => {
            setViewModalOpen(false);
            setViewingPlaybook(null);
          }}>
            {t('job.close')}
          </Button>
        }
        title={null}
        closable={false}
        loading={viewLoading}
      >
        {viewingPlaybook && (
          <div className="flex flex-col h-full">
            {/* Header */}
            <div className="flex items-center justify-between mb-4 flex-shrink-0">
              <div className="flex items-center gap-3">
                <h3
                  className="text-lg font-medium m-0"
                  style={{ color: 'var(--color-text-1)' }}
                >
                  {viewingPlaybook.name}
                </h3>
                <Tag color="blue">{viewingPlaybook.version || 'v1.0.0'}</Tag>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  icon={<DownloadOutlined />}
                  onClick={() => handleDownload(viewingPlaybook)}
                >
                  {t('job.download')}
                </Button>
                <Button
                  type="primary"
                  style={{ backgroundColor: '#52c41a', borderColor: '#52c41a' }}
                  onClick={() => openUpgradeModal(viewingPlaybook.id)}
                >
                  {t('job.upgradeVersion')}
                </Button>
                <CloseOutlined
                  className="cursor-pointer ml-2"
                  style={{ color: 'var(--color-text-3)', fontSize: 16 }}
                  onClick={() => {
                    setViewModalOpen(false);
                    setViewingPlaybook(null);
                  }}
                />
              </div>
            </div>

            {/* Tabs */}
            <Tabs
              items={viewTabs}
              className="flex-1 min-h-0 [&_.ant-tabs-content]:h-full [&_.ant-tabs-tabpane]:h-full [&_.ant-tabs-tabpane]:overflow-auto"
            />
          </div>
        )}
      </Modal>

      {/* Upgrade Version Modal */}
      <OperateModal
        title={t('job.upgradePlaybookTitle')}
        open={upgradeModalOpen}
        confirmLoading={upgradeConfirmLoading}
        onCancel={() => setUpgradeModalOpen(false)}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => setUpgradeModalOpen(false)}>{t('job.cancel')}</Button>
            <Button type="primary" loading={upgradeConfirmLoading} onClick={handleUpgradeSubmit}>
              {t('job.confirm')}
            </Button>
          </div>
        }
        width={600}
      >
        <Form form={upgradeForm} layout="vertical" colon={false}>
          <Alert
            message={t('job.upgradeWarning')}
            type="warning"
            showIcon
            className="mb-4"
          />

          <Form.Item label={t('job.currentVersionLabel')}>
            <Input
              value={upgradeTargetPlaybook?.version || 'v1.0.0'}
              disabled
              className="bg-gray-50"
            />
          </Form.Item>

          <Form.Item label={t('job.uploadNewVersion')}>
            <Dragger
              accept=".zip,.tar.gz,.tgz"
              maxCount={1}
              fileList={upgradeFile ? [{ uid: '-1', name: upgradeFile.name, status: 'done' as const }] : []}
              beforeUpload={(file) => {
                const isValid = file.name.endsWith('.zip') || file.name.endsWith('.tar.gz') || file.name.endsWith('.tgz');
                if (!isValid) {
                  message.error(t('job.onlyZipAllowed'));
                  return Upload.LIST_IGNORE;
                }
                setUpgradeFile(file);
                return false;
              }}
              onRemove={() => {
                setUpgradeFile(null);
              }}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">{t('job.selectNewZip')}</p>
            </Dragger>
          </Form.Item>

          <Form.Item
            name="version"
            label={t('job.newVersionNumber')}
            extra={t('job.newVersionHint')}
          >
            <Input placeholder={t('job.newVersionPlaceholder').replace('{version}', getNextVersion(upgradeTargetPlaybook?.version || 'v1.0.0'))} />
          </Form.Item>
        </Form>
      </OperateModal>
    </div>
  );
};

export default PlaybookLibraryPage;
