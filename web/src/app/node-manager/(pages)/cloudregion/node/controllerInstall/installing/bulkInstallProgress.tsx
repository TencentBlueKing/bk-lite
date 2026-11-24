'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Modal, Popconfirm, Table, Tag, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useControllerApi from '@/app/node-manager/api/useControllerApi';
import {
  BulkInstallAttempt,
  BulkInstallBatch
} from '@/app/node-manager/types/controller';
import {
  bulkAttemptDisplay,
  bulkBatchStatusLabelKey
} from '../installConfig/bulkInstall';

interface BulkInstallProgressProps {
  batchId?: number | string;
  onFinish: () => void;
}

function formatExpiry(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

const BulkInstallProgress: React.FC<BulkInstallProgressProps> = ({
  batchId,
  onFinish
}) => {
  const { t } = useTranslation();
  const { getBulkInstallProgress, revokeBulkInstall } = useControllerApi();
  const progressRef = useRef(getBulkInstallProgress);
  const hasBatchRef = useRef(false);
  const reportedErrorRef = useRef(false);
  const [batch, setBatch] = useState<BulkInstallBatch | null>(null);
  const [loading, setLoading] = useState(true);
  const [revoking, setRevoking] = useState(false);
  progressRef.current = getBulkInstallProgress;

  useEffect(() => {
    if (!batchId) {
      setLoading(false);
      return;
    }
    hasBatchRef.current = false;
    reportedErrorRef.current = false;
    let stopped = false;
    const load = async () => {
      try {
        const payload = await progressRef.current(batchId);
        if (!stopped) {
          hasBatchRef.current = true;
          setBatch(payload);
        }
      } catch (error) {
        if (!stopped && !hasBatchRef.current && !reportedErrorRef.current) {
          reportedErrorRef.current = true;
          message.error(error instanceof Error ? error.message : String(error));
        }
      } finally {
        if (!stopped) {
          setLoading(false);
        }
      }
    };
    load();
    const timer = window.setInterval(load, 3000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [batchId]);

  const rows = batch?.items ?? [];

  const handleRevoke = async () => {
    if (!batchId) {
      return;
    }
    setRevoking(true);
    try {
      const payload = await revokeBulkInstall(batchId);
      setBatch(payload);
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error));
    } finally {
      setRevoking(false);
    }
  };

  const handleFinish = () => {
    const installing = rows.some((item) => item.status === 'installing');
    if (!installing) {
      onFinish();
      return;
    }
    Modal.confirm({
      title: t('node-manager.controller.finishInstall'),
      content: t('node-manager.cloudregion.node.bulkFinishConfirm'),
      okText: t('node-manager.cloudregion.node.confirmFinish'),
      cancelText: t('common.cancel'),
      onOk: onFinish
    });
  };

  return (
    <div className="w-full min-w-0 max-w-full">
      <div className="mb-[12px] flex flex-wrap items-center gap-[8px]">
        <Tag>
          {t(bulkBatchStatusLabelKey(batch?.status || 'active'))}
        </Tag>
        <span className="text-[13px] text-[var(--color-text-2)]">
          {t('node-manager.cloudregion.node.bulkAcceptedCount', '', {
            accepted: batch?.accepted_count ?? 0,
            max: batch?.max_success_count ?? 0
          })}
        </span>
        <span className="text-[13px] text-[var(--color-text-2)]">
          {t('node-manager.cloudregion.node.bulkFailureCount', '', {
            count: batch?.failure_count ?? 0
          })}
        </span>
        {batch?.expires_at && (
          <span className="text-[13px] text-[var(--color-text-3)]">
            {t('node-manager.cloudregion.node.bulkExpiresAt', '', {
              time: formatExpiry(batch.expires_at)
            })}
          </span>
        )}
      </div>
      <div className="mb-[12px]">
        <Popconfirm
          title={t('node-manager.cloudregion.node.bulkRevokeConfirm')}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          disabled={!batch || batch.status !== 'active'}
          onConfirm={handleRevoke}
        >
          <Button
            danger
            loading={revoking}
            disabled={!batch || batch.status !== 'active'}
          >
            {t('node-manager.cloudregion.node.bulkRevoke')}
          </Button>
        </Popconfirm>
      </div>
      <Table
        rowKey="ip"
        loading={loading}
        dataSource={rows}
        pagination={false}
        scroll={{ x: 'max-content' }}
        locale={{
          emptyText: t('node-manager.cloudregion.node.bulkEmptyProgress')
        }}
        columns={[
          {
            title: t('node-manager.cloudregion.node.ip'),
            dataIndex: 'ip',
            render: (ip: string, item: BulkInstallAttempt) => (
              <span className="inline-flex max-w-full items-baseline gap-[8px]">
                <span>{ip}</span>
                {item.attempt_count > 1 ? (
                  <span className="text-[13px] text-[var(--color-text-3)]">
                    {t('node-manager.cloudregion.node.bulkAttemptCount', '', {
                      count: item.attempt_count
                    })}
                  </span>
                ) : null}
              </span>
            )
          },
          {
            title: t('node-manager.cloudregion.node.nodeName'),
            dataIndex: 'node_name'
          },
          {
            title: t('node-manager.cloudregion.node.cpuArchitecture'),
            dataIndex: 'cpu_architecture'
          },
          {
            title: t('node-manager.cloudregion.node.status'),
            dataIndex: 'status',
            render: (_status: string, item: BulkInstallAttempt) => {
              const display = bulkAttemptDisplay(item);
              return <Tag color={display.color}>{t(display.labelKey)}</Tag>;
            }
          },
          {
            title: t('node-manager.cloudregion.node.message'),
            dataIndex: 'message'
          }
        ]}
      />
      <div className="pt-[16px] flex justify-center">
        <Button type="primary" onClick={handleFinish}>
          {t('node-manager.controller.finishInstall')}
        </Button>
      </div>
    </div>
  );
};

export default BulkInstallProgress;
