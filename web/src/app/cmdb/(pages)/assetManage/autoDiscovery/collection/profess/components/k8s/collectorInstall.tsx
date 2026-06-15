'use client';
import React, { useState } from 'react';
import { Button, Alert, message, Input } from 'antd';
import { SearchOutlined, CopyOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useK8sSetupApi } from '@/app/cmdb/api';

interface Props {
  collectorClusterId: string;
  cloudRegionId: number | string;
  onNext: () => void;
  onPrev?: () => void;
}

/**
 * CMDB k8s 引导式接入第二步：拉取安装 token、展示安装命令、轮询验证。
 * 参考 monitor 的 collectorInstall.tsx，但走 CMDB 自己的 /cmdb/api/k8s_setup/* 接口。
 */
const CollectorInstall: React.FC<Props> = ({
  collectorClusterId,
  cloudRegionId,
  onNext,
  onPrev,
}) => {
  const { t } = useTranslation();
  const { generateInstallCommand, verifyCollectorReporting } = useK8sSetupApi();
  const [tokenLoading, setTokenLoading] = useState(false);
  const [command, setCommand] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationStatus, setVerificationStatus] =
    useState<'idle' | 'waiting' | 'success' | 'failed'>('idle');

  const fetchInstallCommand = async () => {
    try {
      setTokenLoading(true);
      const data = await generateInstallCommand({
        collector_cluster_id: collectorClusterId,
        cloud_region_id: cloudRegionId,
      });
      const cmd = data?.command;
      if (!cmd) {
        message.error(t('Collection.k8sTask.generateCmdFailed'));
        return;
      }
      setCommand(cmd);
      setVerificationStatus('waiting');
    } catch (e) {
      console.error(e);
    } finally {
      setTokenLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!command) return;
    try {
      await navigator.clipboard.writeText(command);
      message.success(t('common.copySuccess') || 'Copied');
    } catch {
      message.warning(t('Collection.k8sTask.copyFailedManual'));
    }
  };

  const handleVerify = async () => {
    try {
      setIsVerifying(true);
      const result = await verifyCollectorReporting({
        collector_cluster_id: collectorClusterId,
      });
      if (result?.reporting) {
        setVerificationStatus('success');
        setTimeout(onNext, 1200);
      } else {
        setVerificationStatus('failed');
        message.warning(
          t('Collection.k8sTask.verifyFailed') ||
          'Collector not reporting yet, retry in a moment.'
        );
      }
    } catch (e) {
      console.error(e);
      setVerificationStatus('failed');
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div>
      <div className="mb-[20px]">
        <h3 className="text-base font-semibold mb-2">
          {t('Collection.k8sTask.installCollector') || 'Install Collector'}
        </h3>
        <p className="text-[12px] text-[var(--color-text-3)] mb-2">
          {t('Collection.k8sTask.installCommandDesc') ||
            'Generate a short-lived install token, then copy and run the command on a host with kubectl access to the target cluster.'}
        </p>
        <div className="flex items-center gap-2 mb-2">
          <Button type="primary" loading={tokenLoading} onClick={fetchInstallCommand}>
            {command
              ? t('common.regenerate') || 'Regenerate'
              : t('Collection.k8sTask.generateCommand') || 'Generate Install Command'}
          </Button>
          {command && (
            <Button icon={<CopyOutlined />} onClick={handleCopy}>
              {t('common.copy') || 'Copy'}
            </Button>
          )}
        </div>
        {command && (
          <Input.TextArea
            value={command}
            readOnly
            autoSize={{ minRows: 4, maxRows: 10 }}
            style={{ fontFamily: 'monospace' }}
          />
        )}
      </div>

      <div className="mb-[10px]">
        <h3 className="text-base font-semibold mb-2">
          {t('Collection.k8sTask.verifyStatus') || 'Verify Reporting'}
        </h3>
        <div className="flex items-center gap-3">
          <Button
            type="primary"
            loading={isVerifying}
            icon={<SearchOutlined />}
            disabled={!command}
            onClick={handleVerify}
          >
            {t('Collection.k8sTask.verify') || 'Verify'}
          </Button>
          <span className="text-[12px] text-[var(--color-text-3)]">
            {t('Collection.k8sTask.verifyWaitingDesc') ||
              'After deploying the YAML, click verify; CMDB will query VictoriaMetrics for the configured collector id.'}
          </span>
        </div>
      </div>

      {verificationStatus === 'success' && (
        <Alert
          className="mt-3"
          type="success"
          showIcon
          message={t('Collection.k8sTask.verifySuccess') || 'Collector is reporting'}
          description={t('Collection.k8sTask.verifySuccessDesc') ||
            'Metrics received. CMDB resource discovery will run on the configured schedule.'}
        />
      )}
      {verificationStatus === 'failed' && (
        <Alert
          className="mt-3"
          type="warning"
          showIcon
          message={t('Collection.k8sTask.verifyFailed') || 'Not reporting yet'}
          description={t('Collection.k8sTask.verifyFailedDesc') ||
            'Verify the YAML was applied and that the cluster can reach the configured NATS endpoint.'}
        />
      )}

      <div className="pt-[20px]">
        {onPrev && <Button onClick={onPrev}>← {t('common.pre') || 'Previous'}</Button>}
      </div>
    </div>
  );
};

export default CollectorInstall;
