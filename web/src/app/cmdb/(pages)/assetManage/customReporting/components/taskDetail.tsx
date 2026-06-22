'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Card, Descriptions, Drawer, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useTranslation } from '@/utils/i18n';
import { useCustomReportingApi } from '@/app/cmdb/api/customReporting';
import { useUserInfoContext } from '@/context/userInfo';
import type {
  CustomReportingBatch,
  CustomReportingCredential,
  CustomReportingFieldRegistrationItem,
  CustomReportingOnboardingDocument,
  CustomReportingTask,
  CustomReportingTaskDetail,
} from '@/app/cmdb/types/customReporting';

interface TaskDetailProps {
  open: boolean;
  taskId?: number;
  onClose: () => void;
  onEdit: (task: CustomReportingTask) => void;
  onOpenBatchReview: (task: CustomReportingTask) => void;
}

const flattenGroupNames = (
  nodes: Array<Record<string, any>> = [],
  nameMap: Record<number, string> = {},
) => {
  nodes.forEach((item) => {
    if (item?.id !== undefined) {
      nameMap[Number(item.id)] = item.name;
    }
    flattenGroupNames(item.subGroups || [], nameMap);
  });
  return nameMap;
};

export default function TaskDetail({
  open,
  taskId,
  onClose,
  onEdit,
  onOpenBatchReview,
}: TaskDetailProps) {
  const { t } = useTranslation();
  const { groupTree } = useUserInfoContext();
  const {
    getTaskDetail,
    getOnboardingDocument,
    getFieldRegistrations,
    issueCredential,
    rotateCredential,
    revokeCredential,
  } = useCustomReportingApi();
  const [loading, setLoading] = useState(false);
  const [task, setTask] = useState<CustomReportingTaskDetail | null>(null);
  const [documentData, setDocumentData] = useState<CustomReportingOnboardingDocument | null>(null);
  const [fieldRegs, setFieldRegs] = useState<CustomReportingFieldRegistrationItem[]>([]);
  const [credential, setCredential] = useState<CustomReportingCredential | null>(null);
  const [token, setToken] = useState('');
  const [credentialLoading, setCredentialLoading] = useState(false);
  const requestIdRef = useRef(0);

  const groupNameMap = useMemo(
    () => flattenGroupNames(groupTree as Array<Record<string, any>>),
    [groupTree],
  );

  // 把接入文档拼成一条可直接复制运行的 curl：
  // - 客户脚本应直连 CMDB 后端（非前端代理），host 用 <CMDB_HOST> 占位，交付时替换为真实后端/网关地址；
  // - 载荷只放最小可跑的 instances（单条、身份键占位）做首次上报，关系/批次元数据见下方「示例载荷」；
  // - JSON 多行美化后用单引号包裹，bash 下仍是一次性可粘贴执行；
  // - 有明文 token 时填入，否则保留 <token> 占位由交付人员替换。
  const curlCommand = useMemo(() => {
    if (!documentData) {
      return '';
    }
    const url = documentData.endpoint?.startsWith('/')
      ? `http://<CMDB_HOST>${documentData.endpoint}`
      : documentData.endpoint;
    const authValue = token
      ? documentData.auth_header.format.replace('<token>', token)
      : documentData.auth_header.format;
    const identityKeys = documentData.identity_keys?.length
      ? documentData.identity_keys
      : ['inst_name'];
    const sampleInstance = identityKeys.reduce<Record<string, string>>((acc, key) => {
      acc[key] = `<${key}>`;
      return acc;
    }, {});
    const payload = JSON.stringify({ instances: [sampleInstance] }, null, 2);
    return [
      `curl -X POST "${url}" \\`,
      `  -H "${documentData.auth_header.name}: ${authValue}" \\`,
      '  -H "Content-Type: application/json" \\',
      `  -d '${payload}'`,
    ].join('\n');
  }, [documentData, token]);

  const loadTask = useCallback(async () => {
    if (!taskId) {
      setTask(null);
      setDocumentData(null);
      setCredential(null);
      setToken('');
      return;
    }

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;

    try {
      setLoading(true);
      setTask(null);
      setDocumentData(null);
      setFieldRegs([]);
      setCredential(null);
      setToken('');
      const [taskData, onboarding, fields] = await Promise.all([
        getTaskDetail(taskId),
        getOnboardingDocument(taskId),
        getFieldRegistrations(taskId).catch(() => []),
      ]);
      if (requestId !== requestIdRef.current) {
        return;
      }
      setTask(taskData);
      setDocumentData(onboarding);
      setFieldRegs(fields || []);
      setCredential(taskData.credential || null);
      setToken(taskData.token || '');
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [getFieldRegistrations, getOnboardingDocument, getTaskDetail, taskId]);

  useEffect(() => {
    if (!open) {
      requestIdRef.current += 1;
      setLoading(false);
      setTask(null);
      setDocumentData(null);
      setCredential(null);
      setToken('');
      return;
    }
    void loadTask();
  }, [loadTask, open]);

  const handleIssueCredential = async () => {
    if (!taskId) {
      return;
    }
    const requestId = requestIdRef.current;
    try {
      setCredentialLoading(true);
      const data = await issueCredential(taskId, {
        name: t('CustomReporting.defaultCredential'),
      });
      if (requestId !== requestIdRef.current) {
        return;
      }
      setCredential(data.credential);
      setToken(data.token || '');
      message.success(t('successfulSetted'));
    } finally {
      if (requestId === requestIdRef.current) {
        setCredentialLoading(false);
      }
    }
  };

  const handleRotateCredential = async () => {
    if (!taskId || !credential?.id) {
      return;
    }
    const requestId = requestIdRef.current;
    try {
      setCredentialLoading(true);
      const data = await rotateCredential(taskId, credential.id);
      if (requestId !== requestIdRef.current) {
        return;
      }
      setCredential(data.credential);
      setToken(data.token || '');
      message.success(t('successfulSetted'));
    } finally {
      if (requestId === requestIdRef.current) {
        setCredentialLoading(false);
      }
    }
  };

  const handleRevokeCredential = async () => {
    if (!taskId || !credential?.id) {
      return;
    }
    const requestId = requestIdRef.current;
    try {
      setCredentialLoading(true);
      await revokeCredential(taskId, credential.id);
      if (requestId !== requestIdRef.current) {
        return;
      }
      setCredential((prev) =>
        prev ? { ...prev, is_enabled: false } : prev,
      );
      setToken('');
      message.success(t('successfulSetted'));
    } finally {
      if (requestId === requestIdRef.current) {
        setCredentialLoading(false);
      }
    }
  };

  const copyToken = async () => {
    if (!token) {
      return;
    }
    await navigator.clipboard.writeText(token);
    message.success(t('successfulCopied'));
  };

  const teamLabels = (task?.team || []).map(
    (item) => groupNameMap[item] || `${item}`,
  );

  const batchStatusColor = (status: string) =>
    status === 'success'
      ? 'success'
      : status === 'failed'
        ? 'error'
        : status === 'running'
          ? 'processing'
          : 'default';

  const batchColumns: ColumnsType<CustomReportingBatch> = [
    {
      title: t('CustomReporting.batchTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      render: (value: string) =>
        value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '--',
    },
    {
      title: t('CustomReporting.batchId'),
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: t('CustomReporting.instancesReceived'),
      key: 'instances_received',
      render: (_, batch) => batch.summary?.instances_received ?? 0,
    },
    {
      title: t('CustomReporting.cudCounts'),
      key: 'cud',
      render: (_, batch) =>
        `${batch.summary?.created ?? 0} / ${batch.summary?.updated ?? 0} / ${batch.summary?.deleted ?? 0}`,
    },
    {
      title: t('CustomReporting.errorCount'),
      key: 'errors',
      render: (_, batch) => batch.summary?.errors ?? 0,
    },
    {
      title: t('CustomReporting.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={batchStatusColor(status)}>
          {t(`CustomReporting.statusLabel.${status}`)}
        </Tag>
      ),
    },
  ];

  return (
    <Drawer
      title={t('CustomReporting.taskDetail')}
      open={open}
      onClose={onClose}
      width={720}
      destroyOnClose
      extra={
        task ? (
          <Space>
            <Button onClick={() => onOpenBatchReview(task)}>
              {t('CustomReporting.batchReview')}
            </Button>
            <Button type="primary" onClick={() => onEdit(task)}>
              {t('common.edit')}
            </Button>
          </Space>
        ) : null
      }
    >
      {loading && !task ? (
        <Alert type="info" showIcon message={t('common.loading')} />
      ) : task ? (
        <Space direction="vertical" size={16} className="flex">
          {loading ? (
            <Alert type="info" showIcon message={t('common.loading')} />
          ) : null}
          <Card size="small" title={t('CustomReporting.basicInfo')}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('name')}>{task.name}</Descriptions.Item>
              <Descriptions.Item label={t('CustomReporting.mode')}>
                {task.config?.mode === 'quick'
                  ? t('CustomReporting.modeQuick')
                  : t('CustomReporting.modeStandard')}
              </Descriptions.Item>
              <Descriptions.Item label={t('CustomReporting.targetModel')}>
                {task.config?.mode === 'quick'
                  ? task.config?.quick_model?.model_name || task.config?.quick_model?.model_id || '--'
                  : task.config?.model_id || '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('CustomReporting.identityKeys')}>
                <Space wrap>
                  {(task.config?.quick_model?.identity_keys || task.config?.identity_keys || []).map((item) => (
                    <Tag key={item}>{item}</Tag>
                  ))}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('CustomReporting.teamScope')}>
                <Space wrap>
                  {teamLabels.map((item) => <Tag key={item}>{item}</Tag>)}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('CustomReporting.cleanupStrategy')}>
                {t(`CustomReporting.cleanupLabel.${task.config?.cleanup_strategy || 'none'}`)}
              </Descriptions.Item>
              <Descriptions.Item label={t('CustomReporting.lastReportedAt')}>
                {task.last_reported_at
                  ? dayjs(task.last_reported_at).format('YYYY-MM-DD HH:mm:ss')
                  : '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('updateTime')}>
                {dayjs(task.updated_at).format('YYYY-MM-DD HH:mm:ss')}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Card
            size="small"
            title={t('CustomReporting.credential')}
            extra={
              <Space>
                {!credential ? (
                  <Button
                    type="primary"
                    size="small"
                    loading={credentialLoading}
                    onClick={() => void handleIssueCredential()}
                  >
                    {t('CustomReporting.issueCredential')}
                  </Button>
                ) : (
                  <>
                    <Button
                      size="small"
                      loading={credentialLoading}
                      onClick={() => void handleRotateCredential()}
                    >
                      {t('CustomReporting.rotateCredential')}
                    </Button>
                    <Button
                      danger
                      size="small"
                      loading={credentialLoading}
                      onClick={() => void handleRevokeCredential()}
                    >
                      {t('CustomReporting.revokeCredential')}
                    </Button>
                  </>
                )}
              </Space>
            }
          >
            {credential ? (
              <Space direction="vertical" className="flex">
                <Descriptions column={1} size="small">
                  <Descriptions.Item label={t('name')}>
                    {credential.name}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('type')}>
                    {credential.credential_type}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('CustomReporting.enabled')}>
                    {credential.is_enabled ? t('yes') : t('no')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('CustomReporting.lastUsedAt')}>
                    {credential.last_used_at ||
                      credential.credential_data?.rotated_at ||
                      credential.credential_data?.issued_at ||
                      '--'}
                  </Descriptions.Item>
                </Descriptions>
                <Alert
                  type="info"
                  showIcon
                  message={t('CustomReporting.tokenHint')}
                />
                {token ? (
                  <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-[12px]">
                    <Space direction="vertical" className="flex">
                      <Typography.Text copyable={{ text: token }}>
                        {token}
                      </Typography.Text>
                      <Space>
                        <Button size="small" onClick={() => void copyToken()}>
                          {t('CustomReporting.copyToken')}
                        </Button>
                      </Space>
                    </Space>
                  </div>
                ) : null}
              </Space>
            ) : (
              <Alert
                type="warning"
                showIcon
                message={t('CustomReporting.noCredential')}
              />
            )}
          </Card>

          <Card size="small" title={t('CustomReporting.batchReview')}>
            <Space direction="vertical" size={12} className="flex">
              <Descriptions column={1} size="small">
                <Descriptions.Item label={t('CustomReporting.reviewStatusSummary')}>
                  <Space wrap>
                    <Tag color="warning">{`${t('CustomReporting.statusLabel.pending')}: ${task.review_status_summary?.pending ?? 0}`}</Tag>
                    <Tag color="success">{`${t('CustomReporting.statusLabel.approved')}: ${task.review_status_summary?.approved ?? 0}`}</Tag>
                    <Tag color="error">{`${t('CustomReporting.statusLabel.rejected')}: ${task.review_status_summary?.rejected ?? 0}`}</Tag>
                    <Tag>{`${t('CustomReporting.totalCount')}: ${task.review_status_summary?.total ?? 0}`}</Tag>
                  </Space>
                </Descriptions.Item>
              </Descriptions>
              <Table<CustomReportingBatch>
                rowKey="id"
                size="small"
                pagination={false}
                columns={batchColumns}
                dataSource={task.recent_batches || []}
                locale={{ emptyText: t('CustomReporting.noBatchData') }}
              />
            </Space>
          </Card>

          <Card size="small" title={t('CustomReporting.onboardingDocument')}>
            {documentData ? (
              <Space direction="vertical" className="flex">
                <div>
                  <div className="mb-[4px] flex items-center justify-between">
                    <Typography.Text strong>
                      {t('CustomReporting.curlCommand')}
                    </Typography.Text>
                    <Typography.Text copyable={{ text: curlCommand }}>
                      {t('CustomReporting.copyCommand')}
                    </Typography.Text>
                  </div>
                  <pre className="overflow-auto rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-[12px] text-[12px]">
                    {curlCommand}
                  </pre>
                  <Alert
                    className="mt-[8px]"
                    type="info"
                    showIcon
                    message={
                      <ul className="m-0 list-disc pl-[18px] text-[12px]">
                        <li>{t('CustomReporting.curlHintHost')}</li>
                        <li>{t('CustomReporting.curlHintToken')}</li>
                        <li>{t('CustomReporting.curlHintPayload')}</li>
                      </ul>
                    }
                  />
                </div>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label={t('CustomReporting.endpoint')}>
                    <Typography.Text copyable={{ text: documentData.endpoint }}>
                      {documentData.endpoint}
                    </Typography.Text>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('CustomReporting.authHeader')}>
                    {`${documentData.auth_header.name}: ${documentData.auth_header.format}`}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('CustomReporting.identityKeys')}>
                    <Space wrap>
                      {documentData.identity_keys.map((item) => (
                        <Tag key={item}>{item}</Tag>
                      ))}
                    </Space>
                  </Descriptions.Item>
                </Descriptions>
                <div>
                  <Typography.Text strong>
                    {t('CustomReporting.exampleInstances')}
                  </Typography.Text>
                  <Typography.Paragraph type="secondary" className="!mb-[4px] text-[12px]">
                    {t('CustomReporting.exampleInstancesHint')}
                  </Typography.Paragraph>
                  <pre className="overflow-auto rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-[12px] text-[12px]">
                    {JSON.stringify(documentData.examples.instances, null, 2)}
                  </pre>
                </div>
                <div>
                  <Typography.Text strong>
                    {t('CustomReporting.exampleRelations')}
                  </Typography.Text>
                  <Typography.Paragraph type="secondary" className="!mb-[4px] text-[12px]">
                    {t('CustomReporting.exampleRelationsHint')}
                  </Typography.Paragraph>
                  <pre className="overflow-auto rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-[12px] text-[12px]">
                    {JSON.stringify(documentData.examples.with_relations, null, 2)}
                  </pre>
                </div>
              </Space>
            ) : (
              <Alert
                type="warning"
                showIcon
                message={t('CustomReporting.documentUnavailable')}
              />
            )}
          </Card>

          {task.config?.mode === 'quick' ? (
            <Card size="small" title={t('CustomReporting.fieldRegistration')}>
              <Table<CustomReportingFieldRegistrationItem>
                rowKey="attr_id"
                size="small"
                pagination={false}
                dataSource={fieldRegs}
                locale={{ emptyText: t('CustomReporting.noFieldData') }}
                columns={[
                  {
                    title: t('CustomReporting.fieldName'),
                    dataIndex: 'attr_name',
                    key: 'attr_name',
                    render: (value: string, row) => value || row.attr_id,
                  },
                  {
                    title: t('CustomReporting.recommendedType'),
                    key: 'recommended_type',
                    render: (_, row) => (
                      <Space>
                        <span>{row.recommended_type}</span>
                        {row.is_undefined ? (
                          <Tag color="warning">
                            {t('CustomReporting.undefinedType')}
                          </Tag>
                        ) : null}
                      </Space>
                    ),
                  },
                  {
                    title: t('CustomReporting.firstSeenAt'),
                    dataIndex: 'first_seen_at',
                    key: 'first_seen_at',
                    render: (value: string) =>
                      value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '--',
                  },
                ]}
              />
            </Card>
          ) : null}
        </Space>
      ) : (
        <Alert type="info" showIcon message={t('CustomReporting.noTaskSelected')} />
      )}
    </Drawer>
  );
}
