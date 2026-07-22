'use client';

import React, { useRef, useState } from 'react';
import { Alert, Button, message } from 'antd';
import { SearchOutlined, ToolOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/log/api/integration';
import CodeEditor from '@/components/code-editor';
import Icon from '@/components/icon';
import CommonIssuesDrawer from './commonIssuesDrawer';
import { K8sCommandData } from './k8sConfiguration';

interface CollectorInstallProps {
  onNext: (data?: K8sCommandData) => void;
  onPrev: () => void;
  commandData: K8sCommandData | null;
}

const CollectorInstall: React.FC<CollectorInstallProps> = ({
  onNext,
  onPrev,
  commandData,
}) => {
  const { t } = useTranslation();
  const drawerRef = useRef<{ showDrawer: () => void } | null>(null);
  const { checkK8sCollectStatus } = useIntegrationApi();
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationStatus, setVerificationStatus] = useState<
    'waiting' | 'success' | 'failed'
  >('waiting');

  const installCommand = commandData?.command || '';

  const handleVerify = async () => {
    try {
      setIsVerifying(true);
      const result = await checkK8sCollectStatus({
        instance_id: commandData?.instance_id,
      });
      if (result?.success) {
        setVerificationStatus('success');
        setTimeout(() => {
          onNext();
        }, 1500);
        return;
      }

      setVerificationStatus('failed');
      message.warning(t('log.integration.k8s.verifyFailed'));
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
              {t('log.integration.k8s.installCollector')}
            </h3>
          </div>
          <Button
            icon={<ToolOutlined />}
            onClick={() => drawerRef.current?.showDrawer()}
          >
            {t('log.integration.k8s.commonIssues')}
          </Button>
        </div>
        <div className="bg-[var(--color-fill-1)] p-[10px] rounded-md">
          <p className="text-[var(--color-text-3)] text-[12px] mb-[6px]">
            {t('log.integration.k8s.installCommandDesc')}
          </p>
          <CodeEditor
            mode="shell"
            theme="monokai"
            name="install-command"
            width="100%"
            height="120px"
            readOnly
            value={installCommand}
            headerOptions={{ copy: true }}
          />
        </div>
      </div>

      <div className="mb-[10px]">
        <div className="flex items-center mb-3">
          <Icon type="renzhengyuanguanli" className="text-2xl mr-2" />
          <h3 className="text-base font-semibold">
            {t('log.integration.k8s.verifyStatus')}
          </h3>
        </div>
        <div className="flex items-center gap-4">
          <Button
            type="primary"
            loading={isVerifying}
            icon={<SearchOutlined />}
            onClick={handleVerify}
          >
            {t('log.integration.k8s.verify')}
          </Button>
          <span className="text-[12px] text-[var(--color-text-3)]">
            {t('log.integration.k8s.verifyWaitingDesc')}
          </span>
        </div>
      </div>

      {verificationStatus === 'success' && (
        <Alert
          message={
            <b className="text-[var(--color-success)]">
              {t('log.integration.k8s.verifySuccess')}
            </b>
          }
          description={
            <div className="flex items-center text-[var(--color-success)]">
              <span className="font-medium">
                {t('log.integration.k8s.verifySuccessDesc')}
              </span>
            </div>
          }
          type="success"
          showIcon
        />
      )}

      {verificationStatus === 'failed' && (
        <Alert
          message={<b className="text-[#faad14]">{t('log.integration.k8s.verifyFailed')}</b>}
          description={
            <div className="flex items-center text-[#faad14]">
              <span className="font-medium">
                {t('log.integration.k8s.verifyFailedDesc')}
                <Button
                  type="link"
                  className="p-[0]"
                  onClick={() => drawerRef.current?.showDrawer()}
                >
                  {t('log.integration.k8s.commonIssues')}
                </Button>
                {t('log.integration.k8s.troubleshoot')}
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
