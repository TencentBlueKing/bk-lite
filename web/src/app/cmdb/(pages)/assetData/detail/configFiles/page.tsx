'use client';

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  Button,
  Empty,
  Flex,
  Form,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined } from '@ant-design/icons';
import { useConfigFileApi } from '@/app/cmdb/api';
import type {
  ConfigFileContentResponse,
  ConfigFileItem,
  ConfigFileVersion,
} from '@/app/cmdb/types/configFile';
import { isConfigFileSupportedModel } from '@/app/cmdb/constants/configFile';
import { useTranslation } from '@/utils/i18n';
import ContentDrawer from './components/contentDrawer';
import CompareDrawer from './components/compareDrawer';
import ManualUploadDrawer from './components/manualUploadDrawer';

const { Text } = Typography;

const formatDateTime = (value: string) => {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
};

const ConfigFilesPage = () => {
  const searchParams = useSearchParams();
  const instanceId = searchParams.get('inst_id') || '';
  const modelId = searchParams.get('model_id') || '';
  const isSupportedModel = isConfigFileSupportedModel(modelId);
  const { t } = useTranslation();
  const configFileApi = useConfigFileApi();
  const {
    getConfigFileList,
    getConfigFileVersions,
    getConfigFileContent,
    deleteConfigFileVersion,
    createManualConfigFile,
  } = configFileApi;

  const [fileList, setFileList] = useState<ConfigFileItem[]>([]);
  const [fileListLoading, setFileListLoading] = useState(false);
  const [expandedVersions, setExpandedVersions] = useState<Record<string, ConfigFileVersion[]>>({});
  const [expandedVersionsLoading, setExpandedVersionsLoading] = useState<Record<string, boolean>>({});

  // Content drawer state
  const [contentDrawerOpen, setContentDrawerOpen] = useState(false);
  const [activeFile, setActiveFile] = useState<ConfigFileItem | null>(null);
  const [activeVersionLabel, setActiveVersionLabel] = useState('');
  const [contentData, setContentData] = useState<ConfigFileContentResponse | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentEncoding, setContentEncoding] = useState('utf-8');

  // Compare drawer state
  const [compareDrawerOpen, setCompareDrawerOpen] = useState(false);
  const [compareTarget, setCompareTarget] = useState<ConfigFileItem | null>(null);
  const [versionList, setVersionList] = useState<ConfigFileVersion[]>([]);
  const [leftCompareVersionId, setLeftCompareVersionId] = useState<number | undefined>();
  const [rightCompareVersionId, setRightCompareVersionId] = useState<number | undefined>();
  const [leftCompareContent, setLeftCompareContent] = useState('');
  const [rightCompareContent, setRightCompareContent] = useState('');
  const [compareLoading, setCompareLoading] = useState(false);

  // Manual upload state
  const [manualCreateOpen, setManualCreateOpen] = useState(false);
  const [manualCreateLoading, setManualCreateLoading] = useState(false);
  const [manualForm] = Form.useForm();

  const fetchFileList = async () => {
    if (!instanceId || !isSupportedModel) {
      setFileList([]);
      return;
    }
    try {
      setFileListLoading(true);
      const data = await getConfigFileList(instanceId);
      setFileList(Array.isArray(data) ? data : []);
    } finally {
      setFileListLoading(false);
    }
  };

  useEffect(() => {
    void fetchFileList();
  }, [getConfigFileList, instanceId, isSupportedModel]);

  const fetchExpandedVersions = async (filePath: string) => {
    try {
      setExpandedVersionsLoading((prev) => ({ ...prev, [filePath]: true }));
      const data = await getConfigFileVersions(instanceId, filePath);
      const items = Array.isArray(data) ? data : data?.items || [];
      setExpandedVersions((prev) => ({ ...prev, [filePath]: items }));
    } finally {
      setExpandedVersionsLoading((prev) => ({ ...prev, [filePath]: false }));
    }
  };

  const fetchContent = async (record: ConfigFileItem, encoding = 'utf-8') => {
    try {
      setContentLoading(true);
      const data = await getConfigFileContent(record.latest_version_id, encoding);
      setActiveFile(record);
      setActiveVersionLabel('');
      setContentData(data || null);
      setContentEncoding(data?.encoding || encoding);
      setContentDrawerOpen(true);
    } finally {
      setContentLoading(false);
    }
  };

  const fetchVersionContent = async (version: ConfigFileVersion, encoding = 'utf-8') => {
    try {
      setContentLoading(true);
      const data = await getConfigFileContent(version.id, encoding);
      setActiveFile({
        latest_version_id: version.id,
        file_path: version.file_path,
        file_name: version.file_name,
        collect_task_id: version.collect_task_id,
        latest_version: version.version,
        latest_status: version.status,
        latest_created_at: version.created_at,
      });
      setActiveVersionLabel(version.version);
      setContentData(data || null);
      setContentEncoding(data?.encoding || encoding);
      setContentDrawerOpen(true);
    } finally {
      setContentLoading(false);
    }
  };

  const handleEncodingChange = async (encoding: string) => {
    if (!activeFile) return;
    setContentEncoding(encoding);
    await fetchContent(activeFile, encoding);
  };

  const handleCopyContent = async () => {
    try {
      await navigator.clipboard.writeText(contentData?.content || '');
      message.success(t('ConfigFile.contentCopied'));
    } catch {
      message.error(t('ConfigFile.copyFailed'));
    }
  };

  useEffect(() => {
    if (!compareDrawerOpen || !leftCompareVersionId) {
      setLeftCompareContent('');
      setRightCompareContent('');
      return;
    }

    let mounted = true;
    const fetchCompareContent = async () => {
      try {
        setCompareLoading(true);
        const leftData = await getConfigFileContent(leftCompareVersionId, 'utf-8');
        const rightData = rightCompareVersionId
          ? await getConfigFileContent(rightCompareVersionId, 'utf-8')
          : null;
        if (!mounted) return;
        setLeftCompareContent(leftData?.content || '');
        setRightCompareContent(rightData?.content || '');
      } finally {
        if (mounted) {
          setCompareLoading(false);
        }
      }
    };

    void fetchCompareContent();
    return () => {
      mounted = false;
    };
  }, [compareDrawerOpen, getConfigFileContent, leftCompareVersionId, rightCompareVersionId]);

  const handleDeleteVersion = async (version: ConfigFileVersion) => {
    await deleteConfigFileVersion(version.id);
    message.success(t('ConfigFile.deleteSuccess'));
    if (activeFile?.latest_version_id === version.id) {
      setContentDrawerOpen(false);
      setActiveFile(null);
      setContentData(null);
    }
    await fetchFileList();
    if (expandedVersions[version.file_path]) {
      void fetchExpandedVersions(version.file_path);
    }
  };

  const handleManualCreate = async () => {
    try {
      const values = await manualForm.validateFields();
      setManualCreateLoading(true);
      await createManualConfigFile({
        instance_id: instanceId,
        model_id: modelId,
        file_path: values.file_path,
        content: values.content,
      });
      message.success(t('ConfigFile.uploadSuccess'));
      setManualCreateOpen(false);
      const uploadedFilePath = values.file_path;
      manualForm.resetFields();
      await fetchFileList();
      if (expandedVersions[uploadedFilePath]) {
        void fetchExpandedVersions(uploadedFilePath);
      }
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error(err?.message || t('ConfigFile.uploadFailed'));
    } finally {
      setManualCreateLoading(false);
    }
  };

  const versionStatusTag = (status: string) => {
    const map: Record<string, { color: string; label: string }> = {
      success: { color: 'green', label: t('ConfigFile.statusSuccess') },
      file_not_found: { color: 'red', label: t('ConfigFile.statusFileNotFound') },
      permission_denied: { color: 'red', label: t('ConfigFile.statusPermissionDenied') },
      file_too_large: { color: 'orange', label: t('ConfigFile.statusFileTooLarge') },
      not_text: { color: 'orange', label: t('ConfigFile.statusNotText') },
      error: { color: 'red', label: t('ConfigFile.statusError') },
    };
    const info = map[status] || { color: 'default', label: status };
    return <Tag color={info.color}>{info.label}</Tag>;
  };

  const expandedRowRender = (record: ConfigFileItem) => {
    const versions = expandedVersions[record.file_path] || [];
    const loading = expandedVersionsLoading[record.file_path] || false;

    const versionColumns: ColumnsType<ConfigFileVersion> = [
      {
        title: t('ConfigFile.versionNumber'),
        dataIndex: 'version',
        key: 'version',
        render: (value: string) => (
          <Text className="font-mono text-[13px]">{value}</Text>
        ),
      },
      {
        title: t('ConfigFile.status'),
        dataIndex: 'status',
        key: 'status',
        width: '16%',
        render: (value: string) => versionStatusTag(value),
      },
      {
        title: t('ConfigFile.fileSize'),
        dataIndex: 'file_size',
        key: 'file_size',
        render: (value: number) => {
          if (!value) return '--';
          if (value < 1024) return `${value} B`;
          if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
          return `${(value / 1024 / 1024).toFixed(1)} MB`;
        },
      },
      {
        title: t('ConfigFile.collectTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: '22%',
        render: (value: string) => formatDateTime(value),
      },
      {
        title: t('ConfigFile.actions'),
        key: 'actions',
        width: '20%',
        render: (
          _: unknown,
          versionRecord: ConfigFileVersion,
          index: number,
        ) => (
          <Space size={2}>
            {versionRecord.status === 'success' && (
              <Button
                type="link"
                size="small"
                className="!pl-0"
                onClick={() => void fetchVersionContent(versionRecord)}
              >
                {t('ConfigFile.viewContent')}
              </Button>
            )}
            {versionRecord.status === 'success' &&
              index < versions.length - 1 &&
              versions[index + 1]?.status === 'success' && (
                <Button
                  type="link"
                  size="small"
                  onClick={() => {
                    setCompareTarget(record);
                    setVersionList(versions);
                    setLeftCompareVersionId(versionRecord.id);
                    setRightCompareVersionId(versions[index + 1].id);
                    setLeftCompareContent('');
                    setRightCompareContent('');
                    setCompareDrawerOpen(true);
                  }}
                >
                  {t('ConfigFile.compareWithPrev')}
                </Button>
            )}
            <Popconfirm
              title={t('ConfigFile.deleteConfirmTitle')}
              description={t('ConfigFile.deleteConfirmDesc')}
              okText={t('ConfigFile.delete')}
              cancelText={t('ConfigFile.cancel')}
              onConfirm={() => void handleDeleteVersion(versionRecord)}
            >
              <Button danger type="link" size="small">
                {t('ConfigFile.delete')}
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ];

    return (
      <div className="mt-1" style={{ marginLeft: 48, marginRight: -48 }}>
        <Table
          rowKey="id"
          columns={versionColumns}
          dataSource={versions}
          loading={loading}
          pagination={false}
          size="middle"
          showHeader={true}
          className="[&_.ant-table-thead_th]:!py-1.5 [&_.ant-table-thead_th]:!text-sm [&_.ant-table-thead_th]:!font-semibold [&_.ant-table-thead_th]:!bg-[var(--color-fill-1)] [&_.ant-table-tbody_td]:!py-1.5"
          locale={{
            emptyText: <Empty description={t('ConfigFile.emptyVersionText')} />,
          }}
        />
      </div>
    );
  };

  const columns: ColumnsType<ConfigFileItem> = [
    {
      title: t('ConfigFile.name'),
      dataIndex: 'file_name',
      key: 'file_name',
      width: 160,
      render: (_, record) => (
        <div className="font-medium text-[14px] text-[var(--color-text-primary)]">
          {record.file_name}
        </div>
      ),
    },
    {
      title: t('ConfigFile.latestVersion'),
      dataIndex: 'latest_version',
      key: 'latest_version',
      width: 160,
      render: (value) => (
        <Text className="font-mono text-[13px] text-[var(--color-text-primary)]">
          {value}
        </Text>
      ),
    },
    {
      title: t('ConfigFile.collectPath'),
      dataIndex: 'file_path',
      key: 'file_path',
      width: 200,
      ellipsis: { showTitle: false },
      render: (value) => (
        <Typography.Text className="text-[13px]" ellipsis={{ tooltip: value }}>
          {value}
        </Typography.Text>
      ),
    },
    {
      title: t('ConfigFile.source'),
      dataIndex: 'collect_task_id',
      key: 'source',
      width: 100,
      render: (value) =>
        value ? (
          <Tag color="cyan">{t('ConfigFile.sourceCollected')}</Tag>
        ) : (
          <Tag color="purple">{t('ConfigFile.sourceManual')}</Tag>
        ),
    },
    {
      title: t('ConfigFile.latestTime'),
      dataIndex: 'latest_created_at',
      key: 'latest_created_at',
      width: 180,
      render: (value) => formatDateTime(value),
    },
    {
      title: t('ConfigFile.actions'),
      key: 'actions',
      width: 180,
      fixed: 'right',
      render: (_, record) => (
        <Button
          type="link"
          size="small"
          className="!pl-0"
          onClick={() => void fetchContent(record)}
        >
          {t('ConfigFile.viewLatestContent')}
        </Button>
      ),
    },
  ];

  if (!instanceId) {
    return <Empty description={t('ConfigFile.noInstance')} />;
  }

  if (!isSupportedModel) {
    return <Empty description={t('ConfigFile.modelNotSupported')} />;
  }

  return (
    <>
      <div className="pt-2 px-2">
        <Flex justify="space-between" align="center" className="mb-4">
          <div>
            <div className="text-[16px] font-semibold text-[var(--color-text-primary)]">
              {t('ConfigFile.title')}
            </div>
            <div className="mt-1 text-xs text-[var(--color-text-tertiary)]">
              {t('ConfigFile.description')}
            </div>
          </div>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setManualCreateOpen(true)}
          >
            {t('ConfigFile.manualUpload')}
          </Button>
        </Flex>
        <Table
          rowKey="latest_version_id"
          className="[&_.ant-table-body]:!min-h-[calc(100vh-300px)] [&_.ant-table-thead_th]:!bg-[var(--color-fill-1)] [&_.ant-table-thead_th]:!py-3 [&_.ant-table-thead_th]:text-sm [&_.ant-table-thead_th]:font-semibold [&_.ant-table-tbody_td]:!py-2.5 [&_.ant-table-tbody_td]:!align-middle [&_.ant-table-tbody_tr:hover_td]:!bg-[var(--color-fill-1)] [&_.ant-table-placeholder_td]:!h-[calc(100vh-330px)] [&_.ant-table-expanded-row>td]:!bg-white [&_.ant-table-expanded-row]:!bg-white"
          loading={fileListLoading}
          dataSource={fileList}
          columns={columns}
          expandable={{
            expandedRowRender,
            columnWidth: 48,
            onExpand: (expanded, record) => {
              if (expanded && !expandedVersions[record.file_path]) {
                void fetchExpandedVersions(record.file_path);
              }
            },
          }}
          pagination={{
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            defaultPageSize: 10,
            showTotal: (total) => `${total}`,
          }}
          locale={{
            emptyText: <Empty description={t('ConfigFile.emptyText')} />,
          }}
          scroll={{ x: 960, y: 'calc(100vh - 300px)' }}
        />
      </div>

      <ContentDrawer
        open={contentDrawerOpen}
        loading={contentLoading}
        activeFile={activeFile}
        activeVersionLabel={activeVersionLabel}
        contentData={contentData}
        contentEncoding={contentEncoding}
        onClose={() => setContentDrawerOpen(false)}
        onEncodingChange={(value) => void handleEncodingChange(value)}
        onCopy={() => void handleCopyContent()}
      />

      <CompareDrawer
        open={compareDrawerOpen}
        loading={compareLoading}
        compareTarget={compareTarget}
        versionList={versionList}
        leftVersionId={leftCompareVersionId}
        rightVersionId={rightCompareVersionId}
        leftContent={leftCompareContent}
        rightContent={rightCompareContent}
        onClose={() => {
          setCompareDrawerOpen(false);
          setCompareTarget(null);
          setVersionList([]);
          setLeftCompareVersionId(undefined);
          setRightCompareVersionId(undefined);
          setLeftCompareContent('');
          setRightCompareContent('');
        }}
        onLeftVersionChange={setLeftCompareVersionId}
        onRightVersionChange={setRightCompareVersionId}
      />

      <ManualUploadDrawer
        open={manualCreateOpen}
        loading={manualCreateLoading}
        form={manualForm}
        onClose={() => {
          setManualCreateOpen(false);
          manualForm.resetFields();
        }}
        onSubmit={() => void handleManualCreate()}
      />
    </>
  );
};

export default ConfigFilesPage;
