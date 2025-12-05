'use client';
import React, { useState, useRef } from 'react';
import { Button, Alert, message } from 'antd';
import {
  ToolOutlined,
  CheckCircleOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import CodeEditor from '@/app/monitor/components/codeEditor';
import CommonIssuesDrawer from './commonIssuesDrawer';
import useIntegrationApi from '@/app/monitor/api/integration';
import { CollectorInstallProps } from '@/app/monitor/types/integration';

const CollectorInstall: React.FC<CollectorInstallProps> = ({
  onNext,
  onPrev,
  commandData,
}) => {
  const { t } = useTranslation();
  const drawerRef = useRef<any>(null);
  const { checkCollectStatus } = useIntegrationApi();
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationStatus, setVerificationStatus] = useState<
    'waiting' | 'success' | 'failed'
  >('waiting');

  const installCommand = commandData?.command || '';

  const handleVerify = async () => {
    try {
      setIsVerifying(true);
      const result = await checkCollectStatus({
        instance_id: commandData?.instance_id,
        monitor_object_id: commandData?.monitor_object_id,
      });
      if (result?.success) {
        setVerificationStatus('success');
        return setTimeout(() => {
          onNext();
        }, 2000);
      }
      setVerificationStatus('failed');
      message.warning(t('monitor.integrations.k8s.verifyFailed'));
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div>
      <div className="mb-[20px]">
        <div className="flex items-center justify-between mb-[10px]">
          <div className="flex items-center">
            <Icon type="caijiqi" className="text-lg mr-2" />
            <h3 className="text-base font-semibold">
              {t('monitor.integrations.k8s.installCollector')}
            </h3>
          </div>
          <Button
            icon={<ToolOutlined />}
            onClick={() => drawerRef.current?.showDrawer()}
          >
            {t('monitor.integrations.k8s.commonIssues')}
          </Button>
        </div>
        <div className="bg-[var(--color-fill-1)] p-[10px] rounded-md">
          <p className="text-[var(--color-text-3)] text-[12px] mb-[6px]">
            {t('monitor.integrations.k8s.installCommandDesc')}
          </p>
          <CodeEditor
            mode="shell"
            theme="monokai"
            name="install-command"
            width="100%"
            height="120px"
            readOnly
            value={installCommand}
            showCopy
          />
        </div>
      </div>
      {/* 验证接入状态 */}
      <div className="mb-[10px]">
        <div className="flex items-center mb-3">
          <CheckCircleOutlined className="text-lg mr-2 text-[var(--color-success)]" />
          <h3 className="text-base font-semibold">
            {t('monitor.integrations.k8s.verifyStatus')}
          </h3>
        </div>
        <div className="flex items-center gap-4">
          <Button
            type="primary"
            loading={isVerifying}
            icon={<SearchOutlined />}
            onClick={handleVerify}
          >
            {t('monitor.integrations.k8s.verify')}
          </Button>
          <span className="text-[12px] text-[var(--color-text-3)]">
            {t('monitor.integrations.k8s.verifyWaitingDesc')}
          </span>
        </div>
      </div>
      {/* 验证成功状态 */}
      {verificationStatus === 'success' && (
        <Alert
          message={
            <b className="text-[var(--color-success)]">
              {t('monitor.integrations.k8s.verifySuccess')}
            </b>
          }
          description={
            <div className="flex items-center text-[var(--color-success)]">
              <span className="font-medium">
                {t('monitor.integrations.k8s.verifySuccessDesc')}
              </span>
            </div>
          }
          type="success"
          showIcon
        />
      )}
      {verificationStatus === 'failed' && (
        <Alert
          message={
            <b className="text-[#faad14]">
              {t('monitor.integrations.k8s.verifyFailed')}
            </b>
          }
          description={
            <div className="flex items-center text-[#faad14]">
              <span className="font-medium">
                {t('monitor.integrations.k8s.verifyFailedDesc')}
                <Button
                  type="link"
                  className="p-[0]"
                  onClick={() => drawerRef.current?.showDrawer()}
                >
                  {t('monitor.integrations.k8s.commonIssues')}
                </Button>
                {t('monitor.integrations.k8s.troubleshoot')}
              </span>
            </div>
          }
          type="warning"
          showIcon
        />
      )}
      <div className="pt-[20px]">
        <Button onClick={onPrev}>← {t('common.pre')}</Button>
      </div>
      <CommonIssuesDrawer ref={drawerRef} />
    </div>
  );
};

export default CollectorInstall;
