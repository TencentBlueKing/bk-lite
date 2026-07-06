'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Descriptions, Drawer, Empty, Modal, Space, Spin, Tag, message } from 'antd';
import dayjs from 'dayjs';
import { useTranslation } from '@/utils/i18n';
import { useCustomReportingApi } from '@/app/cmdb/api/customReporting';
import type {
  CustomReportingBatch,
  CustomReportingBatchActivityResponse,
  CustomReportingCleanupReview,
  CustomReportingTask,
} from '@/app/cmdb/types/customReporting';

interface BatchReviewDrawerProps {
  open: boolean;
  task?: CustomReportingTask | null;
  onClose: () => void;
}

const getReviewColor = (status: string) => {
  if (status === 'approved') {
    return 'success';
  }
  if (status === 'rejected') {
    return 'error';
  }
  return 'warning';
};

export default function BatchReviewDrawer({
  open,
  task,
  onClose,
}: BatchReviewDrawerProps) {
  const { t } = useTranslation();
  const { getTaskBatchActivity, approveCleanupReview, rejectCleanupReview } =
    useCustomReportingApi();
  const [loading, setLoading] = useState(false);
  const [activity, setActivity] = useState<CustomReportingBatchActivityResponse | null>(null);
  const [actionId, setActionId] = useState<number | null>(null);
  const requestIdRef = useRef(0);

  const loadActivity = useCallback(async () => {
    if (!task?.id) {
      setActivity(null);
      return;
    }
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    try {
      setLoading(true);
      setActivity(null);
      const data = await getTaskBatchActivity(task.id);
      if (requestId !== requestIdRef.current) {
        return;
      }
      setActivity(data);
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [getTaskBatchActivity, task?.id]);

  useEffect(() => {
    if (!open) {
      requestIdRef.current += 1;
      setLoading(false);
      setActivity(null);
      return;
    }
    void loadActivity();
  }, [loadActivity, open]);

  const handleReview = (
    review: CustomReportingCleanupReview,
    action: 'approve' | 'reject',
  ) => {
    if (!task?.id) {
      return;
    }
    const isApprove = action === 'approve';
    const deleteCount = (review.review_payload?.delete_ids as unknown[])?.length ?? 0;
    Modal.confirm({
      title: isApprove
        ? t('CustomReporting.approveReviewTitle')
        : t('CustomReporting.rejectReviewTitle'),
      content: isApprove
        ? `${t('CustomReporting.approveReviewConfirm')}（${deleteCount}）`
        : t('CustomReporting.rejectReviewConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: isApprove ? { danger: true } : undefined,
      centered: true,
      onOk: async () => {
        setActionId(review.id);
        try {
          if (isApprove) {
            await approveCleanupReview(task.id, review.id);
          } else {
            await rejectCleanupReview(task.id, review.id);
          }
          message.success(t('successfulSetted'));
          await loadActivity();
        } finally {
          setActionId(null);
        }
      },
    });
  };

  const renderBatch = (batch: CustomReportingBatch) => (
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
                <Tag key={review.id} color={getReviewColor(review.status)}>
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

  const renderReview = (review: CustomReportingCleanupReview) => (
    <div
      key={review.id}
      className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-[12px]"
    >
      <Descriptions column={1} size="small">
        <Descriptions.Item label={t('CustomReporting.review')}>
          <Space wrap>
            <Tag>{`#${review.id}`}</Tag>
            <Tag>{`batch #${review.batch_id}`}</Tag>
            <Tag color={getReviewColor(review.status)}>
              {t(`CustomReporting.statusLabel.${review.status}`)}
            </Tag>
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label={t('CustomReporting.reviewedBy')}>
          {review.reviewed_by || '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('updateTime')}>
          {review.reviewed_at ? dayjs(review.reviewed_at).format('YYYY-MM-DD HH:mm:ss') : '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('CustomReporting.reviewPayload')}>
          <pre className="overflow-auto rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-[12px] text-[12px]">
            {JSON.stringify(review.review_payload || {}, null, 2)}
          </pre>
        </Descriptions.Item>
        {review.status === 'pending' ? (
          <Descriptions.Item label={t('action')}>
            <Space>
              <Button
                type="primary"
                danger
                size="small"
                loading={actionId === review.id}
                onClick={() => handleReview(review, 'approve')}
              >
                {t('CustomReporting.approveReview')}
              </Button>
              <Button
                size="small"
                loading={actionId === review.id}
                onClick={() => handleReview(review, 'reject')}
              >
                {t('CustomReporting.rejectReview')}
              </Button>
            </Space>
          </Descriptions.Item>
        ) : null}
      </Descriptions>
    </div>
  );

  return (
    <Drawer
      title={t('CustomReporting.batchReview')}
      open={open}
      onClose={onClose}
      width={680}
      destroyOnHidden
    >
      <Space direction="vertical" size={16} className="flex">
        {task ? (
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
          </Descriptions>
        ) : null}

        {loading ? <Spin /> : null}

        {activity ? (
          <>
            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('CustomReporting.reviewStatusSummary')}>
                <Space wrap>
                  <Tag color="warning">{`${t('CustomReporting.statusLabel.pending')}: ${activity.review_status_summary.pending}`}</Tag>
                  <Tag color="success">{`${t('CustomReporting.statusLabel.approved')}: ${activity.review_status_summary.approved}`}</Tag>
                  <Tag color="error">{`${t('CustomReporting.statusLabel.rejected')}: ${activity.review_status_summary.rejected}`}</Tag>
                  <Tag>{`${t('CustomReporting.totalCount')}: ${activity.review_status_summary.total}`}</Tag>
                </Space>
              </Descriptions.Item>
            </Descriptions>

            {activity.batches.length ? (
              <Space direction="vertical" size={12} className="flex">
                {activity.batches.map(renderBatch)}
              </Space>
            ) : (
              <Empty description={t('CustomReporting.noBatchData')} />
            )}

            {activity.cleanup_reviews.length ? (
              <Space direction="vertical" size={12} className="flex">
                {activity.cleanup_reviews.map(renderReview)}
              </Space>
            ) : (
              <Alert showIcon type="info" message={t('CustomReporting.noReviewData')} />
            )}
          </>
        ) : (
          !loading && <Empty description={t('CustomReporting.noBatchData')} />
        )}
      </Space>
    </Drawer>
  );
}
