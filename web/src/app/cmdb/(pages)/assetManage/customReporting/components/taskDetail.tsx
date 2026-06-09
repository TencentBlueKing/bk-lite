'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Card, Descriptions, Drawer, Empty, Space, Tag, Typography, message } from 'antd';
import dayjs from 'dayjs';
import { useTranslation } from '@/utils/i18n';
import { useCustomReportingApi } from '@/app/cmdb/api/customReporting';
import { useUserInfoContext } from '@/context/userInfo';
import type {
  CustomReportingBatch,
  CustomReportingCredential,
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
    issueCredential,
    rotateCredential,
    revokeCredential,
  } = useCustomReportingApi();
  const [loading, setLoading] = useState(false);
  const [task, setTask] = useState<CustomReportingTaskDetail | null>(null);
  const [documentData, setDocumentData] = useState<CustomReportingOnboardingDocument | null>(null);
  const [credential, setCredential] = useState<CustomReportingCredential | null>(null);
  const [token, setToken] = useState('');
  const [credentialLoading, setCredentialLoading] = useState(false);
  const requestIdRef = useRef(0);

  const groupNameMap = useMemo(
    () => flattenGroupNames(groupTree as Array<Record<string, any>>),
    [groupTree],
  );

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
      setCredential(null);
      setToken('');
      const [taskData, onboarding] = await Promise.all([
        getTaskDetail(taskId),
        getOnboardingDocument(taskId),
      ]);
      if (requestId !== requestIdRef.current) {
        return;
      }
      setTask(taskData);
      setDocumentData(onboarding);
      setCredential(taskData.credential || null);
      setToken(taskData.token || '');
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [getOnboardingDocument, getTaskDetail, taskId]);

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

  const renderBatchCard = (batch: CustomReportingBatch) => (
    <div
      key={batch.id}
      className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-[12px]"
    >
      <Descriptions column={1} size="small">
        <Descriptions.Item label={t('CustomReporting.batch')}>
          <Space wrap>
            <Tag>{`#${batch.id}`}</Tag>
            <Tag color="processing">{t(`CustomReporting.statusLabel.${batch.status}`)}</Tag>
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label={t('updateTime')}>
          {batch.updated_at ? dayjs(batch.updated_at).format('YYYY-MM-DD HH:mm:ss') : '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('CustomReporting.batchSummary')}>
          <Space wrap>
            <Tag>{`${t('CustomReporting.instancesReceived')}: ${batch.summary?.instances_received ?? 0}`}</Tag>
            <Tag>{`${t('CustomReporting.relationsReceived')}: ${batch.summary?.relations_received ?? 0}`}</Tag>
            <Tag>{`${t('CustomReporting.createdCount')}: ${batch.summary?.created ?? 0}`}</Tag>
            <Tag>{`${t('CustomReporting.updatedCount')}: ${batch.summary?.updated ?? 0}`}</Tag>
            <Tag>{`${t('CustomReporting.pendingRelations')}: ${batch.summary?.pending_relations ?? 0}`}</Tag>
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label={t('CustomReporting.review')}>
          {batch.cleanup_reviews?.length ? (
            <Space wrap>
              {batch.cleanup_reviews.map((review) => (
                <Tag key={review.id} color={review.status === 'approved' ? 'success' : review.status === 'rejected' ? 'error' : 'warning'}>
                  {`${t(`CustomReporting.statusLabel.${review.status}`)}${review.reviewed_by ? ` · ${review.reviewed_by}` : ''}`}
                </Tag>
              ))}
            </Space>
          ) : (
            '--'
          )}
        </Descriptions.Item>
      </Descriptions>
    </div>
  );

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
              {task.recent_batches?.length ? (
                <Space direction="vertical" size={12} className="flex">
                  {task.recent_batches.map(renderBatchCard)}
                </Space>
              ) : (
                <Empty description={t('CustomReporting.noBatchData')} />
              )}
            </Space>
          </Card>

          <Card size="small" title={t('CustomReporting.onboardingDocument')}>
            {documentData ? (
              <Space direction="vertical" className="flex">
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
                <Typography.Text strong>
                  {t('CustomReporting.examplePayload')}
                </Typography.Text>
                <pre className="overflow-auto rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-[12px] text-[12px]">
                  {JSON.stringify(documentData.example_payload, null, 2)}
                </pre>
              </Space>
            ) : (
              <Alert
                type="warning"
                showIcon
                message={t('CustomReporting.documentUnavailable')}
              />
            )}
          </Card>
        </Space>
      ) : (
        <Alert type="info" showIcon message={t('CustomReporting.noTaskSelected')} />
      )}
    </Drawer>
  );
}
